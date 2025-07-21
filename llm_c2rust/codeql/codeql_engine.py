import logging
import subprocess
from pathlib import Path
from typing import List, Literal, Optional, Tuple, Union


import logging

logger: logging.Logger = logging.getLogger(__name__)

CodeqlSupportedLanguage = Literal[
    "c-cpp",
    "csharp",
    "go",
    "java-kotlin",
    "javascript-typescript",
    "python",
    "ruby",
    "swift",
]
LanguageType = Union[CodeqlSupportedLanguage, List[CodeqlSupportedLanguage]]


class CodeqlEngine(object):
    def __init__(self, codeql_bin: str) -> None:
        self.codeql_bin: str = codeql_bin

    def database_create(
        self,
        database_path: Union[Path, str],
        source_root: Union[Path, str],
        language: LanguageType = "c-cpp",
        command: Optional[Union[str, List[str]]] = None,
        build_mode: Optional[Literal["none", "autobuild", "manual"]] = None,
        db_cluster: bool = False,
        no_run_unnecessary_builds: bool = False,
        codescanning_config: Optional[str] = None,
    ) -> None:
        """
        Creates a CodeQL database for code analysis.

        :param database_path: The path where the CodeQL database will be created.
        :type database_path: Union[Path, str]
        :param source_root: The root directory of the source code to be analyzed.
        :type source_root: Union[Path, str]
        :param language: The programming language of the source code (default is "c-cpp").
        :type language: LanguageType
        :param command: The build command(s) to use for compiling the code, if applicable.
        :type command: Optional[Union[str, List[str]]]
        :param build_mode: The build mode to use for creating the database.
        :type build_mode: Optional[Literal["none", "autobuild", "manual"]]
        :param db_cluster: If True, enables database clustering.
        :type db_cluster: bool
        :param no_run_unnecessary_builds: If True, skips unnecessary builds for faster processing.
        :type no_run_unnecessary_builds: bool
        :param codescanning_config: Optional configuration file path for code scanning.
        :type codescanning_config: Optional[str]

        :raises subprocess.CalledProcessError: If the database creation process encounters an error.

        :notes: For additional details, please refer to:
                https://docs.github.com/zh/code-security/codeql-cli/getting-started-with-the-codeql-cli/preparing-your-code-for-codeql-analysis
        """
        if isinstance(database_path, Path):
            database_path = str(database_path)
        if isinstance(source_root, Path):
            source_root = str(source_root)

        if isinstance(language, list) or isinstance(language, tuple):
            language_str = ",".join(language)
        else:
            language_str = language

        commands = [
            self.codeql_bin,
            "database",
            "create",
            database_path,
            "--language=" + language_str,
            "--source-root",
            source_root,
        ]

        if command:
            if isinstance(command, list):
                commands.extend(["--command"] + command)
            else:
                commands.extend(["--command=" + command])

        if build_mode:
            commands.extend(["--build-mode", build_mode])

        if db_cluster:
            commands.append("--db-cluster")

        if no_run_unnecessary_builds:
            commands.append("--no-run-unnecessary-builds")

        if codescanning_config:
            commands.extend(["--codescanning-config", codescanning_config])

        # Run the command
        codeql_results = subprocess.run(
            commands,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if codeql_results.returncode == 0:
            log_fn = logger.info
        else:
            log_fn = logger.error
        if codeql_results.stdout:
            log_fn(codeql_results.stdout)
        if codeql_results.stderr:
            log_fn(codeql_results.stderr)

    def database_analyze(
        self,
        database_path: Union[Path, str],
        queries: List[str],
        format: Literal[
            "csv",
            "sarif-latest",
            "sarifv2.1.0",
            "graphtext",
            "dgml",
            "dot",
        ],
        output: Union[Path, str],
        rerun: bool = True,
        max_paths: Optional[int] = 4,
        sarif_add_file_contents: bool = False,
        sarif_add_snippets: bool = True,
        sarif_include_query_help: Literal[
            "always", "custom_queries_only", "never"
        ] = "custom_queries_only",
        no_group_results: bool = False,
        no_sarif_minify: bool = False,
        csv_location_format: Optional[
            Literal["uri", "line-column", "offset-length"]
        ] = "line-column",
        dot_location_url_format: Optional[str] = None,
    ) -> None:
        """
        Analyzes a CodeQL database using specified queries and formats the results.

        :param database_path: Path to the CodeQL database to analyze.
        :type database_path: Union[Path, str]
        :param queries: A list of queries or query suites to execute in the analysis.
        :type queries: List[str]
        :param format: The output format for the results (e.g., csv, sarif-latest, etc.).
        :type format: str
        :param output: The output path or directory where results will be saved.
        :type output: Union[Path, str]
        :param rerun: Whether to rerun the queries even if results are cached (default is True).
        :type rerun: bool
        :param max_paths: Maximum number of paths generated for each alert (default is 4).
        :type max_paths: Optional[int]
        :param sarif_add_file_contents: Whether to include full file contents in SARIF results.
        :type sarif_add_file_contents: bool
        :param sarif_add_snippets: Whether to include code snippets in SARIF results (default is True).
        :type sarif_add_snippets: bool
        :param sarif_include_query_help: Whether to include query help in SARIF results (default is "custom_queries_only").
        :type sarif_include_query_help: str
        :param no_group_results: Whether to generate a result for each unique message, not just each unique location.
        :type no_group_results: bool
        :param no_sarif_minify: Whether to generate non-minified SARIF output (default is False).
        :type no_sarif_minify: bool
        :param csv_location_format: Format for locations in CSV output (default is "line-column").
        :type csv_location_format: Optional[str]
        :param dot_location_url_format: Format for location URLs in DOT output (default is None).
        :type dot_location_url_format: Optional[str]

        :raises subprocess.CalledProcessError: If the analysis process encounters an error.

        :notes: For more information, please refer to:
                https://docs.github.com/zh/code-security/codeql-cli/getting-started-with-the-codeql-cli/analyzing-your-code-with-codeql-queries
        """
        if isinstance(database_path, Path):
            database_path = str(database_path)
        if isinstance(output, Path):
            output = str(output)

        # Prepare the base command
        commands = [
            self.codeql_bin,
            "database",
            "analyze",
            database_path,
            "--format=" + format,
            "--output=" + output,
        ]

        # Add queries
        for query in queries:
            commands.append(query)

        # Add optional flags and arguments
        if not rerun:
            commands.append("--no-rerun")
        else:
            commands.append("--rerun")

        if max_paths is not None:
            commands.append(f"--max-paths={max_paths}")

        if sarif_add_file_contents:
            commands.append("--sarif-add-file-contents")
        else:
            commands.append("--no-sarif-add-file-contents")

        if not sarif_add_snippets:
            commands.append("--no-sarif-add-snippets")
        else:
            commands.append("--sarif-add-snippets")

        if sarif_include_query_help:
            commands.append(f"--sarif-include-query-help={sarif_include_query_help}")

        if no_group_results:
            commands.append("--no-group-results")

        if no_sarif_minify:
            commands.append("--no-sarif-minify")

        if csv_location_format:
            commands.append(f"--csv-location-format={csv_location_format}")

        if dot_location_url_format:
            commands.append(f"--dot-location-url-format={dot_location_url_format}")

        # Run the command
        codeql_results = subprocess.run(
            commands,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if codeql_results.returncode == 0:
            log_fn = logger.info
        else:
            log_fn = logger.error
        if codeql_results.stdout:
            log_fn(codeql_results.stdout)
        if codeql_results.stderr:
            log_fn(codeql_results.stderr)

    def database_cleanup(
        self,
        database_path: Union[Path, str],
        max_disk_cache: Optional[int] = None,
        min_disk_free: Optional[int] = None,
        min_disk_free_pct: Optional[int] = None,
        cache_cleanup: Optional[Literal["clear", "trim", "fit"]] = "trim",
        cleanup_upgrade_backups: Optional[bool] = None,
    ) -> None:
        """
        Cleans up the CodeQL database by reducing its size on disk.

        For more details, refer to the [CodeQL CLI Manual - Database Cleanup](https://docs.github.com/zh/code-security/codeql-cli/codeql-cli-manual/database-cleanup).

        :param database_path: [Required] The path of the CodeQL database to clean up.
        :type database_path: Union[Path, str]
        :param max_disk_cache: Sets the maximum amount of disk space for caching intermediate query results. Defaults to a reasonable amount based on dataset size and query complexity.
        :type max_disk_cache: Optional[int]
        :param min_disk_free: [Advanced] Target available space on the file system, in MB.
        :type min_disk_free: Optional[int]
        :param min_disk_free_pct: [Advanced] Target percentage of available space on the file system.
        :type min_disk_free_pct: Optional[int]
        :param cache_cleanup: Sets the cache trimming mode. Can be "clear", "trim" (default), or "fit".
            - "clear": Removes the entire cache and resets the database to a freshly extracted state.
            - "trim" (default): Removes everything except explicitly cached predicates.
            - "fit": Ensures disk cache adheres to size limits by removing intermediate files as necessary.
        :type cache_cleanup: Optional[Literal["clear", "trim", "fit"]]
        :param cleanup_upgrade_backups: Deletes backup directories generated by database upgrades if True.
        :type cleanup_upgrade_backups: Optional[bool]

        :raises subprocess.CalledProcessError: If the cleanup process fails.

        :example:
            engine = CodeqlEngine("/path/to/codeql")
            engine.database_cleanup("/path/to/database", max_disk_cache=500, cleanup_upgrade_backups=True)
        """
        if isinstance(database_path, Path):
            database_path = str(database_path)

        commands = [self.codeql_bin, "database", "cleanup", database_path]

        if max_disk_cache is not None:
            commands.append(f"--max-disk-cache={max_disk_cache}")

        if min_disk_free is not None:
            commands.append(f"--min-disk-free={min_disk_free}")

        if min_disk_free_pct is not None:
            commands.append(f"--min-disk-free-pct={min_disk_free_pct}")

        if cache_cleanup is not None:
            commands.append(f"--cache-cleanup={cache_cleanup}")

        if cleanup_upgrade_backups:
            commands.append("--cleanup-upgrade-backups")

        # Run the command
        codeql_results = subprocess.run(
            commands,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if codeql_results.returncode == 0:
            log_fn = logger.info
        else:
            log_fn = logger.error
        if codeql_results.stdout:
            log_fn(codeql_results.stdout)
        if codeql_results.stderr:
            log_fn(codeql_results.stderr)

    def database_finalize(
        self,
        database_path: Union[Path, str],
        db_cluster: bool = False,
        additional_dbs: Optional[Union[str, List[str]]] = None,
        no_cleanup: bool = False,
        no_pre_finalize: bool = False,
        skip_empty: bool = False,
    ) -> None:
        """
        Finalizes the specified CodeQL database, preparing it for analysis.

        For more details, refer to the [CodeQL CLI Manual - Database Finalize](https://docs.github.com/zh/code-security/codeql-cli/codeql-cli-manual/database-finalize).

        :param database_path: The path to the CodeQL database.
        :type database_path: Union[Path, str]
        :param db_cluster: If True, treats `database_path` as a directory containing multiple databases.
        :type db_cluster: bool
        :param additional_dbs: Paths to additional databases to include in the finalization.
        :type additional_dbs: Optional[Union[str, List[str]]]
        :param no_cleanup: If True, skips cleanup operations after finalizing.
        :type no_cleanup: bool
        :param no_pre_finalize: If True, skips pre-finalize scripts.
        :type no_pre_finalize: bool
        :param skip_empty: If True, skips finalization if the database is empty, emitting a warning instead.
        :type skip_empty: bool

        :raises subprocess.CalledProcessError: If the finalization process encounters an error.
        """
        if isinstance(database_path, Path):
            database_path = str(database_path)

        # Base command setup
        commands = [
            self.codeql_bin,
            "database",
            "finalize",
            database_path,
        ]

        # Apply optional flags
        if db_cluster:
            commands.append("--db-cluster")

        if additional_dbs:
            if isinstance(additional_dbs, list):
                additional_dbs_str = ":".join(additional_dbs)
            else:
                additional_dbs_str = additional_dbs
            commands.append(f"--additional-dbs={additional_dbs_str}")

        if no_cleanup:
            commands.append("--no-cleanup")

        if no_pre_finalize:
            commands.append("--no-pre-finalize")

        if skip_empty:
            commands.append("--skip-empty")

        # Execute the finalize command
        codeql_results = subprocess.run(
            commands,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if codeql_results.returncode == 0:
            log_fn = logger.info
        else:
            log_fn = logger.error
        if codeql_results.stdout:
            log_fn(codeql_results.stdout)
        if codeql_results.stderr:
            log_fn(codeql_results.stderr)

    def database_init(
        self,
        database_path: Union[Path, str],
        source_root: Union[Path, str],
        language: Optional[LanguageType] = None,
        build_mode: Optional[Literal["none", "autobuild", "manual"]] = None,
        github_auth_stdin: bool = False,
        github_url: Optional[str] = None,
        extractor_option: Optional[List[str]] = None,
        overwrite: bool = False,
        force_overwrite: bool = False,
        allow_missing_source_root: bool = False,
        begin_tracing: bool = False,
        db_cluster: bool = False,
    ) -> None:
        """
        Initializes a new CodeQL database.

        :param database_path: The path where the CodeQL database will be created.
        :type database_path: Union[Path, str]
        :param source_root: The root directory of the source code to be analyzed.
        :type source_root: Union[Path, str]
        :param language: Language(s) to be used for analysis.
        :type language: Optional[LanguageType]
        :param build_mode: The build mode to use for creating the database. Options are "none", "autobuild", or "manual".
        :type build_mode: Optional[Literal["none", "autobuild", "manual"]]
        :param github_auth_stdin: If True, enables GitHub authentication via stdin.
        :type github_auth_stdin: bool
        :param github_url: GitHub URL for retrieving the language if language is not specified.
        :type github_url: Optional[str]
        :param extractor_option: List of extractor options in the form `name=value`.
        :type extractor_option: Optional[List[str]]
        :param overwrite: If True, allows overwriting an existing database.
        :type overwrite: bool
        :param force_overwrite: If True, forces overwrite even if it doesn’t look like a database.
        :type force_overwrite: bool
        :param allow_missing_source_root: If True, allows proceeding even if the source root doesn’t exist.
        :type allow_missing_source_root: bool
        :param begin_tracing: Enables indirect build tracing scripts.
        :type begin_tracing: bool
        :param db_cluster: Enables database clustering.
        :type db_cluster: bool

        :raises subprocess.CalledProcessError: If the initialization process encounters an error.
        """

        if isinstance(database_path, Path):
            database_path = str(database_path)
        if isinstance(source_root, Path):
            source_root = str(source_root)

        commands = [
            self.codeql_bin,
            "database",
            "init",
            "--source-root",
            source_root,
            database_path,
        ]

        if language:
            if isinstance(language, list):
                commands.append("--language=" + ",".join(language))
            else:
                commands.append("--language=" + language)

        if build_mode:
            commands.append("--build-mode=" + build_mode)

        if github_auth_stdin:
            commands.append("--github-auth-stdin")

        if github_url:
            commands.append("--github-url=" + github_url)

        if extractor_option:
            for option in extractor_option:
                commands.append(f"--extractor-option={option}")

        if overwrite:
            commands.append("--overwrite")

        if force_overwrite:
            commands.append("--force-overwrite")

        if allow_missing_source_root:
            commands.append("--allow-missing-source-root")

        if begin_tracing:
            commands.append("--begin-tracing")

        if db_cluster:
            commands.append("--db-cluster")

        # Run the command
        codeql_results = subprocess.run(
            commands,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if codeql_results.returncode == 0:
            log_fn = logger.info
        else:
            log_fn = logger.error
        if codeql_results.stdout:
            log_fn(codeql_results.stdout)
        if codeql_results.stderr:
            log_fn(codeql_results.stderr)

    def database_index_files(
        self,
        database_path: Union[Path, str],
        language: str,
        threads: Optional[int] = None,
        ram: Optional[int] = None,
        working_dir: Optional[Union[Path, str]] = None,
        extractor_options: Optional[List[str]] = None,
        extractor_options_file: Optional[Union[Path, str]] = None,
        include_extensions: Optional[List[str]] = None,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        prune: Optional[List[str]] = None,
        size_limit: Optional[str] = None,
        total_size_limit: Optional[str] = None,
        follow_symlinks: bool = True,
        find_any: bool = False,
    ) -> None:
        """
        Index files for a CodeQL database using the specified extractor and options.

        :param database_path: Path to the CodeQL database.
        :type database_path: Union[Path, str]
        :param language: The language for which to index files.
        :type language: str
        :param threads: Number of threads to use.
        :type threads: Optional[int]
        :param ram: RAM limit in MB.
        :type ram: Optional[int]
        :param working_dir: Directory in which to execute the command.
        :type working_dir: Optional[Union[Path, str]]
        :param extractor_options: List of extractor options in the form "name=value".
        :type extractor_options: Optional[List[str]]
        :param extractor_options_file: Path to the extractor options bundle file.
        :type extractor_options_file: Optional[Union[Path, str]]
        :param include_extensions: List of file extensions to include.
        :type include_extensions: Optional[List[str]]
        :param include: Glob patterns to include files.
        :type include: Optional[List[str]]
        :param exclude: Glob patterns to exclude files.
        :type exclude: Optional[List[str]]
        :param prune: Glob patterns to prune files.
        :type prune: Optional[List[str]]
        :param size_limit: Maximum file size to include.
        :type size_limit: Optional[str]
        :param total_size_limit: Total size limit for indexed files.
        :type total_size_limit: Optional[str]
        :param follow_symlinks: Whether to follow symbolic links.
        :type follow_symlinks: bool
        :param find_any: If True, stop after finding one match.
        :type find_any: bool

        :raises subprocess.CalledProcessError: If the indexing process encounters an error.
        """

        if isinstance(database_path, Path):
            database_path = str(database_path)
        commands = [
            self.codeql_bin,
            "database",
            "index-files",
            "--language=" + language,
            database_path,
        ]

        if threads is not None:
            commands.append(f"--threads={threads}")
        if ram is not None:
            commands.append(f"--ram={ram}")
        if extractor_options:
            commands.extend(f"--extractor-option={opt}" for opt in extractor_options)
        if extractor_options_file:
            commands.append(f"--extractor-options-file={extractor_options_file}")
        if include_extensions:
            commands.extend(f"--include-extension={ext}" for ext in include_extensions)
        if include:
            commands.extend(f"--include={glob}" for glob in include)
        if exclude:
            commands.extend(f"--exclude={glob}" for glob in exclude)
        if prune:
            commands.extend(f"--prune={glob}" for glob in prune)
        if size_limit:
            commands.append(f"--size-limit={size_limit}")
        if total_size_limit:
            commands.append(f"--total-size-limit={total_size_limit}")
        if follow_symlinks:
            commands.append("--follow-symlinks")
        else:
            commands.append("--no-follow-symlinks")
        if find_any:
            commands.append("--find-any")

        # Run the command
        codeql_results = subprocess.run(
            commands,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if codeql_results.returncode == 0:
            log_fn = logger.info
        else:
            log_fn = logger.error
        if codeql_results.stdout:
            log_fn(codeql_results.stdout)
        if codeql_results.stderr:
            log_fn(codeql_results.stderr)

    def database_bundle(self, database_path: Union[Path, str]) -> None:
        raise NotImplementedError()

    def database_unbundle(self, database_path: Union[Path, str]) -> None:
        raise NotImplementedError()

    def database_upgrade(
        self,
        database_path: Union[Path, str],
        search_path: Optional[Union[Path, str, List[Union[Path, str]]]] = None,
        additional_packs: Optional[Union[Path, str, List[Union[Path, str]]]] = None,
        target_dbscheme: Optional[Union[Path, str]] = None,
        allow_downgrades: bool = False,
        threads: Optional[int] = None,
        ram: Optional[int] = None,
    ) -> None:
        """
        Upgrades a CodeQL database to be compatible with the current tools.

        :param database_path: Path to the CodeQL database to be upgraded.
        :type database_path: Union[Path, str]
        :param search_path: Optional list of directories containing QL packages for upgrade schemes.
        :type search_path: Optional[Union[Path, str, List[Union[Path, str]]]]
        :param additional_packs: Optional list of additional directories to search for upgrade schemes.
        :type additional_packs: Optional[Union[Path, str, List[Union[Path, str]]]]
        :param target_dbscheme: Path to the target dbscheme file to upgrade to.
        :type target_dbscheme: Optional[Union[Path, str]]
        :param allow_downgrades: Whether to allow downgrades during the upgrade process.
        :type allow_downgrades: bool
        :param threads: Number of threads to use for the upgrade process.
        :type threads: Optional[int]
        :param ram: Maximum RAM in MB to use for the upgrade process.
        :type ram: Optional[int]

        :raises subprocess.CalledProcessError: If the upgrade process encounters an error.
        """
        if isinstance(database_path, Path):
            database_path = str(database_path)

        commands = [
            self.codeql_bin,
            "database",
            "upgrade",
            database_path,
        ]

        if search_path:
            if isinstance(search_path, list):
                search_path = ":".join(map(str, search_path))
            commands.extend(["--search-path", str(search_path)])

        if additional_packs:
            if isinstance(additional_packs, list):
                additional_packs = ":".join(map(str, additional_packs))
            commands.extend(["--additional-packs", str(additional_packs)])

        if target_dbscheme:
            commands.extend(["--target-dbscheme", str(target_dbscheme)])

        if allow_downgrades:
            commands.append("--allow-downgrades")
        else:
            commands.append("--no-allow-downgrades")

        if threads is not None:
            commands.extend(["--threads", str(threads)])

        if ram is not None:
            commands.extend(["--ram", str(ram)])

        # Run the command
        codeql_results = subprocess.run(
            commands,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if codeql_results.returncode == 0:
            log_fn = logger.info
        else:
            log_fn = logger.error
        if codeql_results.stdout:
            log_fn(codeql_results.stdout)
        if codeql_results.stderr:
            log_fn(codeql_results.stderr)

    def database_export_diagnostics(self, database_path: Union[Path, str]) -> None:
        raise NotImplementedError()

    def run_query(self, database_path: Union[Path, str]) -> None:
        """
        Please reference the page: https://docs.github.com/zh/code-security/codeql-cli/codeql-cli-manual/query-run
        """

    def database_run_queries(
        self,
        database_path: Union[Path, str],
        queries: Union[List[str], str],
        threads: Optional[int] = 1,
        ram: Optional[int] = 2048,
        model_packs: Optional[List[str]] = None,
        threat_models: Optional[List[str]] = None,
        timeout: Optional[int] = 0,
        no_rerun: bool = False,
        save_cache: bool = False,
        evaluator_log: Optional[str] = None,
        warnings: str = "show",
    ) -> None:
        """
        Runs a set of CodeQL queries on the specified database.

        :param database: Path to the CodeQL database.
        :type database: str
        :param queries: List of queries to execute. Each query can be a file, directory, or package path.
        :type queries: Union[List[str], str]
        :param threads: Number of threads to use for query evaluation. Defaults to 1.
        :type threads: Optional[int]
        :param ram: Maximum RAM usage in MB. Defaults to 2048 MB.
        :type ram: Optional[int]
        :param model_packs: List of CodeQL package names to use as model packs.
        :type model_packs: Optional[List[str]]
        :param threat_models: List of threat models to enable or disable.
        :type threat_models: Optional[List[str]]
        :param timeout: Timeout for query evaluation in seconds. Defaults to 0 (no timeout).
        :type timeout: Optional[int]
        :param no_rerun: If True, skips rerunning queries with existing results.
        :type no_rerun: bool
        :param save_cache: If True, saves intermediate results to disk cache.
        :type save_cache: bool
        :param evaluator_log: Path to the file for structured evaluator log output.
        :type evaluator_log: Optional[str]
        :param warnings: Controls compiler warnings display; options are 'hide', 'show' (default), or 'error'.
        :type warnings: str

        :returns: None
        :rtype: None
        """
        if isinstance(database_path, Path):
            database_path = str(database_path)
        commands = [
            self.codeql_bin,
            "database",
            "run-queries",
            "--threads",
            str(threads),
            "--ram",
            str(ram),
            database_path,
        ]

        # Add the queries
        if isinstance(queries, str):
            queries = [queries]
        commands.extend(queries)

        # Add optional model packs
        if model_packs:
            for pack in model_packs:
                commands.append(f"--model-packs={pack}")

        # Add optional threat models
        if threat_models:
            for model in threat_models:
                commands.append(f"--threat-model={model}")

        # Add other options
        if no_rerun:
            commands.append("--no-rerun")
        if save_cache:
            commands.append("--save-cache")
        if evaluator_log:
            commands.extend(["--evaluator-log", evaluator_log])
        if warnings:
            commands.extend(["--warnings", warnings])

        # Add timeout if specified
        if timeout is None:
            timeout = 0
        if timeout > 0:
            commands.extend(["--timeout", str(timeout)])

        # Run the command
        codeql_results = subprocess.run(
            commands,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if codeql_results.returncode == 0:
            log_fn = logger.info
        else:
            log_fn = logger.error
        if codeql_results.stdout:
            log_fn(codeql_results.stdout)
        if codeql_results.stderr:
            log_fn(codeql_results.stderr)

    def bqrs_decode(
        self,
        bqrs_file: Union[Path, str],
        output_file: Optional[Union[Path, str]] = None,
        result_set: Optional[str] = None,
        sort_key: Optional[List[str]] = None,
        sort_direction: Optional[List[Literal["asc", "desc"]]] = None,
        format: Literal["text", "csv", "json", "bqrs"] = "text",
        no_titles: bool = False,
        entities: Optional[List[str]] = None,
        rows: Optional[int] = None,
        start_at: Optional[int] = None,
    ) -> None:
        """
        Decodes a BQRS file into a desired format (text, csv, json, or bqrs).

        :param bqrs_file: The BQRS file to decode.
        :type bqrs_file: Union[Path, str]
        :param output_file: The file to write the decoded output to.
        :type output_file: Optional[Union[Path, str]]
        :param result_set: The result set to decode from the BQRS file.
        :type result_set: Optional[str]
        :param sort_key: The columns to sort the result set by.
        :type sort_key: Optional[List[str]]
        :param sort_direction: The sorting direction for each column.
        :type sort_direction: Optional[List[Literal['asc', 'desc']]]
        :param format: The output format (default is 'text').
        :type format: Literal['text', 'csv', 'json', 'bqrs']
        :param no_titles: Whether to omit column titles in text and csv formats (default is False).
        :type no_titles: bool
        :param entities: Advanced option for controlling entity column display.
        :type entities: Optional[List[str]]
        :param rows: The number of rows to output (from the top or starting at --start-at).
        :type rows: Optional[int]
        :param start_at: The byte offset to start output at.
        :type start_at: Optional[int]

        :returns: None
        :rtype: None
        """

        if isinstance(bqrs_file, Path):
            bqrs_file = str(bqrs_file)

        if output_file:
            if isinstance(output_file, Path):
                output_file = str(output_file)

        # Base command for decoding the BQRS file
        commands = [self.codeql_bin, "bqrs", "decode", bqrs_file]

        # Output file option
        if output_file:
            commands.extend(["--output", output_file])

        # Result set option
        if result_set:
            commands.extend(["--result-set", result_set])

        # Sorting options
        if sort_key:
            commands.extend(["--sort-key", ",".join(sort_key)])

        if sort_direction:
            commands.extend(["--sort-direction", ",".join(sort_direction)])

        # Format option
        commands.extend(["--format", format])

        # No titles option for text and csv formats
        if no_titles:
            commands.append("--no-titles")

        # Entities option for advanced output formatting
        if entities:
            commands.extend(["--entities", ",".join(entities)])

        # Pagination options
        if rows is not None:
            commands.extend(["--rows", str(rows)])

        if start_at is not None:
            commands.extend(["--start-at", str(start_at)])

        # Run the command
        codeql_results = subprocess.run(
            commands,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if codeql_results.returncode == 0:
            log_fn = logger.info
        else:
            log_fn = logger.error
        if codeql_results.stdout:
            log_fn(codeql_results.stdout)
        if codeql_results.stderr:
            log_fn(codeql_results.stderr)

    def bqrs_diff(
        self,
        file1: Union[Path, str],
        file2: Union[Path, str],
        left: Optional[Union[Path, str]] = None,
        right: Optional[Union[Path, str]] = None,
        both: Optional[Union[Path, str]] = None,
        retain_result_sets: Optional[str] = "nodes,edges,subpaths",
        compare_internal_ids: bool = False,
    ) -> None:
        """
        Compares two CodeQL BQRS result sets and outputs the differences.

        :param file1: The first BQRS file to compare.
        :type file1: Union[Path, str]
        :param file2: The second BQRS file to compare.
        :type file2: Union[Path, str]
        :param left: If provided, writes lines only present in file1.
        :type left: Optional[Union[Path, str]]
        :param right: If provided, writes lines only present in file2.
        :type right: Optional[Union[Path, str]]
        :param both: If provided, writes lines present in both file1 and file2.
        :type both: Optional[Union[Path, str]]
        :param retain_result_sets: Comma-separated list of result set names to retain without comparison.
        :type retain_result_sets: Optional[str]
        :param compare_internal_ids: Whether to include internal entity IDs in the comparison.
        :type compare_internal_ids: bool

        :raises subprocess.CalledProcessError: If the comparison process encounters an error.
        """
        if isinstance(file1, Path):
            file1 = str(file1)
        if isinstance(file2, Path):
            file2 = str(file2)
        if left and isinstance(left, Path):
            left = str(left)
        if right and isinstance(right, Path):
            right = str(right)
        if both and isinstance(both, Path):
            both = str(both)

        commands = [self.codeql_bin, "bqrs", "diff", file1, file2]

        if left:
            commands.extend(["--left", left])

        if right:
            commands.extend(["--right", right])

        if both:
            commands.extend(["--both", both])

        if retain_result_sets:
            commands.extend(["--retain-result-sets", retain_result_sets])

        if compare_internal_ids:
            commands.append("--compare-internal-ids")

        # Run the command
        codeql_results = subprocess.run(
            commands,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if codeql_results.returncode == 0:
            log_fn = logger.info
        else:
            log_fn = logger.error
        if codeql_results.stdout:
            log_fn(codeql_results.stdout)
        if codeql_results.stderr:
            log_fn(codeql_results.stderr)

    def bqrs_hash(self, file: Union[Path, str]) -> str:
        """
        Calculates the stable hash of a BQRS file.

        :param file: The path to the BQRS file to hash.
        :type file: Union[Path, str]

        :returns: The stable hash of the BQRS file.
        :rtype: str

        :raises subprocess.CalledProcessError: If the hashing process encounters an error.
        """
        if isinstance(file, Path):
            file = str(file)

        # Prepare the command for hashing the BQRS file
        commands = [
            self.codeql_bin,
            "bqrs",
            "hash",
            file,
        ]

        # Execute the command
        result = subprocess.run(commands, text=True, capture_output=True, check=True)

        # Extract the hash from the command output
        return result.stdout.strip()

    def bqrs_info(
        self,
        bqrs_file: Union[Path, str],
        format: Literal["text", "json"] = "text",
        paginate_rows: Optional[int] = None,
        paginate_result_set: Optional[str] = None,
    ) -> None:
        """
        Displays metadata information for a BQRS file.

        :param bqrs_file: The path to the BQRS file.
        :type bqrs_file: Union[Path, str]

        :param format: The output format. Default is "text".
        :type format: Literal["text", "json"]

        :param paginate_rows: When used with --format=json, this calculates a byte offset table for paginated results.
        :type paginate_rows: Optional[int]

        :param paginate_result_set: Only process the result set with this name for pagination.
        :type paginate_result_set: Optional[str]

        :raises subprocess.CalledProcessError: If the command fails.
        """
        if isinstance(bqrs_file, Path):
            bqrs_file = str(bqrs_file)

        # Prepare the base command
        commands = [
            self.codeql_bin,
            "bqrs",
            "info",
            bqrs_file,
        ]

        # Add optional flags
        if format:
            commands.append(f"--format={format}")

        if paginate_rows is not None:
            commands.append(f"--paginate-rows={paginate_rows}")

        if paginate_result_set:
            commands.append(f"--paginate-result-set={paginate_result_set}")

        # Run the command
        codeql_results = subprocess.run(
            commands,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if codeql_results.returncode == 0:
            log_fn = logger.info
        else:
            log_fn = logger.error
        if codeql_results.stdout:
            log_fn(codeql_results.stdout)
        if codeql_results.stderr:
            log_fn(codeql_results.stderr)

    def bqrs_interpret(
        self,
        bqrs_file: Union[Path, str],
        output: Union[Path, str],
        format: Literal[
            "csv", "sarif-latest", "sarifv2.1.0", "graphtext", "dgml", "dot"
        ] = "csv",
        query_metadata: List[Tuple[str, str]] = [],
        max_paths: Optional[int] = 4,
        sarif_add_file_contents: Optional[bool] = None,
        sarif_add_snippets: Optional[bool] = None,
        sarif_add_query_help: Optional[bool] = None,
        sarif_include_query_help: Optional[
            Literal["always", "custom_queries_only", "never"]
        ] = None,
        no_sarif_include_alert_provenance: Optional[bool] = None,
        sarif_group_rules_by_pack: Optional[bool] = None,
        sarif_multicause_markdown: Optional[bool] = None,
        no_sarif_minify: Optional[bool] = None,
        sarif_run_property: Optional[List[Tuple[str, str]]] = None,
        no_group_results: Optional[bool] = None,
        csv_location_format: Literal[
            "uri", "line-column", "offset-length"
        ] = "line-column",
        dot_location_url_format: Optional[str] = None,
        sublanguage_file_coverage: Optional[bool] = None,
        sarif_category: Optional[str] = None,
        threads: Optional[int] = 1,
        column_kind: Optional[Literal["utf8", "utf16", "utf32", "byte"]] = None,
        unicode_new_lines: Optional[bool] = None,
        source_archive: Optional[Union[Path, str]] = None,
        source_location_prefix: Optional[Union[Path, str]] = None,
    ) -> None:
        """
        Interprets a single BQRS file and generates output in the specified format.

        :param bqrs_file: The BQRS file to interpret.
        :type bqrs_file: Union[Path, str]

        :param format: The format of the output.
        :type format: Literal["csv", "sarif-latest", "sarifv2.1.0", "graphtext", "dgml"]

        :param output: The output path for the results.
        :type output: Union[Path, str]

        :param query_metadata: A list of query metadata key-value pairs.
        :type query_metadata: List[Tuple[str, str]]

        :param max_paths: The maximum number of paths to generate for each alert with paths.
        :type max_paths: Optional[int]

        :param sarif_add_file_contents: Whether to include full file contents in SARIF output.
        :type sarif_add_file_contents: bool

        :param sarif_add_snippets: Whether to include code snippets in SARIF output.
        :type sarif_add_snippets: bool

        :param sarif_add_query_help: Whether to include query help in SARIF output.
        :type sarif_add_query_help: bool

        :param sarif_include_query_help: Specifies when to include query help in SARIF output.
        :type sarif_include_query_help: Literal["always", "custom_queries_only", "never"]

        :param no_sarif_include_alert_provenance: Whether to exclude alert provenance in SARIF output.
        :type no_sarif_include_alert_provenance: bool

        :param sarif_group_rules_by_pack: Whether to group rules by pack in SARIF output.
        :type sarif_group_rules_by_pack: bool

        :param sarif_multicause_markdown: Whether to include multi-cause alerts as Markdown in SARIF output.
        :type sarif_multicause_markdown: bool

        :param no_sarif_minify: Whether to generate minified SARIF output.
        :type no_sarif_minify: bool

        :param sarif_run_property: A list of key-value pairs to add to the SARIF run properties.
        :type sarif_run_property: Optional[List[dict]]

        :param no_group_results: Whether to generate a result per message instead of per unique location.
        :type no_group_results: bool

        :param csv_location_format: The format for locations in CSV output.
        :type csv_location_format: Literal["uri", "line-column", "offset-length"]

        :param dot_location_url_format: The format for file locations URLs in DOT output.
        :type dot_location_url_format: Optional[str]

        :param sublanguage_file_coverage: Whether to use sublanguage file coverage information.
        :type sublanguage_file_coverage: bool

        :param sarif_category: The category for the SARIF output.
        :type sarif_category: Optional[str]

        :param threads: The number of threads to use for path calculation.
        :type threads: Optional[int]

        :param column_kind: The column kind for SARIF output.
        :type column_kind: Optional[Literal["utf8", "utf16", "utf32", "byte"]]

        :param unicode_new_lines: Whether to treat Unicode line separators as new lines in SARIF output.
        :type unicode_new_lines: bool

        :param source_archive: The source archive directory or zip file.
        :type source_archive: Optional[Union[Path, str]]

        :param source_location_prefix: The source location prefix.
        :type source_location_prefix: Optional[Union[Path, str]]

        :raises subprocess.CalledProcessError: If the interpretation process encounters an error.
        """

        if isinstance(bqrs_file, Path):
            bqrs_file = str(bqrs_file)
        if isinstance(output, Path):
            output = str(output)
        if source_archive and isinstance(source_archive, Path):
            source_archive = str(source_archive)
        if source_location_prefix and isinstance(source_location_prefix, Path):
            source_location_prefix = str(source_location_prefix)

        commands = [
            self.codeql_bin,
            "bqrs",
            "interpret",
            "--format=" + format,
            "--output=" + output,
            bqrs_file,
        ]

        for key, value in query_metadata:
            commands.extend(["-t", f"{key}={value}"])

        if max_paths:
            commands.extend(["--max-paths", str(max_paths)])

        if sarif_add_file_contents is not None:
            if sarif_add_file_contents:
                commands.append("--sarif-add-file-contents")
            else:
                commands.append("--no-sarif-add-file-contents")
        if sarif_add_snippets is not None:
            if sarif_add_snippets:
                commands.append("--sarif-add-snippets")
            else:
                commands.append("--no-sarif-add-snippets")
        if sarif_add_query_help is not None:
            if sarif_add_query_help:
                commands.append("--sarif-add-query-help")
            else:
                commands.append("--no-sarif-add-query-help")

        if sarif_include_query_help is not None:
            commands.extend(["--sarif-include-query-help", sarif_include_query_help])

        if no_sarif_include_alert_provenance:
            commands.append("--no-sarif-include-alert-provenance")
        if sarif_group_rules_by_pack is not None:
            if sarif_group_rules_by_pack:
                commands.append("--sarif-group-rules-by-pack")
            else:
                commands.append("--no-sarif-group-rules-by-pack")
        if sarif_multicause_markdown is not None:
            if sarif_multicause_markdown:
                commands.append("--sarif-multicause-markdown")
            else:
                commands.append("--no-sarif-multicause-markdown")
        if no_sarif_minify:
            commands.append("--no-sarif-minify")

        if sarif_run_property:
            for key, value in sarif_run_property:
                commands.extend(["--sarif-run-property", f"{key}={value}"])

        if no_group_results:
            commands.append("--no-group-results")
        commands.extend(["--csv-location-format", csv_location_format])

        if dot_location_url_format:
            commands.extend(["--dot-location-url-format", dot_location_url_format])

        if sublanguage_file_coverage:
            commands.append("--sublanguage-file-coverage")

        if sarif_category:
            commands.extend(["--sarif-category", sarif_category])

        if threads:
            commands.extend(["-j", str(threads)])

        if column_kind:
            commands.extend(["--column-kind", column_kind])

        if not unicode_new_lines:
            commands.append("--no-unicode-new-lines")

        if source_archive:
            commands.extend(["--source-archive", source_archive])
        if source_location_prefix:
            commands.extend(["--source-location-prefix", source_location_prefix])

        # Run the command
        codeql_results = subprocess.run(
            commands,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if codeql_results.returncode == 0:
            log_fn = logger.info
        else:
            log_fn = logger.error
        if codeql_results.stdout:
            log_fn(codeql_results.stdout)
        if codeql_results.stderr:
            log_fn(codeql_results.stderr)
