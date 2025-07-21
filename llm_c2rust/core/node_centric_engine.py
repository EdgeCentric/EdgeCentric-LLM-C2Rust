import asyncio
import logging
import sys
from collections import defaultdict
from collections.abc import AsyncGenerator, Generator, Iterable
from typing import TYPE_CHECKING

import networkx as nx
from tqdm import tqdm

from llm_c2rust.llm.LLM import NodeCentricAgent
from llm_c2rust.analyzer.matcher import TreesitterMatcher
from llm_c2rust.analyzer.rust_pieces import RustCode

from llm_c2rust.cargo.cargo_message import Package
from llm_c2rust.core.interact import InteractEngine
from llm_c2rust.core.transpilation_workspace import NodeCentricWorkspace
from llm_c2rust.core.utils import (
    aenumerate,
    all_rust_code_from_md,
    validate,
    first_rust_code_from_md,
    new_dependencies,
    ConflictReport,
)
from llm_c2rust.llm.api_inference import AsyncAPIInference
from llm_c2rust.segmenter.code_segment import CodeSegment
from llm_c2rust.segmenter.segmenter import Segmenter

if TYPE_CHECKING:
    from llm_c2rust.core.transpiler import ProjectTranspiler


logger = logging.getLogger(__name__)

# input limit of LLM
TOKENS_FOR_CONFLICT = 54000


class NodeCentricEngine(InteractEngine):
    def describe(self) -> str:
        return "Node-Centric"

    def __init__(
        self,
        segmenter: Segmenter,
        predicator: AsyncAPIInference,
        token_num: int,
        token_num_method: str,
        max_resolve_round: int,
        temperature: float,
    ):
        super().__init__(
            segmenter, predicator, token_num, token_num_method, temperature
        )
        self.max_resolve_round = max_resolve_round
        self._trans_manager = NodeCentricWorkspace()
        self._agent = NodeCentricAgent(predicator)
        self._translate_finished: list[CodeSegment] = []
        if predicator.model_name.startswith("qwen"):
            # Qwen like to split the answer into multiple parts
            self._collect_rust_code = all_rust_code_from_md
        else:
            self._collect_rust_code = first_rust_code_from_md

    async def _get_conflicts(
        self, context: str, rust_code: str
    ) -> list[ConflictReport]:
        full_code = context + "\n" + rust_code

        self.workspace.config.dependencies = new_dependencies(
            full_code, self.workspace.config
        )
        start_line = 1 + context.count("\n")  # 1-based

        msgs = []
        for msg in validate(full_code, self.workspace.config):
            if all(span.line_end < start_line for span in msg.all_spans):
                continue
            msgs.append(msg)

        return msgs

    @property
    def agent(self) -> NodeCentricAgent:
        return self._agent

    async def _sythesize_for_segments(self, segments: list[CodeSegment]) -> str:
        # marked_chunk = MarkedCodeSegment.from_CodeSegment(chunk)

        # logging
        source_code = "\n".join(s.text for s in segments)
        deps = self.workspace.summary_of_dependency(segments)

        raw_result = await self.agent.generate_rust(
            source=source_code, dependency_summary=deps, temperature=self.temperature
        )

        trans_result = self._collect_rust_code(raw_result) or ""

        # examinate all segments are translated
        match, trans_result = TreesitterMatcher(segments).try_to_match(trans_result)
        not_translated = [s for s in segments if s not in match]
        if not_translated:

            source_code = "\n".join(s.text for s in not_translated)

            raw_result = await self.agent.generate_rust(
                source=source_code,
                dependency_summary=deps,
                temperature=self.temperature,
            )

            trans_result.merge_in(
                RustCode.from_text(self._collect_rust_code(raw_result) or "")
            )
        trans_result = trans_result.text

        return trans_result

    def _select_messages(
        self, msgs: list[ConflictReport], rust_code: str
    ) -> Generator[list[ConflictReport]]:

        selected = []
        remain_tokens_num = TOKENS_FOR_CONFLICT
        for msg in msgs:
            if not msg.rendered:
                continue
            token_num = self.tokenizer.token_num(msg.rendered)
            if token_num > remain_tokens_num:
                yield selected
                selected = []
                remain_tokens_num = TOKENS_FOR_CONFLICT
            selected.append(msg)
            remain_tokens_num -= token_num
        if selected:
            yield selected

    async def _resolve_conflicts(
        self,
        segments: list[CodeSegment],
        trans_result: str,
    ) -> str:
        result: RustCode = RustCode.from_text(trans_result)

        for i in range(self.max_resolve_round):
            msgs = await self._get_conflicts(self.workspace.trans_result(), result.text)

            if not msgs:
                break
            for selected in self._select_messages(msgs, result.text):

                selected_msg_text = "\n".join(
                    msg.rendered for msg in selected if msg.rendered
                )

                resp = await self.agent.resolve_conflicts(
                    err_msg=selected_msg_text,
                    rust_code=result.text,
                    temperature=self.temperature,
                )

                code = self._collect_rust_code(resp) or ""
                result.merge_in(RustCode.from_text(code))

        return result.text

    async def _transpile_segments(self, segments: list[CodeSegment]) -> str:

        trans_res = await self._sythesize_for_segments(segments)

        trans_res = await self._resolve_conflicts(segments, trans_res)
        self.workspace.push(segments, trans_res)
        self._translate_finished.extend(segments)
        return trans_res

    async def _translate_order(
        self, segments: list[CodeSegment]
    ) -> AsyncGenerator[list[CodeSegment]]:

        def scc_token_num(segments: Iterable[CodeSegment]) -> int:
            return sum(self.tokenizer.token_num(s.text) for s in segments)

        def pick_scc(
            sccs: Iterable[frozenset[CodeSegment]], tokens_limit: int
        ) -> frozenset[CodeSegment] | None:
            for scc in sccs:
                if scc_token_num(scc) < tokens_limit:
                    return scc

        def find_new_leaves(
            finished: Iterable[CodeSegment],
            indegree: dict[frozenset[CodeSegment], int],
            seg2scc: dict[CodeSegment, frozenset[CodeSegment]],
        ):
            new_leaves = set()
            for s in finished:
                for used in s.used:
                    scc = seg2scc[used]
                    indegree[scc] -= 1
                    if indegree[scc] == 0:
                        new_leaves.add(scc)
            return new_leaves

        g = nx.DiGraph()
        g.add_nodes_from(segments)
        g.add_edges_from((u, v) for u in segments for v in u.use)
        sccs: list[frozenset[CodeSegment]] = [
            frozenset(scc) for scc in nx.strongly_connected_components(g)
        ]

        scc_of_segment: dict[CodeSegment, frozenset[CodeSegment]] = {
            s: scc for scc in sccs for s in scc
        }

        # sum of in_degree of all nodes in a scc, except inner edges
        # when a scc is ready, indegree == 0
        # when a scc is translated, indegree < 0
        scc_indegree: dict[frozenset[CodeSegment], int] = defaultdict(int)
        for u in segments:
            scc_u = scc_of_segment[u]
            uses = [v for v in u.use if scc_of_segment[v] != scc_u]
            scc_indegree[scc_u] += len(uses)

        # an scc is either leaves, translating, to_trans, and not ready.
        # not ready -- indegree=0 --> leaves --> to_trans --> translating --> translated
        leaves: set[frozenset[CodeSegment]] = {
            scc for scc in sccs if scc_indegree[scc] == 0
        }
        translating: set[CodeSegment] = set()

        while leaves or translating:
            leaves.update(
                find_new_leaves(self._translate_finished, scc_indegree, scc_of_segment)
            )
            translating.difference_update(self._translate_finished)
            self._translate_finished = []
            if not leaves:
                await asyncio.sleep(0.1)
                continue

            to_trans: list[CodeSegment] = list(leaves.pop())
            tokens_sum = 0
            while leaves:
                picked = pick_scc(leaves, self.max_source_tokens - tokens_sum)
                if not picked:
                    break
                tokens_sum += scc_token_num(picked)
                leaves.remove(picked)
                to_trans.extend(picked)

            translating.update(to_trans)
            yield to_trans

    async def trans_project(self, project: "ProjectTranspiler") -> None:
        self._project = project
        self.workspace.config.package = Package(
            name=self._project.project_name,
            version="0.1.0",
            edition="2024",
            authors=["Your Name <youremail@example.com>"],
        )
        segments = list(self._get_segments())
        self.workspace.set_segments(segments)
        # Tranlate segments
        bar = tqdm(
            total=len(segments),
            desc="Processing segments",
            unit="segment",
            file=sys.stdout,
        )

        tasks = []
        async for i, to_trans in aenumerate(self._translate_order(segments)):

            tasks.append(asyncio.create_task(self._transpile_segments(to_trans)))
            logger.info(f"Translating { ', '.join(str(s.id) for s in to_trans)}")
            bar.update(len(to_trans))
        await asyncio.wait(tasks)
        bar.close()

    @property
    def workspace(self) -> NodeCentricWorkspace:
        return self._trans_manager
