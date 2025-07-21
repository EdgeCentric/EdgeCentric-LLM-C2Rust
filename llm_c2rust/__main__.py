import argparse
from llm_c2rust.c2rust import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Translate C project to Rust language."
    )

    parser.add_argument(
        "-i", "--input", help="Input directory containing C project", required=True
    )
    parser.add_argument(
        "-o", "--output", help="Output directory to save Rust project", required=True
    )
    parser.add_argument("-m", "--model", help="The LLM model to use", required=True)
    parser.add_argument(
        "--config",
        default="./config.yml",
        help="The configuration file",
    )
    parser.add_argument(
        "--codeql",
        default="~/codeql/codeql",
        help="The codeql execution binary path",
    )
    parser.add_argument(
        "--codeql-db", default="/tmp/database", help="The codeql cache dataset path"
    )
    parser.add_argument(
        "--baseline",
        default=False,
        action="store_true",
        help="Enable node-centric method instead of edge-centric",
    )
    args = parser.parse_args()

    run(
        input_path=args.input,
        output_path=args.output,
        model=args.model,
        config_path=args.config,
        codeql=args.codeql,
        codeql_db=args.codeql_db,
        baseline=args.baseline,
    )
