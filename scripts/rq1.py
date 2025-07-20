import os
import pandas as pd
from scripts.utils import PROJECTS, METHODS, MODELS, get_ranges, locate_ranges, compile
import matplotlib.pyplot as plt
import numpy as np


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
error_count = error_data["errors"].unstack(["method", "models"])  # type: ignore
error_reduction = error_count.groupby(level=1, axis=1).apply(  # type: ignore
    lambda group: 1
    - group.xs("Edge-Centric", level=0, axis=1)
    / group.xs("Node-Centric", level=0, axis=1).replace(0, np.nan)
)

error_count = error_count.reindex(index=PROJECTS)
error_count.loc["Average"] = error_count.mean(axis=0)

error_count = error_count.swaplevel(axis=1).sort_index(axis=1, level=0)
error_count.to_csv(f"{result_dir}/rq1.csv")

error_piece_rate = error_data["error piece"] / error_data["pieces"]
error_piece_rate = error_piece_rate.swaplevel("method", "models").swaplevel(
    "project", "models"
)

error_piece_rate = error_piece_rate.reindex(index=PROJECTS, level="project")
error_piece_rate = error_piece_rate.reindex(index=METHODS, level="method")
to_bar(
    error_piece_rate,
    "Project",
    "Unit Error Rate (%)",
    "Method",
    ["#D55E00", "#009E73"],
    result_dir,
)
