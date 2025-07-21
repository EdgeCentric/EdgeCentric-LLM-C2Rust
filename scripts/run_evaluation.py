from utils import PROJECTS, METHODS, MODELS
from llm_c2rust.c2rust import run

config_path = "config.yml"
codeql = "~/codeql/codeql"
codeql_db = "/tmp/database"

for project in PROJECTS:
    for method in METHODS:
        for model in MODELS:
            input_path = f"benchmark/{project}"
            output_path = f"output/{project}/{model}/{method}"
            run(
                input_path,
                output_path,
                model,
                config_path,
                codeql,
                codeql_db,
                method == "Node-Centric",
            )
