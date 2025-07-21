import os
from typing import Literal
from matplotlib import pyplot as plt
import pandas as pd
from llm_c2rust.cargo.rustc_messages import RustcErrorMessages
import re
from collections import defaultdict

from scripts.utils import METHODS, MODELS, PROJECTS, get_ranges, locate_ranges, compile


def get_names(src_path: str):
    with open(src_path, "r") as f:
        content = f.read()
    struct_names = re.findall(r"struct\s+(\w+)", content)
    enum_names = re.findall(r"enum\s+(\w+)", content)
    return struct_names + enum_names


def to_stacked_bar(
    data: pd.DataFrame,
    x_label: str,
    y_label: str,
    legend: str,
    colors: list[str],
    output_dir: str,
):

    facet_count = len(data.index.get_level_values(0).unique())
    category_count = len(data.columns)
    data = (data * 100).round(0)
    fig, axes = plt.subplots(1, facet_count, figsize=(7 * facet_count, 6), sharey=True)
    for ax, facet in zip(axes, data.index.get_level_values(0).unique()):
        draw_df = data.loc[[facet]].droplevel(0)
        draw_df.plot(kind="bar", stacked=True, ax=ax, width=0.9, color=colors)
        ax.set_title(f"{facet}", fontsize=12)
        ax.set_xlabel(x_label, fontsize=12)
        ax.set_ylabel(y_label, fontsize=12)
        ax.legend(
            title=legend, loc="upper right", bbox_to_anchor=(1, 1), fontsize="small"
        )
        handles, labels = ax.get_legend_handles_labels()
        ax.get_legend().remove()
        for container in ax.containers:
            for rect in container:
                height = rect.get_height()
                if height > 0.05:
                    ax.text(
                        rect.get_x() + rect.get_width() / 2,
                        rect.get_y() + height / 2,
                        f"{height:.0f}%",
                        ha="center",
                        va="center",
                        color="white",
                        fontsize=10,
                        fontweight="bold",
                    )
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=category_count,
        bbox_to_anchor=(0.5, 1.05),
        fontsize=12,
        frameon=False,
    )
    plt.tight_layout()
    plt.savefig(f"{output_dir}/rq2.png")


def error_kind(
    message: RustcErrorMessages, ranges: list[tuple[int, int]]
) -> Literal["External Crate"] | Literal["Inter-Unit"] | Literal["Intra-Unit"]:

    located_ranges = locate_ranges(message.all_spans, ranges)
    if len(located_ranges) > 1:
        return "Inter-Unit"
    file_names = {span.file_name for span in message.all_spans}
    file_names = filter(lambda x: x != "src/lib.rs", file_names)
    if len(list(file_names)):
        return "External Crate"
    if "crate" in message.message:
        return "External Crate"
    if "failed to resolve" in message.message:
        return "External Crate"
    if "unresolved import" in message.message:
        return "External Crate"
    if re.match(r"cannot find .* in this scope", message.message):
        return "Inter-Unit"
    if re.match(r"no .* found for .* in the current scope", message.message):
        return "Inter-Unit"
    if re.match(r".* call to .* function .*", message.message):
        return "Inter-Unit"
    return "Intra-Unit"


message_sets = defaultdict(set)


def classify_result2(path: str) -> tuple[int, int, int]:

    ranges = get_ranges(os.path.join(path, "src/lib.rs"))
    messages = compile(path)
    struct_names = get_names(os.path.join(path, "src/lib.rs"))
    count = defaultdict(int)
    for message in messages:

        kind = error_kind(message, ranges)
        count[kind] += 1
        message_sets[kind].add(message.message)

    return count["External Crate"], count["Inter-Unit"], count["Intra-Unit"]


kind2_data = pd.DataFrame(
    index=pd.MultiIndex.from_product(
        [PROJECTS, METHODS, MODELS], names=["project", "method", "models"]
    ),
    columns=["External Crate", "Inter-Unit", "Intra-Unit"],
)


output_dir = "output"
result_dir = "results"
for method in METHODS:
    for project in PROJECTS:
        for model in MODELS:
            print(f"Processing {project}/{model}/{method}")
            file_path = os.path.join(output_dir, project, model, method)
            kind2_data.loc[(project, method, model)] = classify_result2(file_path)


kind2_data = kind2_data.dropna()
kind2_sum_model = kind2_data.groupby(level=["project", "method"]).sum()
kind2_sum_model_error = kind2_sum_model.sum(axis=1).replace(0, 1)

kind2_percentage = kind2_sum_model.div(kind2_sum_model_error, axis=0)
kind2_percentage = (
    kind2_percentage.swaplevel("project", "method")
    .reindex(index=METHODS, level="method")
    .reindex(index=PROJECTS, level="project")
)
kind2_percentage.index = kind2_percentage.index.set_levels(
    pd.Categorical(
        kind2_percentage.index.levels[1],
        categories=kind2_percentage.index.levels[1].unique(),
    ),
    level="project",
)
to_stacked_bar(
    kind2_percentage,
    "Project",
    "Percentage",
    "Error Type",
    ["#999999", "#E69F00", "#56B4E9"],
    result_dir,
)
