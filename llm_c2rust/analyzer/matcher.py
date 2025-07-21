import functools
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping

from llm_c2rust.analyzer.c_pieces import (
    CClass,
    CDeclaration,
    CEnum,
    CFunction,
    CMacro,
    CMacroFun,
    CMultipleDeclaration,
    CMultipleTypedef,
    CPiece,
    CStruct,
    CTypedef,
    CUnion,
    CUsing,
    c_pieces_of_text,
)
from llm_c2rust.analyzer.rust_pieces import (
    RustCode,
    RustConst,
    RustEnum,
    RustFn,
    RustFnSignature,
    RustImpl,
    RustMacro,
    RustStatic,
    RustStruct,
    RustType,
)
from llm_c2rust.analyzer.utils import (
    P,
    Piece,
    RustPiece,
    exact_same_names,
    match_by_tokens,
    match_exactly_lower,
    match_exactly_or_by_tokens,
    match_similarly,
    match_similarly_lower,
    tokens_same_names,
)

from llm_c2rust.segmenter.code_segment import CodeSegment

logger = logging.getLogger(__name__)

Match = Mapping[CodeSegment, list[RustPiece]]


class MatchFail(Exception):
    def __init__(self, msg):
        super().__init__(f"Match Fail: {msg}")


class Matcher(ABC):
    @abstractmethod
    def match(self, result: str) -> tuple[Match, RustCode]:
        """
        This method gurantee each slices in the chunk is matched with not DummySliceResult.
        Raises:
            MatchFail: if the matching fails
        """
        raise NotImplementedError("The match method in Matcher is abstract")

    @abstractmethod
    def try_to_match(self, result: str) -> tuple[Match, RustCode]:
        """
        This method may return the chunk result with DummySnippetResult. No MatchFail will be raised.
        """
        raise NotImplementedError("The try_to_match method in Matcher is abstract")


def raiseMergeFail(msg):
    raise MatchFail(msg)


class TreesitterMatcher(Matcher):
    segments: dict[CodeSegment, list[CPiece]]

    c_pieces: dict[CPiece, CodeSegment]
    _counter_kinds: dict[type[Piece], list[type[Piece]]] = {
        CTypedef: [RustType],
        CUsing: [RustType],
        CMacro: [RustMacro, RustConst],
        CMacroFun: [RustMacro, RustFn],
        CFunction: [RustFn],
        CEnum: [RustEnum],
        CStruct: [RustStruct],
        CClass: [RustStruct],
        RustFn: [CFunction],
        RustConst: [CDeclaration, CMacro],
        RustType: [CDeclaration],
    }

    def __init__(self, segments: Iterable[CodeSegment]) -> None:

        self.segments = {}
        self.c_pieces = {}
        for s in segments:
            self.segments[s] = list(c_pieces_of_text(s.text))
            for p in self.segments[s]:
                self.c_pieces[p] = s

    def _match(
        self, result: str, match_fail: Callable[[str], None]
    ) -> tuple[Match, RustCode]:

        rust_code = RustCode.from_text(result)
        rust_code.normalize()
        matches: dict[CodeSegment, list[RustPiece]] = defaultdict(list)

        for cp in self.c_pieces:
            match_rps: list[RustPiece] = list(self.match_piece(cp, rust_code.items))
            matches[self.c_pieces[cp]].extend(match_rps)

        # final check
        for s in self.segments - matches.keys():
            match_fail(
                f"the source code contains\n{s.text}\n, but they have no match in the translation result."
            )

        return {s: ps for s, ps in matches.items() if ps}, rust_code

    def match(self, result: str) -> tuple[Match, RustCode]:
        return self._match(result, match_fail=raiseMergeFail)

    def try_to_match(self, result: str) -> tuple[Match, RustCode]:
        return self._match(result, match_fail=lambda m: None)

    def counter_kinds(self, piece: Piece | type[Piece]) -> list[type[Piece]]:
        if isinstance(piece, type):
            return self._counter_kinds.get(piece, [])
        return self._counter_kinds.get(type(piece), [])

    def match_piece_exactly_or_by_tokens(
        self, piece: Piece, target_pieces: Iterable[P]
    ) -> Iterable[P]:
        return match_exactly_or_by_tokens(
            piece.name, target_pieces, self.counter_kinds(piece)
        )

    def match_piece_similarly(
        self, piece: Piece, target_pieces: Iterable[P], threshold: int = 90
    ) -> Iterable[P]:
        return match_similarly(
            piece.name, target_pieces, self.counter_kinds(piece), threshold
        )

    def match_piece_exactly_lower(
        self, piece: Piece, target_pieces: Iterable[P]
    ) -> Iterable[P]:
        return match_exactly_lower(piece.name, target_pieces, self.counter_kinds(piece))

    def match_piece_similarly_lower(
        self, piece: Piece, target_pieces: Iterable[P], threshold: int = 90
    ) -> Iterable[P]:
        return match_similarly_lower(
            piece.name, target_pieces, self.counter_kinds(piece), threshold
        )

    def match_piece_by_tokens(
        self, piece: Piece, target_pieces: Iterable[P]
    ) -> Iterable[P]:
        return match_by_tokens(piece.name, target_pieces, self.counter_kinds(piece))

    @functools.singledispatchmethod
    def match_piece(self, piece: Piece, target_pieces: Iterable[P]) -> Iterable[P]:
        return []

    @match_piece.register
    def _(
        self, piece: CTypedef | CUsing, target_pieces: Iterable[RustPiece]
    ) -> Iterable[RustPiece]:
        return (
            (
                piece.body_piece and self.match_piece(piece.body_piece, target_pieces)
            )  # if there is a body with a name, match the body first
            or (
                piece.body_piece
                and match_exactly_or_by_tokens(
                    piece.name, target_pieces, self.counter_kinds(piece.body_piece)
                )
            )  # try to match with concrete kinds, for example struct, enum, etc.
            or self.match_piece_exactly_or_by_tokens(
                piece, target_pieces
            )  # match type item
            or []
        )

    @match_piece.register
    def _(
        self, piece: CMultipleTypedef, target_pieces: Iterable[RustPiece]
    ) -> Iterable[RustPiece]:
        rust_kinds = (
            self.counter_kinds(piece.body_piece) if piece.body_piece else [RustType]
        )
        for name in piece.names:
            yield from match_exactly_or_by_tokens(name, target_pieces, rust_kinds)

    @match_piece.register
    def _(
        self, piece: CMacro, target_pieces: Iterable[RustPiece]
    ) -> Iterable[RustPiece]:
        return self.match_piece_exactly_or_by_tokens(
            piece, target_pieces
        ) or self.match_piece_exactly_lower(piece, target_pieces)

    @match_piece.register
    def _(
        self, piece: CMacroFun, target_pieces: Iterable[RustPiece]
    ) -> Iterable[RustPiece]:
        return self.match_piece_exactly_or_by_tokens(piece, target_pieces)

    @match_piece.register
    def _(
        self, piece: CDeclaration, target_pieces: Iterable[RustPiece]
    ) -> Iterable[RustPiece]:
        def match_field():
            for rust_piece in target_pieces:
                if not isinstance(rust_piece, RustStruct):
                    continue
                for item in rust_piece.items:
                    if exact_same_names(piece.name, item.name):
                        return [item]

            return []

        if piece.is_function:
            return match_exactly_or_by_tokens(
                piece.name, target_pieces, [RustFnSignature]
            )
        else:
            return (
                match_exactly_or_by_tokens(
                    piece.name, target_pieces, [RustConst, RustStatic]
                )
                or match_field()
            )

    @match_piece.register
    def _(
        self, piece: CMultipleDeclaration, target_pieces: Iterable[RustPiece]
    ) -> Iterable[RustPiece]:
        def match_field(name: str):
            for rust_piece in target_pieces:
                if not isinstance(rust_piece, RustStruct):
                    continue
                for item in rust_piece.items:
                    if exact_same_names(name, item.name):
                        return [item]

            return []

        def match_declarator_case(d: str) -> Iterable[RustPiece]:
            nonlocal piece, target_pieces
            if piece.is_funcs[d]:
                return match_exactly_or_by_tokens(d, target_pieces, [RustFnSignature])
            else:
                return match_exactly_or_by_tokens(
                    d, target_pieces, [RustConst, RustStatic]
                ) or match_field(d)

        matches = []
        for d in piece.names:
            matches.extend(match_declarator_case(d))
        return matches

    @match_piece.register
    def _(
        self, piece: CFunction, target_pieces: Iterable[RustPiece]
    ) -> Iterable[RustPiece]:
        def match_impl_method():
            for rust_piece in target_pieces:
                if not isinstance(rust_piece, RustImpl):
                    continue

                for item in rust_piece.items:
                    if not isinstance(item, RustFn):
                        continue
                    if exact_same_names(piece.name, item.name):
                        return [item]
                    if tokens_same_names(
                        piece.name, rust_piece.type_name + "_" + item._name
                    ):
                        return [item]
            return []

        return (
            self.match_piece_exactly_or_by_tokens(piece, target_pieces)
            or match_impl_method()
        )

    @match_piece.register
    def _(
        self, piece: CUnion, target_pieces: Iterable[RustPiece]
    ) -> Iterable[RustPiece]:
        return self.match_piece_exactly_or_by_tokens(piece, target_pieces)

    @match_piece.register
    def _(
        self, piece: CStruct, target_pieces: Iterable[RustPiece]
    ) -> Iterable[RustPiece]:
        return self.match_piece_exactly_or_by_tokens(piece, target_pieces)

    @match_piece.register
    def _(
        self, piece: CEnum, target_pieces: Iterable[RustPiece]
    ) -> Iterable[RustPiece]:
        def match_enumerators() -> Iterable[RustPiece]:
            nonlocal piece, target_pieces
            # so the source is nameless, we just need to match names of all items
            candidates = [item for item in target_pieces if isinstance(item, RustEnum)]
            lower_names = set(map(str.lower, piece.enumerator_names))
            for c in candidates:

                # get names of all enumerators in the candidate
                target_lower_names = {item.name.lower() for item in c.items}
                if target_lower_names == lower_names:
                    return [c]
            return []

        def match_declarations() -> Iterable[RustPiece]:
            nonlocal target_pieces
            for name in piece.enumerator_names:
                yield from match_exactly_or_by_tokens(
                    name, target_pieces, [RustConst, RustStatic]
                )

        return (
            self.match_piece_exactly_or_by_tokens(piece, target_pieces)
            or self.match_piece_by_tokens(piece, target_pieces)
            or match_enumerators()
            or match_declarations()
        )

    @match_piece.register
    def _(
        self, piece: CClass, target_pieces: Iterable[RustPiece]
    ) -> Iterable[RustPiece]:
        return self.match_piece_exactly_or_by_tokens(piece, target_pieces)
