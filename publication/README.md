# Core LM publication package

This directory preserves the historical real-model paper and its
reproducibility package alongside the current portfolio release tooling.

## Contents

- `arxiv-v5/` - historical prospective real-model VoidToken v5 paper source.
- `corelm_voidtoken_v5.pdf` - visually inspected historical v5 PDF.
- `reproducibility/` - instructions for verifying the real-model evidence.
- `build_archives.py` - deterministic v5 arXiv and reproducibility archive
  builder.
- `PORTFOLIO_RELEASE.md` - fail-closed 14-asset portfolio release and public
  verification contract.
- `verify_portfolio_github_release.py` - network-free exact GitHub request
  generator and saved public-API/14-asset receipt verifier.

The retired synthetic paper and its 115-run data are deliberately absent from
the default branch. Their exact historical bytes remain recoverable from the
immutable `voidtoken-v5-paper-v5` Git tag. They are not part of this package.

The historical v1 runner recorded 150,601,728 canonical BF16 bytes and
73,346,513 complete-container bytes (`2.0532909x`) for the v5 holdout, with
delta NLL `-0.0000609346`, top-1 agreement `4071/4096`, and all seven
registered gates passing. Those immutable v1 artifacts did not retain
per-layer container manifests, so their compression total is protected by
result/file/Git digests but is not independently reconstructible. The evidence
is bounded to the registered model revision, WikiText-2 windows,
teacher-forced replay, and MPS runtime.

The current-source native-app proof is deliberately separate from those
historical claims. Each run uses fixed public validation blocks 64–71 and
retains 192 raw VTL5 containers, the eight 512-token source slices, and 1,024
token-level metric rows. A fast standard-library verifier recomputes container
bytes, compression, NLL, top-1 agreement, and digests; a heavyweight clean-room
replay retokenizes the pinned WikiText input, decodes VTL5 without importing
the RealLLM codec, rebuilds both KV paths, and reruns all 1,024 Qwen decisions.
This improves application-regression reproducibility but does not reconstruct
the immutable v1 containers or independently regenerate full-distribution KL
and cache-error aggregates. Blocks 64–71 have been exercised repeatedly, so
these runs are repeatability checks, not independent experiments or new blind,
holdout, or generalization evidence.

A separate selected-window protocol published its commit, hashes,
parameters, gates, audited eligible pool, and deterministic future-public-
beacon selection rule under tag and GitHub Release
`corelm-beacon-heldout-v1`. Its release summary names four key normative
artifacts; the authoritative `RealLLM/beacon_freeze.json` enumerates and hashes
the complete 26-path normative source set. The freeze preceded the target
pulse; the single recorded execution later selected blocks 512--543 and
published terminal **PASS** at evidence commit
`85c2add1799652a818873a04310b75821728da11`, tag and release
`corelm-beacon-heldout-v1-evidence`. The suite is consumed. This result covers
one pinned Qwen revision and one WikiText-2 window, not arbitrary-model or
corpus-wide generalization. Raw beacon evidence assets are not duplicated in
the current paper package; their immutable evidence ref remains canonical, and
the reproducibility archive includes the evidence/CI report and exact
identities.

## Separate release-tag contours

Two tag families have different contracts and must never be substituted for
one another:

- `voidtoken-v5-paper-vN` is the lightweight historical paper archive contour.
  `publication/build_archives.py --release-tag` accepts only this exact family
  from a checkout whose historical `CITATION.cff` names the same paper tag,
  verifies that the tag is lightweight, points to clean `HEAD`, and is visible
  on the canonical public origin. The current default branch instead names the
  current `corelm-portfolio-v12` software identity.
- `corelm-portfolio-vN` is the SSH-signed annotated portfolio and source-
  verification contour. Its signed-source identity is verified against the
  pinned signer policy and canonical remote; the separate
  `tools/independent_replication.py` workflow remains an open human G10 gate.
  The archive builder rejects portfolio tags as the wrong paper contour.

A paper archive may be linked from a portfolio release, but its provenance
continues to name its own `voidtoken-v5-paper-vN` tag. A portfolio tag does not
retroactively sign or rename a historical paper archive, and a lightweight
paper tag cannot satisfy the signed portfolio source gate.

## Generate and preview

Regenerate the v5 tables and vector figures from checked-in JSON:

```sh
python3 publication/arxiv-v5/generate_figures.py
```

Build preview archives:

```sh
python3 publication/build_archives.py --verify-determinism
python3 publication/build_archives.py
(cd output && shasum -a 256 -c SHA256SUMS)
```

The current archive names are:

- `corelm_voidtoken_v5_arxiv_source.tar.gz`
- `corelm_reproducibility.tar.gz`
- `corelm_voidtoken_v5.pdf`
- `SHA256SUMS` covering all three artifacts above

A preview from a dirty working tree is intentionally not upload-ready.
`PROVENANCE.json` records the source-state mode.

On the default branch that preview includes the current
`corelm-portfolio-v12` CFF/SBOM identity and is an `UNRELEASED_PREVIEW`; it is
not a byte claim about the historical paper-v5 package. Exact paper-v5
reproduction requires the detached tag below.

The V12 portfolio media path is governed by
`corelm-automated-presentation-v2` and is classified
`AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`. It requires no human review or
manual edit to accept generated media, but it does not verify pixel semantics
and does not make the video or poster scientific machine evidence. Gate G10
remains **OPEN** until a non-author, non-agent person publishes the required
clean-clone replication.

V12 is distinct from the preserved V3, V4, V5, and V6 failures. V3 failed its
first tag-push assertion. V4 passed tag CI but stopped in pre-model FFprobe
frame-PTS field validation before `AttemptLog.reserve`, so no V4 model attempt was
invoked or consumed. V5 also passed first-attempt tag CI. Its first local
contour received a safely retryable anonymous API HTTP 403 pre-marker; after
reset, its normative contour rejected real GitHub run/job IDs above `2^31` in
the tag-CI receipt validator, again before `AttemptLog.reserve`. No V5 model
attempt was invoked or consumed. The signed `corelm-portfolio-v6` candidate
passed first-attempt tag CI, and its one scientific proof honestly passed at
2.052384x compression, delta NLL
-0.00000846, 99.5117% top-1 agreement, and all 1,024 heavy-replay decisions
with zero maximum loss error. Its durable state then ended `ATTEMPT_FAILED`
after `REPLAY_VERIFIED` because the preflight-built explanatory-window
executable differed from the proof-rebuilt verified app, before same-run result
capture, media sealing, or collection. None of those failed candidates is
rerun, moved, reused, or relabelled as a later identity.

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
`PORTFOLIO DEMO COLLECTION FAIL: demo MP4 has a truncated atom header`. Each
valid raw ScreenCaptureKit QuickTime MOV's `avc1` sample entry contained a
valid nonempty `avcC` and `colr`, then exactly four NUL padding bytes at the end
of that child region. This was a false reject: the generic nested-box parser
treated those bytes as another atom header. Top-level atoms ended exactly at EOF; independent
FFprobe and full decode passed all raw segments; hashes remained bound in
state/report; and the final MP4 passed atom/decode validation. This does not
justify generic parser weakening. V10's bound raw segments cannot be remuxed,
trimmed, or replaced. Failed collection removed transient staging; the V10
inputs directory, fourteen-asset directory, and GitHub Release remained
absent. V10 is never moved, rerun, reused, or relabelled.

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
relabel V11 proof/tag/final media. V12 keeps final byte/report binding and
byte-exact poster replay. Its replay parser requires a strict per-frame SHA-256
framemd5 manifest together with exact frame count and PTS SHA-256; MD5 and
malformed manifests are rejected. Contract and schema/state/report version stay
v2. V12 requires its own signed identity, tag, first-attempt CI, and sole proof.

## Reproduce the existing tagged package

Use a separate clean clone or worktree at the already published
`voidtoken-v5-paper-v5` tag. Reproduction fetches and checks out the existing
tag; it must not create, move, or push that tag again.

```sh
RELEASE_TAG=voidtoken-v5-paper-v5
git fetch origin \
  "refs/tags/$RELEASE_TAG:refs/tags/$RELEASE_TAG"
git switch --detach "$RELEASE_TAG"
git status --short
python3 publication/build_archives.py \
  --release-tag "$RELEASE_TAG" \
  --verify-determinism
python3 publication/build_archives.py --release-tag "$RELEASE_TAG"
(cd output && shasum -a 256 -c SHA256SUMS)
```

## Create a new historical paper archive release

Corrections or new publication assets require a new, never-used lightweight
`voidtoken-v5-paper-vN` tag and a separate GitHub Release. Never reuse
`voidtoken-v5-paper-v5` or `voidtoken-v5-evidence-v1`, and never replace assets
attached to an existing release. Use a dedicated paper-release commit, then
update and test its CFF, manuscript, SBOM, and archive identity so that
commit's exact `CITATION.cff` version equals the new tag. Do not treat the
default branch's portfolio CFF as paper metadata. Then set `NEW_RELEASE_TAG`
explicitly before running:

```sh
: "${NEW_RELEASE_TAG:?set a new, never-used publication tag}"
printf '%s\n' "$NEW_RELEASE_TAG" \
  | grep -Eq '^voidtoken-v5-paper-v[1-9][0-9]*$' \
  || { echo 'publication tag must be voidtoken-v5-paper-vN' >&2; exit 1; }
git status --short
if git show-ref --verify --quiet "refs/tags/$NEW_RELEASE_TAG"; then
  echo "local tag already exists: $NEW_RELEASE_TAG" >&2
  exit 1
fi
if [ -n "$(git ls-remote origin "refs/tags/$NEW_RELEASE_TAG")" ]; then
  echo "public tag already exists: $NEW_RELEASE_TAG" >&2
  exit 1
fi
git push origin HEAD
# Wait until the branch and pull-request CI runs are green.
git tag "$NEW_RELEASE_TAG"
git push origin "refs/tags/$NEW_RELEASE_TAG"
git ls-remote --exit-code origin "refs/tags/$NEW_RELEASE_TAG"
# Wait until the tag-triggered CI run is green.
python3 publication/build_archives.py \
  --release-tag "$NEW_RELEASE_TAG" \
  --verify-determinism
python3 publication/build_archives.py --release-tag "$NEW_RELEASE_TAG"
(cd output && shasum -a 256 -c SHA256SUMS)
```

The release preflight rejects a dirty worktree, annotated or non-HEAD paper
tag, any tag outside `voidtoken-v5-paper-vN` (including
`corelm-portfolio-vN`), a tag that differs from `CITATION.cff`, wrong origin,
unpublished tag, untracked input, or bytes that differ from `HEAD`. Do not
create the new tag until the exact branch commit has passed CI.

## Before arXiv submission

Open `arxiv-v5/SUBMISSION_CHECKLIST.md`. The author must still confirm the
category, optional email, arXiv account and endorsement status, distribution
license, and final arXiv-generated PDF preview.
