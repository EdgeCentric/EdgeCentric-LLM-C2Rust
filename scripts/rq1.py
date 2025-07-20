import re
import subprocess
import os
import tree_sitter_rust as tsrust
from tree_sitter import Language, Node, Parser
import pandas as pd
from edge_centric.compiler.rust.error_messages import (
    CargoMessageCompilerMessage,
    CargoMessageTypeAdapter,
    RustcErrorMessages,
    RustcErrorSpan,
)
from scripts.evaluation_constants import PROJECTS, METHODS, MODELS
import matplotlib.pyplot as plt
import numpy as np

parser = Parser(Language(tsrust.language()))


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


def no_comments_empty_lines(code_string: str) -> str:
    code_string = re.sub(r"/\*[\s\S]*?\*/", "", code_string)
    code_string = re.sub(r"//.*", "", code_string)
    # empty lines may contain whitespaces
    code_string = re.sub(r"\s*\n", "\n", code_string)
    return code_string


def get_errors(path: str):
    messages = compile(path)

    ranges = get_ranges(os.path.join(path, "src/lib.rs"))
    error_ranges = set()
    for msg in messages:
        located_ranges = locate_ranges(list(msg.spans), ranges)
        error_ranges.update(located_ranges)

    return len(messages), len(error_ranges), len(ranges)


def to_bar(
    data: pd.Series,
    x_label: str,
    y_label: str,
    legend: str,
    colors: list[str],
    output_dir: str,
):
    """

    Draw a multi-facet bar chart with three levels of index. The first level is the facet, the second level is the group of bars, and the third level is the bar.
    """
    facet_count = len(data.index.get_level_values(0).unique())
    group_bar_count = len(data.index.get_level_values(2).unique())
    # Convert the third level index of df to columns
    df = data.unstack(level=2)
    df = (df * 100).round(0)
    # Determine the number of subplots based on the number of first level
    for i, facet in enumerate(df.index.get_level_values(0).unique()):
        fig, ax = plt.subplots(figsize=(7, 6))
        draw_df = df.xs(facet, level=0)
        draw_df.plot(kind="bar", ax=ax, width=0.80, color=colors)
        ax.set_title(f"{facet}", fontsize=12)
        ax.set_xlabel(x_label, fontsize=12)
        ax.set_ylabel(y_label, fontsize=12)
        ax.set_ylim(0, 105)
        ax.legend(
            title=legend, loc="upper right", bbox_to_anchor=(1, 1), fontsize="small"
        )
        # handles, labels = ax.get_legend_handles_labels()
        # ax.get_legend().remove()

        container_to_label = ax.containers[1]
        ax.bar_label(
            container_to_label,  # type: ignore
            fmt="%.0f%%",
            fontsize=9,
            color="dimgray",
            padding=3,
        )
        plt.tight_layout()
        plt.savefig(f"{output_dir}/rq1_{facet}.png")


error_data = pd.DataFrame(
    index=pd.MultiIndex.from_product(
        [PROJECTS, METHODS, MODELS], names=["project", "method", "models"]
    ),
    columns=["errors", "error piece", "pieces"],
)

output_dir = "output"
result_dir = "results"
for method in METHODS:
    for project in PROJECTS:
        for model in MODELS:
            print(f"Processing {project}/{model}/{method}")
            file_path = os.path.join(output_dir, project, model, method)
            errors, error_piece, piece_count = get_errors(file_path)
            error_data.loc[(project, method, model)] = [
                errors,
                error_piece,
                piece_count,
            ]


error_data = error_data.dropna()
os.makedirs(result_dir, exist_ok=True)
error_count = error_data["errors"].unstack(["method", "models"])
error_reduction = error_count.groupby(level=1, axis=1).apply(
    lambda group: 1
    - group.xs("Edge-Centric", level=0, axis=1)
    / group.xs("Node-Centric", level=0, axis=1).replace(0, np.nan)
)
# error_reduction.columns = pd.MultiIndex.from_tuples(
#     ("Error Reduction", col) for col in error_reduction.columns.get_level_values(1)
# )
# error_count = pd.concat([error_count, error_reduction], axis=1)
error_count = error_count.reindex(index=PROJECTS)
error_count.loc["Average"] = error_count.mean(axis=0)
# error_count["Error Reduction"] = error_count["Error Reduction"].apply((lambda x: f"{x:.0%}" if isinstance(x, float) else "-"), convertDtype=True)
error_count = error_count.swaplevel(axis=1).sort_index(axis=1, level=0)
error_count.to_csv(f"{result_dir}/rq1.csv")

error_piece_rate = error_data["error piece"] / error_data["pieces"]
error_piece_rate = error_piece_rate.swaplevel("method", "models").swaplevel(
    "project", "models"
)

error_piece_rate = error_piece_rate.reindex(index=PROJECTS, level="project")
error_piece_rate = error_piece_rate.reindex(
    index=["Node-Centric", "Edge-Centric"], level="method"
)
to_bar(
    error_piece_rate,
    "Project",
    "Unit Error Rate (%)",
    "Method",
    ["#D55E00", "#009E73"],
    result_dir,
)
