import os
import re
import subprocess
from llm_c2rust.cargo.rustc_messages import (
    CargoMessageCompilerMessage,
    CargoMessageTypeAdapter,
    RustcErrorMessages,
    RustcErrorSpan,
)
from tree_sitter import Language, Node, Parser
import tree_sitter_rust as tsrust

PROJECTS = [
    "flingfd",
    "buffer",
    "tinyhttpd",
    "grabc",
    "libcsv",
    "url",
    "genann",
    "sharebox-fs",
    "libopenaptx",
    "time",
    "hat-trie",
    "libzahl",
    "gnu-ed",
    "which",
    "binn",
]

METHODS = [
    "Node-Centric",
    "Edge-Centric",
]

MODELS = [
    "DeepSeek",
    "Qwen",
    "Doubao",
]

parser = Parser(Language(tsrust.language()))


def locate_ranges(
    spans: list[RustcErrorSpan], ranges: list[tuple[int, int]]
) -> set[tuple[int, int]]:
    current_file_spans = [span for span in spans if span.file_name == "src/lib.rs"]
    locate_ranges = {
        (start, end)
        for span in current_file_spans
        for start, end in ranges
        if start <= span.line_start <= span.line_end <= end
    }
    return locate_ranges


def __ranges_of_node(node: Node) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start_point = None
    for child in node.children:
        if child.type == "impl_item":
            ranges.extend(__ranges_of_node(child))
            continue
        if start_point == None:
            start_point = child.start_point[0] + 1, child.start_point[1] + 1
        if child.type not in (
            "inner_attribute_item",
            "attribute_item",
            "block_comment",
            "line_comment",
        ):
            end_point = child.end_point[0] + 1, child.end_point[1] + 1
            ranges.append((start_point[0], end_point[0]))
            start_point = None
    return ranges


def get_ranges(src_path: str) -> list[tuple[int, int]]:
    with open(src_path, "r") as f:
        tree = parser.parse(f.read().encode(), encoding="utf8")

    return __ranges_of_node(tree.root_node)


def compile(rust_dir: str) -> list[RustcErrorMessages]:

    cwd = os.getcwd()
    os.chdir(rust_dir)
    rt = subprocess.run(
        f"cargo build --message-format=json".split(" "),
        capture_output=True,
        text=True,
    )
    os.chdir(cwd)
    if not rt.stdout:
        raise Exception(f"{rust_dir}: {rt.stdout}")
    raw_messages = rt.stdout.split("\n")

    messages = []
    for message in raw_messages:
        if not message:
            continue
        message = CargoMessageTypeAdapter.validate_json(message)
        if not isinstance(message, CargoMessageCompilerMessage):
            continue
        if message.message.level != "error":
            continue
        message = message.message
        if re.match(r"error: aborting due to \d+ previous errors?;", message.message):
            continue
        messages.append(message)
    return messages
