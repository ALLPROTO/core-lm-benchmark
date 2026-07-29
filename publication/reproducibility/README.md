# Reproducing the Core LM evidence

The reproducibility archive contains only the files needed to inspect the
implementation, rerun the test suite and benchmark, rebuild the macOS app, and
trace every number in the paper to machine-readable evidence.

## Requirements

- macOS 13 or newer for the SwiftUI application
- Swift 5.9 or newer
- Python 3.12 (the registered evidence uses 3.12.13)
- NumPy 2.3.5
- ReportLab 4.4.9 for regenerating the vector paper figures

## Verify the implementation

From the extracted archive:

```sh
python3 -m pip install -r requirements.txt
./run_tests.sh
```

The expected result is 34 passing tests.

## Re-run the 115-run benchmark

```sh
python3 BenchmarkCore/run_suite.py --full --output replay-results
```

The expected aggregate verdict is `PASS`. The exact gate is:

- compression ratio at least 4
- NRMSE at most 0.10
- cosine similarity at least 0.95
- absolute mean-energy drift at most 0.05
- zero invariant violations
- deterministic replay

The checked-in `benchmark-results/aggregate.json` names all 115 authoritative
JSON records. This indirection prevents older exploratory runs in a working
directory from entering the reported result.

To rerun the full matrix in a temporary directory and compare every scientific
field against the registered evidence:

```sh
python3 BenchmarkCore/verify_evidence.py
```

The verifier requires exact run IDs, input digests, configurations, Core state
SHA-256, VoidToken payload SHA-256, VoidToken container SHA-256, decoded
VoidToken trajectory SHA-256, invariants, and verdicts. Floating-point
diagnostics use `rtol=1e-4`, `atol=1e-5` for the PCA/LAPACK baseline; the exact
digests prevent this tolerance from accepting a different Core or VoidToken
byte stream or decoded trajectory.

## Regenerate the paper figures

```sh
python3 publication/arxiv/generate_figures.py
```

The generator reads only the registered run IDs named by
`benchmark-results/aggregate.json`.

## Build the native application

```sh
./package_app.sh
```

The application bundle is produced at `dist/CoreLMBenchmark.app`.

## Evidence chain

`BenchmarkCore/corelm_benchmark.py` defines the transition, codecs, metrics,
verdict, and serialization. `BenchmarkCore/run_suite.py` defines the evaluation
matrix. `Tests/test_benchmark.py` exercises invariants and regression gates.
`benchmark-results/aggregate.json` records the authoritative run identifiers.
The paper figure generator reads that aggregate and those records directly.

## Verify the separate real-LLM pilot

The archive also includes the checked-in Qwen KV-cache pilot. It does not alter
the 115-run paper result.

```sh
python3 -m pip install numpy==2.5.1 jsonschema==4.25.1
python3 RealLLM/verify_real_llm_evidence.py
```

The expected result is a successful evidence verification with two independent
scientific verdicts inside the aggregate: VoidToken `FAIL` and packed group
quantization `FAIL`. The latter passes the 2× compression and ΔNLL gates but
misses the runner's fixed 99% top-1 gate. This exploratory pilot had no
independent external preregistration timestamp before first test execution.

Repeating model inference requires the separate pinned environment and downloads
the pinned Qwen weights plus two pinned WikiText-2 parquet files:

```sh
python3 -m pip install -r RealLLM/requirements.txt
./run_real_llm_benchmark.sh
```

The recorded result is an Apple-Silicon/MPS pilot. Cross-device exact PyTorch
logits are not claimed.
