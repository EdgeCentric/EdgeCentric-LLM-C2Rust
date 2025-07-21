import asyncio
import logging
import random
import sys
import time
from asyncio.log import logger
from collections import defaultdict
from collections.abc import AsyncGenerator, Container, Iterable
from typing import TYPE_CHECKING, Any

from tqdm import tqdm

from llm_c2rust.llm.LLM import EdgeCentricAgent
from llm_c2rust.analyzer.matcher import TreesitterMatcher
from llm_c2rust.analyzer.rust_pieces import RustCode
from llm_c2rust.analyzer.utils import RustPieceRef

from llm_c2rust.cargo.cargo_message import Package
from llm_c2rust.core.interact import InteractEngine
from llm_c2rust.core.transpilation_workspace import EdgeCentricWorkspace
from llm_c2rust.core.utils import (
    aenumerate,
    all_rust_code_from_md,
    pieces_of_conflicts,
    validate,
    first_rust_code_from_md,
    new_dependencies,
    ConflictReport,
)
from llm_c2rust.llm.api_inference import AsyncAPIInference
from llm_c2rust.parser.rust_parser import grammar_correct
from llm_c2rust.segmenter.code_segment import CodeSegment
from llm_c2rust.segmenter.segmenter import Segmenter

if TYPE_CHECKING:
    from llm_c2rust.core.transpiler import ProjectTranspiler


logger = logging.getLogger(__name__)

GRAMMAR_RETRY = 2


def interface_equal(original: str, new: str) -> bool:
    original_p = RustCode.from_text(original)
    new_p = RustCode.from_text(new)

    return original_p.interface_equal(new_p)


class EdgeCentricEngine(InteractEngine):

    def __init__(
        self,
        segmenter: Segmenter,
        predicator: AsyncAPIInference,
        token_num: int,
        token_num_method: str,
        temperature: float,
        max_retry: int,
        max_resolve_round: int,
    ):
        super().__init__(
            segmenter, predicator, token_num, token_num_method, temperature
        )

        self.max_retry = max_retry
        self.todo_prority = 3 * (max_retry + 1)
        self.max_resolve_round = max_resolve_round
        self._workspace = EdgeCentricWorkspace()
        self._agent = EdgeCentricAgent(predicator)
        self._in_synthesis = set()
        if predicator.model_name.startswith("qwen"):
            # Qwen like to split the answer into multiple parts
            self._collect_rust_code = all_rust_code_from_md
        else:
            self._collect_rust_code = first_rust_code_from_md

    @property
    def agent(self) -> EdgeCentricAgent:
        return self._agent

    def describe(self):
        return "Edge-Centric"

    @property
    def workspace(self) -> EdgeCentricWorkspace:
        return self._workspace

    async def _sythesize_for_segments(self, segments: Iterable[CodeSegment]) -> str:

        prev_result, signatures = self.workspace.context_of(segments)

        source = "\n".join(s.text for s in segments)

        trans_result = ""
        for i in range(GRAMMAR_RETRY):
            raw_result = await self.agent.generate_rust(
                source=source,
                previous_result=prev_result,
                signatures=signatures,
                temperature=self.temperature,
            )

            trans_result = self._collect_rust_code(raw_result) or ""
            if not grammar_correct(trans_result):

                continue
            return trans_result
        trans_result = await self._fix_grammar(trans_result)

        return trans_result

    _total_relation_num: int
    _relations: set[tuple[CodeSegment, CodeSegment]]
    _relation_try_count: dict[tuple[CodeSegment, CodeSegment], int]
    _segment_timestamp: dict[CodeSegment, float]
    _bar: tqdm

    def _add_relation(self, r: Iterable[tuple[CodeSegment, CodeSegment]]):

        for s1, s2 in set(r):
            if (s1, s2) in self._relations:
                continue
            if self._relation_try_count[(s1, s2)] >= self.max_retry:
                logger.info(
                    f"Translating relation {s1.id} -> {s2.id} exceeds 3 times, skip."
                )
                continue
            self._relations.add((s1, s2))
        self._bar.n = self._total_relation_num - len(self._relations)
        self._bar.refresh()

    def _remove_relation(self, r: Iterable[tuple[CodeSegment, CodeSegment]]):
        for s1, s2 in set(r):
            if (s1, s2) not in self._relations:
                continue
            self._relations.remove((s1, s2))
            self._relation_try_count[(s1, s2)] += 1
        self._bar.n = self._total_relation_num - len(self._relations)
        self._bar.refresh()

    def _get_surrounding(self, s: CodeSegment):
        yield from filter(lambda u: u not in self._in_synthesis, s.use)
        yield from filter(lambda u: u not in self._in_synthesis, s.used)

    def _calc_token_num(self, segments: Iterable[CodeSegment]):
        prev_result, signatures = self.workspace.context_of(segments)
        return self.tokenizer.token_num("\n".join(s.text for s in segments))

    def _pick_randomly(
        self, exclude: Container[CodeSegment]
    ) -> tuple[CodeSegment, CodeSegment] | None:

        for s1, s2 in sorted(self._relations, key=lambda _: random.random()):
            if s1 in exclude or s2 in exclude:
                continue
            return s1, s2

    def _vote_of_candidates(
        self, chosen: Container[CodeSegment], candidates: Iterable[CodeSegment]
    ) -> dict[CodeSegment, int]:
        votes = {}
        for c in candidates:
            votes[c] = sum(
                u in chosen for u in c.use if (c, u) in self._relations
            ) + sum(u in chosen for u in c.used if (u, c) in self._relations)
        return dict(filter(lambda x: x[1], votes.items()))

    async def _choose_to_trans(self) -> set[CodeSegment]:

        chosen = set()
        while not (picked := self._pick_randomly(exclude=self._in_synthesis)):
            await asyncio.sleep(0.01)

        chosen.update(picked)
        candidates = set(self._get_surrounding(picked[0])) | set(
            self._get_surrounding(picked[1])
        )
        if self._calc_token_num(picked) > self.max_source_tokens:
            logger.warning(
                f"Token num of {picked[0].id} and {picked[1].id} exceeds {self.max_source_tokens}"
            )
        out_sizes: set[CodeSegment] = set()  # candidates that will exceed size if added
        while candidates:

            votes = defaultdict(int)

            votes = self._vote_of_candidates(chosen, candidates)
            if votes:
                new_chosen = max(votes, key=lambda s: votes[s])
            else:
                # select the candidate with highest timestamp
                new_chosen = max(candidates, key=lambda s: self._segment_timestamp[s])
            candidates.remove(new_chosen)

            if self._calc_token_num({new_chosen} | chosen) > self.max_source_tokens:
                out_sizes.add(new_chosen)
                continue
            chosen.add(new_chosen)
            candidates |= set(self._get_surrounding(new_chosen)) - chosen - out_sizes

        return chosen

    async def _translate_order(self) -> AsyncGenerator[set[CodeSegment], Any]:
        while self._relations:
            yield await self._choose_to_trans()

    async def _synthesize_rust(self, all_segments: Iterable[CodeSegment]):
        self._relations = set()
        self._relation_try_count = defaultdict(int)
        self._segment_timestamp = defaultdict(float)
        for segment in all_segments:
            for other in segment.use:
                self._relations.add((segment, other))
            ## if there are standalone segments
            if not segment.use and not segment.used:
                self._relations.add((segment, segment))

        self._total_relation_num = len(self._relations)
        self._bar = tqdm(total=self._total_relation_num, file=sys.stdout)

        matcher = TreesitterMatcher(all_segments)

        async def synthesize_for_segments(segments: set[CodeSegment]):
            nonlocal matcher

            logger.info(f"Translating segment {' '.join(s.id for s in segments)}...")

            trans_result = await self._sythesize_for_segments(segments)

            match = matcher.try_to_match(trans_result)[0]

            to_add = []
            for seg, pieces in match.items():
                r = self.workspace.result_of_segment(seg) or ""
                pieces_text = "\n".join(p.text for p in pieces)

                if interface_equal(r, pieces_text):
                    continue

                for dep in seg.used:
                    if seg in segments and dep in segments:
                        continue
                    if seg not in segments and dep not in segments:
                        continue
                    to_add.append((dep, seg))

            self._add_relation(to_add)

            self.workspace.push(segments, trans_result)
            self._in_synthesis -= segments
            for s in segments:
                self._segment_timestamp[s] = time.time()

        tasks = []
        async for i, segments in aenumerate(self._translate_order()):
            to_remove = []
            for s1, s2 in self._relations:
                if s1 in segments and s2 in segments:
                    to_remove.append((s1, s2))
            self._remove_relation(to_remove)
            self._in_synthesis |= segments

            task = asyncio.create_task(synthesize_for_segments(segments))
            tasks.append(task)
        await asyncio.wait(tasks)
        self._bar.close()

    def _get_conflicts(self) -> dict[ConflictReport, set[RustPieceRef]]:
        ranges: list[tuple[RustPieceRef, int, int]] = (
            self.workspace.rust_code.piece_ref_ranges()
        )
        messages = validate(self.workspace.trans_result(), self.workspace.config)
        conflict2pieces = pieces_of_conflicts(messages, ranges)
        return conflict2pieces

    async def _fix_grammar(self, rust_code: str) -> str:
        if grammar_correct(rust_code):
            return rust_code
        messages = validate(rust_code, self.workspace.config)
        message_str = "\n".join(m.rendered for m in messages if m.rendered)
        raw_result = await self.agent.fix_grammar(
            rust_code, message_str, temperature=self.temperature
        )
        result = self._collect_rust_code(raw_result) or ""
        return result

    async def _resolve_pieces_of_conflicts(
        self,
        conflicts: Iterable[ConflictReport],
        pieces: set[RustPieceRef],
    ):
        err_msg = "\n".join(m.rendered for m in conflicts if m.rendered)

        resolved = [r for p in pieces if (r := p.resolve())]

        trimmed = self.workspace.rust_code.trimmed(resolved)
        if not trimmed:
            return ""

        result = ""
        for i in range(GRAMMAR_RETRY):
            raw_result = await self.agent.resolve_conflicts(
                err_msg=err_msg,
                rust_code="\n".join(trimmed.text),
                temperature=self.temperature,
            )

            result = self._collect_rust_code(raw_result) or ""

            if not grammar_correct(result):

                continue
            return result
        result = await self._fix_grammar(result)

        return result

    async def _resolve_conflicts_once(self, round: int) -> bool:
        in_resolution: set[RustPieceRef] = set()

        async def resolve_pieces_of_conflicts(
            conflicts: list[ConflictReport],
            pieces: set[RustPieceRef],
        ):
            nonlocal in_resolution, bar
            while pieces & in_resolution:
                await asyncio.sleep(0.01)
            in_resolution.update(pieces)
            result = await self._resolve_pieces_of_conflicts(conflicts, pieces)
            self.workspace.push(None, result)
            in_resolution -= pieces
            bar.update(len(conflicts))

        tasks = []
        self.workspace.config.dependencies = new_dependencies(
            self.workspace.trans_result(), self.workspace.config
        )

        conflict2prefs: dict[ConflictReport, set[RustPieceRef]] = self._get_conflicts()
        if not conflict2prefs:
            logger.info(f"Round {round}: No conflicts found.")
            return True
        logger.info(f"Round {round}: Resolving {len(conflict2prefs)} conflicts...")

        pref2conflicts = defaultdict(list)
        conflicts_prefs: list[tuple[list[ConflictReport], set[RustPieceRef]]] = []

        for conflict, prefs in conflict2prefs.items():
            if not prefs:
                continue
            if len(prefs) > 1:
                conflicts_prefs.append(([conflict], prefs))
                continue
            p = list(prefs)[0]
            pref2conflicts[p].append(conflict)
        for piece, conflicts in pref2conflicts.items():
            conflicts_prefs.append((conflicts, {piece}))
        conflicts_prefs.reverse()
        bar = tqdm(total=len(conflict2prefs), file=sys.stdout)
        for i, (conflicts, prefs) in enumerate(conflicts_prefs):

            tasks.append(
                asyncio.create_task(resolve_pieces_of_conflicts(conflicts, prefs))
            )
        await asyncio.wait(tasks)
        bar.close()
        return False

    async def _resolve_conflicts(self):

        for i in range(0, self.max_resolve_round):
            if await self._resolve_conflicts_once(i):
                break

    async def trans_project(self, project: "ProjectTranspiler") -> None:
        self._project = project
        self.workspace.config.package = Package(
            name=self._project.project_name,
            version="0.1.0",
            edition="2024",
            authors=["Your Name <youremail@example.com>"],
        )
        segments = self._get_segments()
        self.workspace.set_segments(segments)
        await self._synthesize_rust(segments)
        await self._resolve_conflicts()
