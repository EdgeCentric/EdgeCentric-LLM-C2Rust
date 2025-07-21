# this class is responsible for managing all
# necessary information during translation
# include chunks (which are collections of slices), slices and
# their results

from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Iterable
import logging

from llm_c2rust.analyzer.matcher import TreesitterMatcher
from llm_c2rust.analyzer.rust_pieces import RustCode, RustUse
from llm_c2rust.analyzer.utils import RustExtendable, RustPiece, RustSplittable
from llm_c2rust.cargo.cargo_message import CargoConfig
from llm_c2rust.segmenter.code_segment import CodeSegment

logger = logging.getLogger(__name__)


class TranslationWorkspace(ABC):
    config: CargoConfig

    def __init__(self):
        self.config = CargoConfig(dependencies={})

    @abstractmethod
    def set_segments(self, segments: Iterable[CodeSegment]) -> None:
        raise NotImplementedError()

    @abstractmethod
    def trans_result(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def push(self, segments: set[CodeSegment] | None, code: str) -> None:
        raise NotImplementedError()


class EdgeCentricWorkspace(TranslationWorkspace):

    def __init__(self):
        super().__init__()
        self.seg_to_pieces: dict[CodeSegment, list[RustPiece]] = defaultdict(list)
        self.seg_of_pieces: dict[RustPiece, list[CodeSegment]] = defaultdict(list)
        self.rust_code = RustCode.from_text("")

    def set_segments(self, segments: Iterable[CodeSegment]):
        self.all_segments = set(segments)
        self.matcher = TreesitterMatcher(self.all_segments)

    def result_of_segment(self, segment: CodeSegment) -> str | None:
        return "\n".join(p.text for p in self.seg_to_pieces[segment])

    def push(self, segments: set[CodeSegment] | None, code: str):
        if segments is None:
            segments = self.all_segments

        match, new_code = self.matcher.try_to_match(code)

        for segment, pieces in match.items():

            if segment not in segments:
                for p in pieces:
                    p.remove_from_parent()
                continue
            self.seg_to_pieces[segment] = pieces
            for p in pieces:
                self.seg_of_pieces[p].append(segment)

        self.rust_code.merge_in(new_code)

    def trans_result(self) -> str:
        return self.rust_code.text

    def context_of(self, segments: Iterable[CodeSegment]) -> tuple[str, str]:
        """
        Returns:
            str: previous translation
            str: related function signatures
        """
        matched_pieces = {p for s in segments for p in self.seg_to_pieces[s]}
        included: list[RustPiece] = []

        for item in self.rust_code.items:
            if isinstance(item, RustUse):
                included.append(item)
            elif item in matched_pieces:
                included.append(item)
            elif isinstance(item, RustSplittable):
                spl = item.trimmed(matched_pieces)
                if spl:
                    included.append(spl)
            elif isinstance(item, RustExtendable):
                if any(item.contains(p) for p in matched_pieces):
                    included.append(item)
        used_rp = [
            rp for s in segments for used in s.use for rp in self.seg_to_pieces[used]
        ]
        trimmed = self.rust_code.trimmed(used_rp)
        signatures = trimmed.summary if trimmed else ""
        return "\n".join(item.text for item in included).strip(), signatures


class NodeCentricWorkspace(TranslationWorkspace):
    def __init__(self):
        super().__init__()
        self._segment_results: dict[CodeSegment, RustCode] = {}
        self._use_decls: RustCode = RustCode.from_text("")

    def set_segments(self, segments: Iterable[CodeSegment]):
        self.all_segments = set(segments)

    def push(
        self,
        segments: Iterable[CodeSegment] | None,
        code: str,
    ) -> None:
        if not segments:
            return
        match, rust_code = TreesitterMatcher(segments).try_to_match(code)
        for segment, pieces in match.items():
            self._segment_results[segment] = RustCode.from_text(
                "\n".join(p.text for p in pieces)
            )
        for p in rust_code.items:
            if isinstance(p, RustUse):
                self._use_decls.add(p)

    def trans_result(self) -> str:
        all_code = self._use_decls.copy()
        for code in self._segment_results.values():
            all_code.merge_in(code.copy())
        return all_code.text

    def result_of_segment(self, segment: CodeSegment) -> str:
        if segment not in self._segment_results:
            return ""
        return self._segment_results[segment].text

    def result_of_dependency(self, segments: Iterable[CodeSegment]) -> str:
        deps = {dep for s in segments for dep in s.use}
        return "\n".join(self.result_of_segment(dep) or "" for dep in deps)

    def summary_of_dependency(self, segments: Iterable[CodeSegment]) -> str:
        """
        Returns:
            str: dependencies' signatures
        """
        deps = {dep for s in segments for dep in s.use}
        return "\n".join(
            code.summary for d in deps if (code := self._segment_results.get(d))
        )
