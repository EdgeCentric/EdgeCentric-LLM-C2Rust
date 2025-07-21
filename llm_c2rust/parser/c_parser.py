
import re
from typing import List, Tuple
import os

import tree_sitter_c as tsc
from tree_sitter import Language, Parser, Node, Tree
from .tree_sitter_utils import has_error

def check_grammar(c_code: str) -> bool:
    """
    Check if the provided C code has syntax errors using the tree-sitter C parser.

    :param c_code: The C code to be checked for grammar errors.
    :type c_code: str

    :return: True if there are syntax errors in the code, False otherwise.
    :rtype: bool
    """
    C_LANGUAGE = Language(tsc.language())
    parser = Parser(C_LANGUAGE)
    tree = parser.parse(c_code.encode(), encoding="utf8")
    return has_error(tree.root_node)

def parse_c(c_code: str) -> Tree:
    """
    Parse the provided C code into an abstract syntax tree (AST).

    :param c_code: The C code to be parsed.
    :type c_code: str

    :return: The abstract syntax tree representing the parsed C code.
    :rtype: Tree
    """
    C_LANGUAGE = Language(tsc.language())
    parser = Parser(C_LANGUAGE)
    tree = parser.parse(c_code.encode(), encoding="utf8")
    return tree
