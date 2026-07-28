# Reproducing the Core LM evidence

The reproducibility archive contains only the files needed to inspect the
implementation, rerun the test suite and benchmark, rebuild the macOS app, and
trace every number in the paper to machine-readable evidence.

## Requirements

- macOS 13 or newer for the SwiftUI application
- Swift 5.9 or newer
- Python 3.11 or newer
- NumPy

## Verify the implementation

From the extracted archive:

```sh
./run_tests.sh
```

The expected result is 14 passing tests.

## Re-run the 115-run benchmark

```sh
./run_benchmark.sh
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
