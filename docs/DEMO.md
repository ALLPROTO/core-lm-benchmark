# Automation-only macOS portfolio demo

This is the current V12 product-media contour for portfolio gate G03 under
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
relabel V7.

The signed `corelm-portfolio-v8` candidate is frozen at exact source commit
`b1fc746e7f8a5bd1bf826d9f5219779d568fa0c4`, tree
`3c9c5d64530e7c706dc1c9b9cf91d00c81a08a3d`, and annotated tag object
`64c9d84ddd8aa04b01459447b7c9f3f16f8f6db3`. Exactly one local V8 runner
invocation occurred. Its first resource admission passed, and the release
build completed with top-level `--jobs 1`; the observed Swift frontend argv
nevertheless retained `-num-threads 8`. That observation does not establish
that the frontend setting caused the later host-memory result. The second
unchanged >=50% available-memory admission then failed closed with the exact
PTY line `AUTOMATED PORTFOLIO DEMO FAIL: at least 50% available memory is
required`. After cleanup the durable state, session, and staging directory
were absent. `AttemptLog.reserve` was never reached; no proof or model attempt
was invoked or consumed, and no portfolio media was retained. Never move,
rerun, reuse, or relabel V8. V9 is the distinct successor and adds the exact
Swift frontend `-num-threads 1` pin without weakening the 50% available-memory
threshold. Receipts bind the exact produced app SHA; this does not claim
byte-deterministic executable builds across scratch roots.

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
automation receipt, or release was produced. Never move, rerun, reuse, or
relabel V9. V10 was its distinct successor: exact `/usr/bin/caffeinate -dis`
wrapped the full sterile runner lifetime, `-u`, `-t`, and `-w` were forbidden,
and an unavailable wrapper failed before the attempt marker.

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
All three raw single-window capture hashes were bound in the automation receipt,
and independent FFprobe inspection and full decode passed: preflight SHA-256
`3d6e2cda34e5c0a044c93a28d41160161920cdc75b887e16e7718968760ae22e`,
post-proof presentation SHA-256
`e761c829f153411f6cd2f7b28cbed2d7a6770da24c4450c18c0a110f07c3dc10`,
and same-run result SHA-256
`07c076d38fe3500011526df2a19441fd771b98875fb42f1e76a164881931cdca`.
The sealed 30-second, 900-frame 1280x720 MP4 SHA-256 was
`e353625bbc923916a07746a9cc7cdfca0579f06e5baae36088c09b37b255dc6a`,
its decoded-frame SHA-256 was
`10222e090bb6fa9d10a5443b3879337141ce225dc666ae5dcbc4c159705b0646`,
its PTS SHA-256 was
`9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`,
and its fixed poster SHA-256 was
`d47be9cb975767b5a6f89c0e54d66f5182675c3a0e871245f2838170e8708a61`.

The later collector stopped before publishing with exact terminal line
`PORTFOLIO DEMO COLLECTION FAIL: demo MP4 has a truncated atom header`. This
was a false reject of valid QuickTime MOV
structure: each raw ScreenCaptureKit MOV's `avc1` sample entry contained a
valid nonempty `avcC` and `colr`, followed by exactly four NUL padding bytes at
the end of that child region. The generic nested-box parser treated those four
bytes as another atom header. Top-level atoms ended exactly at EOF; FFprobe and
full decode passed all three raw segments; their bound hashes matched the
report and state; and the final MP4 passed the atom and decode checks. This
does not justify weakening the generic box parser. V10's bound raw segments
cannot be remuxed, trimmed, or replaced. Failed collection removed transient
staging; the V10 inputs directory, fourteen-asset directory, and GitHub Release
remained absent. V10 is never moved, rerun, reused, or relabelled.

V11 is the distinct corrected identity. Its collector accepts exactly four
zero padding bytes only at the end of an `avc1` child region while still
requiring a valid nonempty `avcC`; nonzero, wrong-length, misplaced, or
missing-`avcC` cases remain failures. It does not generically relax atom
parsing. V11 retains `corelm-automated-presentation-v2` and requires its own
signed tag, first-attempt CI, and sole proof.

The signed `corelm-portfolio-v11` candidate is frozen at exact source commit
`0071b1c9cbfffdb591a103fcc836a250d3d405e1`, tree
`4fb72d1dd73b8824f77f562620c16aa6481fc6a4`, and annotated tag object
`2bddc12667f3fac6901f982969003b38abcc3d3e`. Its first tag CI was green on
attempt one: Linux run `31371667051` and macOS run `31371667048`. Exactly one
V11 attempt was consumed, UUID `6bc357a8-4fc6-4f7c-b73f-0718af818952`. Its
sole proof and heavy replay passed at 2.0523837550538349x compression, delta NLL
-8.4598101111055257e-06, top-1 agreement 0.9951171875, and 1,024/1,024 replay
decisions with maximum errors 0. Its exact nine-event durable state order was
`ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL PASS → REPLAY_VERIFIED PASS →
POST_PROOF_PRESENTATION_SURFACE_READY → POST_PROOF_PRESENTATION_CAPTURED →
SAME_RUN_REOPENED → RESULT_CAPTURED → MEDIA_SEALED_FOR_COLLECTION`, with
state SHA-256 `9c24a9c629f43b114ddc3766718079a0ba6b7160ff98e0d2c8339a6b53d6d61c`
and automation-report SHA-256
`635a1347ae93365ab5c03e14c56f329938d4164e353fe5b65690ccdd9a6f4675`.
The bound app executable SHA-256 was
`0192341765bf5e30f9a103e5b2b39d46d3eb35278a942b51d1747055ebf3b9fb`, the
app-run receipt SHA-256 was
`a569802b3a7c76a5ca7283b56227b0730c5f420b80c4d8f2cfb49b727ab78805`, the
result SHA-256 was
`ca671a98c4476de5db1927bf2114693e9901aa96335642b227e55024924dd80d`, and
the readiness SHA-256 was
`f99b32ce5e47cf26c1abe784c7b992fc448aa3f8faadbfe8432d7baca17def20`.
The receipt bound all three raw captures: preflight SHA-256
`6d9363fee0a84967a4b9ba474743d8d1a5501f3ce7c53fecf57eb0fd65fd6241`,
post-proof presentation SHA-256
`356b96e96d2310cb561ed96bc0246428e30bdcd7ac32ac49e47d0d4d7a014169`, and
same-run result SHA-256
`1661a2c7e087087de3848518eae9c95809c3ea5b10361a50f7817061844ef848`.
The sealed 30-second, 900-frame 1280x720 MP4 SHA-256 was
`bb7caa9c0874ac17d259de25ac952f13c9cd832b8dd83bceba94d30772ffe744`,
its decoded-frame SHA-256 was
`7270ca303e891bdd6aaac18a50a518209c7365f794869bb5a974cc5e111f784d`,
its PTS SHA-256 was
`9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`, and
its fixed poster SHA-256 was
`6e5c774b9f6adba9cd5fe68681a246f01a3f7163aac428f36dff29affb9c5919`.

The later collector stopped before publishing with exact terminal line
`PORTFOLIO DEMO COLLECTION FAIL: final video bytes are not the exact raw
composition`. A bounded diagnostic repeated the exact pinned composition and
produced two temporary replay MP4s. The retained, replay-one, and replay-two
SHA-256 values were respectively
`bb7caa9c0874ac17d259de25ac952f13c9cd832b8dd83bceba94d30772ffe744`,
`6e64ff46721b81f8c45e1dfbbac41a6b7595ec8d5b4e101128bbc2f27860ee91`, and
`131953d94a53bd26e5b8d624267df7c88ee96c96cf86671511eaedd07e597ecc`.
All three byte-distinct files were 3,793,619 bytes and had the exact same
900-frame decoded
framemd5 SHA-256
`7270ca303e891bdd6aaac18a50a518209c7365f794869bb5a974cc5e111f784d`
and exact PTS identity; only packet zero's type-6
`user_data_unregistered` SEI payload differed. Thus the collector's encoded
VideoToolbox-byte equality was a false reject, not a decoded composition
difference. Failed collection removed transient staging; the V11 inputs
directory, fourteen-asset directory, evidence archive, and GitHub Release
remained absent. The V11 proof/tag/final media are never moved, rerun, reused,
or relabelled; the bounded diagnostic did not invoke the model or alter them.

V12 is the distinct corrected identity. It retains exact final-video
byte/report binding and exact poster replay. Its replay parser requires a
strict per-frame SHA-256 framemd5 manifest together with exact frame count and
PTS SHA-256; MD5 and malformed manifests are rejected. It compares that exact
decoded identity rather than nondeterministic encoded VideoToolbox bytes.
V12 retains `corelm-automated-presentation-v2` and schema/state/report version
2, and requires its own signed tag, first-attempt CI, and sole proof.

## Fixed source and one-attempt boundary

The command accepts only a clean canonical checkout whose `main`,
`origin/main`, and already-created SSH-signed annotated
`corelm-portfolio-v12` tag all resolve to the same commit/tree. The signed tag
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
requests that prove the exact public V12 tag/main and first-attempt Linux/macOS
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

DEMO_TAG=corelm-portfolio-v12
FFMPEG=/absolute/path/to/ffmpeg
FFPROBE=/absolute/path/to/ffprobe
DEMO_SESSION=/absolute/absent/corelm-portfolio-v12-automated-demo

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
INPUTS=/absolute/absent/corelm-portfolio-v12-inputs
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
  --release-date 2026-08-10 \
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
