# Core LM Benchmark

[![Linux](https://github.com/ALLPROTO/core-lm-benchmark/actions/workflows/verify-linux.yml/badge.svg)](https://github.com/ALLPROTO/core-lm-benchmark/actions/workflows/verify-linux.yml)
[![macOS](https://github.com/ALLPROTO/core-lm-benchmark/actions/workflows/verify-macos.yml/badge.svg)](https://github.com/ALLPROTO/core-lm-benchmark/actions/workflows/verify-macos.yml)

Core LM Benchmark is an open-source, real-data benchmark for inspecting a
KV-cache compression result end to end. It loads a pinned Qwen model, evaluates
registered WikiText input, creates complete compressed cache containers,
fresh-parses them, replays the cache through the model, and independently
verifies the result.

The repository has two active platform targets and one read-only compatibility
contour:

| Contour | Deliverable | Compute path |
|---|---|---|
| macOS | Native SwiftUI application | Apple MPS |
| Linux | Command-line regression and raw evidence | x86_64 CPU |
| Beacon | Immutable-tag integrity verifier | No model or data execution |

## Choose your platform

Clone once, then use the single dispatcher:

```sh
git clone https://github.com/ALLPROTO/core-lm-benchmark.git
cd core-lm-benchmark
./corelm --help
```

### macOS application

Requirements: Apple Silicon, macOS 14 or newer, Swift 6, Python 3.12.13,
8 GB unified memory, 6 GiB free disk, and an active desktop session.

```sh
./corelm macos doctor
./corelm macos proof
```

The proof creates a fresh hash-locked runtime, verifies model and dataset
bytes, builds `dist/CoreLMBenchmark.app`, applies a local ad-hoc signature,
runs real Qwen on Apple MPS, and independently replays all 1,024 decisions.
No Apple developer account, paid certificate, Developer ID, or notarization is
required.

Build without starting the full proof:

```sh
./corelm macos build
open dist/CoreLMBenchmark.app
```

If Python 3.12.13 is missing, the optional owner-local bootstrap downloads the
fixed `astral-sh/python-build-standalone` archive and verifies SHA-256
`62aeee6161d57303a71a138b75fd5cc6fb8c89c4b1d9c7f0a052d89fa0b6652b`:

```sh
./corelm macos bootstrap
```

Prepare a hash-checked wheelhouse and model cache for later offline proofs:

```sh
./corelm macos prepare-offline
CORELM_OFFLINE=1 \
CORELM_WHEELHOUSE="$HOME/.cache/corelm/macos/wheelhouse" \
  ./corelm macos proof
```

See [the macOS guide](platforms/macos/README.md) and the detailed
[build-and-verify walkthrough](docs/BUILD_AND_VERIFY.md).

### Linux CPU regression

Requirements: Ubuntu 24.04 x86_64, Python 3.12.13, 8 GiB available memory,
and 6 GiB free disk.

```sh
./corelm linux doctor
./corelm linux build
./corelm linux run
```

The Linux path builds a separate CPU-only, hash-locked runtime, verifies the
same pinned model and real validation data, retains 192 containers and 1,024
token decisions, and runs the independent raw-evidence verifier. It is a
regression on already-public validation input, not a new blind or held-out
claim. See [the Linux guide](platforms/linux/README.md) and the
[recorded public VM run](docs/LINUX_REAL_QWEN.md).

## Real-data policy

Every supported current `./corelm` benchmark, application proof, model
evaluation, and scientific-evidence run uses the pinned pretrained Qwen model
on registered real WikiText input. Synthetic, generated, toy, or mocked input
is rejected from current metrics, evidence, PASS/FAIL claims, and publication
results. Deterministic fixtures are permitted only in isolated parser,
security, unit, and protocol-control tests; their outputs never enter a current
evidence or result directory.

The old supported synthetic suite entrypoint `BenchmarkCore/run_suite.py`, its
115 result pairs, verifier, schema, paper source, and PDF are absent from the
default branch. Their immutable historical bytes remain available only in the
published
[`voidtoken-v5-paper-v5`](https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/voidtoken-v5-paper-v5)
tag. One frozen compatibility source, `BenchmarkCore/corelm_benchmark.py`, must
remain byte-identical at its registered path until the beacon attempt because
it is part of the published implementation hash. Current v5 macOS/Linux runs
do not import or package it. Evidence verification does not execute it; it
hashes its registered path and bytes. Documented workflows execute it only for
historical-pilot reproduction and an isolated compatibility unit test. The
frozen file still contains a dormant, directly invocable historical synthetic
CLI; it is unsupported and its output cannot be accepted as current evidence.

## Verified reference results

| Evaluation | Predictions | Compression vs BF16 | Delta NLL | Top-1 agreement | Verdict |
|---|---:|---:|---:|---:|---|
| Registered prospective holdout | 4,096 | 2.053291x | -0.000061 | 99.3896% | **PASS** |
| Native macOS integration | 1,024 | 2.052384x | -0.00000849 | 99.5117% | **PASS** |
| Linux CPU regression | 1,024 | 2.052389x | +0.00002232 | 99.6094% | **PASS** |

The macOS and Linux integration rows use fixed public validation blocks
64-71. They demonstrate repeatability of the application, codec, retained
evidence, and verifiers; they are not blind samples or new generalization
evidence. CPU and Apple MPS values need not be bit-identical.

These measurements cover one pinned Qwen revision, registered WikiText-2
windows, canonical BF16 prefill KV cache, teacher-forced replay, and the stated
devices. They do not claim weight compression, free-running generation
quality, latency, throughput, arbitrary-model transfer, or state of the art.

## Prospective beacon experiment

The separately preregistered selected-window experiment is frozen under the
immutable release
[`corelm-beacon-heldout-v1`](https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/corelm-beacon-heldout-v1).
Its tag commit is `0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44`, and the exact
NIST pulse is `2026-08-02T18:00:00.000Z`. It still has no result.

That one-shot must be executed only from a clean detached checkout of the
immutable tag, never from the evolving default branch. Follow the
[launch runbook](docs/BEACON_LAUNCH_RUNBOOK.md). A repeat after terminal
`PASS` or `FAIL_GATES` is regression-only; execution failure or an incomplete
attempt cannot be retried.

The evolving branch exposes only a read-only Git-object integrity check:

```sh
./corelm beacon verify-tag
```

## Repository map

- `platforms/macos/` — native application, Swift tests, and macOS scripts.
- `platforms/linux/` — CPU runtime and real-Qwen regression scripts.
- `platforms/beacon/` — read-only boundary for the immutable tagged protocol.
- `RealLLM/` — shared pinned model, codec, protocols, and verifiers.
- `Tests/` — Python unit, protocol, evidence, and security gates.
- `security/` and `schemas/` — independent validation and contracts.
- `app-real-llm-evidence/` and `real-llm-v5-*` — registered real-data records.
- `publication/` — current paper, submission source, and archive tooling.
- `docs/` — architecture, results, limitations, and maintainer records.

Run the lightweight repository gates with:

```sh
./corelm verify
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Build and verify on macOS](docs/BUILD_AND_VERIFY.md)
- [Real Qwen on Linux](docs/LINUX_REAL_QWEN.md)
- [Results](docs/RESULTS.md)
- [Limitations](docs/LIMITATIONS.md)
- [Security policy](SECURITY.md)
- [Publication reproducibility](publication/reproducibility/README.md)

## Citation and license

Citation metadata is in `CITATION.cff`. Author:
[Ivan Tyshchenko](https://orcid.org/0009-0000-7935-6090).

The software is released under the MIT License. The paper and submission source
retain their stated distribution terms.
