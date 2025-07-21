from pathlib import Path
from typing import Union

from llm_c2rust.autobuild.filegraph import CppFileGraph

CLANG_BUILD = "clang -fsyntax-only {c_files} {include_paths}\n"  # -c
CLANGPP_BUILD = "clang++ -fsyntax-only {cpp_files} {include_paths}\n"  # -c


def create_build_script(project_path: Union[Path, str]) -> str:
    if isinstance(project_path, Path):
        project_path = str(project_path)
    filegraph = CppFileGraph(project_path)
    files = filegraph.files
    out = "#!/bin/sh\n"

    for file in files:
        if file.ftype == "Source" and file.language == "c":
            includes_dirs = [
                inc_path for pathnode, inc_path in file.includes if inc_path is not None
            ]
            includes_dirs = list(set(includes_dirs))
            out += CLANG_BUILD.format(
                c_files=file.path,
                include_paths=" ".join("-I " + d for d in includes_dirs),
            )
        if file.ftype == "Source" and file.language == "cpp":
            includes_dirs = [
                inc_path for pathnode, inc_path in file.includes if inc_path is not None
            ]
            includes_dirs = list(set(includes_dirs))
            out += CLANGPP_BUILD.format(
                cpp_files=file.path,
                include_paths=" ".join("-I " + d for d in includes_dirs),
            )
    return out
