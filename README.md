# Core LM Benchmark

[![Verify](https://github.com/ALLPROTO/core-lm-benchmark/actions/workflows/verify.yml/badge.svg)](https://github.com/ALLPROTO/core-lm-benchmark/actions/workflows/verify.yml)

Core LM Benchmark is a native macOS application with an independent Python
measurement core for comparing Dense, PCA, and VoidToken v3 trajectory
representations. VoidToken v3 encodes a sparse, quantized residual against the
state actually reconstructed by the decoder, inserts byte-budgeted keyframes,
and round-trips through the canonical `voidtoken-residual-keyframe-v4` binary
format. The previous v3 binary format remains readable through an explicit
legacy path; old readers reject the new format instead of silently applying
different arithmetic.

## Registered result

The checked-in evaluation contains **115 passing runs and zero failures**.

| Gate | Required | Observed worst case |
|---|---:|---:|
| Compression ratio | at least 4x | 4.2353x |
| NRMSE | at most 0.10 | 0.06089 |
| Cosine similarity | at least 0.95 | 0.99821 |
| Relative mean-energy drift | at most 0.05 | 0.04955 |
| Invariant violations | 0 | 0 |
| Deterministic replay | required | true |

The claim is deliberately bounded: these values establish a reproducible
operating region for the registered test matrix, not universal performance on
arbitrary learned-model states or task-level language-model quality.

## Real pretrained-model pilot

A separate exploratory pilot now compresses the actual 24-layer KV cache of the
pinned pretrained `Qwen/Qwen2.5-0.5B` model and feeds the decoded cache back
into Qwen for 1,024 held-out WikiText-2 next-token predictions.

| Family | Ratio vs BF16 | ΔNLL | PPL ratio | Top-1 agreement | Verdict |
|---|---:|---:|---:|---:|---|
| VoidToken v4 | 2.4184× | +0.203580 | 1.225783 | 79.88% | **FAIL** |
| Mixed group quant baseline | 2.0214× | +0.001356 | 1.001357 | 97.95% | **FAIL** |

Both verdicts use the runner's fixed gates of ≥2× compression, ΔNLL ≤0.01
nat/token, and ≥99% top-1 agreement. This exploratory pilot was not externally
preregistered before first test execution. The baseline passes the compression
and NLL gates but misses top-1; VoidToken misses both quality gates. These
negative results are kept intact and do not alter the separate 115/115
synthetic PASS.
See [`RealLLM/PROTOCOL.md`](RealLLM/PROTOCOL.md) and
[`real-llm-results/README.md`](real-llm-results/README.md).

## Reproduce the evidence

Requirements:

- Python 3.12 (the registered evidence uses 3.12.13)
- NumPy 2.3.5
- ReportLab 4.4.9 for rebuilding the paper figures
- macOS 14 and Swift 5.9 or newer for the native application

Run the 34 lightweight implementation tests:

```sh
python3 -m pip install -r requirements.txt
PYTHON_BIN=python3 ./run_tests.sh
```

Run one benchmark configuration:

```sh
PYTHON_BIN=python3 ./run_benchmark.sh \
  --dimension 96 \
  --steps 200 \
  --seed 42 \
  --scenario gaussian_bounded \
  --pca-components 8 \
  --top-k 16 \
  --qmax 127
```

Re-run the registered 115-run matrix:

```sh
python3 BenchmarkCore/run_suite.py --full --output output/replay-results
```

Verify a fresh 115-run replay against every registered scientific result:

```sh
python3 BenchmarkCore/verify_evidence.py
```

Run IDs, input digests, configurations, Core state SHA-256, VoidToken payload
SHA-256, VoidToken container SHA-256, decoded-trajectory SHA-256, invariants,
and verdicts must match exactly on macOS/ARM and Linux/x86. Floating-point
diagnostics are additionally checked with `rtol=1e-4`, `atol=1e-5` for the
PCA/LAPACK baseline; the tolerance cannot hide a different Core, VoidToken
stream, or decoded trajectory.

The test suite includes complete Dense, PCA, and VoidToken
`serialize -> parse -> decode` round trips plus rejection tests for truncated or
corrupted containers.

The authoritative `benchmark-results/aggregate.json` lists the exact run IDs
used by the paper. Only those JSON and Markdown records are committed.

Verify the checked-in real-LLM result without downloading model weights:

```sh
python -m pip install numpy==2.5.1 jsonschema==4.25.1
python RealLLM/verify_real_llm_evidence.py
```

To repeat the heavy model run, create a separate environment from
`RealLLM/requirements.txt`, set `HF_HOME` if desired, and run:

```sh
PYTHON_BIN=python ./run_real_llm_benchmark.sh --device mps
```

## Native macOS application

```sh
./package_app.sh
open dist/CoreLMBenchmark.app
```

The application invokes the same Python measurement core, reads real JSON
results, and does not synthesize dashboard values.

## Repository map

- `BenchmarkCore/` — deterministic system, codecs, metrics, and suite runner
- `Tests/` — unit and integration tests
- `App/` — native SwiftUI benchmark interface
- `benchmark-results/` — aggregate plus the 115 registered evidence records
- `RealLLM/` — pinned real-model protocol, codec baseline, runner, and verifier
- `real-llm-results/` — separate exploratory Qwen KV-cache pilot artifact
- `publication/arxiv/` — self-contained paper source and vector figures
- `publication/corelm_voidtoken_v3.pdf` — visually inspected paper
- `EVIDENCE.md` — result summary and acceptance gates
- `KNOWN_LIMITATIONS.md` — explicit boundary of the demonstrated claim

## Citation

Use the metadata in `CITATION.cff`. The paper is:

> Ivan Tyshchenko. “Closed-Loop Residual Tokenization for Stable Compression
> of Dynamical State Trajectories.” 2026.

Author ORCID: [0009-0000-7935-6090](https://orcid.org/0009-0000-7935-6090).

The software is released under the MIT License. The paper and arXiv submission
retain their own distribution terms.
