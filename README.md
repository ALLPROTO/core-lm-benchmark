# Core LM Benchmark

[![Verify](https://github.com/ALLPROTO/core-lm-benchmark/actions/workflows/verify.yml/badge.svg)](https://github.com/ALLPROTO/core-lm-benchmark/actions/workflows/verify.yml)

Core LM Benchmark is an open-source macOS application for checking a real
KV-cache compression result on your own machine. It builds from source, loads a
pinned Qwen model, creates compressed cache containers, replays them through the
model, displays every architecture module, and independently verifies the
result and application receipt.

The release application has one clear workflow: **Compression Proof**.
Synthetic experiments, rejected approaches, protocol revisions, and release
engineering are kept in the separate [development record](docs/development/HISTORY.md).

## Build and verify

Requirements:

- Apple Silicon Mac with macOS 14 or newer;
- Python 3.12 from a trusted installation;
- Apple's free Command Line Tools or Xcode;
- at least 6 GB of free disk space;
- network access for the first pinned model and dataset download.

Run the complete proof:

```sh
git clone https://github.com/ALLPROTO/core-lm-benchmark.git
cd core-lm-benchmark
./run_local_app_proof.sh
```

The command creates a fresh Python runtime with hash-locked packages and an
exact signed runtime manifest, verifies the model and dataset bytes, builds
`dist/CoreLMBenchmark.app`, applies a local ad-hoc signature, runs the real
model on Apple MPS, and checks the new result against a random challenge.

No Apple Developer Program membership, Apple signing account, paid certificate,
Developer ID identity, or notarization is required. The repository distributes
source so the verifier builds and signs the application locally.

See [Build and verify](docs/BUILD_AND_VERIFY.md) for the detailed walkthrough
and troubleshooting.

This flow verifies the current public checkout. To reproduce the exact frozen
publication instead, use its recorded release tag and checksums, then follow
the [reproducibility archive instructions](publication/reproducibility/README.md).

## Verified reference result

| Evaluation | Predictions | Compression vs BF16 | Delta NLL | Top-1 agreement | Verdict |
|---|---:|---:|---:|---:|---|
| Registered prospective holdout | 4,096 | 2.053291x | -0.000061 | 99.3896% | **PASS** |
| Native application integration | 1,024 | 2.052384x | -0.00000849 | 99.5117% | **PASS** |

Three challenge-bound application runs from one unchanged local bundle produced
the same scientific metrics and 192-entry container manifest. Only timestamps,
timing measurements, and their derived receipt digest changed.

These measurements cover the pinned `Qwen/Qwen2.5-0.5B` revision, registered
WikiText-2 windows, canonical BF16 prefill KV cache, teacher-forced replay, and
Apple MPS. They are not claims about full-model weight compression, free-running
generation, latency, serving throughput, arbitrary models, or state of the art.

Read [Results](docs/RESULTS.md) and [Limitations](docs/LIMITATIONS.md) before
reusing the numbers.

## Use the application

To build without automatically running the full proof:

```sh
./build_local_app.sh
open dist/CoreLMBenchmark.app
```

The release interface opens directly on **Compression Proof**. Its sidebar
shows the state of model loading, prefill, cache extraction, compression,
rebuild, continuation, metrics, and verification. Press **Run Compression
Proof** to produce a new local result.

Development builds expose the synthetic benchmark workbench separately; they
are not part of the final-user flow.

## Documentation

- [Build and verify](docs/BUILD_AND_VERIFY.md) — ordinary-user installation and proof flow.
- [Results](docs/RESULTS.md) — current measurements and what PASS means.
- [Limitations](docs/LIMITATIONS.md) — honest boundary of the demonstrated claim.
- [Architecture](ARCHITECTURE.md) — final application and verifier pipeline.
- [Security policy](SECURITY.md) — runtime, bundle, asset, and supply-chain controls.
- [Development history](docs/development/HISTORY.md) — versioned experiments and chronology.
- [Scientific identifiers](docs/development/SCIENTIFIC_IDENTIFIERS.md) — internal names retained for reproducibility.
- [Release process](docs/development/RELEASE_PROCESS.md) — maintainer-only publication workflow.

## Repository map

- `App/` — native SwiftUI application.
- `BenchmarkCore/` — deterministic synthetic measurement core.
- `RealLLM/` — pinned real-model runner, codec, and independent verifiers.
- `security/` — bundle, runtime, result, dependency, and workflow checks.
- `Tests/` and `TestsSwift/` — regression and security suites.
- `app-real-llm-evidence/` — sanitized native-application reference receipt.
- `docs/` — final-user documentation and separate development history.
- `publication/` — paper, submission source, and deterministic archive tooling.

## Citation and license

Citation metadata is provided in `CITATION.cff`. Author:
[Ivan Tyshchenko](https://orcid.org/0009-0000-7935-6090).

The software is released under the MIT License. The paper and submission source
retain their stated distribution terms.
