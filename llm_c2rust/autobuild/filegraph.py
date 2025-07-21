import glob
import logging
import os
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from tree_sitter import Node

from llm_c2rust.parser.constants import (
    C_HEADERS,
    C_SUFFIXES,
    CPP_HEADERS,
    CPP_SUFFIXES,
)
from llm_c2rust.parser.cpp_parser import parse_cpp

import logging

logger: logging.Logger = logging.getLogger(__name__)


def common_suffix_length(s1: str, s2: str) -> int:
    """caculate the common suffix length of two strings
    :param s1: left string
    :type s1: str
    :param s2: right string
    :type s2: str
    :return: common suffix length
    :rtype: int
    """

    length = 0

    for c1, c2 in zip(reversed(s1), reversed(s2)):
        if c1 == c2:
            length += 1
        else:
            break

    return length


class CppFileNode:
    def __init__(
        self,
        path: str,
        ftype: Literal["Header", "Source"],
        language: Literal["c", "cpp", "unknown"],
    ) -> None:
        self.path: str = path
        self.ftype: Literal["Header", "Source"] = ftype
        self.language: Literal["c", "cpp", "unknown"] = language

        self.includes: List[Tuple["CppFileNode", Optional[str]]] = []
        self.has_main: bool = False

    def __eq__(self, other: object) -> bool:
        if other is None:
            return False
        if not isinstance(other, CppFileNode):
            raise NotImplementedError(f"Invalid comparison with type {type(other)}")
        return self.path == other.path

    def __hash__(self) -> int:
        return hash((self.path, self.ftype))

    def __repr__(self) -> str:
        return f"CppFileNode(path='{self.path}', ftype='{self.ftype}', lang='{self.language}', has_main='{self.has_main}')"


class CppFileGraph(object):
    def __init__(self, project_path: str) -> None:
        self.project_path: str = project_path
        self.files: List[CppFileNode] = self.collect_files(project_path=project_path)

        for filenode in self.files:
            filedir = os.path.dirname(filenode.path)
            includes = self.collect_single_file_includes(file_path=filenode.path)
            for each_include, include_type in includes:
                resolved_include = self.resolve_include(each_include)
                if resolved_include is None:
                    continue

                if include_type == "rel" and os.path.exists(
                    os.path.join(self.project_path, filedir, each_include)
                ):
                    path_dir = None
                else:

                    path_dir: Optional[str] = os.path.dirname(resolved_include.path)
                    while each_include in path_dir:
                        path_dir = os.path.dirname(path_dir)
                    if len(path_dir.strip()) == 0:
                        path_dir = None

                    if include_type == "abs" and path_dir is None:
                        path_dir = os.path.normpath(filedir)

                filenode.includes.append((resolved_include, path_dir))

    def collect_files(self, project_path: str) -> List[CppFileNode]:
        files = set()
        headers_pattern = list(set(C_HEADERS + CPP_HEADERS))
        source_pattern = list(set(C_SUFFIXES + CPP_SUFFIXES))
        for header in headers_pattern:
            header_files = glob.glob(
                os.path.join("**", f"*{header}"), recursive=True, root_dir=project_path
            )
            for each_header in header_files:
                file_suffix = Path(each_header).suffix
                if file_suffix in C_HEADERS and file_suffix in CPP_HEADERS:
                    lang = "unknown"
                elif file_suffix in CPP_HEADERS:
                    lang = "cpp"
                elif file_suffix in C_HEADERS:
                    lang = "c"
                else:
                    lang = "unknown"
                filenode = CppFileNode(
                    path=os.path.normpath(each_header), ftype="Header", language=lang
                )
                if filenode not in files:
                    files.add(filenode)

        for source in source_pattern:
            source_files = glob.glob(
                os.path.join("**", f"*{source}"), recursive=True, root_dir=project_path
            )
            for each_source in source_files:
                file_suffix = Path(each_source).suffix
                if file_suffix in C_SUFFIXES and file_suffix in CPP_SUFFIXES:
                    lang = "unknown"
                elif file_suffix in C_SUFFIXES:
                    lang = "c"
                elif file_suffix in CPP_SUFFIXES:
                    lang = "cpp"
                else:
                    lang = "unknown"
                filenode = CppFileNode(
                    path=os.path.normpath(each_source), ftype="Source", language=lang
                )
                if self.has_main_function(file_path=each_source):
                    filenode.has_main = True
                if filenode not in files:
                    files.add(filenode)
        return list(files)

    def has_main_function(self, file_path: str) -> bool:
        # Parse the file using parse_cpp to get the root of the Tree-sitter syntax tree
        try:
            with open(
                os.path.join(self.project_path, file_path), "r", encoding="utf-8"
            ) as f:
                code = f.read()
            tree = parse_cpp(code)
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return False

        def traverse_function_definition(node: Node) -> bool:
            out = False
            for child in node.children:
                if (
                    child.text is not None
                    and child.type == "identifier"
                    and child.text.decode("utf-8") == "main"
                ):
                    return True
                else:
                    out |= traverse_function_definition(child)
                    if out:
                        return out
            return out

        def traverse_node(node: Node) -> bool:
            if node.type == "function_definition":

                return traverse_function_definition(node)
            out = False
            for child in node.children:
                out |= traverse_node(child)
                if out:
                    return out
            return out

        return traverse_node(tree.root_node)

    def collect_single_file_includes(
        self, file_path: str
    ) -> List[Tuple[str, Literal["abs", "rel"]]]:
        """
        Parses a single file and returns a list of file paths included by the file using the Tree-sitter AST.
        Assumes the file is a C or C++ source or header file.
        """
        # Parse the file using parse_cpp to get the root of the Tree-sitter syntax tree
        try:
            with open(
                os.path.join(self.project_path, file_path), "r", encoding="utf-8"
            ) as f:
                code = f.read()
            tree = parse_cpp(code)
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return []

        # Initialize an empty list to store the include paths
        includes: List[Tuple[str, Literal["abs", "rel"]]] = []

        # Traverse the syntax tree to find include directives (usually represented by a specific node type)
        def traverse_node(node: Node):
            # Check if the current node is an 'include' directive
            if (
                node.text is not None and node.type == "preproc_include"
            ):  # Assuming 'preproc_include' represents #include directives
                include_text = node.text.decode("utf-8").strip()

                # Extract the file path from the include directive
                # Include directive format: #include "file.h" or #include <file.h>
                if include_text.startswith("#include"):
                    # Get the file path within quotes or angle brackets
                    start = (
                        include_text.find('"')
                        if '"' in include_text
                        else include_text.find("<")
                    )
                    end = (
                        include_text.find('"', start + 1)
                        if '"' in include_text
                        else include_text.find(">", start + 1)
                    )
                    if start != -1 and end != -1:
                        if '"' in include_text:
                            include_type = "rel"
                        else:
                            include_type = "abs"
                        include_file = include_text[start + 1 : end]
                        includes.append((include_file, include_type))

            # Recursively traverse child nodes
            for child in node.children:
                traverse_node(child)

        # Start traversing the root node
        traverse_node(tree.root_node)

        return includes

    def resolve_include(self, include_str: str) -> Optional[CppFileNode]:
        candidates: List[Tuple[CppFileNode, int]] = []
        for filenode in self.files:
            if filenode.path.endswith(os.path.normpath(include_str)):
                candidates.append(
                    (filenode, common_suffix_length(filenode.path, include_str))
                )

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[1], reverse=True)

        return candidates[0][0]
