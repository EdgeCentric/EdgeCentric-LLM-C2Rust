import asyncio
import json
import logging
import os
from pathlib import Path
from subprocess import CalledProcessError
from typing import Any

import yaml

from llm_c2rust.utils.config import Config
from llm_c2rust.core.edge_centric_engine import EdgeCentricEngine
from llm_c2rust.core.node_centric_engine import NodeCentricEngine
from llm_c2rust.core.transpiler import ProjectTranspiler
from llm_c2rust.core.utils import analyze_source
from llm_c2rust.llm.api_inference import AsyncAPIInference
from llm_c2rust.utils.logging import enable_capture
from llm_c2rust.segmenter.segmenter import SemanticSegmenter
from llm_c2rust.utils.hash import calculate_md5

enable_capture()
__logger__ = logging.getLogger(__name__)


def run(
    input_path: str,
    output_path: str,
    model: str,
    config_path: str,
    codeql: str,
    codeql_db: str,
    baseline: bool = False,
):
    method = "Edge-Centric" if baseline else "Node-Centric"
    __logger__.info(
        f"Transpiling {input_path} to {output_path} with {model} in {method} method"
    )
    # Read Configs
    try:
        config_dict: dict[str, Any] = yaml.safe_load(Path(config_path).read_text())
    except FileNotFoundError as error:
        message = "Error: yml config file not found."
        __logger__.exception(message)
        raise FileNotFoundError(error, message) from error

    __logger__.info("configs: \n" + json.dumps(config_dict, indent=2))

    config: Config = Config.model_validate(config_dict)

    # Setup LLM Endpoints
    predicators: dict[str, AsyncAPIInference] = {}
    for endpoint in config.endpoints:
        predicators[endpoint.name] = AsyncAPIInference(
            model_name=endpoint.model,
            base_url=endpoint.base_url,
            api_keys=endpoint.api_keys,
            qpm=endpoint.qpm,
            tpm=endpoint.tpm,
            default_max_tokens=endpoint.max_tokens,
            reasoning=endpoint.reasoning,
        )

    project_hash = calculate_md5(os.path.abspath(input_path))
    os.makedirs(codeql_db, exist_ok=True)
    database_path = os.path.join(codeql_db, project_hash)
    try:
        database = analyze_source(input_path, codeql, database_path)
    except CalledProcessError as e:
        __logger__.error(e.stdout)
        __logger__.error(e.stderr)
        exit(1)

    transpiler = ProjectTranspiler(input_path)

    segmenter = SemanticSegmenter(database)

    if not baseline:

        engine = EdgeCentricEngine(
            segmenter,
            predicators[model],
            config.token_num,
            config.token_num_method,
            0,
            config.max_retry,
            config.max_resolve_round,
        )
    else:
        engine = NodeCentricEngine(
            segmenter,
            predicators[model],
            config.token_num,
            config.token_num_method,
            max_resolve_round=config.max_resolve_round,
            temperature=0,
        )

    asyncio.run(transpiler.transpile_project(engine, output_path))
