# Reproducing the Core LM evidence

The reproducibility archive contains the files needed to inspect the
implementation, rerun the test suite and benchmark, rebuild the macOS app, and
trace the historical VoidToken v3 result and the prospective VoidToken v5
result to machine-readable evidence.

## Requirements

- macOS 14 or newer for the SwiftUI application
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

All tests discovered under `Tests/` must pass. The count is intentionally not
hard-coded because new integrity tests are added with the protocol.

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
python3 publication/arxiv-v5/generate_figures.py
```

The v5 generator reads the adaptive development manifest plus the frozen
selection and holdout JSON records. The historical v3 generator remains in a
full repository clone under `publication/arxiv/`.

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

## Verify the historical real-LLM pilot

The archive also includes the checked-in exploratory Qwen KV-cache pilot. Its
negative verdicts remain intact and do not alter either the historical
115-run v3 result or the separate prospective v5 result.

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

## Verify VoidToken v5 development evidence

The archive contains the four exact adaptive development shards for validation
source blocks 0–31. They do not count as a prospective verdict.

```sh
python3 RealLLM/verify_voidtoken_v5_development.py
```

The verifier checks the manifest and raw file SHA-256 values, canonical result
digests, pinned revisions, candidate index `32`, source ranges, block records,
container byte accounting, structural replay, shard aggregates, Student-t and
Wilson bounds, and the combined observation.

To repeat one shard with separately installed pinned real-LLM dependencies and
cached inputs:

```sh
HF_HOME=/path/to/cache python \
  RealLLM/develop_voidtoken_v5.py \
  --device mps \
  --validation-start-block 0 \
  --validation-blocks 8 \
  --candidate-index 32 \
  --local-files-only \
  --output replay-validation-000-007.json
```

Repeat with start blocks `8`, `16`, and `24`.

## Verify prospective VoidToken v5 artifacts

In a full clone, fetch tags and require commit/tag provenance:

```sh
git fetch --tags --force
python3 RealLLM/verify_voidtoken_v5_evidence.py --require-git-provenance
```

In this extracted tar, run without that flag:

```sh
python3 RealLLM/verify_voidtoken_v5_evidence.py
```

Tar mode verifies artifact self-consistency only. It does not verify Git
objects, public tags, or a public timestamp; `PROVENANCE.json` states this
limitation explicitly. A tar extracted inside some other Git worktree is
rejected to prevent an accidental provenance downgrade.

The registered artifact state is `holdout-pass`. Selection and holdout each
pass all seven gates. The holdout records `2.0532909x` complete-container
compression, delta NLL `-0.0000609346`, top-1 agreement `4071/4096`,
blockwise top-1 lower 95% `0.9924722061`, and Wilson lower 95%
`0.9915430006`.

Frozen runner exits have scientific meaning:

- `0` — a PASS result was durably recorded;
- `2` — a valid terminal scientific FAIL was durably recorded;
- `1` after an attempt marker exists — terminal `CONSUMED_INCOMPLETE`.

A correct FAIL or incomplete marker is published unchanged and is not retried.
Selection FAIL permanently forbids a pretest tag and holdout.

## Archive integrity

`PROVENANCE.json` records the source-state mode, repository, commit when
available, v5 configuration/registration/implementation digests, evidence
state, and hashes of included evidence files. It is descriptive metadata, not
a replacement for Git history. The distribution-side `SHA256SUMS` verifies the
v5 arXiv source archive and the reproducibility archive.

Maintainers generate final release archives from a full repository clone—not
from this extracted tar—only after the lightweight release tag is public and
the worktree is clean:

```sh
RELEASE_TAG=voidtoken-v5-paper-v1
python3 publication/build_archives.py \
  --release-tag "$RELEASE_TAG" \
  --verify-determinism
python3 publication/build_archives.py \
  --release-tag "$RELEASE_TAG"
(cd output && shasum -a 256 -c SHA256SUMS)
```
