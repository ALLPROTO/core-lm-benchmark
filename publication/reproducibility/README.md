# Reproducing the Core LM evidence

> This is a versioned scientific and provenance record. Revision numbers in
> this document identify protocols and immutable evidence, not alternative app
> editions. Ordinary users should begin with the repository `README.md` and
> `docs/BUILD_AND_VERIFY.md`.

The reproducibility archive contains the files needed to inspect the
implementation, rerun the test suite and benchmark, rebuild the macOS app, and
trace the historical VoidToken v3 result and the prospective VoidToken v5
result to machine-readable evidence.

## Requirements

- Apple Silicon and macOS 14 or newer for the real-Qwen application run
- Swift 6 or newer from Apple's free Command Line Tools or Xcode
- an active desktop login for the visible native-application run
- at least 8 GB unified memory and 6 GiB free disk for the full proof
- Python 3.12 (the registered and owner-local bootstrap version is 3.12.13)
- network access, or the prepared wheelhouse and registered model/data cache
- NumPy 2.3.5 for the core archive suite; the separately locked application
  runtime installs NumPy 2.5.1 and its complete real-model dependency closure
- ReportLab 4.4.9 for regenerating the vector paper figures

## Verify the implementation

From the extracted archive:

```sh
python3 -m pip install --require-hashes -r requirements.lock
./run_tests.sh
```

This command runs the explicit real-model, application-evidence, and security
suite used by the ordinary-user proof. Historical development benchmarks are
kept separate from this gate.

## Re-run the historical 115-run development benchmark

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

This is a source-build verification workflow. It needs no Apple Developer
Program account, paid certificate, Developer ID identity, or notarization. A
local ad-hoc signature seals the user's own build without claiming a binary
publisher identity.

Run the read-only readiness check before downloading packages or model files:

```sh
./doctor.sh
```

It checks Apple Silicon/macOS compatibility, Swift 6, signing utilities,
Python trust-chain permissions, at least 8 GB physical memory, at least 6 GiB
free under the user profile, an active GUI session, and the required online or
offline sources.

If Python 3.12 is absent, an optional owner-local bootstrap is available:

```sh
./bootstrap_python312_macos.sh
```

It downloads the immutable
`astral-sh/python-build-standalone` CPython 3.12.13+20260718 Apple Silicon
archive and requires SHA-256
`62aeee6161d57303a71a138b75fd5cc6fb8c89c4b1d9c7f0a052d89fa0b6652b`
before safe extraction below `~/.local/share/corelm/`. It rejects unsafe paths,
escaping links, and special files and uses neither `sudo` nor the system Python
installation. This third-party binary archive is an explicit trust boundary,
not a build-from-source claim. The final signed application manifest covers
every loadable file in that base interpreter and the fresh virtual environment.
Users who do not accept this bootstrap may supply another trusted Python 3.12:

```sh
CORELM_BOOTSTRAP_PYTHON="$(command -v python3.12)" ./doctor.sh
```

To build without automatically running model inference:

```sh
./build_local_app.sh
open dist/CoreLMBenchmark.app
```

The script installs hash-locked dependencies, verifies the exact installed
closure, downloads and hashes the pinned model plus validation inputs, confirms
offline resolution, creates a local ad-hoc signed bundle, runs the complete
bundle verifier, and performs an application-launch smoke test. The bundle is
produced at `dist/CoreLMBenchmark.app`.

The connected one-command proof runs the Python and Swift gates, the visible
real-Qwen application, the fast independent verifier, and the heavyweight
independent replay:

```sh
./run_local_app_proof.sh
```

The automated proof creates and retains a fresh runtime with hash-locked
packages and an exact signed runtime manifest (roughly 1 GB plus caches), then
prints its path. It supplies a random challenge to the app and requires that
exact nonce in the receipt. This is only a trusted-local stale-run binding: it
guards against accidentally selecting an older local result, not cryptographic
remote freshness. The owner-local ad-hoc receipt has no independently trusted
signature and a malicious local user could edit it. Another observer may
instead provide exactly 64 lowercase hexadecimal characters in
`CORELM_PROOF_CHALLENGE`; the value is propagated unchanged under the same
trust boundary.

The receipt embeds canonical build provenance. A Git build requires a clean
tree and binds the public remote, commit, tree, and exact tag when present; an
archive build verifies its canonical source-file manifest and inherited
commit/tree identity. The record also identifies the Apple SDK, developer
tools, Swift compiler, and compiler executable digest. Packaging compares this
identity before and after compilation and again after staging, and the full
proof rejects dirty-source overrides.

For a later network-free proof, prepare all inputs once while connected:

```sh
./prepare_offline_inputs.sh
```

Then disconnect if desired and run:

```sh
CORELM_OFFLINE=1 \
CORELM_WHEELHOUSE="$HOME/.cache/corelm-wheelhouse" \
  ./run_local_app_proof.sh
```

The offline package stage uses `--no-index`, `--only-binary=:all:`, and
`--require-hashes`. Model/data resolution is local-only and repeats registered
revision, byte-size, and SHA-256 checks. Offline mode never means skipping an
integrity gate. Connected users may configure HTTPS mirrors through
`CORELM_PYPI_INDEX_URL` and `CORELM_HF_ENDPOINT`; the same hashes remain
mandatory.

For a manual run, keep fixed public validation blocks 64–71, click
**Run Compression Proof**, then:

```sh
"$HOME/.cache/corelm-app-runtime/bin/python" \
  security/verify_local_app_run.py \
  --app dist/CoreLMBenchmark.app
```

Without the automated proof's challenge, the manual command checks consistency,
not trusted-local stale-run binding. Neither mode proves remote freshness. New
runs from the current source retain a
`primary-evidence/` directory with 192 raw `.vtl5` containers, all eight source
token slices of 512 IDs, and 1,024 per-token baseline/candidate loss and top-1
rows. The fast standard-library verifier parses the raw format independently,
reconstructs byte accounting, recomputes NLL/top-1 and canonical digests, and
binds the result to source/build provenance, receipt, locally compiled app,
signed runtime manifest, Python executable, and bundled source.

The full proof then invokes a separate heavyweight clean-room decoder. It
retokenizes the pinned WikiText input, decodes all 192 containers without
calling the production codec, rebuilds baseline and candidate KV state, and
reruns all 1,024 Qwen decisions sequentially on MPS. Top-1 IDs must match
exactly; each retained loss must match within absolute tolerance `2e-5` or
relative tolerance `2e-6`. The historical checked-in sanitized application
receipt predates primary-evidence retention and does not retroactively provide
those raw bytes. A locally compiled executable is not expected to match the
author's historical executable SHA-256 because source paths, toolchains,
runtime paths, and signing bytes differ.

Neither fresh verifier independently recomputes full-distribution KL or the
aggregate cache-error metrics from new model tensors. Those fields remain
subject to schema, identity, and aggregate-arithmetic checks. The retained
primary evidence and heavyweight replay independently establish the byte,
compression, NLL, and top-1 paths described above.

Validation blocks 64–71 have been exercised repeatedly and are now an
application-regression fixture. Repeating this workflow checks repeatability;
three same-machine runs are not three independent experiments. Neither a local
nor an external repeat on these blocks creates a new blind, holdout, or
generalization result.

## Prospective beacon-selected experiment

The archive includes the preregistered beacon protocol, frozen registration,
audited public-result ledger, strict schemas, NIST certificate fixture, one-shot
runner, regression runner, and independent verifier.
`RealLLM/BEACON_HELDOUT_PROTOCOL.md` is the normative operator guide. The target
pulse is in the future, so this archive contains no result from the
beacon-selected suite and makes no new generalization claim.

Before the target pulse, the protocol requires two public commits, a lightweight
tag, and a non-draft, non-prerelease immutable GitHub Release. After the NIST
pulse deterministically selects one preregistered window, exactly one recorded
execution is permitted. A later regression is allowed only after terminal
`PASS` or `FAIL_GATES`; `FAIL_EXECUTION` or an incomplete attempt cannot be
retried. Parameters and gates may not be adjusted after observing the outcome.
Blocks 64–71 remain a public application-regression fixture and cannot support
this claim.

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
python3 -m pip install --require-hashes -r RealLLM/requirements.lock
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
pass all seven gates. The historical v1 holdout records `2.0532909x`
runner-recorded complete-container compression, delta NLL `-0.0000609346`,
top-1 agreement `4071/4096`, blockwise top-1 lower 95% `0.9924722061`, and
Wilson lower 95% `0.9915430006`. Because the consumed v1 artifact did not
retain per-layer container manifests, the compression total is
digest/provenance-protected but not independently reconstructible.

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
v5 arXiv source archive, reproducibility archive, and rendered paper PDF.

Maintainers generate final release archives from a full repository clone—not
from this extracted tar—only after the lightweight release tag is public and
the worktree is clean:

```sh
RELEASE_TAG=voidtoken-v5-paper-v5
python3 publication/build_archives.py \
  --release-tag "$RELEASE_TAG" \
  --verify-determinism
python3 publication/build_archives.py \
  --release-tag "$RELEASE_TAG"
(cd output && shasum -a 256 -c SHA256SUMS)
```
