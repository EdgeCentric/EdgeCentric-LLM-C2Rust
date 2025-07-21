from collections import OrderedDict
import re
from abc import ABC
from collections.abc import Callable, Container, Generator, Iterable, Mapping, Sequence
from typing import Generic, NewType, Self, TypeVar

from thefuzz import fuzz
from tree_sitter import Node


def remove_comments(code: str) -> str:
    code = re.sub(r"//.*", "", code)

    no_star = r"[^*]*"
    # strings endswith a star and not followed by a slash
    star_end = no_star + r"\*(?!/)"
    many_star_end = f"(" + star_end + r")*"
    code = re.sub(r"/\*" + many_star_end + no_star + r"\*/", "", code)
    return code


def normalize(text: str) -> str:
    text = remove_comments(text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text


class NoSuchChild(Exception):
    def __init__(self, *, name: str | None = None, id: int | None = None):
        if name is not None:
            super().__init__(f"no child with field name {name}")
        if id is not None:
            super().__init__(f"no child with index {id}")


class NoText(Exception):
    def __init__(self):
        super().__init__(f"no text")


class Piece(ABC):
    _text: str
    _attr_text: str
    _comm_text: str

    @property
    def text(self) -> str:
        return "\n".join(filter(None, [self._comm_text, self._attr_text, self._text]))

    @property
    def comment(self) -> str:
        return self._comm_text

    @property
    def name(self) -> str | None:
        return None

    @classmethod
    def create(cls: type[Self], node: Node, attr_nodes: Sequence[Node], comment_nodes: Sequence[Node]) -> Self | None:

        p = cls()
        try:
            texts = [unsafe_text(comment) for comment in comment_nodes]
            p._comm_text = "\n".join(texts)
            texts = [unsafe_text(attr) for attr in attr_nodes]
            p._attr_text = "\n".join(texts)
            p._text = unsafe_text(node)
        except NoText:
            return None
        return p

    def __eq__(self, other):
        return self.text == other.text

    def __hash__(self):
        return hash(self.text)

    def copy(self) -> Self:
        p = type(self)()
        p._text = self._text
        p._attr_text = self._attr_text
        p._comm_text = self._comm_text
        return p


CNode = NewType("CNode", Node)
RustNode = NewType("RustNode", Node)
N = TypeVar("N", bound=Node)
P = TypeVar("P", bound=Piece)


class CPiece(Piece):
    pass


class RustPiece(Piece):
    _parent: "RustExtendable | None"
    _name: str

    def __init__(self):
        self._parent = None

    @classmethod
    def create(cls: type[Self], node: Node, attr_nodes: Sequence[Node], comment_nodes: Sequence[Node]) -> Self | None:
        p = super().create(node, attr_nodes, comment_nodes)
        if p is None:
            return None
        # drop '#[test]' in _attr_text
        p._attr_text = re.sub(r"\n?[ \t]*#\[test\]", "", p._attr_text)
        # replace #[no_mangle] with #[unsafe(no_mangle)]
        p._attr_text = p._attr_text.replace("#[no_mangle]", "#[unsafe(no_mangle)]")
        return p

    @property
    def parent(self):
        return self._parent

    @property
    def root(self):
        p = self
        while p.parent is not None:
            p = p.parent
        return p

    def remove_from_parent(self):
        if self._parent is None:
            return
        self._parent.remove(self)

    @property
    def name(self) -> str:
        return self._name

    @property
    def summary(self) -> str:
        return self._text

    def interface_equal(self, other: "RustPiece") -> bool:
        return (
            type(self) == type(other)
            and normalize(self._attr_text) == normalize(other._attr_text)
            and normalize(self._text) == normalize(other._text)
        )

    def set_comment(self, comment: str):
        self._comm_text = comment

    def copy(self) -> Self:
        p = super().copy()
        # _parent is not copied
        p._parent = None
        p._name = self._name
        return p


RP = TypeVar("RP", bound=RustPiece)


class RustExtendable(RustPiece, Generic[RP]):
    # unordered items
    _items_of_name: dict[str, RP]

    def __init__(self):
        super().__init__()
        self._items_of_name = OrderedDict()

    @property
    def _header(self) -> str:
        return ""

    @property
    def _tail(self) -> str:
        return ""

    @property
    def _sep(self) -> str:
        return ""

    @property
    def items(self) -> list[RP]:
        return list(self._items_of_name.values())

    def add(self, item: RP) -> list[RP]:
        """
        Params:
            item(RP): add `item` to replace the old, notice that this item will be added as it is not copied.
        Returns:
            list of items that are removed from the container
        """
        popped = []

        old_item = self._items_of_name.get(item.name)
        if old_item and isinstance(item, RustExtendable) and type(old_item) == type(item):
            # if added item is the same RustExtendable as the old,
            # the newer RustExtendable will be kept, try to move subitem from the old to the new
            for sub_item in old_item.items:
                if item.__add(sub_item):
                    # if add successfully, the subitem from the old RustExtendable will be removed as the old is removed
                    popped.append(sub_item)

        if old_item:
            self.remove(old_item)
            popped.append(old_item)
        self._items_of_name[item.name] = item
        item._parent = self
        return popped

    def __add(self, item: RP) -> bool:
        """
        Params:
            item(RP): add `item` only if it is not in the container. THIS IS DESTRUCTIVE.
        Returns:
            bool: success or not
        """

        old_item = self._items_of_name.get(item.name)
        if old_item:
            # old exists, do nothing
            return False
        self._items_of_name[item.name] = item
        item._parent = self
        return True

    def remove(self, item: RP):
        item._parent = None
        if item in self._items_of_name.values():
            del self._items_of_name[item.name]
        if not self.items:
            self.remove_from_parent()

    def remove_by_name(self, name: str):
        if name not in self._items_of_name:
            return
        self.remove(self._items_of_name[name])

    def is_empty(self) -> bool:
        return len(self._items_of_name) == 0

    @property
    def text(self):
        self._text = self._header + self._sep.join(item.text for item in self.items) + self._tail
        return super().text

    @property
    def summary(self) -> str:
        return self._header + self._sep.join(p.summary for p in self.items) + self._tail

    def interface_equal(self: Self, other: RustPiece) -> bool:
        return (
            isinstance(other, RustExtendable)
            and type(self) == type(other)
            and normalize(self._attr_text) == normalize(other._attr_text)
            and self.name == other.name
            and self._items_of_name.keys() == other._items_of_name.keys()
            and all(self._items_of_name[name].interface_equal(other._items_of_name[name]) for name in self._items_of_name)
        )

    def contains(self, piece: RP):
        """
        Returns:
            bool: True if this piece is inside me directly or indirectly
        """
        p = piece.parent
        while p is not self:
            if p is None:
                return False
            p = p.parent
        return True

    def empty_copy(self) -> Self:
        return super().copy()

    def copy(self) -> Self:
        p = self.empty_copy()
        for item in self.items:
            p.add(item.copy())
        return p


class RustPieceRef:
    """
    A reference to a piece inside a splittable, and the referenced piece will be anything other than splittable.
    """

    def __init__(self, root: "RustSplittable", names: Iterable[str] = []):
        self._root = root
        self._names = tuple(names)

    def resolve(self) -> RustPiece | None:
        """
        Returns:
            str: the referenced piece with rich context
        """
        p = self._root
        for name in self._names:
            if isinstance(p, RustExtendable) and name in p._items_of_name:
                p = p._items_of_name[name]
            else:
                return None
        return p

    def is_root(self):
        return not self._names

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RustPieceRef):
            return False
        return self._root == other._root and self._names == other._names

    def __hash__(self) -> int:
        # use object id of self._root and hash(self._names)
        return hash((id(self._root), self._names))


class RustSplittable(RustExtendable[RP]):
    def split(self, items: Iterable[RP]) -> tuple[Self | None, Self | None]:
        """
        Returns:
            tuple[Self, Self]: return a splittable piece that have as many these items as possible , and another piece not. If a splittable have nothing, the corresponding position is None.
        """
        p1 = self.empty_copy()
        p2 = self.empty_copy()
        items_set = set(items)
        for item in self.items:
            if item in items_set:
                p1.add(item.copy())
            else:
                p2.add(item.copy())
        return (p1 if not p1.is_empty() else None), (p2 if not p2.is_empty() else None)

    def trimmed(self, pieces: Iterable[RP]) -> Self | None:
        pieces_set = set(pieces)
        """
        Returns: 
            Self: a splittable piece that contains and only contains as many given pieces as possible.
        """
        p = self.empty_copy()
        for item in self.items:
            if item in pieces_set:
                p.add(item.copy())
            elif isinstance(item, RustSplittable):
                spl = item.trimmed(pieces)
                if spl:
                    p.add(spl)

            elif isinstance(item, RustExtendable):
                if any(item.contains(p) for p in pieces_set):
                    p.add(item.copy())

        return p if not p.is_empty() else None

    def walk(self, ref_as: RustPieceRef | None = None) -> Generator[tuple[RustPieceRef, str]]:
        if not ref_as:
            ref_as = RustPieceRef(self)
        yield ref_as, self._header
        # _items_of_name is not ordered
        # we should use `items` instead
        items = self.items
        last_one_index = len(items) - 1
        for i, item in enumerate(items):

            ref = RustPieceRef(ref_as._root, ref_as._names + (item.name,))

            if isinstance(item, RustSplittable):
                yield from item.walk(ref)
            else:
                yield ref, item.text
            if i < last_one_index:
                yield ref_as, self._sep
        yield ref_as, self._tail


class Extracter(ABC, Generic[P, N]):
    extract_rules: Mapping[type[P], list[str] | Callable[[N], bool]]

    def extract(self, nodes: Sequence[N]) -> Iterable[P]:
        attributes = []
        comments = []
        last_end_line = 0
        for node in nodes:
            if t := self.extractable(node):

                if p := t.create(node, attributes, comments):
                    yield p
                last_end_line = node.end_point[0]
            if self.is_attribute(node):
                attributes.append(node)
            elif (
                self.is_comment(node) and node.start_point[0] > last_end_line
            ):  # we do not recognzie the comment right after the node
                if comments and comments[-1].end_point[0] < node.start_point[0] - 1:
                    # we drop previous comments if they are not continuous
                    comments = [node]
                else:
                    comments.append(node)
            else:
                attributes = []
                comments = []

    def extractable(self, node: N) -> type[P] | None:
        for t, rule in self.extract_rules.items():
            if callable(rule):
                if rule(node):
                    return t
            elif node.type in rule:
                return t

    def is_attribute(self, node: N) -> bool:
        return False

    def is_comment(self, node: N) -> bool:
        return False


def unsafe_child_by_name(node: N, field_name: str) -> N:
    """
    Raises:
        NoSuchChild: if there is no such child with the specified field name
    """
    child = node.child_by_field_name(field_name)
    if child is None:
        raise NoSuchChild(name=field_name)
    return child  # type: ignore


def unsafe_child_by_index(node: N, index: int) -> N:
    """
    Raises:
        NoSuchChild: if the index is out of range
    """
    child = node.child(index)
    if child is None:
        raise NoSuchChild(id=index)
    return child  # type: ignore


def unsafe_text(node: Node) -> str:
    if node.text is None:
        raise NoText()
    return node.text.decode("utf-8")


def unsafe_child_text(node: Node, field_name: str) -> str:
    """
    Raises:
        NoSuchChild
        NoText
    """
    return unsafe_text(unsafe_child_by_name(node, field_name))


def unsafe_declarator_name(node: Node) -> str:
    """
    Raises:
        NoSuchChild
        NoText
    """
    while True:
        if (_tmp_node := node.child_by_field_name("declarator")) is not None:
            node = _tmp_node
        elif node.type == "parenthesized_declarator":
            node = unsafe_child_by_index(node, 1)
        else:
            break
    return unsafe_text(node)


def _match_similarly(
    name: str | None, pieces: Iterable[P], kinds: Container[type[Piece]], threshold: int, convert_name: Callable[[str], str]
) -> Iterable[P]:
    if not name:
        return []
    name = convert_name(name)
    matched: list[tuple[float, P]] = []
    candidates = [p for p in pieces if type(p) in kinds]
    for p in candidates:
        p_name = p.name
        if not p_name:
            continue
        p_name = convert_name(p_name)
        similarity = fuzz.ratio(name, p_name)
        if similarity >= threshold:
            matched.append((similarity, p))
    if len(matched) > 0:
        best_match = max(matched, key=lambda x: x[0])
        return [best_match[1]]
    else:
        return []


def match_similarly(name: str | None, pieces: Iterable[P], kinds: Container[type[Piece]], threshold: int = 90) -> Iterable[P]:
    return _match_similarly(name, pieces, kinds, threshold, lambda x: x)


def match_similarly_lower(
    name: str | None, pieces: Iterable[P], kinds: Container[type[Piece]], threshold: int = 90
) -> Iterable[P]:
    return _match_similarly(name, pieces, kinds, threshold, lambda x: x.lower())


def match_exactly_or_by_tokens(name: str | None, pieces: Iterable[P], kinds: Container[type[Piece]]) -> Iterable[P]:
    return match_similarly(name, pieces, kinds, 100) or match_by_tokens(name, pieces, kinds)


def match_exactly_lower(name: str | None, pieces: Iterable[P], kinds: Container[type[Piece]]) -> Iterable[P]:
    return match_similarly_lower(name, pieces, kinds, 100)


def match_similar_str(str1: str | None, str2: str | None, threshold: int = 90):
    if not str1 or not str2:
        return False
    return fuzz.ratio(str1, str2) >= threshold


def exact_same_names(str1: str | None, str2: str | None):
    if not str1 or not str2:
        return False
    return str1 == str2


def similar_same_lower_names(str1: str | None, str2: str | None, threshold: int = 90):
    if not str1 or not str2:
        return False
    return fuzz.ratio(str1.lower(), str2.lower()) >= threshold


def exact_same_lower_names(str1: str | None, str2: str | None):
    if not str1 or not str2:
        return False
    return str1.lower() == str2.lower()


def tokenize(name: str) -> list[str]:
    # Split camelCase and PascalCase
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    name = name.lower()
    # Split snake_case
    tokens = re.split(r"[_\s]+", name)
    return tokens


def match_by_tokens(name: str | None, pieces: Iterable[P], kinds: Container[type[Piece]]) -> Iterable[P]:
    if not name:
        return []
    tokens = "".join(tokenize(name))
    for p in filter(lambda p: type(p) in kinds, pieces):
        if not p.name:
            continue
        p_tokens = "".join(tokenize(p.name))
        if tokens == p_tokens:
            return [p]
    return []


def tokens_same_names(str1: str | None, str2: str | None) -> bool:
    if not str1 or not str2:
        return False
    return "".join(tokenize(str1)) == "".join(tokenize(str2))


def text_of_pieces(pieces: Sequence[Piece], sep="\n"):
    return sep.join(p.text for p in pieces)
