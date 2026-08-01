# Core LM Benchmark

[![Verify](https://github.com/ALLPROTO/core-lm-benchmark/actions/workflows/verify.yml/badge.svg)](https://github.com/ALLPROTO/core-lm-benchmark/actions/workflows/verify.yml)

Core LM Benchmark is an open-source macOS application for checking a real
KV-cache compression result on your own machine. It builds from source, loads a
pinned Qwen model, creates compressed cache containers, replays them through the
model, displays every architecture module, and independently verifies the
result and application receipt.

The release application has one clear workflow: **Compression Proof**.
Earlier experiments, rejected approaches, protocol revisions, and release
engineering are retained in the separate
[development record](docs/development/HISTORY.md).

## Real-data policy

Every benchmark, application proof, model evaluation, and scientific-evidence
run executes the pinned pretrained Qwen model on registered real WikiText
inputs. Synthetic, generated, toy, or mocked inputs cannot produce benchmark
metrics, evidence, PASS/FAIL claims, or publication results. Deterministic
fixtures remain permitted only in isolated parser, security, unit, and
protocol-control tests; their outputs never enter evidence or result channels.
Historical synthetic artifacts are preserved for provenance and integrity
checking only, not rerun as current evidence.

## Build and verify

Requirements:

- Apple Silicon Mac with macOS 14 or newer;
- Python 3.12 from a trusted owner-controlled installation;
- Swift 6 or newer from Apple's free Command Line Tools or Xcode;
- an active macOS desktop session for the visible application run;
- at least 8 GB of unified memory, with memory-heavy apps closed;
- at least 6 GiB of free disk space;
- network access, or a previously prepared hash-checked offline cache.

Clone the source, then run the read-only prerequisite check:

```sh
git clone https://github.com/ALLPROTO/core-lm-benchmark.git
cd core-lm-benchmark
./doctor.sh
```

If Python 3.12 is missing, `./bootstrap_python312_macos.sh` downloads a fixed
owner-local CPython archive, verifies its registered SHA-256 and safe archive
topology, and installs it below `~/.local/share/corelm` without `sudo` or a
system Python change. The binary archive is the explicitly disclosed
third-party `astral-sh/python-build-standalone` 3.12.13+20260718 distribution;
its archive SHA-256 is
`62aeee6161d57303a71a138b75fd5cc6fb8c89c4b1d9c7f0a052d89fa0b6652b`.
That binary archive is an explicit trust boundary, and the resulting
interpreter and complete runtime are covered by the application manifest.

Run the complete proof:

```sh
./run_local_app_proof.sh
```

The command creates a fresh Python runtime with hash-locked packages and an
exact signed runtime manifest, verifies the model and dataset bytes, builds
`dist/CoreLMBenchmark.app`, applies a local ad-hoc signature, runs the real
model on Apple MPS, binds the new result to a random local challenge, then uses
a separate decoder to replay all retained containers and all 1,024 Qwen
decisions.

The nonce is a trusted-local workflow guard against accidentally selecting an
older run; the owner-local ad-hoc receipt is not a cryptographic remote
attestation. See the security policy for that trust boundary.

No Apple Developer Program membership, Apple signing account, paid certificate,
Developer ID identity, or notarization is required. The repository distributes
source so the verifier builds and signs the application locally.

For a later network-free proof, prepare the wheelhouse and registered model
cache once while connected, then run:

```sh
./prepare_offline_inputs.sh
CORELM_OFFLINE=1 \
CORELM_WHEELHOUSE="$HOME/.cache/corelm-wheelhouse" \
  ./run_local_app_proof.sh
```

Both online and offline package installation retain `--require-hashes` and
binary-wheel-only enforcement. See the detailed guide for HTTPS mirror
configuration and externally supplied proof challenges.

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

The native application row uses fixed, public validation blocks 64–71. Those
blocks have been exercised repeatedly and are now application-regression input,
not a blind sample, holdout, or basis for a new generalization claim. Three runs
bound to a trusted-local challenge from one unchanged local bundle produced the
same scientific metrics and 192-entry container manifest; they are repeatability
checks of one fixed workflow, not three independent experiments. The scientific
fields and container manifest remained identical; operational fields such as
the challenge, timestamps, timings, and derived receipt digest changed.

These measurements cover the pinned `Qwen/Qwen2.5-0.5B` revision, registered
WikiText-2 windows, canonical BF16 prefill KV cache, teacher-forced replay, and
Apple MPS. They are not claims about full-model weight compression, free-running
generation, latency, serving throughput, arbitrary models, or state of the art.

The next evidence line is separately preregistered in the
[beacon-selected held-out protocol](RealLLM/BEACON_HELDOUT_PROTOCOL.md). Its
protocol and hashes are already published under immutable release
[`corelm-beacon-heldout-v1`](https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/corelm-beacon-heldout-v1):
tag commit `0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44`, protocol commit
`b34bc4d06c00c86b99076b117049e2d590d73bcd`, and GitHub server publication
time `2026-08-01T01:18:09Z`. The release body names four key artifacts; the
authoritative complete normative inventory is the 26 entries in
`RealLLM/beacon_freeze.json`. A pre-pulse notes-only correction at
`2026-08-01T10:08:12Z` clarified that label without changing the tag, assets,
frozen files, or original `published_at`.

That suite still has no result. At `2026-08-02T18:00:00.000Z`, the exact NIST
beacon selects one of fifteen previously unreported test windows for one
irreversible recorded run, which must complete by
`2026-08-04T18:00:00.000Z`. A repeat after terminal `PASS` or `FAIL_GATES` is
regression-only; `FAIL_EXECUTION` or an incomplete attempt cannot be retried.
The public [launch and publication runbook](docs/BEACON_LAUNCH_RUNBOOK.md)
fixes the clean-checkout, Mac power, no-retry, and unchanged-artifact procedure.
The separate [v1 audit and v2 hardening record](docs/BEACON_V1_AUDIT_AND_V2.md)
states the trusted-local limitations that remain frozen into v1 and the changes
required before any stronger future protocol.

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

## Documentation

- [Build and verify](docs/BUILD_AND_VERIFY.md) — ordinary-user installation and proof flow.
- [Real Qwen on Linux](docs/LINUX_REAL_QWEN.md) — CPU regression on pinned public validation data.
- [Results](docs/RESULTS.md) — current measurements and what PASS means.
- [Limitations](docs/LIMITATIONS.md) — honest boundary of the demonstrated claim.
- [Architecture](ARCHITECTURE.md) — final application and verifier pipeline.
- [Beacon launch runbook](docs/BEACON_LAUNCH_RUNBOOK.md) — one-shot operator and publication procedure.
- [Security policy](SECURITY.md) — runtime, bundle, asset, and supply-chain controls.
- [Development history](docs/development/HISTORY.md) — versioned experiments and chronology.
- [Scientific identifiers](docs/development/SCIENTIFIC_IDENTIFIERS.md) — internal names retained for reproducibility.
- [Release process](docs/development/RELEASE_PROCESS.md) — maintainer-only publication workflow.

## Repository map

- `App/` — native SwiftUI application.
- `RealLLM/` — pinned real-model runner, codec, and independent verifiers.
- `security/` — bundle, runtime, result, dependency, and workflow checks.
- `Tests/` and `TestsSwift/` — real-model regression and security suites.
- `app-real-llm-evidence/` — sanitized native-application reference receipt.
- `docs/` — final-user documentation and separate development history.
- `publication/` — paper, submission source, and deterministic archive tooling.

## Citation and license

Citation metadata is provided in `CITATION.cff`. Author:
[Ivan Tyshchenko](https://orcid.org/0009-0000-7935-6090).

The software is released under the MIT License. The paper and submission source
retain their stated distribution terms.
