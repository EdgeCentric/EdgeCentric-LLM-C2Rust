import tree_sitter_rust as tsrust
from tree_sitter import Language, Parser, Tree


def grammar_correct(rust_code: str) -> bool:
    RUST_LANGUAGE = Language(tsrust.language())
    parser = Parser(RUST_LANGUAGE)
    tree = parser.parse(rust_code.encode(), encoding="utf8")
    return not tree.root_node.has_error


def parse_rust(rust_code: str) -> Tree:
    RUST_LANGUAGE = Language(tsrust.language())
    parser = Parser(RUST_LANGUAGE)
    tree = parser.parse(rust_code.encode(), encoding="utf8")
    return tree
