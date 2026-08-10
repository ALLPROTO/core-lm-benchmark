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

A default-branch preview carries the current `corelm-portfolio-v15` software
CFF/SBOM identity and records `UNRELEASED_PREVIEW`; it is not the historical
paper-v5 release. Exact paper-v5 bytes must be built from the detached tag.

The V15 portfolio's `corelm-automated-presentation-v2` path records and checks a
post-proof model-free explanatory window plus the exact same-run result without
a required human acceptance or manual edit. Its video and poster are explicitly
`AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`: they aid inspection but do not
replace the receipt, result, raw containers, or replay reports, and pixel
semantics are not claimed to be verified. Independent-replication gate G10
remains **OPEN** until a non-author, non-agent person publishes a clean-clone
replication.

The current V15 identity does not replace the failed V3, V4, V5, or V6
candidates.
V3 remains at its first tag-push assertion failure. V4 remains at a pre-model
FFprobe frame-PTS field-validation failure before `AttemptLog.reserve`; no V4
model attempt was invoked or consumed. V5 passed first-attempt tag CI, then
stopped pre-marker on a safely retryable anonymous API HTTP 403. After reset,
its normative contour rejected real GitHub run/job IDs above `2^31` in the
tag-CI receipt validator, still before `AttemptLog.reserve`; no V5 model
attempt was invoked or consumed. The signed `corelm-portfolio-v6` candidate
passed first-attempt tag CI, and its one scientific proof honestly passed at
2.052384x compression, delta NLL
-0.00000846, 99.5117% top-1 agreement, and all 1,024 heavy-replay decisions
with zero maximum loss error. Its durable state then ended `ATTEMPT_FAILED`
after `REPLAY_VERIFIED` because the preflight-built explanatory-window
executable differed from the proof-rebuilt verified app, before same-run result
capture, media sealing, or collection. Their tags and first-attempt records are
never moved, rerun, or relabelled as a later identity.

The signed `corelm-portfolio-v7` tag and first-attempt tag CI are likewise
historical. The three V7 runner invocations all stopped strictly before
`AttemptLog.reserve`: two failed the >=50% available-memory admission after the
parallel Swift preflight build left less than 50% available memory, and one
transient pre-marker public tag-CI admission failure had an unretained nested
cause; the exact same 8-response validation subsequently passed. The durable state and
session remained absent after all three; no proof or model attempt was
consumed. V7 is never moved, rerun, or relabelled.

The signed `corelm-portfolio-v8` candidate is frozen at exact source commit
`b1fc746e7f8a5bd1bf826d9f5219779d568fa0c4`, tree
`3c9c5d64530e7c706dc1c9b9cf91d00c81a08a3d`, and annotated tag object
`64c9d84ddd8aa04b01459447b7c9f3f16f8f6db3`. Exactly one local V8 runner
invocation occurred. Its first resource admission passed and the release build
completed with top-level `--jobs 1`; the observed Swift frontend argv retained
`-num-threads 8`. That observation does not establish that the frontend
setting caused the later host-memory result. The second unchanged >=50%
available-memory admission failed closed with the exact PTY line `AUTOMATED
PORTFOLIO DEMO FAIL: at least 50% available memory is required`. After cleanup
the durable state, session, and staging directory were absent.
`AttemptLog.reserve` was never reached; no proof or model attempt was invoked
or consumed, and no portfolio media was retained. V8 is never moved, rerun,
reused, or relabelled. V9 adds the exact Swift frontend `-num-threads 1` pin
without weakening the 50% available-memory threshold. Receipts bind the exact
produced app SHA; this does not claim byte-deterministic executable builds
across scratch roots.

The signed `corelm-portfolio-v9` candidate is frozen at exact source commit
`33d99db9a8cb239732910d96fc18dcaa43b78e3e`, tree
`8fb25db8c54fc248e3b6c1b119fc06fb06be300f`, and annotated tag object
`ac69a22fef383f78634cda5e7256bca37e914acf`. Its first tag CI was green on
attempt one: Linux run `31335135716` and macOS run `31335135699`. Exactly one
V9 attempt was consumed, UUID `57a75c79-f37f-44b0-adc0-ba0762d200b0`.
Proof and replay passed at 2.0523837550538349x compression, delta NLL
-8.4598101111055257e-06, top-1 agreement 0.9951171875, and 1,024/1,024 replay
decisions with maximum errors 0. Its exact durable state order was
`ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL PASS → REPLAY_VERIFIED PASS →
POST_PROOF_PRESENTATION_SURFACE_READY → ATTEMPT_FAILED`, with state SHA-256
`eff033376bb6cc026c11c8a421da3a8834d78b1a4a7ab34580304c86d0646fce`.
The exact terminal PTY line was `AUTOMATED PORTFOLIO DEMO FAIL: post-proof
presentation capture failed: raw capture segment duration/topology is invalid`.
The partial MOV SHA-256 was
`5814eac71b5d2fb9ecd940a2aef09bfec9722a6d86a85a95ec230f7334c5514a`:
one frame, 0.028333 seconds, 2400x1540. The proven cause timeline was display
off at 23:00:00, idle sleep at 23:00:30, capture beginning during DarkWake at
23:01:36, maintenance sleep at 23:01:42, human wake at 23:09:18, and file
finalization at 23:09:19. The app remained alive; the launcher lacked a
display/system-sleep assertion. No result capture/readiness asset, final media,
automation receipt, or release was produced. V9 is never moved, rerun, reused, or
relabelled. V10 was the distinct successor and wrapped the full sterile runner
lifetime with exact `/usr/bin/caffeinate -dis`; `-u`, `-t`, and `-w` were
forbidden, and an unavailable wrapper failed before the attempt marker.

The signed `corelm-portfolio-v10` candidate is frozen at exact source commit
`bb53cd81d9e9ece92a078d823e6bf07474ff762b`, tree
`d840e2a2112fc5ee0cdae0c1f0bf1e5fb2c875da`, and annotated tag object
`27419a0b91934bd76d430ac7c0eadf073389e26c`. Its first tag CI was green on
attempt one: Linux run `31338205386` and macOS run `31338205397`. Exactly one
V10 attempt was consumed, UUID `7cad5bc5-57dd-4778-b00f-528ae3ba7936`. Its
sole proof and heavy replay passed at 2.0523837550538349x compression, delta NLL
-8.4598101111055257e-06, top-1 agreement 0.9951171875, and 1,024/1,024 replay
decisions with maximum errors 0. Its exact durable state order was
`ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL PASS → REPLAY_VERIFIED PASS →
POST_PROOF_PRESENTATION_SURFACE_READY → POST_PROOF_PRESENTATION_CAPTURED →
SAME_RUN_REOPENED → RESULT_CAPTURED → MEDIA_SEALED_FOR_COLLECTION`, with state
SHA-256 `2fe562b4026bbbda3944d194e05f9ce20a4ebfebbccf58c769a53a198e13cd24`
and automation-report SHA-256
`2183f16f2f81584a7c13a05a2509df4f1b7bbc2a445edcb34fa77d532ace7ee2`.
All three raw capture hashes were bound in the automation receipt: preflight
`3d6e2cda34e5c0a044c93a28d41160161920cdc75b887e16e7718968760ae22e`,
post-proof presentation
`e761c829f153411f6cd2f7b28cbed2d7a6770da24c4450c18c0a110f07c3dc10`, and
same-run result
`07c076d38fe3500011526df2a19441fd771b98875fb42f1e76a164881931cdca`.
Independent FFprobe inspection and full decode passed. The sealed 30-second,
900-frame
1280x720 MP4 SHA-256 was
`e353625bbc923916a07746a9cc7cdfca0579f06e5baae36088c09b37b255dc6a`,
decoded-frame SHA-256 was
`10222e090bb6fa9d10a5443b3879337141ce225dc666ae5dcbc4c159705b0646`,
PTS SHA-256 was
`9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`,
and poster SHA-256 was
`d47be9cb975767b5a6f89c0e54d66f5182675c3a0e871245f2838170e8708a61`.

The collector later stopped before publishing with exact terminal line
`PORTFOLIO DEMO COLLECTION FAIL: demo MP4 has a truncated atom header`. This
was a false reject: each valid raw ScreenCaptureKit QuickTime MOV's `avc1`
sample entry ended its valid nonempty `avcC` and `colr` children with exactly
four NUL padding bytes, which the generic nested-box parser treated as another
atom header. Top-level atoms ended exactly at EOF; independent FFprobe and full
decode passed all raw segments; hashes remained bound in state/report; and the
final MP4 passed atom/decode checks. This does not justify generic parser
weakening. V10's bound raw segments cannot be remuxed, trimmed, or replaced.
Failed collection removed transient staging; the V10 inputs directory,
fourteen-asset directory, and GitHub Release remained absent. V10 is never
moved, rerun, reused, or relabelled.

V11 is the distinct corrected identity. Its collector accepts exactly four
zero padding bytes only at the end of an `avc1` child region while requiring a
valid nonempty `avcC`; nonzero, wrong-length, misplaced, and missing-`avcC`
cases fail. The generic parser and presentation contract v2 remain unchanged.
V11 requires its own signed tag, first-attempt CI, and sole proof.

The frozen `corelm-portfolio-v11` source commit/tree/tag-object IDs are
`0071b1c9cbfffdb591a103fcc836a250d3d405e1`,
`4fb72d1dd73b8824f77f562620c16aa6481fc6a4`, and
`2bddc12667f3fac6901f982969003b38abcc3d3e`; first-attempt Linux/macOS tag-CI
runs `31371667051`/`31371667048` passed. Exactly one attempt was consumed,
UUID `6bc357a8-4fc6-4f7c-b73f-0718af818952`; sole proof/replay passed at
2.0523837550538349x, delta NLL -8.4598101111055257e-06, top-1 0.9951171875,
and 1,024/1,024 decisions with maximum errors 0. Its exact nine events were
`ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL PASS → REPLAY_VERIFIED PASS →
POST_PROOF_PRESENTATION_SURFACE_READY → POST_PROOF_PRESENTATION_CAPTURED →
SAME_RUN_REOPENED → RESULT_CAPTURED → MEDIA_SEALED_FOR_COLLECTION`.
State/report SHA-256 values were
`9c24a9c629f43b114ddc3766718079a0ba6b7160ff98e0d2c8339a6b53d6d61c` and
`635a1347ae93365ab5c03e14c56f329938d4164e353fe5b65690ccdd9a6f4675`;
app/receipt/result/readiness values were
`0192341765bf5e30f9a103e5b2b39d46d3eb35278a942b51d1747055ebf3b9fb`,
`a569802b3a7c76a5ca7283b56227b0730c5f420b80c4d8f2cfb49b727ab78805`,
`ca671a98c4476de5db1927bf2114693e9901aa96335642b227e55024924dd80d`, and
`f99b32ce5e47cf26c1abe784c7b992fc448aa3f8faadbfe8432d7baca17def20`.
Raw preflight/post-proof/result hashes were
`6d9363fee0a84967a4b9ba474743d8d1a5501f3ce7c53fecf57eb0fd65fd6241`,
`356b96e96d2310cb561ed96bc0246428e30bdcd7ac32ac49e47d0d4d7a014169`, and
`1661a2c7e087087de3848518eae9c95809c3ea5b10361a50f7817061844ef848`;
final MP4/decoded/PTS/poster hashes were
`bb7caa9c0874ac17d259de25ac952f13c9cd832b8dd83bceba94d30772ffe744`,
`7270ca303e891bdd6aaac18a50a518209c7365f794869bb5a974cc5e111f784d`,
`9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`, and
`6e5c774b9f6adba9cd5fe68681a246f01a3f7163aac428f36dff29affb9c5919`.
Collection failed exactly: `PORTFOLIO DEMO COLLECTION FAIL: final video bytes
are not the exact raw composition`. Retained/replay hashes
`bb7caa9c0874ac17d259de25ac952f13c9cd832b8dd83bceba94d30772ffe744`,
`6e64ff46721b81f8c45e1dfbbac41a6b7595ec8d5b4e101128bbc2f27860ee91`, and
`131953d94a53bd26e5b8d624267df7c88ee96c96cf86671511eaedd07e597ecc`
were byte-distinct but had exact decoded framemd5
`7270ca303e891bdd6aaac18a50a518209c7365f794869bb5a974cc5e111f784d`
and PTS identity; only packet-zero type-6 `user_data_unregistered` SEI differed.
Cleanup left inputs/assets/evidence/release absent. Never rerun, move, reuse, or
relabel V11 proof/tag/final media.

The signed `corelm-portfolio-v12` identity is frozen at source commit
`6e49fc14244230227ed08820cdd295c28bf0e7ca`, tree
`9c6c4e5cf050d3a882faeaf8dfc55e7b94c70ee6`, and annotated tag object
`f6166661047cb753e3a63230311fdd69bf357b80`. First tag CI Linux run
`31379694116` and macOS run `31379694145` passed on attempt 1. The first local
V12 runner invocation failed at tag-CI admission strictly before
`AttemptLog.reserve`; durable attempt state/session remained absent and no
proof or model attempt was consumed. Exactly one later V12 attempt was
consumed, UUID `c42fdea1-d0d5-49b9-aed3-f44e0549c061`, as its sole proof/model
invocation.

That sole run completed `END-TO-END PROOF PASS` and 1,024/1,024 heavy-replay
decisions at `2.0523837550538349x`, delta NLL
`-8.4598101111055257e-06`, and top-1 `0.9951171875`, with zero maximum
baseline/candidate loss error. Its proof receipt is
`014485f16de4f6ca2d7fd9f9b8472a6ee58fcd7338fee6953b91f272d1cad93a`, result
`12ab1cbdd6a18b3dc0245d17c52eb2ebe925ebebfbef156d198f1c210afb3f44`, and app
executable
`76d0f757faacbd92a20eda265a363ebcb7d5bf1f633951c4f46ab2922b5e50a4`. The
exact state order is `ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL →
REPLAY_VERIFIED → POST_PROOF_PRESENTATION_SURFACE_READY →
POST_PROOF_PRESENTATION_CAPTURED → SAME_RUN_REOPENED → RESULT_CAPTURED →
MEDIA_SEALED_FOR_COLLECTION`; state, automation-receipt, and readiness SHA-256
values are respectively
`3aec174dfbc1f40a5176cf8b021346dc9045baad6450812ea1858b1fd6a02f9c`,
`cc59a374376c2562d0c76db10ebf055671033fbcf88ea5043efb171d34537d50`, and
`4346bf3a8a9037481d6a99ef27180f81f6bad6b836e44b82a7bf8f68b543933e`.

Raw preflight, post-proof, and same-run MOV identities are
`70fc0f97b3a4e0317667728deaa23e4758390c93617d9185caa534bf28a41654`
(57 frames),
`268013e6ac671b85ebac2d39fe9dce3b52d96f81378b8512c0a347560e633538`
(681 frames), and
`2d3f0c00d2e7122b2d5b02c99e45be7e94e7332a588caf488df9266501446a40`
(1,024 frames). Final video/poster SHA-256 values are
`526130332ee358c52980cc339530ad1e67dc2e2e144d0b26779ae1b582f80dea` and
`f4217d69b4b715e61e4f2e5c3fca937a61117dbb1daf26a0f3b919da3a450a4f`; exact
strict per-frame SHA-256 framemd5 and PTS identities are
`a311d0b25102d5eb1ce00e56ba98976f95071653e9ef97661ca43ae056244c04` and
`9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`.
Collector and builder passed, retaining evidence
`96f940fed8d0470dae697133a8f191322a590798de4fd78bfa6b7a8980c2ddde`, provenance
`1e648042f78433a7c952dd266d3e07480ce0a2a966eab346c21897e47f82b469`, runtime
`accb52ae54b4e5ec279cc3c9456de0fdd1a665750c4e495e559d10c6e5915216`, and
exactly fourteen signed local assets with `SHA256SUMS`
`bdf6c6d6e961b863d4b38df866e3b673cae5476cea6196df0f3875535bbae919`.

Canonical create request
`479d7547b455adecaf8fa42ec47e04581994f13096346b82f40429b3fa5b2e5f`
required `draft:false`, `prerelease:false`, and `make_latest:"true"`. Its
one POST created release ID `367936819`, published
`2026-08-10T13:33:30Z`; response
`c337cb166b44d567937d88bfebeaedb2dadaf18e5b5d1ab4a4a0a9492ae9305c`
already reported the exact title/body/target, `immutable:true`, and `assets:[]`.
A separate authenticated `/releases/latest` GET then returned the same ID
`367936819`. The first upload, `REPRODUCE-corelm-portfolio-v12.md`, received
exact `HTTP 422: Cannot upload assets to an immutable release.` Failure record
`dc1cb5436e87816a357c8cb88c3a8a590bcfdf2861af2df4fdc0dfeb2b85c5ce`
binds that boundary. There was no partial upload, retry, deletion, metadata
edit, retag, rerun, reuse, or relabel. The fourteen local assets remain
retained; the V12 GitHub Release contract is a terminal FAIL and the public
V12 release remains empty and immutable.
No conforming fourteen-asset GitHub release receipt was produced.
The fail-closed successor rule was explicit: there is no delete/recreate, retry, retag, or V12 relabel.

The signed `corelm-portfolio-v13` identity is frozen at source commit
`b1fa1298971548eef8c2e0afa00d8c661812b16f`, tree
`29ee5d1b152bc8f2ef156664023ae4cd878dea2f`, and annotated tag object
`908c0913d5e7ca98dfb217287430fd251fa13994`. First tag CI Linux run `31398790350` and
macOS run `31398790626` passed on attempt 1. Exactly one V13 attempt was consumed, UUID
`51c4ebae-44ee-4cc8-b4e3-4a57fc170d83`, as its sole proof/model invocation.

That sole run completed `END-TO-END PROOF PASS` and 1,024/1,024 heavy-replay decisions
at `2.052383755053835x`, delta NLL `-8.459810111105526e-06`, and top-1 `0.9951171875`,
with zero maximum baseline/candidate loss error. Its proof receipt is
`1a3444f223cab3a95a626d2061def0c9a2814fadc22c173d1881e1803e3f3694`, result
`ad8724e0270be366703f38c874bb43dc1eed4387fd44e8b86e9a5cea7684a8e1`, and app executable
`504c0d137da22c4d39c6d380ca39126f0b82b855e3ff6a9873ee123f3b2a96f9`.

The exact state order is `ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL →
REPLAY_VERIFIED → POST_PROOF_PRESENTATION_SURFACE_READY →
POST_PROOF_PRESENTATION_CAPTURED → SAME_RUN_REOPENED → RESULT_CAPTURED →
MEDIA_SEALED_FOR_COLLECTION`; state, automation-receipt, and readiness SHA-256 values
are respectively `35d149c1c0e7cd5342153b69c37d09b3630489a687e0c63fcfe4de3c8d5d326b`,
`58a58a069a9327c969a7ee58f1f86bd9e0ff7be1e8fdceec8161bd76fb0220ea`, and
`8f05d45aa7a3847bdf557437b9da3d69ba507038cba3656c6a1a0ba909b3be07`.

Raw preflight, post-proof-presentation, and same-run MOV identities are
`afb6f14ad49a09be84c68a89e09183852805d1411b0cdf7baa2e8b2c61ef757c` (56 frames),
`bc0f549683c0a510f38302de9b89db273461bab1c18da044fc86ef03ac16177b` (685 frames), and
`7c6bdc3a18d691e6172df4815af4aa0b0e654377798c3376f7a2e9cdac50fad7` (1,027 frames). Final
video/poster SHA-256 values are
`4e23449ff2be2ad8c0dc868f85d768f0867cc393a45f9c0b04ff8475c67787f1` and
`1328d02715a7926612b3547f8fdd01697c1fc3d087a36f134fe399dec3022fda`; exact strict
per-frame SHA-256 framemd5 and PTS identities are
`391fd7b93d0a619240b55ad343bc310d69419f43a5f8ec0add58de5b3c3ec84d` and
`9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`.

Collector and builder both passed, retaining evidence
`123dcf8fbf0833fcac1a634952807151bed69b4dbded482331a04843a108f2d4`, provenance
`d2aca3293107bbca9f1648a0c36fd3f56f81d9efb0ca528217d4f7c9085e2bcd`, runtime
`a0243322187fb29fb475b63b910ffef699ea1386b3caff71b65649c0a389e8d3`, private
release-input manifest
`c765cf5584d1271bbfaa335bd42517ff0cbc315f18cf5766eab95cb97dfc385f`, and exactly fourteen
signed local assets with `SHA256SUMS`
`f30f6d60c4ca27bab7cbbde10d5428b27cea2501fd9f80f3ef18dfe7caef963a`. The independent
offline verifier returned exact-fourteen-asset PASS.

The exact canonical create-draft request bytes were derived at SHA-256
`521ed09b11c5946a2728384d6052e37ee1ee424d330fec48a8af96e05ccae919`. Before any POST, the
authenticated immutable-policy GET returned exact raw JSON
`{"enabled":true,"enforced_by_owner":false}` with SHA-256
`f4b2b8919d556de186d7b4afe009126b30c99e3edefb005e4e56ab17069b52dd`. The frozen V13
verifier rejected that official two-field response and exited 2 with exact terminal line
`PORTFOLIO GITHUB RELEASE FAIL: GitHub immutable-releases policy response must be exact
enabled:true`.

No precreate policy receipt, draft, GitHub Release, upload, PATCH, or publication
receipt was produced. There was no retry, deletion, retag, rerun, reuse, or relabel. The
fourteen signed local assets remain retained, and no conforming fourteen-asset GitHub
release receipt was produced.

V14 is the distinct corrected identity. It keeps presentation contract and
schema/state/report version v2. Its media gate retains the exact frame count, PTS
identity, and strict per-frame SHA-256 framemd5 manifest; MD5 and malformed manifests
are rejected.

Its GitHub operator boundary accepts an immutable-policy response with exactly the keys
`enabled` and `enforced_by_owner`. Both values must be strict JSON booleans, `enabled`
must be `true`, and `enforced_by_owner` may honestly be either boolean; missing, extra,
projected, or non-boolean fields fail. The raw snapshot SHA-256 and both values are
bound into the precreate and populated-draft operator receipts, whose schema version is
2. Public portfolio schemas and automation/presentation contract v2 do not change.

The fail-closed staged publication remains `prepare-draft` → fresh authenticated
precreate policy GET and `verify-policy` → one saved draft POST → `verify-empty-draft` →
exactly fourteen no-clobber uploads → fresh authenticated prepublish policy GET and
`verify-draft` → same-ID seven-field publish PATCH → logged-out
by-ID/by-tag/latest/download verification. The empty-draft snapshot binds `draft:true`,
`prerelease:false`, `immutable:false`, and `published_at:null`; the publish request binds
`make_latest:"true"`. In that flow, logged-out final verification binds by-ID, by-tag,
latest, and all downloads. Any mismatch or partial operation stops; there is no
delete/recreate, retry, retag, or V13 relabel. V14 requires its own signed
tag, first-attempt CI, and sole proof.

The signed `corelm-portfolio-v14` identity is frozen at source commit
`3d3273674d854a825636ec49ddc18be04cb82b05`, tree
`df363235a8945838a3f1aadd936df78498e471c8`, and annotated tag object
`7b92d0cd5852a2f75fa72d664965a7b51b9c6217`. First tag CI Linux run
`31408473142` and macOS run `31408473015` passed on attempt 1. Exactly one
V14 attempt was consumed, UUID `2b098099-1588-438e-922c-b88eae2b1803`, as
its sole proof/model invocation.

That sole run completed `END-TO-END PROOF PASS` and 1,024/1,024 heavy-replay
decisions at `2.0523837550538349x`, delta NLL `-8.4598101111055257e-06`,
and top-1 `0.9951171875`, with zero maximum baseline/candidate loss error.
Its proof receipt is
`a74fe758ea8de046dd14cc492669e7b096e0d0619c8e0ec5042f208944e8f315`,
result `3605fefa0916a0d5e88d537f3138c7e28fa69dbd21cf7521d63d86f5f9d7429a`,
and app executable
`be274ee658294f6b24d660ddfe879abb6865ba67d2de4fa84994af412750ff53`.

The exact state order is `ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL →
REPLAY_VERIFIED → POST_PROOF_PRESENTATION_SURFACE_READY →
POST_PROOF_PRESENTATION_CAPTURED → SAME_RUN_REOPENED → RESULT_CAPTURED →
MEDIA_SEALED_FOR_COLLECTION`; state, automation-receipt, and readiness
SHA-256 values are respectively
`ac342977affbde1bb0c2d7ef1cb206799d44d6582f3faa2c3e3622948fcfa58c`,
`cdf5c0ba4b5f6a09bea66045dd6dfa2fb56fb1af758206cbae350da817b4c25e`,
and `d110fc2d9fb23407043a6f9ca382a50646002789e4e3531d6e8f7b2cd580595c`.

Raw preflight, post-proof-presentation, and same-run MOV identities are
`5aeffe89b450dfe47e46a017487909a11fc160f25146b1db335a5b004b1bdd75`
(58 frames),
`1cd8880d169f6897c9a199b899b5140ba3a95a61c009ced1728dc3fcdc6c8405`
(685 frames), and
`4ad3d8fc5471289cb96354c41c26efc3529267e7b672b544d46fac447c8fd184`
(1,030 frames). Final video/poster SHA-256 values are
`db790f6518a9fea5533dff1744d5889f7bad0b332dba3080014f32ebe3164618`
and `b84fee40f7093b7a062d36ec332ff1a4bb0461e1cea4675c12c9e1f1a626ebb1`;
exact strict per-frame SHA-256 framemd5 and PTS identities are
`6a21df99c238d365a88d0aede78c3b3daeb79d6e277cc90e69179d56938cd23d`
and `9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`.

Collector and builder both passed, retaining evidence
`37703b9e727ff4568cd3504aa49ef9e0bac6abeb2668372dab7d4deb6751a33c`,
provenance
`05232ae09a61976a701acd685fa1321bb5cb38d14bf30474812928185705bd67`,
runtime
`3870bd9d1cf64f9123994e2e205a393c5b92c0e7639694d8ada646a8dbc9d1a0`,
private release-input manifest
`1fb631d76c0057a7ad5144f061ecd8408b7a4d9764ee8e99a761c6396ed9b4c6`,
and exactly fourteen signed local assets with `SHA256SUMS`
`8c505e0e6e1ed0f727c75d9602054b060158b6fcc8c3fe1462b17bf3ff7de89c`.
The independent offline verifier returned exact-fourteen-asset PASS.

The canonical create-draft request SHA-256 was
`a5955010e5002d466677d2b4e495c9d4c157edfdbd495dc364dfcf511838d0e9`;
its exact body SHA-256 was
`83fd1800d6bacb3d2882df73ff499c78827f90ad1d51b19cccdc7eb03fb2d036`.
The authenticated precreate immutable-policy snapshot was exact raw JSON
`{"enabled":true,"enforced_by_owner":false}` at
`f4b2b8919d556de186d7b4afe009126b30c99e3edefb005e4e56ab17069b52dd`,
and its schema-v2 receipt was
`f306618afaf01d1becc80c42a9a327d6465b1bdaef1ce68bd59df638051bd781`.
One POST created draft ID `368090960`; create response
`5e9db42406e4b4a4d95a741270544c696874a11071c8bdcaf8f8d7639b97a68c`
and empty-draft receipt
`fc1df0643d987e86aa695fa3f84daf531d63d9588189d91e3f22aacb7f7bd010`
passed before upload.

Exactly fourteen no-clobber uploads completed. The authenticated populated
draft snapshot
`be3b0937acdf0515f0ad97743f62bf3d468257dbca7c6beaea3b1f578273f2a0`
remained `draft:true`, `prerelease:false`, `immutable:false`, and
`published_at:null`. All fourteen unique assets were `uploaded` with exact
names, sizes, and `sha256:` digests and no missing, extra, or partial asset.
Tag-ref, tag-object, and commit-object snapshots were respectively
`b403017080419bc7e3613df4027312928a7de6e9cadf4be1da9078afe9b4c46a`,
`1040c4bb9e730d20602bf4d9774d65582dbc7c8c89bf7a1ca9151f137034ced4`,
and `634c98fe6e23bde35fab60235daec42298dd5074fad58eedb38292788009e74d`;
the fresh prepublish policy snapshot repeated the exact
`f4b2b8919d556de186d7b4afe009126b30c99e3edefb005e4e56ab17069b52dd`
bytes.

GitHub truthfully assigned the common draft download slug
`untagged-b7af7777ad2ad1f2cd20` to all fourteen
`browser_download_url` values. The signed V14 verifier prematurely required
the final tagged URL form at the mandatory prepublish gate and failed with
exact terminal line `PORTFOLIO GITHUB RELEASE FAIL: GitHub populated draft
asset URL differs: allowed_signers`. This was the sole populated-draft
mismatch; every scalar and non-URL asset field passed independently.

No `publish.json`, populated-draft receipt, PATCH, publish response, logged-out
download, public GitHub Release, or conforming fourteen-asset GitHub release
receipt was produced. The exact14 draft and local assets remain retained and
unmodified. There was no retry, deletion, recreation, metadata edit, retag,
rerun, reuse, relabel, or V14 publication. V14 will never be moved, rerun,
published, or relabelled.

V15 is the distinct corrected identity. It keeps presentation contract and
schema/state/report version v2. Its media gate retains the exact frame count, PTS
identity, and strict per-frame SHA-256 framemd5 manifest; MD5 and malformed manifests
are rejected.

Its GitHub operator boundary accepts an immutable-policy response with exactly the keys
`enabled` and `enforced_by_owner`. Both values must be strict JSON booleans, `enabled`
must be `true`, and `enforced_by_owner` may honestly be either boolean; missing, extra,
projected, or non-boolean fields fail. The raw snapshot SHA-256 and both values are
bound into the precreate and populated-draft operator receipts, whose schema version is
2. Public portfolio schemas and automation/presentation contract v2 do not change.

The V15 draft URL gate distinguishes authenticated prepublication URLs from
public postpublication URLs without weakening either boundary. Both the saved
create response and populated draft must expose one exact canonical
`html_url` slug matching `untagged-[0-9a-f]{20}`; those slugs must be
identical, and every one of the exact fourteen draft
`browser_download_url` values must use that same slug and its exact asset
name. Mixed slugs, tagged draft URLs, a wrong host/prefix/path, or a changed
create/populated slug fail closed. The final logged-out verifier still
requires exact tagged `corelm-portfolio-v15` download URLs. Empty-draft
receipt schema v1 and populated-draft receipt schema v2 remain unchanged
because their raw API snapshot digests already bind the URL facts.

The fail-closed staged publication remains `prepare-draft` → fresh authenticated
precreate policy GET and `verify-policy` → one saved draft POST → `verify-empty-draft` →
exactly fourteen no-clobber uploads → fresh authenticated prepublish policy GET and
`verify-draft` → same-ID seven-field publish PATCH → logged-out
by-ID/by-tag/latest/download verification. The empty-draft snapshot binds `draft:true`,
`prerelease:false`, `immutable:false`, and `published_at:null`; the publish request binds
`make_latest:"true"`. In that flow, logged-out final verification binds by-ID, by-tag,
latest, and all downloads. Any mismatch or partial operation stops; there is no
delete/recreate, retry, retag, or V14 relabel. V15 requires its own signed
tag, first-attempt CI, and sole proof.

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
