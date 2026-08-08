# Reproducing the Core LM evidence

> This is a versioned scientific and provenance record. Revision numbers in
> this document identify protocols and immutable evidence, not alternative app
> editions. Ordinary users should begin with the repository `README.md` and
> `platforms/macos/BUILD_AND_VERIFY.md`.

The reproducibility archive contains the files needed to inspect the
implementation, run the verification suites, rebuild the macOS app or Linux
CPU runtime, and trace the real-model result to machine-readable evidence.

## Requirements

- Apple Silicon and macOS 14 or newer for the real-Qwen application run
- Swift 6 or newer from Apple's free Command Line Tools or Xcode
- an active desktop login for the visible native-application run
- at least 8 GB unified memory and 6 GiB free disk for the full proof
- Python 3.12.13 from a trusted owner-controlled installation
- network access, or the prepared wheelhouse and registered model/data cache
- NumPy 2.3.5 for the core archive suite; the separately locked application
  runtime installs NumPy 2.5.1 and its complete real-model dependency closure
- ReportLab 4.4.9 for regenerating the vector paper figures

If the exact interpreter is absent, use the platform-specific pinned bootstrap
before the verification command: `./corelm macos bootstrap` on Apple Silicon
or `./corelm linux bootstrap` on Ubuntu x86_64. Both verify a fixed immutable
archive by SHA-256, install under an owner-only platform-specific path, use no
administrator access, and remain disclosed third-party binary trust roots
rather than build-from-source claims.

## Verify the implementation

From the extracted archive:

```sh
python3 -m pip install --require-hashes -r requirements.lock
./corelm verify
```

This command runs the explicit real-model, application-evidence, and security
suite used by the ordinary-user proof. Historical development benchmarks are
kept separate from this gate.

## Real-data-only scope

The retired supported synthetic suite runner, verifier, schema, and result
directory are not included in the current archive. Their exact historical
bytes remain in the immutable `voidtoken-v5-paper-v5` Git tag. The archive
retains only the frozen compatibility source
`BenchmarkCore/corelm_benchmark.py`, byte-identical at its registered path
because it contributes to the published implementation hash; current v5
macOS/Linux runs do not import or package it, and evidence verification does
not execute it—it hashes the registered path and bytes. The historical-pilot
reproduction command and one isolated compatibility unit test execute it;
neither produces current evidence. The frozen source also retains a dormant,
directly invocable historical synthetic CLI; it is unsupported, excluded from
`./corelm` and both platform builds, and cannot create evidence accepted by
current verifiers.
Supported current benchmark, application-proof, model-evaluation, and
scientific-evidence runs use only the pinned pretrained Qwen model and
registered real WikiText inputs. Mocked values are restricted to isolated
unit, parser, security, and protocol-control tests whose outputs never enter a
current evidence or result directory.

## Regenerate the paper figures

```sh
python3 publication/arxiv-v5/generate_figures.py
```

The generator reads the adaptive development manifest plus the frozen
selection and holdout JSON records.

## Build the native application

This is a source-build verification workflow. It needs no Apple Developer
Program account, paid certificate, Developer ID identity, or notarization. A
local ad-hoc signature seals the user's own build without claiming a binary
publisher identity.

Run the read-only readiness check before downloading packages or model files:

```sh
./corelm macos doctor
```

It checks Apple Silicon/macOS compatibility, Swift 6, signing utilities,
Python trust-chain permissions, at least 8 GB physical memory, at least 6 GiB
free under the user profile, an active GUI session, and the required online or
offline sources.

If Python 3.12.13 is absent, an optional owner-local bootstrap is available:

```sh
./corelm macos bootstrap
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
Users who do not accept this bootstrap may supply another trusted Python 3.12.13:

```sh
CORELM_BOOTSTRAP_PYTHON="$(command -v python3.12)" ./corelm macos doctor
```

To build without automatically running model inference:

```sh
./corelm macos build
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

```zsh
set -euo pipefail
PROOF_LOG="$(mktemp "${TMPDIR:-/tmp}/corelm-proof-operator.XXXXXX")"
chmod 600 "$PROOF_LOG"
trap 'rm -f "$PROOF_LOG"' EXIT
./corelm macos proof 2>&1 | tee "$PROOF_LOG"
```

The automated proof creates and retains a fresh runtime with hash-locked
packages and an exact signed runtime manifest (roughly 1 GB plus caches). Its
public output contains only `Fresh proof runtime ID: <lowercase-uuid>`, never a
home-directory path. Parse and validate that identifier before reconstructing
the private cache path locally:

```zsh
PROOF_ID="$(/usr/bin/sed -n \
  's/^Fresh proof runtime ID: //p' "$PROOF_LOG")"
test "${#PROOF_ID}" -eq 36
printf '%s\n' "$PROOF_ID" | /usr/bin/grep -Eq \
  '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'

PROOF_RUNTIME="$HOME/.cache/corelm/macos/proof-runtimes/$PROOF_ID"
case "$PROOF_RUNTIME" in
  "$HOME/.cache/corelm/macos/proof-runtimes/"*) ;;
  *) printf '%s\n' 'unexpected proof runtime path' >&2; exit 1 ;;
esac
test -d "$PROOF_RUNTIME"
test ! -L "$PROOF_RUNTIME"
test -x "$PROOF_RUNTIME/bin/python"

PROOF_OUTCOME="$(/usr/bin/sed -n \
  -e '/^END-TO-END PROOF PASS:/p' \
  -e '/^END-TO-END PROOF VERIFIED — METRIC FAIL:/p' \
  "$PROOF_LOG")"
case "$PROOF_OUTCOME" in
  'END-TO-END PROOF PASS:'*) ;;
  'END-TO-END PROOF VERIFIED — METRIC FAIL:'*) ;;
  *) printf '%s\n' 'unexpected proof outcome' >&2; exit 1 ;;
esac
```

Both outcomes represent a fully executed proof with verified retained
evidence. The second preserves a failed metric gate and must not be rerun merely
to obtain PASS. A timeout, memory stop, verifier error, or missing outcome is an
infrastructure failure. The proof supplies a random challenge to the app and
requires that exact nonce in the receipt. This is only a trusted-local stale-run
binding: it guards against accidentally selecting an older local result, not
cryptographic remote freshness. The owner-local ad-hoc receipt has no
independently trusted signature and a malicious local user could edit it.
Another observer may instead provide exactly 64 lowercase hexadecimal
characters in `CORELM_PROOF_CHALLENGE`; the value is propagated unchanged under
the same trust boundary.

The receipt embeds canonical build provenance. A Git build requires a clean
tree and binds the public remote, commit, tree, and exact tag when present; an
archive build verifies its canonical source-file manifest and inherited
commit/tree identity. The record also identifies the Apple SDK, developer
tools, Swift compiler, and compiler executable digest. Packaging compares this
identity before and after compilation and again after staging, and the full
proof rejects dirty-source overrides.

For a later network-free proof, prepare all inputs once while connected:

```sh
./corelm macos prepare-offline
```

Then disconnect if desired and run:

```sh
CORELM_OFFLINE=1 \
CORELM_WHEELHOUSE="$HOME/.cache/corelm/macos/wheelhouse" \
  ./corelm macos proof
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
"$HOME/.cache/corelm/macos/runtime/bin/python" \
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

## Closed beacon-selected experiment

The archive includes the preregistered beacon protocol, frozen registration,
audited public-result ledger, strict schemas, NIST certificate fixture, one-shot
runner, regression runner, independent verifier, and the current evidence/CI
report. The raw attempt artifacts remain canonical at evidence commit
`85c2add1799652a818873a04310b75821728da11`, tag and release
`corelm-beacon-heldout-v1-evidence`; they are not reconstructed inside this
current-source archive.
`RealLLM/BEACON_HELDOUT_PROTOCOL.md` is the normative operator guide. The
protocol source and hashes are publicly frozen under tag and GitHub Release
`corelm-beacon-heldout-v1`; the authoritative freeze manifest enumerates 26
normative paths. The one recorded attempt selected blocks 512--543 and
published terminal **PASS**. It covers one pinned Qwen revision and one
WikiText-2 window only, so this archive makes no arbitrary-model or
corpus-wide generalization claim.

The required public commits, lightweight tag, and non-draft, non-prerelease
immutable protocol Release were published before the target pulse. That freeze
was a prerequisite, not the result itself. The later NIST pulse selected the
preregistered window and the single recorded execution completed at
`2026-08-02T18:18:20Z`. The suite is consumed; no later execution can become a
second scientific attempt. Regression-only runs cannot change the outcome, and
parameters or gates may not be adjusted after observing it. Blocks 64–71
remain a public application-regression fixture and cannot support this claim.

## Evidence chain

`RealLLM/voidtoken_v5.py` defines the production container and codec,
`RealLLM/develop_voidtoken_v5.py` defines the public-validation regression,
and the frozen runner plus independent verifiers bind the registered selection
and holdout. The paper figure generator reads only the checked-in real-Qwen
development and frozen-result artifacts.

## Verify the historical real-LLM pilot

The archive also includes the checked-in exploratory Qwen KV-cache pilot. Its
negative verdicts remain intact and do not alter the later prospective result.

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
python3 RealLLM/benchmark_real_llm.py
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

To reproduce the already published `voidtoken-v5-paper-v5` package, maintainers
use a full clean repository clone at that existing public tag. They do not
create or push it again:

```sh
RELEASE_TAG=voidtoken-v5-paper-v5
git fetch origin \
  "refs/tags/$RELEASE_TAG:refs/tags/$RELEASE_TAG"
git switch --detach "$RELEASE_TAG"
python3 publication/build_archives.py \
  --release-tag "$RELEASE_TAG" \
  --verify-determinism
python3 publication/build_archives.py \
  --release-tag "$RELEASE_TAG"
(cd output && shasum -a 256 -c SHA256SUMS)
```

A corrected or updated publication package must use a new unique tag and a
new GitHub Release. The guarded creation procedure is documented in
`publication/README.md`; existing tags and uploaded assets are never replaced.
