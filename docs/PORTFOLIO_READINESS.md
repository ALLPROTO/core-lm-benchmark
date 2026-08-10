# Core LM readiness boundary

This document defines the measurable boundary for presenting Core LM as a
flagship engineering portfolio project. It does not expand any scientific
claim and does not convert the Blind V1 draft into a preregistration or result.

## Two separate states

- `CV_READY` means all twelve portfolio gates below are satisfied.
- `SCIENTIFIC_READY` means a separate, validly frozen blind-suite lifecycle
  has reached a registered terminal outcome and an independent replay.

The project may become `CV_READY` without a blind result. Blind V1 missed its
registered checkpoint and is retained only as an unrun development record; it
cannot be repaired or launched late. A future blind result requires a new
suite ID and cannot repair a missing product demo, reproducibility path, or
public identity. Conversely, a polished portfolio does not establish
scientific generalization.

## CV_READY

```text
CV_READY = G01 AND G02 AND G03 AND G04 AND G05 AND G06
           AND G07 AND G08 AND G09 AND G10 AND G11 AND G12
```

| Gate | Required evidence |
|---|---|
| G01 Public identity | GitHub shows Ivan Tyshchenko, a contact route, ORCID, pinned repositories, accurate descriptions, and topics. |
| G02 Canonical entry | `core-lm-benchmark` default `main` explains within the first screen that this is complete-container KV-cache compression, not weight compression; it links the app, Linux path, lab, and retired unrun Blind V1 draft. |
| G03 Visible product | README contains a current screenshot and a public demo no longer than 90 seconds showing the fixed module/pipeline overview, exact same-run metrics, and verifier verdict from a publicly reproducible build. Runtime stderr and free-form progress are intentionally excluded from the automation-safe surface; retained machine evidence carries the measured execution. |
| G04 macOS reproduction | A clean Apple-Silicon clone builds the SwiftUI app, runs pinned real Qwen on MPS, creates a fresh challenge-bound receipt, and passes the separate verifier. |
| G05 Linux reproduction | A clean Ubuntu 24.04 x86-64 environment builds the hash-locked CPU runtime, retains raw real-Qwen evidence, and passes the verifier as a regression. |
| G06 Exact-commit CI | Required Linux x86-64 and macOS arm64 jobs are green on the same exact head SHA, with no required skipped, cancelled, or neutralized job. |
| G07 Supply chain | Hash locks, SHA-pinned Actions, least permissions, secret/history scan, runtime and asset manifests, SBOM, signatures, and archive checks pass on the exact commit. |
| G08 Honest claims | Results separate narrow Qwen evidence, public regressions, the cross-model diagnostic including the Pythia FAIL, and the retired unrun Blind V1 draft. |
| G09 No P0 contradiction | Normative byte counts, SHA-256 values, commit/tree identities, model revisions, deadlines, lifecycle states, schemas, code, and prose agree. |
| G10 Human clean clone | At least one non-author, non-agent person runs the public instructions on another machine and publishes commit, environment, log, receipt, result digest, and verifier report. A preserved FAIL is acceptable. |
| G11 Engineering ownership | A public code tour covers codec format, model replay, verifier separation, failure-state semantics, and the supply-chain threat model; AI assistance is disclosed. |
| G12 Stable release | One obvious signed current portfolio release binds source identity, checksums, public key, SBOM, reproduce command, release notes, and demo. Historical releases are clearly archival. |

The `corelm-portfolio-v11` `corelm-automated-presentation-v2` product-media path
may satisfy G03 with a deterministic, single-window automation receipt
classified
`AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`. Its signed result, raw evidence,
and replay reports—not the pixels—support the metrics. Automated capture and
agent audit never satisfy G10. Later passive viewing by a CV recipient does
not satisfy it either; that gate still requires the specified non-author,
non-agent clean-clone publication.

V11 is a new identity rather than a relabel of any failed candidate. V3
remains frozen at its first tag-push assertion failure. V4 remains frozen at a
pre-model FFprobe frame-PTS field-validation failure that occurred before
`AttemptLog.reserve`; no V4 model attempt was invoked or consumed. V5 passed
first-attempt tag CI, then stopped twice before the marker: first on a safely
retryable anonymous API HTTP 403, and after reset on real GitHub run/job IDs
above the receipt validator's old signed 32-bit ceiling. No V5 model attempt
was invoked or consumed. The signed `corelm-portfolio-v6` candidate passed
first-attempt tag CI, and one scientific proof honestly passed at 2.052384x
compression, delta NLL
-0.00000846, 99.5117% top-1 agreement, and a 1,024/1,024-decision replay with
zero maximum loss error. Its durable automation state nevertheless ended
`ATTEMPT_FAILED` after `REPLAY_VERIFIED`: the preflight-built explanatory
executable differed from the proof-rebuilt verified app, before same-run result
capture, media sealing, or collection. None of the V3/V4/V5/V6 tags or
workflows are rerun or moved, and none of those candidates' bytes can satisfy
a later gate.

The signed `corelm-portfolio-v7` tag and first-attempt tag CI are also frozen.
The three V7 runner invocations all stopped strictly before
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
invocation occurred. Its first resource admission passed, and the release
build completed with top-level `--jobs 1`; the observed Swift frontend argv
nevertheless retained `-num-threads 8`. That observation does not establish
that the frontend setting caused the later host-memory result. The second
unchanged >=50% available-memory admission then failed closed with the exact
PTY line `AUTOMATED PORTFOLIO DEMO FAIL: at least 50% available memory is
required`. After cleanup the durable state, session, and staging directory
were absent. `AttemptLog.reserve` was never reached; no proof or model attempt
was invoked or consumed, and no portfolio media was retained. V8 is never
moved, rerun, reused, or relabelled. The distinct V9 identity adds the exact
Swift frontend `-num-threads 1` pin without weakening the 50% available-memory
threshold. Receipts bind the exact produced app SHA; this does not claim
byte-deterministic executable builds across scratch roots or weaken any
evidence or G10 boundary.

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
relabelled. V10 was its distinct successor and wrapped the full sterile runner
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
All three raw capture hashes were bound in the automation receipt, and
independent FFprobe inspection and full decode passed: preflight SHA-256
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
full decode passed all three raw segments; bound hashes matched the report and
state; and the final MP4 passed atom and decode checks. This does not justify
weakening the generic parser. V10's bound raw segments cannot be remuxed,
trimmed, or replaced. Failed collection removed transient staging; the V10
inputs directory, fourteen-asset directory, and GitHub Release remained
absent. V10 is never moved, rerun, reused, or relabelled.

V11 is the distinct corrected identity. Its collector accepts exactly four
zero padding bytes only at the end of an `avc1` child region while still
requiring a valid nonempty `avcC`; nonzero, wrong-length, misplaced, or
missing-`avcC` cases remain failures, and atom parsing is not generically
relaxed. V11 keeps presentation contract v2 and requires its own signed tag,
first-attempt CI, and sole proof; no evidence or G10 boundary is weakened.

No gate can be replaced by a large test count, an author-controlled agent
review, an uncommitted local run, or a future promise.

## Claim boundary at CV_READY

Acceptable summary:

> Built and reproducibly evaluated complete-container KV-cache compression on
> pinned real-model workloads.

Do not claim that the project compressed an entire LLM, reduced model weights,
proved generalization, achieved state of the art, eliminated quality loss, or
received independent human review unless separately supported by published
evidence.

## SCIENTIFIC_READY

This separate state requires all of the following:

1. A signed immutable design release closes every real freeze blocker and
   binds the exact implementation commit/tree, runtime, assets, NIST trust,
   model pool, future-corpus rule, gates, and deadlines before confirmatory
   data or inference is opened.
2. Exact-commit Linux and macOS CI receipts and their archived bytes are bound
   into the design evidence.
3. Snapshot and execution reservation are published inside their registered
   windows; late or missing state is not repaired under the same suite ID.
4. No confirmatory-pool forward pass occurs before the registered marker.
5. The one permitted attempt reaches exactly one registered terminal state,
   without retry, model substitution, data substitution, or threshold changes.
6. All surviving bytes are published: raw NIST exchange, corpus and rights,
   containers, token evidence, logs, environment, terminal result, manifests,
   signatures, and independent replay report.
7. Even a `PASS` supports only the exact preregistered sample. It does not
   establish universal LLM generalization.

Blind V1 must remain labelled `draft`, `not frozen`, `not preregistered`,
`not run`, and `retired after missed checkpoint`. `SCIENTIFIC_READY` now
requires a new suite ID, a fully shifted timeline, and completion of that new
lifecycle.
