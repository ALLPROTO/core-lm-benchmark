# Core LM engineering case study

Core LM is a source-distributed macOS/Linux benchmark for one narrow systems
question: can a complete, serialized KV-cache container be reduced to about
half of canonical BF16 storage while a real language model continues from the
decoded cache with bounded behavioral change?

The current application result is a **regression on fixed public validation
blocks**, not a new blind or generalization result. It compresses KV cache, not
model weights, source text, or the whole application. The useful engineering
artifact is the end-to-end chain: pinned inputs -> model prefill -> canonical
container -> fresh parse -> cache rebuild -> model continuation -> retained
evidence -> separate verification.

## Five-part code tour

### 1. Codec format: bytes are part of the claim

Start with [`RealLLM/voidtoken_v5.py`](../RealLLM/voidtoken_v5.py), especially
`VoidTokenV5Backend.encode()`, `from_bytes()`, and `_parse_container()`.
The wire format is deliberately small and explicit:

```text
b"VTL5" | uint32_le(metadata_length) | canonical_json | binary_payload
```

The format supports an optional deterministic sign rotation followed by a
normalized Walsh-Hadamard transform, group quantization, float16 scales,
packed codes, and optional canonical zlib level 9. The current application
profile explicitly uses `signMode: none`, so its sign transform is the
identity. Metadata binds the shape, bit schedule, transforms, payload digest,
input digest, and decoded reconstruction digest. The parser rejects
non-canonical JSON/zlib, invalid lengths, unused codes, non-finite scales, and
oversized decoded matrices.

[`RealLLM/app_proof_core.py`](../RealLLM/app_proof_core.py) then serializes and
fresh-parses every layer with `VoidTokenV5Backend.from_bytes()`. It requires a
byte-identical round trip before accepting reconstructed cache data. Reported
compression is
`sum(canonical dense BF16 cache bytes) / sum(complete VTL5 container bytes)`;
metadata and framing are included, rather than reporting payload-only size.

**Engineering decision:** a compact algorithm without a canonical bounded
format is difficult to archive, fuzz, or verify independently. Core LM makes
the serialized representation—not an in-memory estimate—the accounting unit.

### 2. Real-model replay: decoded cache must affect real inference

The production macOS worker is
[`RealLLM/app_proof_runner.py`](../RealLLM/app_proof_runner.py). It resolves the
exact Qwen2.5-0.5B revision and WikiText validation file by size and SHA-256,
requires local-only assets, disables remote model code, fixes runtime versions
and seeds, and runs on Apple MPS.

The central path is `_evaluate_block()` in
[`RealLLM/app_proof_core.py`](../RealLLM/app_proof_core.py):

1. Run a real Qwen prefill and extract all KV layers.
2. Establish exact flatten/rebuild and canonical-BF16 baselines.
3. Encode each layer, parse its VTL5 bytes again, and reconstruct the cache.
4. Build a new Transformers `DynamicCache` from the decoded arrays.
5. Continue Qwen with that cache and retain per-token baseline/candidate loss
   and top-1 IDs.

One application regression covers eight known validation blocks, 1,024
teacher-forced decisions, and 192 complete containers. The native integration
result is approximately `2.052384x`, delta NLL `-0.00000849` nat/token, and
`99.5117%` top-1 agreement. Because blocks 64-71 have been used repeatedly,
these numbers establish repeatability of this fixed workflow only.

The public entrypoints are intentionally short:

```sh
./corelm macos doctor
./corelm macos proof

./corelm linux bootstrap
./corelm linux doctor
./corelm linux build
./corelm linux run
```

The macOS command builds and visibly runs the SwiftUI application. The Linux
command executes a separate CPU regression; CPU and MPS results are not
required to be bit-identical.

### 3. Verifier separation: do not trust the producer's parser

The evidence producer writes raw containers and token rows through
`PrimaryEvidenceWriter` in
[`RealLLM/app_proof_core.py`](../RealLLM/app_proof_core.py). Three other paths
check the result:

- [`platforms/macos/App/Sources/PrimaryEvidenceValidation.swift`](../platforms/macos/App/Sources/PrimaryEvidenceValidation.swift)
  validates bounded evidence, hashes, container ordering, and metric
  recomputation inside the native UI.
- [`security/verify_primary_evidence.py`](../security/verify_primary_evidence.py)
  uses only the Python standard library. It intentionally imports neither the
  writer nor the codec and independently parses all 192 containers and
  recomputes byte accounting, NLL, top-1, and gates.
- [`security/verify_primary_replay.py`](../security/verify_primary_replay.py)
  independently decodes the retained VTL5 bytes, reconstructs the registered
  token slice, rebuilds both caches, and reruns all 1,024 Qwen decisions.

[`security/verify_local_app_run.py`](../security/verify_local_app_run.py) also
binds the receipt to the exact application executable, source/build
provenance, runner, runtime manifest, result, and primary evidence. The
orchestrator in
[`platforms/macos/scripts/run-proof.sh`](../platforms/macos/scripts/run-proof.sh)
does not print end-to-end PASS until the app, structural verifier, and heavy
model replay have all returned successfully.

The `corelm-portfolio-v12` `corelm-automated-presentation-v2` contour is also
automation-only: after proof and replay it records a fixed model-free
explanatory overview from the exact verified proof app, reopens the exact
retained run, derives the poster at a fixed timestamp,
and emits a canonical receipt binding the media to the tag, source tree,
challenge, result, evidence, and tool hashes. That receipt
classifies the pixels as `AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`; metric
support remains in signed result/evidence bytes and the heavy replay. The
capture-safe view and metadata scans reduce disclosure risk but do not prove
that no private glyph exists.

This V12 contour does not rewrite the failed V4 candidate. V4 stopped during
pre-model tool admission when its FFprobe frame-PTS field validator rejected
n8.1.2's `duration_time`/SEI output grammar, before the durable attempt marker
and before any model invocation; no V4 model attempt was consumed. V5 then
passed first-attempt tag CI. Its first local contour received an anonymous API
HTTP 403 pre-marker and was safely retryable; after reset, its normative
contour rejected the real GitHub run/job IDs above `2^31` in the tag-CI receipt
validator, again before `AttemptLog.reserve` and without invoking a model. The
V4 and V5 tags and first-attempt CI records stay historical. The signed
`corelm-portfolio-v6` candidate passed first-attempt tag CI, then produced one
honest scientific proof PASS:
2.052384x compression, delta NLL -0.00000846, 99.5117% top-1 agreement, and a
1,024/1,024-decision heavy replay with zero maximum loss error. Its durable
state ended `ATTEMPT_FAILED` after `REPLAY_VERIFIED` because the preflight-built
explanatory-window executable differed from the proof-rebuilt verified app,
before same-run result capture, media sealing, or collection. V3 through V6 are
never moved, rerun, or relabelled as a later identity. The earlier V3 tag-push
assertion failure remains immutable for the same record-preservation reason.

The signed `corelm-portfolio-v7` tag and its first-attempt tag CI are likewise
frozen. The three V7 runner invocations all stopped strictly before
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
All three raw capture hashes were bound in the automation receipt: preflight
`3d6e2cda34e5c0a044c93a28d41160161920cdc75b887e16e7718968760ae22e`,
post-proof presentation
`e761c829f153411f6cd2f7b28cbed2d7a6770da24c4450c18c0a110f07c3dc10`, and
same-run result
`07c076d38fe3500011526df2a19441fd771b98875fb42f1e76a164881931cdca`.
Independent FFprobe inspection and full decode passed. The sealed 30-second,
900-frame 1280x720 MP4 SHA-256 was
`e353625bbc923916a07746a9cc7cdfca0579f06e5baae36088c09b37b255dc6a`,
its decoded-frame SHA-256 was
`10222e090bb6fa9d10a5443b3879337141ce225dc666ae5dcbc4c159705b0646`,
its PTS SHA-256 was
`9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`,
and its fixed poster SHA-256 was
`d47be9cb975767b5a6f89c0e54d66f5182675c3a0e871245f2838170e8708a61`.

The later collector stopped before publishing with exact terminal line
`PORTFOLIO DEMO COLLECTION FAIL: demo MP4 has a truncated atom header`. This
was a false reject: each valid raw ScreenCaptureKit
QuickTime MOV's `avc1` sample entry ended its valid nonempty `avcC` and `colr`
children with exactly four NUL padding bytes, which the generic nested-box
parser treated as another truncated atom header. Top-level atoms ended exactly
at EOF; FFprobe and full decode passed all raw segments; their hashes matched
the report/state; and the final MP4 passed atom and decode checks. This does
not justify generic parser weakening. V10's bound raw segments cannot be
remuxed, trimmed, or replaced. Failed collection removed transient staging;
the V10 inputs directory, fourteen-asset directory, and GitHub Release remained
absent. V10 is never moved, rerun, reused, or relabelled.

V11 is the distinct corrected identity. Its collector accepts exactly four
zero padding bytes only at the end of an `avc1` child region while still
requiring a valid nonempty `avcC`; nonzero, wrong-length, misplaced, and
missing-`avcC` cases fail, without generically relaxing atom parsing. V11 keeps
presentation contract v2 and requires its own signed tag, first-attempt CI,
and sole proof.

The signed `corelm-portfolio-v11` candidate is frozen at source commit
`0071b1c9cbfffdb591a103fcc836a250d3d405e1`, tree
`4fb72d1dd73b8824f77f562620c16aa6481fc6a4`, and annotated tag object
`2bddc12667f3fac6901f982969003b38abcc3d3e`; first-attempt tag CI passed in
Linux run `31371667051` and macOS run `31371667048`. Exactly one V11 attempt
was consumed, UUID `6bc357a8-4fc6-4f7c-b73f-0718af818952`. Its sole proof and
heavy replay passed at 2.0523837550538349x compression, delta NLL
-8.4598101111055257e-06, top-1 agreement 0.9951171875, and 1,024/1,024 replay
decisions with maximum errors 0. Its exact nine-event order was
`ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL PASS → REPLAY_VERIFIED PASS →
POST_PROOF_PRESENTATION_SURFACE_READY → POST_PROOF_PRESENTATION_CAPTURED →
SAME_RUN_REOPENED → RESULT_CAPTURED → MEDIA_SEALED_FOR_COLLECTION`.
State SHA-256 was `9c24a9c629f43b114ddc3766718079a0ba6b7160ff98e0d2c8339a6b53d6d61c`;
automation-report SHA-256 was
`635a1347ae93365ab5c03e14c56f329938d4164e353fe5b65690ccdd9a6f4675`;
app executable, app-run receipt, result, and readiness SHA-256 values were
`0192341765bf5e30f9a103e5b2b39d46d3eb35278a942b51d1747055ebf3b9fb`,
`a569802b3a7c76a5ca7283b56227b0730c5f420b80c4d8f2cfb49b727ab78805`,
`ca671a98c4476de5db1927bf2114693e9901aa96335642b227e55024924dd80d`, and
`f99b32ce5e47cf26c1abe784c7b992fc448aa3f8faadbfe8432d7baca17def20`.
The receipt-bound preflight, post-proof-presentation, and same-run-result MOV
SHA-256 values were
`6d9363fee0a84967a4b9ba474743d8d1a5501f3ce7c53fecf57eb0fd65fd6241`,
`356b96e96d2310cb561ed96bc0246428e30bdcd7ac32ac49e47d0d4d7a014169`, and
`1661a2c7e087087de3848518eae9c95809c3ea5b10361a50f7817061844ef848`.
The sealed 30-second, 900-frame 1280x720 MP4, decoded frames, PTS, and poster
SHA-256 values were
`bb7caa9c0874ac17d259de25ac952f13c9cd832b8dd83bceba94d30772ffe744`,
`7270ca303e891bdd6aaac18a50a518209c7365f794869bb5a974cc5e111f784d`,
`9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`, and
`6e5c774b9f6adba9cd5fe68681a246f01a3f7163aac428f36dff29affb9c5919`.

Collection then failed exactly with `PORTFOLIO DEMO COLLECTION FAIL: final
video bytes are not the exact raw composition`. A bounded exact-composition
diagnostic produced retained/replay SHA-256 values
`bb7caa9c0874ac17d259de25ac952f13c9cd832b8dd83bceba94d30772ffe744`,
`6e64ff46721b81f8c45e1dfbbac41a6b7595ec8d5b4e101128bbc2f27860ee91`, and
`131953d94a53bd26e5b8d624267df7c88ee96c96cf86671511eaedd07e597ecc`:
three byte-distinct, equal-size MP4s with the exact same 900-frame decoded
framemd5 SHA-256 `7270ca303e891bdd6aaac18a50a518209c7365f794869bb5a974cc5e111f784d`
and PTS identity. Only packet zero's type-6 `user_data_unregistered` SEI
payload differed. This was a false encoded-byte reject, not a decoded
composition difference. Cleanup removed staging; V11 inputs, fourteen assets,
evidence archive, and GitHub Release remained absent. Never move, rerun, reuse,
or relabel the V11 proof/tag/final media; the diagnostic invoked no model and
altered no retained bytes.

V12 is the distinct correction: final video bytes remain exactly report-bound
and poster replay remains byte-exact. Replay requires a strict per-frame
SHA-256 framemd5 manifest together with exact frame count and PTS SHA-256; MD5
and malformed manifests are rejected. This exact decoded identity replaces
comparison of nondeterministic VideoToolbox encoded bytes.
Presentation contract and schema/state/report version remain v2; V12 requires
its own signed tag, first-attempt CI, and sole proof.

This is **implementation/process separation**, not independent scientific
review. The project is currently author-operated and
`AUTHOR_SELF_VERIFICATION`; no independent human reviewer or independent
external replication has completed the same evidence chain.

### 4. Failure-state semantics: execution success is not metric success

The macOS proof uses a private fresh runtime, an exclusive lock, a challenge
nonce, a unique result-directory check, process-group cleanup, a five-minute
timeout, and a memory-pressure watchdog. Timeout, low memory, stale/multiple
results, non-zero worker exit, or verifier disagreement terminate the command
as failure. The Linux path in
[`platforms/linux/scripts/run-regression.sh`](../platforms/linux/scripts/run-regression.sh)
requires a clean Git checkout and a new output directory, forbids beacon state,
records a regression-only pre-run contract, applies a hard timeout, and writes
the final run manifest only after raw evidence verification succeeds.

The cross-model project demonstrates why metric and execution states must stay
separate. Its public
[`RESULTS.md`](https://github.com/ALLPROTO/core-lm-cross-model-lab/blob/main/RESULTS.md)
records a real Pythia-410M-deduped run that executed and verified correctly but
produced `2.059581758x` compression with `+0.270073175` delta NLL and only
`74.9023438%` top-1 agreement: **FAIL**. The negative cell is not dropped,
replaced, or averaged away. It directly rules out a universal transfer claim
for the unchanged Qwen-derived profile.

**Engineering decision:** an infrastructure error is not evidence that the
codec fails behaviorally, and a successfully executed negative metric result
is not an infrastructure error. Preserving that distinction makes retries,
incident analysis, and scientific boundaries auditable.

### 5. Supply-chain threat model: reproduce inputs, not just commands

The policy is implemented primarily in
[`security/verify_supply_chain.py`](../security/verify_supply_chain.py),
[`security/generate_build_provenance.py`](../security/generate_build_provenance.py),
[`security/generate_python_runtime_manifest.py`](../security/generate_python_runtime_manifest.py),
and [`SECURITY.md`](../SECURITY.md).

Controls cover several concrete threats:

- GitHub Actions must use full commit SHAs and read-only repository
  permissions; risky workflow triggers and duplicate YAML keys fail closed.
- Python requirements are exact and hash-locked; deterministic direct SBOM and
  live OSV checks cover their stated scopes.
- The secret scanner checks the worktree plus reachable commit/tag history for
  high-confidence credentials.
- Build provenance records commit, tree, clean/dirty state, remote, exact tag,
  toolchain, architecture, SDK, and Swift compiler identity.
- The app's signed runtime manifest covers the external Python base prefix,
  virtual environment, native libraries, and package bytes.
- Model, tokenizer, and corpus files are revision-, size-, and SHA-256-bound
  before inference, then used offline for evidence-bearing execution.

The local app is ad-hoc signed: this seals a user's build but does not
authenticate Ivan Tyshchenko as a binary publisher. The prototype is not a
sandbox for hostile Python, models, datasets, the operating system, or the
current user, and its checks do not prove the absence of every vulnerability.
Source—not a portable prebuilt app—is the supported reproducibility artifact.

Verify the public codec source tag and repository gates with:

```sh
git -c gpg.ssh.allowedSignersFile=signing/allowed_signers \
  verify-tag corelm-codec-source-2e8d3b-v1
./corelm verify
```

## Ownership and claim boundary

Ivan Tyshchenko directed the project and is responsible for its architecture,
claims, releases, and mistakes. Implementation, testing, adversarial audits,
and documentation were developed with substantial AI/Codex assistance. AI
agents are tools, not coauthors, independent human reviewers, or external
replicators. A reviewer should therefore evaluate ownership by asking Ivan to
explain and modify the five paths above without agent assistance.

What the project supports today: a working source-built macOS UI, Linux CPU
path, canonical KV-cache format, real-Qwen replay, retained evidence, separate
verifiers, and transparent positive and negative regression results. It does
not support claims of universal LLM generalization, model-weight compression,
free-running generation quality, lower latency or memory, production-serving
readiness, state of the art, independent human validation, or completed Blind
V1 confirmation.

For exact result scope, continue with [`RESULTS.md`](RESULTS.md) and
[`LIMITATIONS.md`](LIMITATIONS.md).
