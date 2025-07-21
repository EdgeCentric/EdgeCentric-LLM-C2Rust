import logging
from typing import Callable, Dict, List, Mapping, Optional, Self, Sequence, Set, Type

from tree_sitter import Node

from llm_c2rust.analyzer.utils import (
    NoSuchChild,
    NoText,
    unsafe_child_by_name,
    unsafe_child_text,
    unsafe_declarator_name,
)

from llm_c2rust.parser.cpp_parser import parse_cpp

from .utils import CNode, CPiece, Extracter


import logging

logger: logging.Logger = logging.getLogger(__name__)


class CNamed(CPiece):
    _name: str

    @property
    def name(self) -> str:
        return self._name


class CSimpleNamed(CNamed):
    @classmethod
    def create(
        cls: Type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Optional[Self]:
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None
        try:
            p._name = unsafe_child_text(node, "name")
        except NoSuchChild:
            return None
        return p


class CDeclaratorNamed(CNamed):
    @classmethod
    def create(
        cls: Type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Optional[Self]:
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None
        try:
            declarator = unsafe_child_by_name(node, "declarator")
            p._name = unsafe_declarator_name(declarator)
        except NoSuchChild:
            return None
        return p


def get_body(type_node: Node):

    type_kind_str = type_node.type.split("_")[0]
    type_kind = {
        "enum": CEnum,
        "union": CUnion,
        "struct": CStruct,
        "class": CClass,
    }.get(type_kind_str)
    body_piece = None
    if (
        type_node.child_by_field_name("body") and type_kind
    ):  # both struct and enum have body
        body_piece = type_kind.create(type_node, [], [])
    return body_piece


class CTypedef(CDeclaratorNamed):
    body_piece: Optional["CTypeDefinition"]

    @classmethod
    def create(
        cls: Type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Optional[Self]:
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None

        try:
            type_node = unsafe_child_by_name(node, "type")
            p.body_piece = get_body(type_node)
        except (NoSuchChild, NoText):
            return None
        return p


class CUsing(CSimpleNamed):

    body_piece: Optional["CTypeDefinition"]

    @classmethod
    def create(
        cls: Type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Optional[Self]:
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None
        try:
            type_node = unsafe_child_by_name(node, "type")
            type_node = unsafe_child_by_name(type_node, "type")
            p.body_piece = get_body(type_node)
        except (NoSuchChild, NoText):
            return None
        return p


class CMultipleDeclarators(CPiece):
    names: List[str]

    @classmethod
    def create(
        cls: Type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Optional[Self]:
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None
        declarators = node.children_by_field_name("declarator")
        p.names = []
        for d in declarators:
            try:
                d_name = unsafe_declarator_name(d)
            except (NoSuchChild, NoText):
                continue
            p.names.append(d_name)
        return p


class CMultipleTypedef(CMultipleDeclarators):
    body_piece: Optional["CTypeDefinition"]

    @classmethod
    def create(
        cls: Type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Optional[Self]:
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None
        p.body_piece = None
        try:
            type_node = unsafe_child_by_name(node, "type")
            p.body_piece = get_body(type_node)

        except (NoSuchChild, NoText):
            return None

        return p


# macro matches constants
class CMacro(CSimpleNamed):
    value: Optional[str]

    @classmethod
    def create(
        cls: Type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Optional[Self]:
        p = super().create(node, attr_nodes, comment_nodes)
        # extract some useful message
        if not p:
            return None
        try:
            p.value = unsafe_child_text(node, "value")
        except (NoSuchChild, NoText):
            p.value = None
        return p


class CMacroFun(CSimpleNamed):
    pass


class CDeclaration(CDeclaratorNamed):

    is_function: bool
    has_init: bool

    @classmethod
    def create(
        cls: Type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Optional[Self]:
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None
        try:
            declarator = unsafe_child_by_name(node, "declarator")
            p.has_init = declarator.type == "init_declarator"
            p.is_function = declarator.type == "function_declarator"
        except (NoSuchChild, NoText):
            return None
        return p


class CMultipleDeclaration(CMultipleDeclarators):

    has_inits: Dict[str, bool]
    is_funcs: Dict[str, bool]

    @classmethod
    def create(
        cls: Type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Optional[Self]:
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None

        declarators = node.children_by_field_name("declarator")
        p.is_funcs = {}
        p.has_inits = {}
        for d in declarators:
            try:
                d_name = unsafe_declarator_name(d)
            except (NoSuchChild, NoText):
                continue
            p.has_inits[d_name] = d.type == "init_declarator"
            p.is_funcs[d_name] = d.type == "function_declarator"

        return p


class CFunction(CDeclaratorNamed):
    pass


class CEmptyPiece(CPiece):
    pass


class CTypeDefinition(CPiece):
    _name: Optional[str]
    # full_name: Optional[str]

    @property
    def name(self) -> Optional[str]:
        return self._name

    @classmethod
    def create(
        cls: Type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Optional[Self]:
        if cls == CTypeDefinition:
            raise NotImplementedError("TypeDefinition is an abstract class")
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None
        try:
            p._name = unsafe_child_text(node, "name")
        except (NoSuchChild, NoText):
            p._name = None
        return p


class CUnion(CTypeDefinition):
    pass


class CStruct(CTypeDefinition):
    pass


class CEnum(CTypeDefinition):
    enumerator_names: Set[str]

    @classmethod
    def create(
        cls: Type[Self],
        node: Node,
        attr_nodes: Sequence[Node],
        comment_nodes: Sequence[Node],
    ) -> Optional[Self]:
        p = super().create(node, attr_nodes, comment_nodes)
        if not p:
            return None

        p.enumerator_names = set()
        body_node = node.child_by_field_name("body")
        if body_node is None:
            return
        for item in body_node.children:
            if item.type != "enumerator":
                continue
            try:
                enumerator_name = unsafe_child_text(item, "name")
            except (NoSuchChild, NoText):
                continue
            p.enumerator_names.add(enumerator_name)
        return p


class CClass(CTypeDefinition):
    pass


def empty_expr_pred(node: Node) -> bool:
    if node.type == ";":
        return True
    if node.type == "expression_statement":
        first_child = node.child(0)
        if first_child and first_child.type == ";":
            return True
    return False


class CExtracter(Extracter[CPiece, CNode]):
    extract_rules: Mapping[Type[CPiece], List[str] | Callable] = {
        CTypedef: lambda n: (
            n.type == "type_definition"
            and len(n.children_by_field_name("declarator")) == 1
        ),
        CUsing: ["alias_declaration"],
        CMultipleTypedef: lambda n: n.type == "type_definition"
        and len(n.children_by_field_name("declarator")) > 1,
        CMacro: ["preproc_def"],
        CMacroFun: ["preproc_function_def"],
        CDeclaration: lambda n: n.type == "declaration"
        and len(n.children_by_field_name("declarator")) == 1,
        CMultipleDeclaration: lambda n: n.type == "declaration"
        and len(n.children_by_field_name("declarator")) > 1,
        CFunction: ["function_definition"],
        CUnion: ["union_specifier"],
        CStruct: ["struct_specifier"],
        CEnum: ["enum_specifier"],
        CClass: ["class_specifier"],
    }


def c_pieces_of_text(text: str) -> Sequence[CPiece]:

    nodes: List[CNode] = parse_cpp(text).root_node.children  # type: ignore
    return list(CExtracter().extract(nodes))
