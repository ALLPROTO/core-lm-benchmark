# Core LM Benchmark

[![Verify](https://github.com/ALLPROTO/core-lm-benchmark/actions/workflows/verify.yml/badge.svg)](https://github.com/ALLPROTO/core-lm-benchmark/actions/workflows/verify.yml)

Core LM Benchmark is a native macOS application with an independent Python
measurement core for comparing Dense, PCA, and VoidToken v3 trajectory
representations. VoidToken v3 encodes a sparse, quantized residual against the
state actually reconstructed by the decoder, inserts byte-budgeted keyframes,
and round-trips through a validated binary container.

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

## Reproduce the evidence

Requirements:

- Python 3.10 or newer
- NumPy
- ReportLab for rebuilding the paper figures
- macOS 14 and Swift 5.9 or newer for the native application

Run the 20 implementation tests:

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

Exact identifiers, input digests, configurations, invariants, and verdicts must
match. Floating-point scientific values use the declared cross-platform
tolerance `rtol=1e-4`, `atol=1e-5`, which is orders of magnitude below the PASS
thresholds.

The test suite includes complete Dense, PCA, and VoidToken
`serialize -> parse -> decode` round trips plus rejection tests for truncated or
corrupted containers.

The authoritative `benchmark-results/aggregate.json` lists the exact run IDs
used by the paper. Only those JSON and Markdown records are committed.

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
