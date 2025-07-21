import logging
import os
import shutil
import time
from pathlib import Path


from llm_c2rust.core.interact import InteractEngine
from llm_c2rust.core.utils import write_project

from llm_c2rust.utils.hash import calculate_md5


logger: logging.Logger = logging.getLogger(__name__)


class Timer:
    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        self.end = time.time()
        self.elapsed = self.end - self.start


class ProjectTranspiler(object):
    def __init__(
        self,
        project_path: str | Path,
    ) -> None:
        if isinstance(project_path, Path):
            project_path = str(project_path)

        self.project_path: str = os.path.abspath(project_path)
        self.project_hash: str = calculate_md5(os.path.abspath(project_path))
        self.project_name: str = Path(project_path).name

    async def transpile_project(self, engine: InteractEngine, output_path: str) -> None:
        logger.info(
            f"Translating project {self.project_name} using {engine.agent.predicator.model_name} and {engine.describe()} method."
        )

        shutil.rmtree(output_path, ignore_errors=True)
        os.makedirs(output_path, exist_ok=True)
        with Timer() as timer:
            await engine.trans_project(self)

        write_project(
            output_path,
            engine.workspace.config,
            engine.workspace.trans_result(),
        )

        logger.info(f"Translate project {self.project_name} done.")
