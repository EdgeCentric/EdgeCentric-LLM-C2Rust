import logging
from collections.abc import Callable, Iterable, Sequence
from typing import Mapping, Self

from tree_sitter import Node

from llm_c2rust.analyzer.utils import (
    Extracter,
    NoSuchChild,
    NoText,
    RustExtendable,
    RustNode,
    RustPiece,
    RustPieceRef,
    RustSplittable,
    unsafe_child_by_name,
    unsafe_child_text,
    unsafe_text,
)

from llm_c2rust.parser.rust_parser import parse_rust

# since it is target based, it does not manage slice relation
# rather, it only manages source-target relation
import logging

logger: logging.Logger = logging.getLogger(__name__)


def get_path(path_node: Node | None):
    path = []
    while path_node:
        if path_node.type == "identifier":
            path.append(unsafe_text(path_node))
        elif path_node.type == "scoped_identifier":
            path.append(unsafe_child_text(path_node, "name"))
        path_node = path_node.child_by_field_name("path")
    path.reverse()
    return path


class RustUseId(RustPiece):
    path: list[str]
    alias: str | None

    @classmethod
    def create(
        cls: type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Self | None:
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None
        try:
            p.alias = None
            if node.type == "use_as_clause":
                p.path = get_path(unsafe_child_by_name(node, "path"))
                p.alias = unsafe_child_text(node, "alias")
                p._name = p.alias
            elif node.type == "scoped_identifier":
                p.path = get_path(node)
                p._name = p.path[-1]
            elif node.type == "identifier":
                p._name = unsafe_text(node)
                p.path = [p._name]
            elif node.type == "self":
                p._name = "self"
                p.path = ["self"]
            elif node.type == "crate":
                p._name = "crate"
                p.path = ["crate"]
            else:
                return None
        except (NoSuchChild, NoText):
            return None
        return p

    def copy(self) -> Self:
        p = super().copy()
        p.path = list(self.path)
        p.alias = self.alias
        return p


class RustUse(RustExtendable[RustUseId]):
    path: list[str]

    @classmethod
    def create(
        cls: type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Self | None:
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None

        try:
            argument = unsafe_child_by_name(node, "argument")

            path_node = argument.child_by_field_name("path")

            p.path = get_path(path_node)
            p._name = "use " + "::".join(p.path)
            if argument.type == "identifier":
                name_nodes = [argument]
            elif name_node := argument.child_by_field_name("name"):
                name_nodes = [name_node]
            else:
                name_nodes = unsafe_child_by_name(argument, "list").named_children
            for name_node in name_nodes:
                id = RustUseId.create(name_node, [], [])

                if not id:
                    continue
                p.add(id)
        except (NoSuchChild, NoText):
            return None

        return p

    def empty_copy(self) -> Self:
        p = super().empty_copy()
        p.path = list(self.path)
        return p

    @property
    def _header(self):
        bracket = "{" if len(self.items) > 1 else ""
        return f"use " + "::".join(self.path + [bracket])

    @property
    def _tail(self):
        return ("}" if len(self.items) > 1 else "") + ";"

    @property
    def _sep(self):
        return ", "

    def decl_names(self) -> dict[str, RustUseId]:
        names = {}
        for id in self.items:
            name = id.name
            if name == "self":
                name = self.path[-1]
            names[name] = id
        return names


class RustSimplePiece(RustPiece):
    """
    RustSimplePiece is a piece of code that has a name.
    """

    @classmethod
    def create(
        cls: type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Self | None:
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None

        try:
            p._name = unsafe_child_text(node, "name")
        except (NoSuchChild, NoText):
            return None
        return p


class RustStatic(RustSimplePiece):
    type_name: str

    @classmethod
    def create(
        cls: type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Self | None:
        p = super().create(node, attr_nodes, comment_nodes)
        if p is None:
            return None
        try:
            p.type_name = unsafe_child_text(node, "type")
        except (NoSuchChild, NoText):
            return None
        return p

    @property
    def summary(self) -> str:
        return f"static {self._name}: {self.type_name};"

    def interface_equal(self, other: RustPiece) -> bool:
        return (
            isinstance(other, RustStatic)
            and self.name == other.name
            and self.type_name == other.type_name
        )

    def copy(self) -> Self:
        p = super().copy()
        p.type_name = self.type_name
        return p


class RustConst(RustSimplePiece):
    type_name: str

    @classmethod
    def create(
        cls: type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Self | None:
        p = super().create(node, attr_nodes, comment_nodes)
        if p is None:
            return None
        try:
            p.type_name = unsafe_child_text(node, "type")
        except (NoSuchChild, NoText):
            return None
        return p

    def copy(self) -> Self:
        p = super().copy()
        p.type_name = self.type_name
        return p

    @property
    def summary(self) -> str:
        return f"const {self._name}: {self.type_name};"

    def interface_equal(self, other: RustPiece) -> bool:
        return (
            isinstance(other, RustConst)
            and self.name == other.name
            and self.type_name == other.type_name
        )


class RustField(RustSimplePiece):
    pass


class RustStruct(RustExtendable[RustField]):
    type_parameters: list[str]

    @classmethod
    def create(
        cls: type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Self | None:

        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None

        try:

            body_node = unsafe_child_by_name(node, "body")
            p._name = unsafe_child_text(node, "name")
            type_parameters_node = node.child_by_field_name("type_parameters")
            if type_parameters_node:
                p.type_parameters = [
                    unsafe_text(type_parameter)
                    for type_parameter in type_parameters_node.named_children
                ]
            else:
                p.type_parameters = []
        except (NoSuchChild, NoText):
            return None
        item_nodes: list[RustNode] = body_node.named_children  # type: ignore
        for item in RustExtracter().extract(item_nodes):
            if not isinstance(item, RustField):
                logger.warning(f"unexpected item in struct: {item.text}")
                continue
            p.add(item)  # type: ignore
        return p

    def empty_copy(self) -> Self:
        p = super().empty_copy()
        p.type_parameters = list(self.type_parameters)
        return p

    @property
    def _header(self):
        type_parameters = (
            f"<{', '.join(self.type_parameters)}>" if self.type_parameters else ""
        )
        return f"struct {self._name}{type_parameters} {{\n    "

    @property
    def _tail(self):
        return "\n}"

    @property
    def _sep(self):
        return ",\n    "


class RustMacro(RustSimplePiece):
    rules: list[tuple[str, str]]

    @classmethod
    def create(
        cls: type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Self | None:
        p = super().create(node, attr_nodes, comment_nodes)
        if p is None:
            return None
        try:
            p.rules = []
            for rule in node.named_children:
                if rule.type != "macro_rule":
                    continue
                p.rules.append(
                    (unsafe_child_text(rule, "left"), unsafe_child_text(rule, "right"))
                )

        except (NoSuchChild, NoText):
            return None
        return p

    def copy(self) -> Self:
        p = super().copy()
        p.rules = list(self.rules)
        return p

    @property
    def summary(self) -> str:
        text = f"macro_rules! {self._name} {{\n"
        for l, _ in self.rules:
            text += f"    {l} => {{ // omitted }}"
        text += "\n}"
        return text


class RustFn(RustSimplePiece):
    signature: str  # parameter types is included here
    parameter_types: list[str]
    return_type: str
    type_parameter_kinds: list[
        str
    ]  # not parameter types, but their kinds: lifetime, type, const, etc.

    @classmethod
    def create(
        cls: type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Self | None:

        p = super().create(node, attr_nodes, comment_nodes)
        if p is None:
            return None
        try:
            p.signature = unsafe_text(node).replace(unsafe_child_text(node, "body"), "")
            p.parameter_types = []
            for param in unsafe_child_by_name(node, "parameters").named_children:
                if param.type == "self_parameter":
                    p.parameter_types.append(unsafe_text(param))
                else:
                    p.parameter_types.append(unsafe_child_text(param, "type"))
            return_type_node = node.child_by_field_name("return_type")
            if return_type_node:
                p.return_type = unsafe_text(return_type_node)
            else:
                p.return_type = "()"
            type_parameters_node = node.child_by_field_name("type_parameters")
            if type_parameters_node:
                p.type_parameter_kinds = [
                    type_parameter.type
                    for type_parameter in type_parameters_node.named_children
                ]
            else:
                p.type_parameter_kinds = []
        except (NoSuchChild, NoText):
            return None
        return p

    def copy(self) -> Self:
        p = super().copy()
        p.signature = self.signature
        p.parameter_types = list(self.parameter_types)
        p.return_type = self.return_type
        p.type_parameter_kinds = list(self.type_parameter_kinds)
        return p

    @property
    def summary(self) -> str:
        return self.signature + ";"

    def interface_equal(self, other: "RustPiece") -> bool:
        return isinstance(other, RustFn) and (
            self._name == other._name
            and self.parameter_types == other.parameter_types
            and self.return_type == other.return_type
            and self.type_parameter_kinds == other.type_parameter_kinds
        )


class RustEnumVariant(RustSimplePiece):
    pass


class RustEnum(RustExtendable[RustEnumVariant]):
    type_parameters: list[str]

    @classmethod
    def create(
        cls: type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Self | None:

        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None
        try:

            body_node = unsafe_child_by_name(node, "body")
            p._name = unsafe_child_text(node, "name")
            type_parameters_node = node.child_by_field_name("type_parameters")
            if type_parameters_node:
                p.type_parameters = [
                    unsafe_text(type_parameter)
                    for type_parameter in type_parameters_node.named_children
                ]
            else:
                p.type_parameters = []
        except (NoSuchChild, NoText):
            return None
        item_nodes: list[RustNode] = body_node.named_children  # type: ignore
        for item in RustExtracter().extract(item_nodes):
            if not isinstance(item, RustEnumVariant):
                logger.warning(f"unexpected item in enum: {item.text}")
                continue
            p.add(item)  # type: ignore
        return p

    def empty_copy(self) -> Self:
        p = super().empty_copy()
        p.type_parameters = list(self.type_parameters)
        return p

    @property
    def _header(self):
        type_parameters = (
            f"<{', '.join(self.type_parameters)}>" if self.type_parameters else ""
        )
        return f"enum {self._name}{type_parameters} {{\n    "

    @property
    def _tail(self):
        return "\n}"

    @property
    def _sep(self):
        return ",\n    "


class RustType(RustSimplePiece):
    pass


class RustFnSignature(RustSimplePiece):
    pass


class RustAssociatedType(RustSimplePiece):
    pass


ImplContent = RustFn | RustConst | RustType


class RustImpl(RustSplittable[ImplContent]):

    type_name: str
    type_parameters: list[str]  # for impl block
    type_arguments: list[str]  # for the struct type

    @classmethod
    def create(
        cls: type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Self | None:
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None

        try:
            body_node = unsafe_child_by_name(node, "body")

            type_parameters_node = node.child_by_field_name("type_parameters")
            if type_parameters_node:
                p.type_parameters = [
                    unsafe_text(type_parameter)
                    for type_parameter in type_parameters_node.named_children
                ]
            else:
                p.type_parameters = []
            type_node = unsafe_child_by_name(node, "type")
            if type_node.type == "generic_type":
                type_arguments_node = unsafe_child_by_name(type_node, "type_arguments")
                p.type_arguments = [
                    unsafe_text(type_argument)
                    for type_argument in type_arguments_node.named_children
                ]
                p.type_name = unsafe_child_text(type_node, "type")
            elif type_node.type == "type_identifier":
                p.type_name = unsafe_text(type_node)
                p.type_arguments = []
            else:
                logger.warning(f"unexpected type in impl: {type_node.type}")
                p.type_name = unsafe_text(type_node)
                p.type_arguments = []
            p._name = f"impl {p.type_name}"
        except (NoSuchChild, NoText):
            return None
        item_nodes: list[RustNode] = body_node.named_children  # type: ignore
        for item in RustExtracter().extract(item_nodes):
            if not isinstance(item, ImplContent):
                logger.warning(f"unexpected item in impl: {item.text}")
                continue
            p.add(item)  # type: ignore
        return p

    def empty_copy(self) -> Self:
        p = super().empty_copy()
        p.type_name = self.type_name
        p.type_parameters = list(self.type_parameters)
        p.type_arguments = list(self.type_arguments)
        return p

    @property
    def _header(self):
        type_paramters = (
            f"<{', '.join(self.type_parameters)}>" if self.type_parameters else ""
        )
        type_arguments = (
            f"<{', '.join(self.type_arguments)}>" if self.type_arguments else ""
        )
        return f"impl{type_paramters} {self.type_name}{type_arguments} {{\n    "

    @property
    def _tail(self):
        return "\n}"

    @property
    def _sep(self):
        return "\n    "


TraitContent = RustFnSignature | RustAssociatedType | RustConst | RustFn


class RustTrait(RustExtendable[TraitContent]):
    trait_name: str

    @classmethod
    def create(
        cls: type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Self | None:

        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None

        try:

            body_node = unsafe_child_by_name(node, "body")

            p.trait_name = unsafe_child_text(node, "name")
            p._name = p.trait_name
        except (NoSuchChild, NoText):
            return None
        item_nodes: list[RustNode] = body_node.named_children  # type: ignore
        for item in RustExtracter().extract(item_nodes):
            if not isinstance(item, ImplContent):
                logger.warning(f"unexpected item in trait: {item.text}")
                continue
            p.add(item)  # type: ignore
        return p

    def empty_copy(self) -> Self:
        p = super().empty_copy()
        p.trait_name = self.trait_name
        return p

    @property
    def _header(self):
        return f"trait {self.trait_name} {{\n    "

    @property
    def _tail(self):
        return "\n}"

    @property
    def _sep(self):
        return "\n    "


class RustImplTrait(RustImpl):
    trait_name: str
    trait_arguments: list[str]

    @classmethod
    def create(
        cls: type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Self | None:

        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None

        try:
            trait_node = unsafe_child_by_name(node, "trait")
            if trait_node.type == "generic_type":
                type_arguments_node = unsafe_child_by_name(trait_node, "type_arguments")
                p.trait_arguments = [
                    unsafe_text(type_argument)
                    for type_argument in type_arguments_node.named_children
                ]
                p.trait_name = unsafe_child_text(trait_node, "type")
            elif trait_node.type == "type_identifier":
                p.trait_name = unsafe_text(trait_node)
                p.trait_arguments = []
            else:
                logger.warning(f"unexpected trait in impl: {trait_node.type}")
                p.trait_name = unsafe_text(trait_node)
                p.trait_arguments = []

            p._name = f"impl {p.trait_name} for {p.type_name}"
        except (NoSuchChild, NoText):
            return None

        return p

    def empty_copy(self):
        p = super().empty_copy()
        p.trait_name = self.trait_name
        p.trait_arguments = list(self.trait_arguments)
        return p

    @property
    def _header(self):
        type_parameters = (
            f"<{', '.join(self.type_parameters)}>" if self.type_parameters else ""
        )
        type_arguments = (
            f"<{', '.join(self.type_arguments)}>" if self.type_arguments else ""
        )
        trait_arguments = (
            f"<{', '.join(self.trait_arguments)}>" if self.trait_arguments else ""
        )
        return f"impl{type_parameters} {self.trait_name}{trait_arguments} for {self.type_name}{type_arguments} {{\n    "

    @property
    def _tail(self):
        return "\n}"

    @property
    def _sep(self):
        return "\n    "


class RustExtracter(Extracter[RustPiece, RustNode]):
    extract_rules: Mapping[type[RustPiece], list[str] | Callable[[RustNode], bool]] = {
        RustImpl: lambda n: n.type == "impl_item"
        and (n.child_by_field_name("trait") is None),
        RustImplTrait: lambda n: n.type == "impl_item"
        and (n.child_by_field_name("trait") is not None),
        RustStatic: ["static_item"],
        RustConst: ["const_item"],
        RustStruct: ["struct_item"],
        RustField: ["field_declaration"],
        RustEnumVariant: ["enum_variant"],
        RustMacro: ["macro_definition"],
        RustFn: ["function_item"],
        RustEnum: ["enum_item"],
        RustType: ["type_item"],
        RustUse: ["use_declaration"],
        RustAssociatedType: ["associated_type"],
        RustFnSignature: ["function_signature_item"],
        RustTrait: ["trait_item"],
    }

    def is_attribute(self, node: RustNode) -> bool:
        return node.type in ("attribute_item", "inner_attribute_item")

    def is_comment(self, node: RustNode) -> bool:
        return node.type in ("block_comment", "line_comment")


def sort_rust_pieces(pieces: Iterable[RustPiece]) -> list[RustPiece]:
    order: list[type[RustPiece]] = [
        RustUse,
        RustMacro,
        RustStatic,
        RustConst,
        RustEnum,
        RustStruct,
        RustImpl,
    ]

    def key(p: RustPiece) -> int:
        try:
            return order.index(type(p))
        except ValueError:
            return len(order)

    return sorted(pieces, key=key)


LOCAL_CRATES = ["std", "core", "alloc", "proc_macro", "test"]


class RustCode(RustSplittable[RustPiece]):

    use_decls: dict[str, RustUseId]

    @classmethod
    def create(
        cls: type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Self | None:

        p = super().create(node, [], [])
        if not p:
            return None
        p._name = ""
        toplevels: list[RustNode] = node.children  # type: ignore
        for item in RustExtracter().extract(toplevels):
            p.add(item)
        return p

    def __init__(self):
        super().__init__()
        self.use_decls = {}

    def add(self, item: RustPiece):
        if isinstance(item, RustUse):
            names = item.decl_names()
            for name in names:
                if name in self.use_decls:
                    self.use_decls[name].remove_from_parent()
                self.remove_by_name(name)

            self.use_decls |= names

        return super().add(item)

    @property
    def items(self) -> list[RustPiece]:
        """
        Returns: sorted items of the whole code."""
        return sort_rust_pieces(super().items)

    @property
    def _sep(self):
        return "\n\n"

    def merge_in(self, other: "RustCode") -> list[RustPiece]:
        """
        This method will another RustCode and its pieces themselves in to this RustCode
        """
        popped = []
        for item in other.items:
            popped += self.add(item)
        return popped

    def piece_ref_ranges(self) -> list[tuple[RustPieceRef, int, int]]:
        ranges: list[tuple[RustPieceRef, int, int]] = []  # both inclusive, 1-based
        start_line = 1
        for piece_ref, text in self.walk():
            end_line = start_line + text.count("\n")
            # if text contains only white spaces, ';', ','
            if text.strip(" \t\n,;{}"):
                ranges.append((piece_ref, start_line, end_line))
            start_line = end_line
        return ranges

    @staticmethod
    def from_text(text: str) -> "RustCode":
        return RustCode.create(parse_rust(text).root_node, [], [])  # type: ignore

    def normalize(self) -> None:
        for item in self.items:
            if isinstance(item, RustUse) and len(item.path) and item.path[0] == "crate":
                self.remove(item)
