#!/bin/env python3

import functools
import json
import logging
import os
import re
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path


from llm_c2rust.codeql.codeql_database import CodeqlDatabase
from llm_c2rust.utils.constants import RESOURCES_DIR

from llm_c2rust.utils.hash import calculate_md5

from .code_segment import CodeSegment, CodeSegmentPool

logger: logging.Logger = logging.getLogger(__name__)

C_SUFFIXES = [".c"]
CPP_SUFFIXES = [".cpp", ".cc", ".cxx"]
CLANG_INCLUDE_PATHS = [
    "/usr/include",
    "/usr/local/include",
    "/usr/include/bits/types",
    "/usr/include/gnu",
    "/usr/include/bits",
    "/usr/lib/clang/19/include",
    "/usr/include/sys",
    "/usr/include/asm",
    "/usr/lib/gcc/x86_64-pc-linux-gnu/15.1.1/include",
    "/usr/include/linux",
    "/usr/include/asm-generic",
]
from .builtin_macros import BUILTIN_MACROS


def inside_project(path: Path | str, project_path: Path | str) -> bool:
    if isinstance(path, Path):
        path = str(path)
    if isinstance(project_path, Path):
        project_path = str(project_path)
    path = path.lstrip()
    return path.startswith(project_path.lstrip())


def filter_file(source_file: str) -> bool:

    if "CMakeScratch/TryCompile" in source_file:
        return False
    if "CompilerIdC/" in source_file:
        return False
    if "lib/" in source_file:
        return False
    return True


class Segmenter(ABC):
    @functools.cache
    @abstractmethod
    def segment(self) -> list[CodeSegment]:
        """
        Returns:
            list[CodeChunk]: the code chunks in topological order.
        """
        raise NotImplementedError("segment method is not implemented")


class SemanticSegmenter(Segmenter):

    def __init__(self, codeql_database: CodeqlDatabase, config: list[str] = []):
        project_hash = calculate_md5(os.path.abspath(codeql_database.project_path))
        self.codeql_database: CodeqlDatabase = codeql_database
        self.segments_pool: CodeSegmentPool = CodeSegmentPool(
            namespace=f"CodeSlice-{project_hash}"
        )
        self.c_files: set[str] = set()
        self.cpp_files: set[str] = set()
        self.include_files: set[str] = set()
        self.main_files: set[str] = set()
        self.files: set[str] = set()
        self.include_paths: set[str] = set()
        self.config_macros = []
        for macro in config:
            macro = macro.split("=", 1)
            if len(macro) == 1:
                self.config_macros.append((macro[0], ""))
            else:
                self.config_macros.append((macro[0], macro[1]))

    def _load_include_files(self, path: str | Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            self.include_files = {
                p
                for p, in json.load(f)["#select"]["tuples"]
                if inside_project(p, self.codeql_database.project_path)
                and filter_file(p)
            }

    def _load_include_path(self, path: str | Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            for file, include_path in json.load(f)["#select"]["tuples"]:

                # ignore clang default include paths
                if include_path in CLANG_INCLUDE_PATHS:
                    continue
                self.include_paths.add(include_path)

    def _load_macros(self, path: str | Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            for name, loc, value in json.load(f)["#select"]["tuples"]:
                m = re.match(r"file://(.*):(.*):.*:(.*):.*", loc)
                if m is None:
                    continue

                # if the macro locates in file://:0:0:0:0, it may be a config macro
                if m[1] == "":
                    if name == "" or name in BUILTIN_MACROS:
                        continue
                    self.config_macros.append((name, value))
                if m[1] not in self.files:
                    continue
                file = m[1]
                start_line = int(m[2])
                end_line = int(m[3])

                code = CodeSegment(
                    pool=None, file=file, start_line=start_line, end_line=end_line
                )
                code.decls.append(("Macro", name))
                self.segments_pool.add_segment(code)

    def _load_source_files(self, path: str | Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            for file, type in json.load(f)["#select"]["tuples"]:
                if not inside_project(file, self.codeql_database.project_path):
                    continue
                if not filter_file(file):
                    continue
                if type == "CFile":
                    self.c_files.add(file)
                elif type == "CppFile":
                    self.cpp_files.add(file)
                else:
                    logger.warning(f"{file} is not a C or Cpp file, but {type}")

    def _load_defintions(self, path: str | Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            for type, loc, name in json.load(f)["#select"]["tuples"]:
                m = re.match(r"file://(.*):(.*):.*:(.*):.*", loc)
                if m is None:
                    continue
                file = m[1]
                start_line = int(m[2])
                end_line = int(m[3])
                if not m[1] in self.files:
                    continue
                code = self.segments_pool.find_code_slice(file, start_line, end_line)
                if name == "main":
                    self.main_files.add(file)
                    if code:
                        code.has_main = True
                if code is not None:
                    code.decls.append((type, name))
                else:
                    logger.warning(
                        f"{type} @ {file}:{start_line}-{end_line} is not covered by any code slices"
                    )

    def _load_dependency(self, results_path: Path) -> None:

        code_slices = self.segments_pool
        dependencies = set()
        for file in results_path.glob("*.json"):
            with open(file, "r", encoding="utf-8") as f:
                dependencies.update(tuple(t) for t in json.load(f)["#select"]["tuples"])

        for depender, dependee in dependencies:
            mer = re.match(r"file://(.*):(.*):.*:(.*):.*", depender)
            mee = re.match(r"file://(.*):(.*):.*:(.*):.*", dependee)
            if mer is None or mee is None:
                continue
            if mer[1] not in self.files:
                continue
            if mee[1] not in self.files:
                continue

            depender = code_slices.find_code_slice(mer[1], int(mer[2]), int(mer[3]))
            dependee = code_slices.find_code_slice(mee[1], int(mee[2]), int(mee[3]))

            if depender is None:
                logger.warning(
                    f"{mer[1]}:{mer[2]}-{mer[3]} is not covered by any top level code slices"
                )
                continue

            if dependee is None:
                logger.warning(
                    f"{mee[1]}:{mee[2]}-{mee[3]} is not covered by any top level code slices"
                )
                continue
            if (
                dependee.file in self.main_files
                and depender.file in self.main_files
                and dependee.file != depender.file
            ):
                logger.debug(
                    f"{depender.loc} depends on {dependee.loc}, but they are in different main files."
                )
                continue

            depender.use_symbol_in(dependee)

    @functools.cache
    def segment(self) -> list[CodeSegment]:
        """
        Args:
            results_path (Optional[str]):
            max_size (int): the maximum size for each chunk's size plus its dependencies' sizes.
            size_calc (Callable[[str], int]): a function to calculate the size of a string.
        Returns:
            list[CodeChunk]: the code chunks in topological order.

        """

        temp_dir = tempfile.TemporaryDirectory()
        query_results_path = Path(temp_dir.name)

        logger.info(f"query results will be saved in {query_results_path.name}")
        meta_results = query_results_path / "meta"
        dependency_results = query_results_path / "dependency"
        os.makedirs(meta_results, exist_ok=True)
        os.makedirs(dependency_results, exist_ok=True)

        self.codeql_database.run_queries(
            queries_path=os.path.join(RESOURCES_DIR, "ql/meta")
        )
        self.codeql_database.decode_results(
            queries_path=os.path.join(RESOURCES_DIR, "ql/meta"),
            pack="meta",
            query_results_path=meta_results,
        )
        self._collect_metadata(meta_results)

        self.codeql_database.run_queries(
            queries_path=os.path.join(RESOURCES_DIR, "ql/dependency")
        )
        self.codeql_database.decode_results(
            queries_path=os.path.join(RESOURCES_DIR, "ql/dependency"),
            pack="dependency",
            query_results_path=dependency_results,
        )
        self._load_dependency(dependency_results)

        self.segments_pool.seal()

        return list(self.segments_pool.all_segments())

    def _load_files(self, query_results_path: Path):
        # collect result files
        self._load_include_files(query_results_path / "include.json")
        self._load_source_files(query_results_path / "source_files.json")
        self.files = self.c_files | self.cpp_files | self.include_files

    def _load_segments(self):
        for file in self.c_files | self.cpp_files:
            self.getTopLevelSegments(file)

    def _collect_metadata(self, query_results_path: Path):
        # collect result files
        self._load_files(query_results_path)
        self._load_include_path(query_results_path / "include_path.json")
        self._load_macros(query_results_path / "macro.json")
        self._load_segments()
        self._load_defintions(query_results_path / "definition.json")

    def getTopLevelSegments(self, filepath: str):
        logger.info(f"segmenting {filepath}")
        if filepath in self.cpp_files:
            compiler = "clang++"
        elif filepath in self.c_files:
            compiler = "clang"
        else:
            raise ValueError("Cannot determine C or Cpp: " + filepath)

        def get_ast(extra_args: list[str] = []) -> dict | None:
            nonlocal compiler, self, filepath
            commands = (
                [
                    compiler,
                    "-Xclang",
                    "-ast-dump=json",
                    "-fsyntax-only",
                    "-fparse-all-comments",
                    "-w",
                    filepath,
                ]
                + ["-I" + path for path in self.include_paths]
                + [f"-D{macro}={value}" for macro, value in self.config_macros]
                + extra_args
            )
            logger.info(" ".join(commands))
            subprocess_result = subprocess.run(
                commands,
                text=True,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            if (
                subprocess_result.returncode != 0
                and subprocess_result.stderr is not None
            ):
                logger.error(subprocess_result.stderr)
                return None
            return json.loads(subprocess_result.stdout)

        if ast := get_ast():
            pass
        elif ast := get_ast(["-std=c99", "-D_GNU_SOURCE"]):
            pass
        else:
            logger.error(f"Failed to get AST for {filepath}")
            return
        # file property is shared through out the ast, so we need to keep track of the real file

        codes = []

        def iterate(entities, file):
            nonlocal codes

            for entity in entities:
                if len(entity["loc"]) == 0:
                    continue
                if "expansionLoc" in entity["loc"]:
                    loc = entity["loc"]["expansionLoc"]
                    if "file" in entity["loc"]["spellingLoc"]:
                        file = entity["loc"]["spellingLoc"]["file"]
                    if "file" in entity["loc"]["expansionLoc"]:
                        file = entity["loc"]["expansionLoc"]["file"]
                else:
                    loc = entity["loc"]
                    if "file" in entity["loc"]:
                        file = entity["loc"]["file"]
                if "expansionLoc" in entity["range"]["begin"]:
                    begin = entity["range"]["begin"]["expansionLoc"]
                else:
                    begin = entity["range"]["begin"]
                if "expansionLoc" in entity["range"]["end"]:
                    end = entity["range"]["end"]["expansionLoc"]
                else:
                    end = entity["range"]["end"]
                # get header code slices by analyzing source files
                # directly parsing the header files doesn't work, because header files may depend on other header files included in the source file!

                if file not in self.files:
                    continue

                if (
                    entity["kind"] == "NamespaceDecl"
                    or entity["kind"] == "LinkageSpecDecl"
                ):
                    iterate(entity["inner"], file)
                    continue
                if not entity["kind"].endswith("Decl"):
                    logger.warning(f"{entity['kind']} in top-level, what is this ?")
                    continue
                if "line" not in loc:
                    continue
                start_line = loc["line"]
                end_line = start_line
                if "line" in begin:
                    start_line = begin["line"]
                    end_line = start_line
                if "line" in end:
                    end_line = end["line"]
                comments = filter(
                    lambda x: x["kind"] == "FullComment", entity.get("inner", [])
                )
                for comment in comments:
                    loc = (
                        comment["loc"]["expansionLoc"]
                        if "expansionLoc" in comment
                        else comment["loc"]
                    )
                    if "line" not in loc:
                        continue
                    if loc["line"] >= start_line:
                        continue
                    start_line = loc["line"]
                self.segments_pool.add_segment(
                    CodeSegment(
                        pool=self.segments_pool,
                        file=file,
                        start_line=start_line,
                        end_line=end_line,
                    )
                )

        iterate(ast["inner"], filepath)
