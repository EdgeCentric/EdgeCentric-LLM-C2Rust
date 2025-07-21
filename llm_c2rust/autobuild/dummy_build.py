import os
from pathlib import Path
from typing import List, Set, Tuple, Union


CLANG_DUMMY_BUILD = "clang -fsyntax-only {c_files} {include_paths}\n"
CLANGPP_DUMMY_BUILD = "clang++ -fsyntax-only {cpp_files} {include_paths}\n"

C_SUFFIXES = [".c"]
CPP_SUFFIXES = [".cpp", ".cc", ".cxx"]


def collect_files(
    project_path: Union[Path, str],
    absolute: bool = False,
    no_root: bool = False,
) -> Tuple[List[str], List[str], Set[str]]:
    if isinstance(project_path, Path):
        project_path = str(project_path)
    if absolute:
        pathpost = os.path.abspath
    else:
        pathpost = lambda x: x
    c_files = []
    cpp_files = []
    dirs = {project_path}
    for root, dirnames, filenames in os.walk(project_path):
        rel_root = os.path.relpath(root, project_path)
        for filename in filenames:
            if any(filename.endswith(suffix) for suffix in C_SUFFIXES):
                if no_root:
                    c_files.append(pathpost(os.path.join(rel_root, filename)))
                else:
                    c_files.append(pathpost(os.path.join(root, filename)))
            if any(filename.endswith(suffix) for suffix in CPP_SUFFIXES):
                if no_root:
                    cpp_files.append(pathpost(os.path.join(rel_root, filename)))
                else:
                    cpp_files.append(pathpost(os.path.join(root, filename)))
        for dirname in dirnames:
            if no_root:
                dirs.add(pathpost(os.path.join(rel_root, dirname)))
            else:
                dirs.add(pathpost(os.path.join(root, dirname)))

    return c_files, cpp_files, dirs


def create_build_script(project_path: Union[Path, str]) -> str:
    c_files, cpp_files, include_paths = collect_files(project_path, no_root=True)
    out = "#!/bin/sh\n"
    if len(c_files) > 0:
        out += CLANG_DUMMY_BUILD.format(
            c_files=" ".join(c_files),
            include_paths=" ".join("-I" + path for path in include_paths),
        )
    if len(cpp_files) > 0:
        out += CLANGPP_DUMMY_BUILD.format(
            cpp_files=" ".join(cpp_files),
            include_paths=" ".join("-I" + path for path in include_paths),
        )
    return out
