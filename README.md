# EdgeCentric-LLM-C2Rust

Edge-centric LLM-based transpilation prototype for C to Rust.

## Data

Benchmark dataset, output data are compressed in `data.zip`. To extract, run this command in shell:

```bash
unzip data.zip
```

This command requires `unzip` to be installed. You can install it by:

- Debian/Ubuntu:
  ```bash
  sudo apt install unzip
  ```
- Arch Linux:
  ```bash
  sudo pacman -S unzip
  ```
- Fedora/RHEL:
  ```bash
  sudo dnf install unzip
  ```

There are three directories in `data.zip`:
- `benchmark`: the benchmark of C projects for transpilation
- `output`: the transpilation results by Edge-Centric and Node-Centric with DeepSeek, Qwen, Doubao. These results have been manually repaired the syntax errors and project configuration errors.
- `test_bench`: some selected results for evaluation functional correctness. They have been rid of compilation errors by manually repair.
## Edge-Centric Implementaion & Baseline

To be continue
## Evaluation

To be continue