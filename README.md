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

## Prospective VoidToken v5 result

An engineering diagnosis attributed the v4 failure to value-cache
reconstruction error being obscured by the key cache's larger energy; the
published aggregate does not independently establish that causal split.
VoidToken v5 replaces temporal sparse residuals with per-layer
Walsh-Hadamard group quantization, canonical zigzag codes, complete binary
containers, and fresh-parser replay.

The frozen workflow is complete. Adaptive development used validation blocks
0–31 and does not count as prospective evidence. The already fixed
configuration then passed one-shot selection on validation blocks 32–63 and a
later prospective holdout on test blocks 384–415.

| Phase | Role | Ratio vs canonical BF16 | ΔNLL | Top-1 | Block lower 95% | Wilson lower 95% | Verdict |
|---|---|---:|---:|---:|---:|---:|---|
| Development | adaptive, disclosed | 2.055836× | +0.000804 | 99.5605% | 99.3638% | 99.3548% | not evidence |
| Selection | one-shot acceptance | 2.054320× | +0.000573 | 99.4141% | 99.1762% | 99.1827% | **PASS** |
| Holdout | prospective test | 2.053291× | −0.000061 | 99.3896% | 99.2472% | 99.1543% | **PASS** |

The historical v1 holdout runner recorded 150,601,728 canonical BF16
prefill-cache bytes and 73,346,513 complete-container bytes (51.30% fewer)
over 4,096 teacher-forced predictions. All seven registered gates passed,
including the one-sided block ΔNLL upper bound and both top-1 lower bounds.
Because the consumed v1 artifacts did not retain per-layer container
manifests, the compression totals are integrity-protected by exact
result/file/Git digests but are not independently reconstructible. The
verifier admits only the byte-identical historical artifacts; current v2 runs
require exact 24-layer manifests. See the protocol limitation before treating
the recorded ratio as independently reproduced.

The public chronology is bound by
`voidtoken-v5-selection-protocol-v1`,
`voidtoken-v5-pretest-v1`, and final evidence tag
`voidtoken-v5-evidence-v1`. A crash after durable marker creation consumes a
phase rather than permitting a retry. The claim covers only the pinned
Qwen2.5-0.5B revision, registered WikiText-2 windows, canonical BF16 prefill
KV cache, teacher-forced replay, and recorded MPS runtime. It is not a
full-model, free-running generation, latency, serving, or SOTA claim.

See [`RealLLM/V5_PROTOCOL.md`](RealLLM/V5_PROTOCOL.md),
[`real-llm-v5-results/README.md`](real-llm-v5-results/README.md), and the
[VoidToken v5 paper source](publication/arxiv-v5/).

## Reproduce the evidence

Requirements:

- Python 3.12 (the registered evidence uses 3.12.13)
- NumPy 2.3.5
- ReportLab 4.4.9 for rebuilding the paper figures
- macOS 14 and Swift 5.9 or newer for the native application

Run the lightweight implementation tests:

```sh
python3 -m pip install --require-hashes -r requirements.lock
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
python RealLLM/verify_real_llm_evidence.py
python RealLLM/verify_voidtoken_v5_development.py
python RealLLM/verify_voidtoken_v5_evidence.py --require-git-provenance
python security/verify_app_run_evidence.py
```

The last command requires a full clone with tags. In the extracted
reproducibility tar, omit `--require-git-provenance`; the verifier then reports
artifact self-consistency without claiming Git-tag or public-timestamp
provenance.

To repeat the heavy model run, create a separate environment from the
hash-complete `RealLLM/requirements.lock`, set `HF_HOME` if desired, and run:

```sh
python3.12 -m pip install --require-hashes -r RealLLM/requirements.lock
PYTHON_BIN=python ./run_real_llm_benchmark.sh --device mps
```

## Native macOS application

```sh
python3.12 -m venv "$HOME/.cache/corelm-real-llm-venv-v5"
"$HOME/.cache/corelm-real-llm-venv-v5/bin/python" -m pip install \
  --require-hashes -r RealLLM/requirements.lock
ALLOW_ADHOC_SIGNING=1 ./package_app.sh
open dist/CoreLMBenchmark.app
```

The application invokes the same Python measurement core, reads real JSON
results, and does not synthesize dashboard values. The command above produces
an explicitly local ad-hoc build. Packaging seals a deterministic manifest of
the loadable external Python base prefix and venv into the signed bundle; the
app hashes every listed file and rejects unlisted additions before launch.
Volatile `__pycache__` trees are bypassed with a private empty
`-X pycache_prefix`.
That makes the build runtime-authenticated but path-specific, not a portable
bundled-Python distribution. Public binary distribution additionally requires
a Developer ID identity and `security/notarize_app.sh`; see [`SECURITY.md`](SECURITY.md).

The checked-in
[`app-real-llm-evidence/`](app-real-llm-evidence/README.md) directory records
an actual `CoreLMBenchmark.app` run on the pinned Qwen model: 8 validation
blocks, 192 exact per-layer container entries, `2.052384×` compression,
delta NLL `-0.00000849`, top-1 agreement `99.5117%`, scientific `PASS`, Swift
verification `PASS`, and independent Python verification `PASS`. It is a
post-development integration test on blocks 64–71, not prospective holdout
evidence. To bind it to the locally packaged executable and signed runtime
manifest, run:

```sh
python security/verify_app_run_evidence.py \
  --app dist/CoreLMBenchmark.app
```

## Repository map

- `BenchmarkCore/` — deterministic system, codecs, metrics, and suite runner
- `Tests/` — unit and integration tests
- `App/` — native SwiftUI benchmark interface
- `benchmark-results/` — aggregate plus the 115 registered evidence records
- `RealLLM/` — pinned real-model protocol, codec baseline, runner, and verifier
- `real-llm-results/` — separate exploratory Qwen KV-cache pilot artifact
- `real-llm-v5-development/` — exact adaptive v5 development shards and manifest
- `real-llm-v5-results/` — frozen selection and holdout attempt/result artifacts
- `app-real-llm-evidence/` — sanitized real-Qwen macOS application run and receipt
- `publication/arxiv/` — historical VoidToken v3 paper source
- `publication/arxiv-v5/` — prospective real-model VoidToken v5 paper source
- `publication/corelm_voidtoken_v3.pdf` — visually inspected v3 paper
- `publication/corelm_voidtoken_v5.pdf` — visually inspected v5 paper
- `EVIDENCE.md` — result summary and acceptance gates
- `KNOWN_LIMITATIONS.md` — explicit boundary of the demonstrated claim

## Citation

Use the metadata in `CITATION.cff`. The current real-model paper is:

> Ivan Tyshchenko. “VoidToken v5: Prospectively Frozen Evidence for KV-Cache
> Compression on a Real Language Model.” 2026.

The historical v3 synthetic benchmark paper remains in `publication/arxiv/`.

Author ORCID: [0009-0000-7935-6090](https://orcid.org/0009-0000-7935-6090).

The software is released under the MIT License. The paper and arXiv submission
retain their own distribution terms.
