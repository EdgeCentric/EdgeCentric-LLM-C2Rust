import os
from pathlib import Path
import shutil
from typing import Optional, Union
from .codeql_engine import CodeqlEngine


class CodeqlDatabase(object):
    def __init__(
        self,
        codeql_engine: CodeqlEngine,
        project_path: str,
        database_path: str,
        build_script_path: Optional[str] = None,
    ) -> None:
        self.codeql_engine: CodeqlEngine = codeql_engine
        self.project_path: str = os.path.abspath(project_path)
        self.database_path: str = os.path.abspath(database_path)
        self.build_script_path: Optional[str] = build_script_path
        self._check_and_build()

    def _is_codeql_database(self, path: str) -> bool:
        """
        :param path: the path to be checked
        :type path: str
        :return: if it is a CodeQL database
        :rtype: bool
        """
        # check diagnostic, log, results dir
        diagnostic_path = os.path.join(path, "diagnostic")
        log_path = os.path.join(path, "log")
        results_path = os.path.join(path, "results")

        # check baseline-info.json, codeql-database.yml, src.zip files
        baseline_info_file = os.path.join(path, "baseline-info.json")
        database_config_file = os.path.join(path, "codeql-database.yml")
        source_zip_file = os.path.join(path, "src.zip")

        # Verify the existence of required files and directories
        if (
            os.path.isdir(diagnostic_path)
            and os.path.isdir(log_path)
            and os.path.isfile(baseline_info_file)
            and os.path.isfile(database_config_file)
        ):
            return True
        return False

    def _check_and_build(self) -> None:
        if os.path.exists(self.database_path):
            if self._is_codeql_database(self.database_path):
                shutil.rmtree(self.database_path)
            else:
                raise ValueError(
                    f"The directory at {self.database_path} is not a valid CodeQL database. "
                    "Deletion aborted to prevent accidental data loss."
                )

        if not os.path.exists(self.database_path):
            if self.build_script_path is None:
                self.codeql_engine.database_create(
                    database_path=self.database_path,
                    source_root=self.project_path,
                    build_mode="autobuild",
                )
            else:
                self.codeql_engine.database_create(
                    database_path=self.database_path,
                    source_root=self.project_path,
                    build_mode="manual",
                    command=self.build_script_path,
                )

    def run_queries(self, queries_path: str) -> None:
        self.codeql_engine.database_run_queries(
            database_path=self.database_path, queries=queries_path, warnings="show"
        )

    def decode_results(
        self,
        queries_path: Union[Path, str],
        pack: str,
        query_results_path: Union[Path, str],
    ):
        if isinstance(queries_path, Path):
            queries_path = str(queries_path)
        if isinstance(query_results_path, Path):
            query_results_path = str(query_results_path)

        for ql_file in os.listdir(queries_path):
            if Path(ql_file).suffix != ".ql":
                continue
            basename = Path(os.path.basename(ql_file)).with_suffix("")
            self.codeql_engine.bqrs_decode(
                bqrs_file=Path(self.database_path)
                / "results"
                / pack
                / f"{basename}.bqrs",
                output_file=Path(query_results_path) / f"{basename}.json",
                format="json",
            )
