# EdgeCentric-LLM-C2Rust

Edge-centric LLM-based transpilation prototype for C to Rust.

## Prerequisite
### System Software
- unzip, curl, wget
- cargo 1.86: As suggested in [the official page](https://doc.rust-lang.org/cargo/getting-started/installation.html):
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```
- conda 25.5: As suggested in [the official page](https://www.anaconda.com/docs/getting-started/miniconda/install#linux)
```bash
mkdir -p ~/miniconda3
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh
bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
rm ~/miniconda3/miniconda.sh
source ~/miniconda3/bin/activate
conda init --all
```
- codeql:
```bash
wget -P ~ https://github.com/github/codeql-action/releases/download/codeql-bundle-v2.22.2/codeql-bundle-linux64.tar.gz

```

### Python Environment
We recommend using `conda` to quickly setup the Python environment.
```bash
conda env create -f environment.yml
conda activate edge-centric
```

## Data

Benchmark dataset, output data are compressed in `data.zip`. To extract, run this command in shell:

```bash
unzip data.zip
```

There are three directories in `data.zip`:
- `benchmark`: the benchmark of C projects for transpilation
- `output`: the transpilation results by Edge-Centric and Node-Centric with DeepSeek, Qwen, Doubao. These results have been manually repaired the syntax errors and project configuration errors.
- `test_bench`: some selected results for evaluation functional correctness. They have been rid of compilation errors by manually repair.

## Transpilation Tool
```bash
python -m llm_c2rust -i <C project path> -o <output path> [--config <config path>] [--baseline] [--codeql <binary path of CodeQL>] 
```

Explanation:
- `<C project path>`: Path of C project to be transpiled. Note that the C project should have the build procedures provided in `llm_c2rust_build.sh`. Otherwise, our transpilation tool will make the simplest build, which is to compile every source files.
- `<output path>`: where the resulting Rust project should be put.
- `<config path>`: default to `./config.yml`, containing the LLM API information, such as `base_url`, `api-keys`. Note that you should fill the `<API-KEY>` with your own keys before you run.
- `--baseline`: enable node-centric method. If not given, out tools use edge-centric by default.
- `<binary path of CodeQL>`: specify the location of CodeQL binary. Default to `~/codeql/codeql`.
## Evaluation
### Get Results
```bash
python -m scripts.run_evaluation
```
### RQ1 & RQ2
```bash
python -m scripts.rq1
python -m scripts.rq2
```

This will produce 1 table and 4 figures as in the paper.

### RQ3

There is no automation scripts to examine the functional correctness of the results.

However, for those tested with test suites, you can test it like:
```bash
cd test_bench/libcsv
cargo test
```

For those tested with example usage，you have to follow the operations detailed in the paper. You can run it like:
```bash
cd tinyhttpd
cargo run
```