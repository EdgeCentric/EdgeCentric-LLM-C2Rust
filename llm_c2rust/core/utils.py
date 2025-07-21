import json
import os
import re
import subprocess
import tempfile
from collections.abc import AsyncGenerator, AsyncIterable
from typing import TypeVar

import requests

from llm_c2rust.analyzer.utils import RustPieceRef
from llm_c2rust.autobuild.clang_build import create_build_script
from llm_c2rust.codeql.codeql_database import CodeqlDatabase
from llm_c2rust.codeql.codeql_engine import CodeqlEngine
from llm_c2rust.cargo.rustc_messages import (
    CargoMessage,
    CargoMessageCompilerMessage,
    CargoMessageTypeAdapter,
    RustcErrorMessages,
)
from llm_c2rust.cargo.cargo_message import CargoConfig, Dependency, write_cargo_config
from llm_c2rust.parser.rust_parser import grammar_correct
from llm_c2rust.utils.markdown import extract_code_blocks_with_language

ElementType = TypeVar("ElementType")


async def aenumerate(
    iterable: AsyncIterable[ElementType], start: int = 0
) -> AsyncGenerator[tuple[int, ElementType]]:
    id = start
    async for e in iterable:
        yield id, e
        id += 1


def fetch_name_version(crate_name: str) -> tuple[str, str] | None:
    """
    Check if a crate exists on crates.io by sending a GET request
    to the crates.io API endpoint.

    Args:
        crate_name (str): The name of the crate to search for.

    Returns:
        bool: True if the crate exists, False otherwise.
    """
    url = f"https://crates.io/api/v1/crates/{crate_name}"
    for i in range(3):
        try:
            response = requests.get(url)
            # A successful API call returns status code 200 when the crate exists.
            if response.status_code == 200:
                data = response.json()
                # The 'max_version' field in the "crate" object holds the latest version.
                crate = data.get("crate", {})
                crate_name = crate.get("name", crate_name)
                for field in ["default_version", "max_stable_version", "max_version"]:
                    version_num: str = crate.get(field)
                    if not version_num:
                        continue
                    if version_num == "0.0.0":
                        continue
                    return crate_name, version_num
                return None
            else:
                # Handle any unexpected status codes
                print(f"Received unexpected status code: {response.status_code}")
                return None

        except requests.RequestException as e:
            print(f"An error occurred while making the request: {e}")


def write_project(output_path: str, config: CargoConfig, code: str) -> None:
    write_cargo_config(config, os.path.join(output_path, "Cargo.toml"))
    # Write Files
    os.makedirs(os.path.join(output_path, "src"), exist_ok=True)
    with open(os.path.join(output_path, "src", "lib.rs"), "w", encoding="utf-8") as f:
        f.write(code)


class RustBuildError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def build_project(project_path):

    rt = subprocess.run(
        [
            "cargo",
            "build",
            "--message-format",
            "json",
            "--manifest-path",
            os.path.join(project_path, "Cargo.toml"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    raw_messages = rt.stdout.split("\n")
    messages: list[CargoMessage] = []
    for message in raw_messages:
        if message:
            messages.append(
                CargoMessageTypeAdapter.validate_python(json.loads(message))
            )
    return messages


ConflictReport = RustcErrorMessages


def validate(code: str, config: CargoConfig) -> list[ConflictReport]:
    tmpdir = tempfile.TemporaryDirectory()
    write_project(tmpdir.name, config, code)
    msgs: list[RustcErrorMessages] = []
    for message in build_project(tmpdir.name):
        if not isinstance(message, CargoMessageCompilerMessage):
            continue
        message = message.message
        if message.level != "error":
            continue
        if re.match(r"error: aborting due to \d+ previous errors?", message.message):
            continue
        msgs.append(message)
    return msgs


def is_import_error(message: RustcErrorMessages) -> str | None:
    if m := re.match(r"unresolved imports? `(\S+)`", message.message):
        return m[1].split("::")[0]
    if m := re.match(
        r"failed to resolve: use of unresolved modules? or unlinked crates? `(\S+)`",
        message.message,
    ):
        return m[1].split("::")[0]
    if m := re.match(
        r"failed to resolve: .* `(\S+)` is not a crate or module", message.message
    ):
        return m[1].split("::")[0]


def new_dependencies(code: str, config: CargoConfig) -> dict[str, str | Dependency]:
    config = config.model_copy()
    if not config.dependencies:
        config.dependencies = {}

    # add dependencies
    tempdir = tempfile.TemporaryDirectory()
    write_project(tempdir.name, config, code)

    for message in build_project(tempdir.name):
        if not isinstance(message, CargoMessageCompilerMessage):
            continue
        message = message.message
        if not (guess_name := is_import_error(message)):
            continue
        if not (name_version := fetch_name_version(guess_name)):
            continue
        real_name, version = name_version
        config.dependencies[real_name] = Dependency(version=version)
    # add features
    write_project(tempdir.name, config, code)
    for message in build_project(tempdir.name):
        if not isinstance(message, CargoMessageCompilerMessage):
            continue
        message = message.message
        for i, child in enumerate(message.children):
            if child.message != "found an item that was configured out":
                continue
            if len(child.spans) == 0 or not (
                m := re.match(
                    r".*/\.cargo/registry/src/.*/([\w-]+)-\d+\.\d+\.\d+/.*",
                    child.spans[0].file_name,
                )
            ):
                continue
            crate_name = m[1]
            if i >= len(message.children) or not (
                m := re.match(
                    r"the item is gated behind the `(.*)` feature",
                    message.children[i + 1].message,
                )
            ):
                continue

            d = config.dependencies[crate_name]
            if isinstance(d, str):
                d = Dependency(version=d)
                d.features = []
                config.dependencies[crate_name] = d
            elif not d.features:
                d.features = []
            if m[1] not in d.features:
                d.features.append(m[1])
    return config.dependencies


def analyze_source(project_path, codeql_path, database_path):
    build_script_path = os.path.abspath(
        os.path.join(project_path, "llm_c2rust_build.sh")
    )
    if not os.path.exists(build_script_path):
        build_script = create_build_script(project_path)
        with open(build_script_path, "w", encoding="utf-8") as f:
            f.write(build_script)

    return CodeqlDatabase(
        codeql_engine=CodeqlEngine(codeql_path),
        project_path=project_path,
        database_path=database_path,
        build_script_path=build_script_path,
    )


def first_rust_code_from_md(md_string: str):
    for lang, content in extract_code_blocks_with_language(md_string):
        if lang == "rust" or grammar_correct(content):
            return content
    return None


def all_rust_code_from_md(md_string: str) -> str:
    rust_code = ""
    for lang, content in extract_code_blocks_with_language(md_string):
        # strict check
        if grammar_correct(content):
            rust_code += content + "\n"
    return rust_code


def pieces_of_conflict(
    message: ConflictReport, ranges: list[tuple[RustPieceRef, int, int]]
) -> set[RustPieceRef]:
    pieces = set()
    for span in message.all_spans:
        if span.file_name != "src/lib.rs":
            continue
        for item, start_line, end_line in ranges:
            if start_line <= span.line_start <= span.line_end <= end_line:
                pieces.add(item)
            if span.line_end < start_line:
                break
    return pieces


def pieces_of_conflicts(
    messages: list[ConflictReport], ranges: list[tuple[RustPieceRef, int, int]]
) -> dict[ConflictReport, set[RustPieceRef]]:
    message_with_pieces: dict[ConflictReport, set[RustPieceRef]] = {}
    for message in messages:
        if pieces := pieces_of_conflict(message, ranges):
            message_with_pieces[message] = pieces
    return message_with_pieces
