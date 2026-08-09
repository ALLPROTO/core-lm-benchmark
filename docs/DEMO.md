# Automation-only macOS portfolio demo

This is the current V8 product-media contour for portfolio gate G03 under
`corelm-automated-presentation-v2`. It has no interactive window selection,
editor, manual trim, chosen poster frame, or human-review acceptance step. Its
exact classification is:

`AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`

Signed result/evidence files and the separate author-side heavy replay support the
metrics. The pixels help a viewer understand the product. Automated controls
can establish exact bytes, single-window targeting, fixed composition,
metadata checks, and proof/media bindings; they do not prove semantic pixel
privacy or independent replication. G10 remains open until a non-author,
non-agent person publishes the required clean-clone replication.

The signed `corelm-portfolio-v3` candidate remains frozen at its first
tag-push assertion failure. The signed `corelm-portfolio-v4` candidate is a
separate historical failure: its automated contour stopped in the pre-model
tool preflight when the FFprobe frame-PTS field validator rejected n8.1.2's
`duration_time`/SEI output grammar. That happened before `AttemptLog.reserve`,
so no V4 model attempt was invoked or consumed.

The signed `corelm-portfolio-v5` candidate also remains frozen. Its first tag
push Linux/macOS CI passed. The first local contour then received an anonymous
GitHub API HTTP 403 before the durable marker, which the contract classifies as
safely retryable. After the API limit reset, the normative V5 contour fetched
the exact public responses but its tag-CI receipt validator rejected GitHub's
real run/job identifiers because they exceeded the old signed 32-bit ceiling.
That failure also preceded `AttemptLog.reserve`; no V5 model attempt was
invoked or consumed. Never rerun or move V3, V4, or V5, and never relabel their
bytes as V6. V6 is the distinct corrected identity with a bounded signed
64-bit GitHub identifier contract.

The signed `corelm-portfolio-v6` candidate passed first-attempt tag CI and its
one scientific proof reached honest PASS: 2.052384x compression, delta NLL
-0.00000846, top-1 agreement 99.5117%, and a 1,024/1,024-decision heavy replay
with zero maximum loss error. Its durable state then ended `ATTEMPT_FAILED`
after `REPLAY_VERIFIED`: the preflight-built explanatory-window executable
differed from the proof-rebuilt verified app. This was before
same-run result capture, media sealing, or collection. Never rerun or move V6,
and never relabel its proof or partial media as V7, V8, or any later identity.

The signed `corelm-portfolio-v7` candidate is also immutable. Its exact source
commit is `8d53e43208f76141a01bb2c0914459fbc101e7d5`, tree
`ea82aa490c008d8560a6d44a70407d8d5e33bdbc`, and annotated tag object
`2c82497617173e3dfd965502860082ab5bf98130`. Its first tag CI was green on
attempt one: Linux run `31328178519` and macOS run `31328178525`. The three V7
runner invocations all stopped strictly before `AttemptLog.reserve`. Two failed
the >=50% available-memory admission after the parallel Swift preflight build
left less than 50% available memory; one transient pre-marker public tag-CI
admission failure had an unretained nested cause, while the exact same
8-response validation subsequently passed. The durable state and session remained absent
after all three; no proof or model attempt was consumed. Never rerun, move, or
relabel V7. V8 is the distinct successor. Its single-job/low-peak-memory
pre-marker build scheduling avoids the V7 parallel-build admission pressure
without weakening the 50% available-memory threshold. Receipts bind the exact
produced app SHA; this does not claim byte-deterministic executable builds
across scratch roots. V8 retains presentation contract
`corelm-automated-presentation-v2`.

## Fixed source and one-attempt boundary

The command accepts only a clean canonical checkout whose `main`,
`origin/main`, and already-created SSH-signed annotated
`corelm-portfolio-v8` tag all resolve to the same commit/tree. The signed tag
and its first-attempt Linux/macOS Actions must already be green.

Before model execution the command checks power, the offline doctor, pinned
assets, exact FFmpeg/ffprobe executables, and non-prompting Screen Recording
authorization. It compiles the tracked window helper, opens an owner-only
session, and creates an exclusive per-tag attempt marker. A second tagged
proof-driver attempt in that retained owner-local state is rejected. This is
not a claim that an owner could never delete or copy local state, or run
altered software on another host. The proof driver includes the required
author-side heavy replay, so one proof attempt intentionally contains more
than one pinned-Qwen model execution.

`CORELM_OFFLINE=1` applies to the model, corpus, app proof, replay, and media
pipeline. Before reserving the attempt, the runner makes the sole bounded
online exception: eight anonymous, direct, no-proxy/no-redirect GitHub API
requests that prove the exact public V8 tag/main and first-attempt Linux/macOS
tag CI. Failure remains pre-marker and safely retryable. Exact response bytes,
the recomputed public receipt, and hard-pinned local tag-trust receipt are
retained for collector and release verification; they record admission-time
state rather than a GitHub-signed attestation or perpetual live-state claim.

The durable state sequence is:

`ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL → REPLAY_VERIFIED → POST_PROOF_PRESENTATION_SURFACE_READY → POST_PROOF_PRESENTATION_CAPTURED → SAME_RUN_REOPENED → RESULT_CAPTURED → MEDIA_SEALED_FOR_COLLECTION`

If proof execution ends in verified metric FAIL, that FAIL is preserved. If
capture, encoding, or collection fails after proof execution, the retained
proof remains available but the demo/release gates stay open; the command does
not rerun the model to seek a better outcome.

The only accepted terminal outcomes are exactly `END-TO-END PROOF PASS` and
`END-TO-END PROOF VERIFIED — METRIC FAIL`; neither outcome authorizes an
outcome-seeking rerun.

## Run the automated tagged contour

Requirements: macOS arm64, AC power, an active GUI session, Python 3.12.13,
the exact offline wheelhouse/model cache, and a full local FFmpeg installation
providing both `ffmpeg` and `ffprobe`.

```sh
set -eu

DEMO_TAG=corelm-portfolio-v8
FFMPEG=/absolute/path/to/ffmpeg
FFPROBE=/absolute/path/to/ffprobe
DEMO_SESSION=/absolute/absent/corelm-portfolio-v8-automated-demo

CORELM_OFFLINE=1 \
CORELM_WHEELHOUSE="$HOME/.cache/corelm/macos/wheelhouse" \
./corelm macos portfolio-demo \
  --tag "$DEMO_TAG" \
  --ffmpeg "$FFMPEG" \
  --ffprobe "$FFPROBE" \
  --output "$DEMO_SESSION"
```

No `screencapture -i`, display/region capture, QuickTime, or editor is part of
the supported contour. The tracked helper binds exactly one visible layer-0
window to the Core LM process and bundle identifier `com.corelm.benchmark`.
Ambiguous/missing windows or permission failure stop fail-closed.

The app exposes a dedicated `--portfolio-capture` view. It contains fixed
labels plus bounded, cross-checked fields from one exact run; it never renders
worker stderr, free-form errors, file paths, browser content, mock data, or a
fallback "latest" run. The visible watermark is:

`AUTOMATED PRESENTATION · NOT MACHINE EVIDENCE · PUBLIC VALIDATION REGRESSION · NOT INDEPENDENT REPLICATION`

## Fixed media pipeline

The timeline is fixed by tracked code. The first public raw role is exactly
`post_proof_presentation`; legacy live-role names are rejected:

- after the proof and heavy replay terminate, 12 seconds of the fixed,
  model-free `--portfolio-capture-presentation` explanatory overview launched
  from the exact verified proof app;
  it is labelled `NOT MEASURED TELEMETRY`, contains no inference telemetry,
  and is presentation rather than proof evidence;
- 18 seconds of the exact same retained run reopened by lowercase UUID;
- silent H.264 composition with a fixed FFmpeg recipe;
- poster derived automatically at exactly 15.000000 seconds.

The output receipt binds tag, commit, tree, run UUID, challenge digest,
receipt/result/application hashes, metric and replay verdicts, both window
segments, helper/screencapture/FFmpeg/ffprobe identities, final video/poster,
frame count, PTS digest, decoded-frame digest, and the durable attempt-log
digest. It records `automation_only:true`, `human_reviewed:false`,
`manual_edits:false`, `machine_evidence:false`, and
`pixel_semantics_verified:false`.

The capture-safe window is the primary disclosure control. Metadata and byte
scans are mandatory. OCR is not a completeness proof and is not required for
PASS; the canonical receipt says only `NO_CONFIGURED_PATTERN_DETECTED` and
`semantic_pixel_privacy: NOT_CLAIMED`.

## Collect the bounded release inputs

After the automation command finishes, use its exact video, poster, bounded
session receipts, state log, raw segments, helper, and tag-CI response bundle.
The collector replays the fixed poster extraction,
recomputes decoded-frame/PTS identities, verifies the same proof and app, and
embeds `reports/automated-media.json` in the canonical evidence archive.
The session directory may also retain private driver/UI logs. Never upload or
publish the session directory as a whole; only the explicitly named inputs
below enter the collector, whose public-safe evidence output is scanned again.

```sh
set -eu

LAB=/absolute/clean/core-lm-cross-model-lab
RUN_DIRECTORY=/absolute/retained/real-llm-results/uuid
APP=/absolute/clean/source/dist/CoreLMBenchmark.app
VIDEO="$DEMO_SESSION/$DEMO_TAG-demo.mp4"
POSTER="$DEMO_SESSION/$DEMO_TAG-demo-poster.png"
AUTOMATION_RECEIPT="$DEMO_SESSION/automation-receipt.json"
RESULT_READINESS="$DEMO_SESSION/result-readiness.json"
ATTEMPT_STATE="$DEMO_SESSION/attempt-state.jsonl"
PREFLIGHT_SEGMENT="$DEMO_SESSION/preflight-window.mov"
POST_PROOF_PRESENTATION_SEGMENT="$DEMO_SESSION/post-proof-presentation.mov"
RESULT_SEGMENT="$DEMO_SESSION/same-run-result.mov"
WINDOW_HELPER="$DEMO_SESSION/find-proof-window"
TAG_CI_RECEIPT="$DEMO_SESSION/tag-ci-receipt.json"
LOCAL_TAG_TRUST_RECEIPT="$DEMO_SESSION/local-tag-trust-receipt.json"
TAG_CI_BUNDLE="$DEMO_SESSION/tag-ci-bundle"
INPUTS=/absolute/absent/corelm-portfolio-v8-inputs
PYTHON="$HOME/.cache/corelm/macos/runtime/bin/python"

publication/run_portfolio_python.sh \
  "$PYTHON" collect_portfolio_demo.py \
  --repository "$PWD" \
  --cross-model-lab "$LAB" \
  --run-directory "$RUN_DIRECTORY" \
  --app "$APP" \
  --video "$VIDEO" \
  --poster "$POSTER" \
  --automation-receipt "$AUTOMATION_RECEIPT" \
  --result-readiness "$RESULT_READINESS" \
  --attempt-state "$ATTEMPT_STATE" \
  --preflight-segment "$PREFLIGHT_SEGMENT" \
  --post-proof-presentation-segment "$POST_PROOF_PRESENTATION_SEGMENT" \
  --result-segment "$RESULT_SEGMENT" \
  --window-helper "$WINDOW_HELPER" \
  --tag-ci-receipt "$TAG_CI_RECEIPT" \
  --local-tag-trust-receipt "$LOCAL_TAG_TRUST_RECEIPT" \
  --tag-ci-bundle "$TAG_CI_BUNDLE" \
  --ffmpeg "$FFMPEG" \
  --ffprobe "$FFPROBE" \
  --tag "$DEMO_TAG" \
  --release-date 2026-08-09 \
  --output "$INPUTS"
```

The collector accepts schema version 2 only. It rejects legacy/mixed media
roles, arbitrary media, mismatched proof/run/challenge/app/tool identities,
audio or extra streams, noncanonical PNG/video metadata, a poster that is not
the fixed video frame, decoded-frame drift, placeholders, credentials, private
paths, symlinks, hard links, extra evidence members, and manual edits.

The resulting private input directory contains five public-candidate inputs
plus `release-input.private.json`. The latter contains absolute local paths and
must never be uploaded. Continue with
[`publication/PORTFOLIO_RELEASE.md`](../publication/PORTFOLIO_RELEASE.md).

## Acceptance record

Automation-ready G03 requires all of the following:

- first retained tagged proof outcome preserved without selection;
- exact-window post-proof presentation and same-run result segments;
- canonical automation receipt and evidence archive;
- fixed poster replay and decoded-frame/PTS checks;
- no human-review or pixel-evidence claim;
- public immutable release media and presentation successor only after a
  separately authorized GitHub Release.

It does not close G10 and does not establish blind/generalization results.
