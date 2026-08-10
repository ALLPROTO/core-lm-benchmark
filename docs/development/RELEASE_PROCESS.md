# Release process

This document is for maintainers. End users should start with
`platforms/macos/BUILD_AND_VERIFY.md`.

## Preserved artifact channels

Historical evidence and protocol tags/releases are frozen scientific records.
Publication tags, releases, and uploaded assets are likewise preserved by
project policy. Never move a tag, replace an uploaded asset, rewrite a consumed
attempt marker, or change a frozen result in place. GitHub's per-release
`immutable` API flag is a separate platform property and must be checked rather
than inferred from this preservation policy.

The existing publication snapshot uses `voidtoken-v5-paper-v5`. At that
immutable tag, its CFF version, manuscript reference, SBOM component, archive
provenance, and canonical asset names are synchronized. The current default
branch instead uses the `corelm-portfolio-v11` software CFF/SBOM identity and
the `corelm-automated-presentation-v2` automation contract.
Check GitHub's live
`immutable` API field before making a platform-immutability statement; do not
derive it from the project policy alone. Regardless of that field, do not
modify the existing snapshot: publish corrections under a new unique tag and
release instead. The beacon protocol uses the separate
`corelm-beacon-heldout-v1` release channel and is not superseded by whichever
release GitHub labels “Latest.”

## Common candidate checks

Before creating any new release, complete the shared checks:

1. work from a clean branch and preserve all historical evidence;
2. run the Python and Swift suites;
3. integrity-check preserved historical artifacts without regenerating them,
   and execute or replay only registered real-model evidence;
4. verify workflow policy, dependency locks, SBOM, secret history, and OSV;
5. build the application and run a fresh challenge-bound proof;
6. verify deterministic archives twice;
7. push the exact commit and wait for branch and pull-request CI.

Then choose exactly one release contour. Do not reuse one contour's tag or
packager for the other.

### Historical paper archive

1. create a new, never-used **lightweight** `voidtoken-v5-paper-vN` tag only
   after CI is green;
2. require that tag to equal the exact `version` in `CITATION.cff` at the
   dedicated paper-release commit and the paper SBOM/manuscript identity;
3. wait for tag-triggered CI;
4. run `publication/build_archives.py --release-tag ...` from the publicly
   visible tag and verify checksums.

### Portfolio engineering release

1. use a new, never-used **SSH-signed annotated** `corelm-portfolio-vN` tag
   only after exact-commit Linux and macOS CI are green;
2. require the portfolio CFF, SBOM, source identity, demo evidence, public key,
   and checksum signatures to bind that same tag/commit/tree;
3. follow `publication/PORTFOLIO_RELEASE.md` and independently verify the
   fourteen final assets before upload;
4. generate the exact seven-field GitHub request with
   `publication/verify_portfolio_github_release.py prepare`, publish without
   replacing names, then download all assets and five API views logged out;
5. run the full offline artifact verifier and
   `publication/verify_portfolio_github_release.py verify`, retaining the
   canonical receipt outside the same release; and
6. never pass a portfolio tag to `publication/build_archives.py`.

For V11, post-proof recording, deterministic poster extraction, media assembly,
metadata checks, and evidence collection must complete through the tracked
automation contract without a required human review or manual-edit acceptance
step. Both media assets are classified
`AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`; the machine evidence is the
bound receipt, result, raw containers, logs, and verifier reports. The
automation receipt must state `human_reviewed:false`, `manual_edits:false`,
`machine_evidence:false`, and `pixel_semantics_verified:false`. These fields
describe the accepted artifact path, not a claim that nobody subsequently
viewed the files.

The signed annotated `corelm-portfolio-v3` tag is a preserved failed release
candidate. Its first tag-push Linux and macOS workflows terminated at the exact
tag-ref assertion because the workflow searched for literal backslashes around
the CFF version. That first-attempt admission is irreversibly failed: do not
rerun it, move or replace the tag, or relabel V3 bytes as a later candidate.

The signed annotated `corelm-portfolio-v4` tag is a second preserved failed
candidate. Its tag CI passed, but the automated proof stopped during pre-model
tool preflight when the FFprobe frame-PTS field validator rejected n8.1.2's
`duration_time`/SEI output grammar. The failure occurred before `AttemptLog.reserve`; the durable
V4 attempt marker was never created and no model attempt was invoked or
consumed. Never rerun the V4 contour, move or replace its tag, or relabel V4
bytes as a later candidate.

The signed annotated `corelm-portfolio-v5` tag is a third preserved failed
candidate. Its first tag-push Linux and macOS workflows passed on attempt one.
The first local contour then received an anonymous GitHub API HTTP 403 before
the durable marker; by contract that transport failure was safely retryable.
After the rate limit reset, the normative contour fetched the exact public
responses but rejected GitHub's real run/job IDs above `2^31` in the tag-CI
receipt validator. This second failure also preceded `AttemptLog.reserve`; no
V5 model attempt was invoked or consumed. Never rerun the V5 contour, move or
replace its tag, or relabel its bytes as a later candidate.

The signed annotated `corelm-portfolio-v6` tag is a fourth preserved failed
release candidate. Its signed first-attempt tag CI passed, and its one
scientific proof honestly passed at 2.052384x compression, delta NLL
-0.00000846, 99.5117% top-1 agreement, and 1,024/1,024 heavy-replay decisions
with zero maximum loss error. Its durable state then ended `ATTEMPT_FAILED`
after `REPLAY_VERIFIED`: the preflight-built explanatory-window executable
differed from the proof-rebuilt verified app. Same-run result capture, media
sealing, and collection never occurred. Never rerun the V6 contour, move or
replace its tag, or relabel its proof or partial media as a later identity.

The signed annotated `corelm-portfolio-v7` tag is a fifth preserved failed
release candidate. Its exact source commit is
`8d53e43208f76141a01bb2c0914459fbc101e7d5`, tree
`ea82aa490c008d8560a6d44a70407d8d5e33bdbc`, and tag object
`2c82497617173e3dfd965502860082ab5bf98130`. Its first tag CI passed on attempt
one in Linux run `31328178519` and macOS run `31328178525`. The three V7 runner
invocations all stopped strictly before `AttemptLog.reserve`: two failed the
>=50% available-memory admission after the parallel Swift preflight build left
less than 50% available memory, and one transient pre-marker public tag-CI
admission failure had an unretained nested cause; the exact same 8-response
validation subsequently passed. The durable state and session remained absent after all
three; no proof or model attempt was consumed. Never rerun the V7 contour, move
or replace its tag, or relabel it as a later identity.

The signed annotated `corelm-portfolio-v8` tag is a sixth preserved failed
release candidate. Its exact source commit is
`b1fc746e7f8a5bd1bf826d9f5219779d568fa0c4`, tree
`3c9c5d64530e7c706dc1c9b9cf91d00c81a08a3d`, and tag object
`64c9d84ddd8aa04b01459447b7c9f3f16f8f6db3`. Exactly one local V8 runner
invocation occurred. Its first resource admission passed and the release build
completed with top-level `--jobs 1`, while the observed Swift frontend argv
retained `-num-threads 8`. That observation does not establish that the
frontend setting caused the later host-memory result. The second unchanged
>=50% available-memory admission failed closed with the exact PTY line
`AUTOMATED PORTFOLIO DEMO FAIL: at least 50% available memory is required`.
After cleanup the durable state, session, and staging directory were absent.
`AttemptLog.reserve` was never reached; no proof or model attempt was invoked
or consumed, and no portfolio media was retained. Never rerun the V8 contour,
move or replace its tag, or relabel it as V9. The distinct V9 identity adds the
exact Swift frontend `-num-threads 1` pin without weakening the 50%
available-memory threshold. Receipts bind the exact produced app SHA; this does
not claim byte-deterministic executable builds across scratch roots. V9 retains
`corelm-automated-presentation-v2` and requires its own signed commit, tag,
first-attempt tag CI, and proof.

The signed annotated `corelm-portfolio-v9` tag is a seventh preserved failed
release candidate. Its exact source commit is
`33d99db9a8cb239732910d96fc18dcaa43b78e3e`, tree
`8fb25db8c54fc248e3b6c1b119fc06fb06be300f`, and tag object
`ac69a22fef383f78634cda5e7256bca37e914acf`. Its first tag CI passed on attempt
one in Linux run `31335135716` and macOS run `31335135699`. Exactly one V9
attempt was consumed, UUID `57a75c79-f37f-44b0-adc0-ba0762d200b0`. Proof and
replay passed at 2.0523837550538349x compression, delta NLL
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
automation receipt, or release was produced. Never rerun the V9 contour, move
or replace its tag, or relabel it. V10 was the distinct successor and wrapped
the full sterile runner lifetime with exact `/usr/bin/caffeinate -dis`; `-u`,
`-t`, and `-w` were forbidden, and an unavailable wrapper failed before the
attempt marker.

The signed annotated `corelm-portfolio-v10` tag is an eighth preserved
candidate. Its exact source commit is
`bb53cd81d9e9ece92a078d823e6bf07474ff762b`, tree
`d840e2a2112fc5ee0cdae0c1f0bf1e5fb2c875da`, and tag object
`27419a0b91934bd76d430ac7c0eadf073389e26c`. First-attempt tag CI was green:
Linux run `31338205386` and macOS run `31338205397`. Exactly one V10 attempt
was consumed, UUID `7cad5bc5-57dd-4778-b00f-528ae3ba7936`. Its sole proof and
heavy replay passed at 2.0523837550538349x compression, delta NLL
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
900-frame 1280x720
MP4 SHA-256 was
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
treated those bytes as a truncated atom header. Top-level atoms ended exactly at EOF; independent
FFprobe and full decode passed all raw segments; their hashes remained bound
in state/report; and the final MP4 passed atom/decode validation. This does not
justify generic parser weakening. V10's bound raw segments cannot be remuxed,
trimmed, or replaced. Failed collection removed transient staging; the V10
inputs directory, fourteen-asset directory, and GitHub Release remained
absent. Never move, rerun, reuse, or relabel V10.

V11 is the distinct corrected identity. Its collector accepts exactly four
zero padding bytes only at the end of an `avc1` child region while requiring a
valid nonempty `avcC`; nonzero, wrong-length, misplaced, and missing-`avcC`
cases fail. The generic parser and `corelm-automated-presentation-v2` contract
remain unchanged. V11 requires its own signed commit/tag, first-attempt tag CI,
and sole proof.

This contour leaves independent-replication gate G10 **OPEN**. An author-run
automation, including an agent-run audit, cannot satisfy it. Only a later
published clean-clone replication by a non-author, non-agent person can close
that gate.

The receipt records the live response's `immutable` boolean; it does not
require that value to be true and does not convert project preservation policy
into a GitHub platform claim. Its API files are saved snapshots, so the
operator must separately preserve the logged-out fetch commands and confirm
the public page. Caller-selected `ffprobe` hash/version are invocation evidence
only, not a release trust root.

After that snapshot, `verify-successor` may approve one signed documentation-
only child commit if C0 is API-immutable, the tag still names C0, the public
diff contains only modified `README.md` plus added
`docs/media/corelm-result.png`, the PNG equals the released poster, and README
contains only the two exact tagged release-media URLs. The portfolio tag stays
on C0; C1 is presentation only and cannot replace or redefine evidence.

Code or packaging corrections discovered after C0 cannot be smuggled into that
presentation-only C1. If the existing release is preserved first, land such
corrections as a separately signed linear C2 after C1 and rerun exact-commit
CI. If a correction is required in the release source itself, mint a new
`corelm-portfolio-vN` identity and record a new tagged regression proof; never
move the old tag or rebind its proof to successor bytes.

The signed `corelm-portfolio-v1` source has two known collector portability
defects: its app-created empty `python-cache/` conflicts with the frozen live-run
topology, and its evidence verifier observes macOS temporary paths through the
`/var` alias instead of the canonical `/private/var` path. A local v1 collection
may retain an operator record, temporarily exclude and then restore only the
proven-empty owner-only cache, set a canonical `TMPDIR`, and run the frozen
collector; neither workaround changes evidence bytes or permits a model rerun.
Those workarounds do not make v1 generally reproducible. A workaround-free
portfolio publication and CV-ready claim therefore require the corrected
successor source under a new signed tag plus a new tagged regression proof.

Historical paper publication commands and arXiv submission steps remain in
`publication/README.md`, `publication/reproducibility/README.md`, and the
submission checklist. The portfolio release has a separate signed-asset
workflow because its tag and trust contract are intentionally different.

## Final and development output

- `.build/` contains Swift development products.
- `dist/CoreLMBenchmark.app` is the locally built final application.
- `output/development/` is the recommended location for preview archives.
- `output/final/<release-tag>/` is the recommended location for final tagged
  archives.

Pass an explicit `--output` directory to `publication/build_archives.py`. Do
not rename canonical files inside a published package; consumers and checksum
manifests may depend on them.
