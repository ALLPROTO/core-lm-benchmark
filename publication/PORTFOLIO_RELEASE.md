# Portfolio release contract

`publication/build_portfolio_release.py` is the offline, fail-closed builder
and public verifier for the stable engineering release family
`corelm-portfolio-vN`. It does not create, move, publish, or fetch a tag. It
does not call GitHub. Do not use it for the historical
`voidtoken-v5-paper-vN` contour.

The builder accepts only:

- the exact clean `main` worktree at its canonical HTTPS origin;
- input commit/tree equal to `HEAD`, annotated tag-object SHA equal to the exact
  tag ref, upstream exactly `origin/main`, and local `origin/main` equal to
  `HEAD`;
- an existing local annotated tag with the exact `corelm-portfolio-vN` name,
  targeting that `HEAD`, with one valid SSH signature under the tracked
  `signing/allowed_signers` policy;
- locally available lab and Blind V1 commit/tree objects matching the
  canonical cross-model-lab origin;
- release-exact `CITATION.cff` version, date, Ivan Tyshchenko author identity,
  ORCID, MIT license, and repository URL;
- canonical input, demo-provenance, and runtime-assets JSON with no unknown
  keys or unresolved `@PLACEHOLDER@` values; and
- real silent H.264 demo bytes, a PNG frame, a canonical automation receipt,
  and a safe evidence archive for a non-synthetic
  `AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION`. The media classification is
  exactly `AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`; signed result and
  evidence bytes, not pixels, support the metric.

It produces exactly 14 regular files. `SHA256SUMS` covers exactly the first 12
in bytewise filename order; both it and the canonical source identity receive
detached SSH signatures in namespace `file`:

```text
REPRODUCE-corelm-portfolio-vN.md
allowed_signers
corelm-portfolio-signing.pub
corelm-portfolio-vN-demo-evidence.tar.gz
corelm-portfolio-vN-demo-poster.png
corelm-portfolio-vN-demo-provenance.json
corelm-portfolio-vN-demo.mp4
corelm-portfolio-vN-direct-dependencies.cdx.json
corelm-portfolio-vN-runtime-assets.json
corelm-portfolio-vN-source-identity.json
corelm-portfolio-vN-source-identity.json.sig
corelm-portfolio-vN-source.tar.gz
SHA256SUMS
SHA256SUMS.sig
```

`publication/verify_portfolio_github_release.py` is the separate, network-free
publication-boundary tool. Its `prepare` mode writes the exact GitHub REST
create-release request; its `verify` mode checks saved public API responses
against the exact fourteen downloaded bytes and writes a canonical receipt.
It does not call GitHub, upload an asset, create a tag, or publish a release.

Missing, extra, linked, special, tampered, credential-like, private-key, cache,
or model-weight entries are rejected. Generated manifests, instructions, and
demo evidence also reject author-only absolute paths. The exact source archive
may retain only the hardcoded `(relative path, SHA-256)` allowlist of
already-public historical evidence fields and security-test string fixtures
from the signed Git tree; a new path or byte drift fails. They are not demo
runtime provenance and cannot be silently rewritten by a packager. The source archive uses prefix
`core-lm-benchmark/`, is compressed twice in memory with gzip level 9,
filename empty, and timestamp zero; unequal bytes fail the build. The
direct-dependency CycloneDX 1.5 SBOM is generated twice by
`security/generate_direct_sbom.py`; it must be byte-identical and retain scope
`direct-python-dependencies-only`.

This V12 contract does not reopen a failed historical candidate. V3 remains
frozen at its first tag-push assertion failure. V4 remains frozen after its
automation stopped in pre-model FFprobe frame-PTS field validation, before
`AttemptLog.reserve`; no V4 model attempt was invoked or consumed. V5 passed
first-attempt tag CI. Its first local contour received a safely retryable
anonymous GitHub API HTTP 403 before the marker; after reset, its normative
contour fetched the exact responses but rejected real GitHub run/job IDs above
the tag-CI receipt validator's old signed 32-bit ceiling. That rejection also
preceded `AttemptLog.reserve`; no V5 model attempt was invoked or consumed.
The signed `corelm-portfolio-v6` candidate passed first-attempt tag CI and its
one scientific proof honestly passed at 2.052384x compression, delta NLL
-0.00000846, 99.5117% top-1
agreement, and all 1,024 heavy-replay decisions with zero maximum loss error.
Its durable state then ended `ATTEMPT_FAILED` after `REPLAY_VERIFIED` because
the preflight-built explanatory-window executable differed from the
proof-rebuilt verified app, before same-run result capture, media sealing, or
collection. Never rerun or move V3, V4, V5, or V6, and never relabel their bytes
or partial evidence as a later identity.

The signed `corelm-portfolio-v7` candidate is also frozen. Its exact source
commit is `8d53e43208f76141a01bb2c0914459fbc101e7d5`, tree
`ea82aa490c008d8560a6d44a70407d8d5e33bdbc`, and annotated tag object
`2c82497617173e3dfd965502860082ab5bf98130`. Its first-attempt tag CI passed in
Linux run `31328178519` and macOS run `31328178525`. The three V7 runner
invocations all stopped strictly before `AttemptLog.reserve`: two failed the
>=50% available-memory admission after the parallel Swift preflight build left
less than 50% available memory, and one transient pre-marker public tag-CI
admission failure had an unretained nested cause; the exact same 8-response validation
subsequently passed. The durable state and session remained absent after all
three; no proof or model attempt was consumed. Never rerun or move V7, and never
relabel it as a later identity.

The signed `corelm-portfolio-v8` candidate is also frozen. Its exact source
commit is `b1fc746e7f8a5bd1bf826d9f5219779d568fa0c4`, tree
`3c9c5d64530e7c706dc1c9b9cf91d00c81a08a3d`, and annotated tag object
`64c9d84ddd8aa04b01459447b7c9f3f16f8f6db3`. Exactly one local V8 runner
invocation occurred. Its first resource admission passed and the release build
completed with top-level `--jobs 1`, while the observed Swift frontend argv
retained `-num-threads 8`. That observation does not establish that the
frontend setting caused the later host-memory result. The second unchanged
>=50% available-memory admission failed closed with the exact PTY line
`AUTOMATED PORTFOLIO DEMO FAIL: at least 50% available memory is required`.
After cleanup the durable state, session, and staging directory were absent.
`AttemptLog.reserve` was never reached; no proof or model attempt was invoked
or consumed, and no portfolio media was retained. Never rerun or move V8, and
never relabel it as V9. The distinct V9 identity adds the exact Swift frontend
`-num-threads 1` pin without weakening the 50% available-memory threshold.
Receipts bind the exact produced app SHA; this does not claim byte-deterministic
executable builds across scratch roots. V9 retains
`corelm-automated-presentation-v2`.

The signed `corelm-portfolio-v9` candidate is also frozen. Its exact source
commit is `33d99db9a8cb239732910d96fc18dcaa43b78e3e`, tree
`8fb25db8c54fc248e3b6c1b119fc06fb06be300f`, and annotated tag object
`ac69a22fef383f78634cda5e7256bca37e914acf`. Its first-attempt tag CI passed in
Linux run `31335135716` and macOS run `31335135699`. Exactly one V9 attempt was
consumed, UUID `57a75c79-f37f-44b0-adc0-ba0762d200b0`. Proof and replay passed
at 2.0523837550538349x compression, delta NLL -8.4598101111055257e-06, top-1
agreement 0.9951171875, and 1,024/1,024 replay decisions with maximum errors 0.
Its exact durable state order was `ATTEMPT_STARTED → PROOF_INVOKED →
PROOF_TERMINAL PASS → REPLAY_VERIFIED PASS →
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
automation receipt, or release was produced. Never rerun or move V9, and never
relabel it. V10 was the distinct successor and wrapped the full sterile runner
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
valid nonempty `avcC` and `colr`, followed by exactly four NUL padding bytes at
the end of that child region. This was a false reject: the generic nested-box
parser treated those bytes as another atom header. Top-level atoms ended exactly at EOF;
independent FFprobe and full decode passed all raw segments; hashes remained
bound in state/report; and the final MP4 passed atom/decode validation. This
does not justify generic parser weakening. V10's bound raw segments cannot be
remuxed, trimmed, or replaced. Failed collection removed transient staging;
the V10 inputs directory, fourteen-asset directory, and GitHub Release remained
absent. V10 is never moved, rerun, reused, or relabelled.

V11 is the distinct corrected identity. Its collector accepts exactly four
zero padding bytes only at the end of an `avc1` child region while requiring a
valid nonempty `avcC`; nonzero, wrong-length, misplaced, and missing-`avcC`
cases fail. The generic parser and `corelm-automated-presentation-v2` contract
remain unchanged. V11 requires its own signed tag, first-attempt CI, and sole
proof.

The frozen `corelm-portfolio-v11` source commit/tree/tag-object IDs are
`0071b1c9cbfffdb591a103fcc836a250d3d405e1`,
`4fb72d1dd73b8824f77f562620c16aa6481fc6a4`, and
`2bddc12667f3fac6901f982969003b38abcc3d3e`; first-attempt Linux/macOS tag-CI
runs `31371667051`/`31371667048` passed. Exactly one V11 attempt was consumed,
UUID `6bc357a8-4fc6-4f7c-b73f-0718af818952`. Sole proof/heavy replay passed at
2.0523837550538349x, delta NLL -8.4598101111055257e-06, top-1 0.9951171875,
and 1,024/1,024 decisions with maximum errors 0. Exact nine-event order was
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
Raw preflight/post-proof/result SHA-256 values were
`6d9363fee0a84967a4b9ba474743d8d1a5501f3ce7c53fecf57eb0fd65fd6241`,
`356b96e96d2310cb561ed96bc0246428e30bdcd7ac32ac49e47d0d4d7a014169`, and
`1661a2c7e087087de3848518eae9c95809c3ea5b10361a50f7817061844ef848`;
final MP4/decoded/PTS/poster SHA-256 values were
`bb7caa9c0874ac17d259de25ac952f13c9cd832b8dd83bceba94d30772ffe744`,
`7270ca303e891bdd6aaac18a50a518209c7365f794869bb5a974cc5e111f784d`,
`9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`, and
`6e5c774b9f6adba9cd5fe68681a246f01a3f7163aac428f36dff29affb9c5919`.

Collection failed exactly with `PORTFOLIO DEMO COLLECTION FAIL: final video
bytes are not the exact raw composition`. Retained/replay SHA-256 values
`bb7caa9c0874ac17d259de25ac952f13c9cd832b8dd83bceba94d30772ffe744`,
`6e64ff46721b81f8c45e1dfbbac41a6b7595ec8d5b4e101128bbc2f27860ee91`, and
`131953d94a53bd26e5b8d624267df7c88ee96c96cf86671511eaedd07e597ecc`
were byte-distinct but had exact 900-frame decoded framemd5 SHA-256
`7270ca303e891bdd6aaac18a50a518209c7365f794869bb5a974cc5e111f784d`
and PTS identity; only packet-zero type-6 `user_data_unregistered` SEI differed.
This was a false encoded-byte reject. Cleanup left V11 inputs, fourteen assets,
evidence archive, and GitHub Release absent. Never move, rerun, reuse, or
relabel V11 proof/tag/final media; the diagnostic invoked no model and changed
no retained bytes.

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

V13 is the distinct corrected identity. It keeps presentation contract and
schema/state/report version v2. Its media gate retains the exact frame count,
PTS identity, and strict per-frame SHA-256 framemd5 manifest; MD5 and malformed
manifests are rejected. It uses a fail-closed staged publication:
`prepare-draft` emits the exact draft request; authenticated `verify-policy`
binds an exact precreate `{"enabled":true}` immutable-release policy snapshot;
POST runs once and its response
is saved; `verify-empty-draft` requires the exact positive ID, tag, name, body,
target, `draft:true`, `prerelease:false`, `immutable:false`,
`published_at:null`, empty assets, and exact upload URL; exactly fourteen
assets upload with no clobber; authenticated `verify-draft` requires the same
ID, exact fourteen names/digests, and a fresh exact prepublish
`{"enabled":true}` policy snapshot; its exact seven-field request PATCHes that
same ID to `draft:false`, `prerelease:false`, and `make_latest:"true"`; then
logged-out final verification binds by-ID, by-tag, latest, and all downloads.
Any mismatch or partial operation stops; there is no delete/recreate, retry,
retag, or V12 relabel. V13 requires its own signed tag, first-attempt CI, and
sole proof.

## Automated public tag-CI admission

Before the retained attempt is reserved or any model is loaded, the automation
runner performs one bounded online admission against anonymous
`api.github.com` endpoints. This is the sole network exception to the otherwise
offline proof: model weights, corpus assets, app execution, replay, capture,
collection, and release construction remain offline. Proxy, authentication,
redirect, ambiguous response, timeout, or API failure stops before the durable
attempt marker and is safely retryable. The admission verifies all of the
following:

1. each URL resolves in `ALLPROTO/core-lm-benchmark`;
2. each run's `head_sha` equals the input source commit;
3. conclusion is `success` and no required job is skipped or cancelled;
4. one run is the required Linux x86-64 gate and the other is the required
   macOS arm64 gate; and
5. the tag object/target still equals the signed tag-object SHA and source
   commit/tree.

The runner retains the exact eight bounded API responses, a canonical public
admission receipt, and a separately hard-pinned local SSH trust receipt. The
collector and release builder parse those raw bytes again, recompute the
receipt, bind its exact Linux/macOS URLs and annotated tag-object identity, and
archive the complete response bundle. There is no operator-confirmation
Boolean. Retained responses prove what the public API returned at admission
time; they are not a GitHub-signed attestation or a substitute for a later live
current-state recheck.
Cross-model-lab `main` and PR #5 are a separate local exact-ref boundary
checked by collector and builder; these eight benchmark-repository responses
do not claim current public lab state.

## Canonical input

The input must validate against
`schemas/portfolio-release-input.schema.json` and be serialized as compact
UTF-8, sorted keys, no ASCII escaping requirement, and exactly one final LF:

```python
target.write_bytes(
    (json.dumps(value, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False) + "\n").encode()
)
```

It binds the tag/date, source commit/tree, two distinct successful Actions run
URLs plus the same commit, lab main commit/tree, Blind V1 draft commit/tree and
lifecycle, the exact automation-only presentation contract, and absolute paths
to five local automatically collected demo assets. Absolute paths are
input-only and never enter an output asset.

The canonical V13 demo-provenance object has the exact keys documented by the
builder: source/tag; video hash, duration, dimensions, silent H.264;
poster hash, dimensions and fixed frame timestamp; both media objects
classified `AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`; macOS arm64
single-window capture; automation-receipt, executable, result, receipt and
evidence hashes; workload classification; and `synthetic_data:false`. Its
capture contract is `corelm-automated-presentation-v2` with
`automation_only:true`, `human_reviewed:false`, `manual_edits:false`,
`machine_evidence:false`, and `pixel_semantics_verified:false`. The canonical
runtime-assets object binds source/tag, macOS arm64, Python 3.12.13, the exact
window-helper, `screencapture`, FFmpeg, and ffprobe identities, and the complete
canonical Apple toolchain object copied from the run's validated
`build-provenance.json`. That object records
either `developerTools.kind:command-line-tools` with the exact CLT package
identifier/version and a null `buildVersion`, or `developerTools.kind:xcode`
with the exact Xcode identifier/version/build. It never invents a separate
`xcode_version` when only Command Line Tools were used. The manifest also binds
exact tracked lockfile and verifier/dependency-source hashes, the exact
ffprobe executable SHA-256 and first `ffprobe -version` line used by the
builder, pinned Qwen repository/revision/license and the exact seven
path/size/SHA-256 assets, pinned WikiText validation
repository/revision/path/size/SHA-256/license/source URL, executable
hash, and proof hashes. The builder verifies tracked lockfile/verifier hashes
against the clean source.

`AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION` is the exact workload enum for
the public validation range fixed before this V13 execution. It is not a media
selection or human-review state: the tagged proof-driver attempt and its first
honest terminal outcome are retained once by the owner-local automation state.
The proof driver also performs the required pinned-Qwen heavy replay; the
contour does not describe that as zero additional model execution or claim
global historical uniqueness.

The evidence archive contains a canonical public runtime projection, not the
private manifest's owner-specific absolute roots. The projection binds the
source runtime-manifest SHA-256 and schema, entry-list SHA-256, file/symlink/
byte totals, Python version, and executable SHA-256. Verification requires that
Python identity to equal `runtime-assets.json`, the receipt worker identity,
and the result environment exactly.

Before build, fetch the related refs into the exact local names
`refs/remotes/origin/main` and `refs/remotes/origin/pull/5/head`. The builder
requires the recorded lab and Blind commits/trees to equal those refs.

The evidence gzip tar has exact regular members
`run/app-run-receipt.json`, `run/validation-064-071.json`,
`run/build-provenance.json`, `run/runtime-provenance.json`,
`reports/structural-verifier.json`, `reports/fresh-model-replay.json`,
`reports/automated-media.json`, `reports/result-readiness.json`,
`reports/tag-ci-receipt.json`, `reports/local-tag-trust-receipt.json`,
`session/attempt-state.jsonl`, `session/preflight-window.mov`,
`session/post-proof-presentation.mov`, `session/same-run-result.mov`,
`session/find-proof-window`, `logs/terminal.log`, all nine exact files under
`tag-ci-responses/` (eight raw API responses plus the recomputed public
receipt), and only raw files below `run/primary-evidence/`.
Receipt/result bytes are bound to demo provenance; canonical reports bind their
hashes, source commit/tree, metric outcome, pinned model, raw-token digests and
the author-recorded replay. The replay report is labelled
`AUTHOR_RECORDED_HEAVY_REPLAY_INTEGRITY_PASS`, not independently re-executed
proof. It retains the author-side 1,024-decision maxima; the public verifier
recomputes the primary-manifest/token-metrics/per-decision digests and finite
mathematical tolerance envelope before accepting those values. The tracked
product verifier rechecks the complete retained run with metric
PASS or preserved verified metric FAIL. Every member is streamed
through secret/path scanning regardless of size. Links, special entries,
traversal, duplicate paths, secrets, model weights, and private paths fail. The
terminal log is one exact PASS-or-verified-metric-FAIL byte string. The archive
must equal the deterministic reserialization of its sorted regular members
with mode `0600`, zero uid/gid/mtime, and empty owner names.

## Run and collect one automated tagged proof

`platforms/macos/scripts/run-automated-portfolio-demo.py` is the only current
V13 capture entry point. Invoke it through `./corelm macos portfolio-demo` from
the exact clean, signed tagged checkout. It checks the tag/main/source binding,
AC power, offline runtime and assets, capture authorization, exact app/window,
and tool identities before invoking the model. It then reserves one durable
exclusive attempt for the tag, invokes the proof once, preserves its first
honest terminal PASS or verified metric FAIL, then records a fixed 12-second,
model-free `--portfolio-capture-presentation` explanatory overview from the
exact verified proof app and an
18-second capture-safe view of the exact retained result,
creates one fixed silent H.264 composition, and derives the poster at exactly
15.000000 seconds. The normal proof UI, worker log, and free-form error surface
are never captured.

```sh
DEMO_TAG=corelm-portfolio-v13
FFMPEG=/absolute/path/to/ffmpeg
FFPROBE=/absolute/path/to/ffprobe
DEMO_SESSION=/absolute/absent/corelm-portfolio-v13-automated-demo

CORELM_OFFLINE=1 \
CORELM_WHEELHOUSE="$HOME/.cache/corelm/macos/wheelhouse" \
./corelm macos portfolio-demo \
  --tag "$DEMO_TAG" \
  --output "$DEMO_SESSION" \
  --ffmpeg "$FFMPEG" \
  --ffprobe "$FFPROBE"
```

The output used by collection is the final video/poster plus the fixed bounded
session evidence: automation and readiness receipts, the nine-event state log,
three raw window segments, compiled window helper, public/local tag trust
receipts, and eight-response tag-CI bundle. The receipt binds the exact source,
run UUID and challenge, result/receipt/app hashes, two window identities,
capture tools, media bytes, decoded-frame and PTS digests, fixed poster,
privacy boundary, and durable attempt-state digest. A capture or media failure
after proof invocation consumes the tag attempt and cannot be retried to seek
a preferred result.

The exact V13 state order is
`ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL → REPLAY_VERIFIED → POST_PROOF_PRESENTATION_SURFACE_READY → POST_PROOF_PRESENTATION_CAPTURED → SAME_RUN_REOPENED → RESULT_CAPTURED → MEDIA_SEALED_FOR_COLLECTION`.
The first composed raw role is exactly `post_proof_presentation`; legacy
live-role names, paths, and command-line options are not accepted by this
contour.

The same session may contain private driver/UI logs. Do not upload or publish
the session directory as a whole. Only the explicitly named bounded inputs
below enter collection; the collector revalidates them and embeds their exact
public-safe subset into the signed evidence archive.

`publication/collect_portfolio_demo.py` is the bounded offline bridge from
that exact retained proof, media, and automation receipt to the five release
assets. It does not run a model, choose a result, or infer the newest run. Pass
the run UUID named by the receipt, the exact app, silent H.264 video, fixed PNG,
receipts, raw segments, helper, tag-CI response bundle, FFmpeg/ffprobe, signed
tag, and local lab checkout:

```sh
PORTFOLIO_PYTHON="$HOME/.cache/corelm/macos/runtime/bin/python"
LAB=/absolute/clean/core-lm-cross-model-lab
RUN_DIRECTORY=/absolute/exact/run-directory-from-automation-receipt
INPUTS=/absolute/absent/corelm-portfolio-v13-inputs

publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" collect_portfolio_demo.py \
  --repository "$PWD" \
  --cross-model-lab "$LAB" \
  --run-directory "$RUN_DIRECTORY" \
  --app "$PWD/dist/CoreLMBenchmark.app" \
  --video "$DEMO_SESSION/$DEMO_TAG-demo.mp4" \
  --poster "$DEMO_SESSION/$DEMO_TAG-demo-poster.png" \
  --automation-receipt "$DEMO_SESSION/automation-receipt.json" \
  --result-readiness "$DEMO_SESSION/result-readiness.json" \
  --attempt-state "$DEMO_SESSION/attempt-state.jsonl" \
  --preflight-segment "$DEMO_SESSION/preflight-window.mov" \
  --post-proof-presentation-segment "$DEMO_SESSION/post-proof-presentation.mov" \
  --result-segment "$DEMO_SESSION/same-run-result.mov" \
  --window-helper "$DEMO_SESSION/find-proof-window" \
  --tag-ci-receipt "$DEMO_SESSION/tag-ci-receipt.json" \
  --local-tag-trust-receipt "$DEMO_SESSION/local-tag-trust-receipt.json" \
  --tag-ci-bundle "$DEMO_SESSION/tag-ci-bundle" \
  --ffmpeg "$FFMPEG" \
  --ffprobe "$FFPROBE" \
  --tag "$DEMO_TAG" \
  --release-date 2026-08-10 \
  --output "$INPUTS"
```

The collector recomputes product evidence, fixed-poster and decoded-video
identity, requires all proof and automation reports, preserves an honest metric
FAIL, checks privacy and exact archive topology, and writes canonical
provenance/runtime manifests, a deterministic evidence gzip tar, and a private
release-input draft. Before verification and archiving it seals all run inputs
into a private stable snapshot; later changes to the original run cannot alter
the collected bytes. Never publish `release-input.private.json`, because its
local asset paths are input-only. See `docs/DEMO.md` for the complete preflight
and failure semantics.
The live run has one additional non-evidence entry: the app-created
`python-cache/`. It is mandatory, must be an empty owner-controlled mode-`0700`
directory, is held open and rechecked throughout sealing, and is never copied
into the snapshot or evidence archive. Any contents, link, replacement, missing
directory, or unsafe mode fail closed. Temporary evidence extraction uses the
canonical resolved directory, so the macOS `/var` to `/private/var` alias cannot
invalidate an otherwise canonical extracted run.

## Build locally

Do not place the private key in the repository or input JSON. Use an absolute
0600 path through the environment; the tool verifies that its public half
matches the hard-pinned tracked ED25519 key and never emits or copies the key
path:

Install a local `ffprobe` first (for example from the platform FFmpeg package).
The Core LM bootstrap intentionally does not install it. Build mode binds its
exact executable SHA-256 and version; public verify uses the reproducer's
local binary only as a caller-side decoder check.

```sh
./corelm macos bootstrap
./corelm macos build
PORTFOLIO_PYTHON="$HOME/.cache/corelm/macos/runtime/bin/python"
test "$("$PORTFOLIO_PYTHON" -I -B -c \
  'import platform; print(platform.python_version())')" = 3.12.13
FFPROBE=$(command -v ffprobe)
test -x "$FFPROBE"
export CORELM_PORTFOLIO_SIGNING_KEY=/absolute/private/path
publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" build_portfolio_release.py \
  --input /absolute/release-input.json \
  --repository /absolute/core-lm-benchmark \
  --cross-model-lab /absolute/core-lm-cross-model-lab \
  --ffprobe "$FFPROBE" \
  --output /absolute/corelm-portfolio-vN-assets
```

The output path must not exist. Build occurs in a private sibling staging
directory, performs a full public verification, then renames the directory
only after every gate passes. No release is published by this command.

## Public offline verification

Use the verifier from the exact signed source tag and point it at a directory
containing all downloaded release files:

```sh
case "$(uname -s):$(uname -m)" in
  Darwin:arm64)
    ./corelm macos bootstrap
    ./corelm macos build
    PORTFOLIO_PYTHON="$HOME/.cache/corelm/macos/runtime/bin/python" ;;
  Linux:x86_64)
    ./corelm linux bootstrap
    ./corelm linux build
    PORTFOLIO_PYTHON="$HOME/.cache/corelm/linux/runtime/bin/python" ;;
  *) exit 2 ;;
esac
FFPROBE=$(command -v ffprobe)
test -x "$FFPROBE"
publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" build_portfolio_release.py \
  --verify /absolute/downloaded-assets \
  --ffprobe "$FFPROBE"
```

This checks the exact 14-file set, public-key hard pins, both detached
signatures, the sorted checksum manifest, canonical identities, all internal
hash bindings, archive safety, source commit PAX identity, SBOM scope,
reproduction document, complete PNG structure/CRC, MP4 `avc1`/`avcC` sample
description, nonempty media payload, and the Git tree reconstructed from every
source-archive blob and executable bit. Required local `ffprobe` rechecks
codec, audio, dimensions, and duration as a **caller-side decoder check**; it
is not a release trust root, and without it the tool refuses to print PASS.
Build mode additionally requires its executable hash and version to equal the
runtime-assets record. The success message is explicitly **offline signed-
artifact PASS — caller-side decoder check only — live CI API recheck
required**. A source tar proves archive-to-tree identity; its PAX commit field
alone does not independently prove commit-to-tree identity without the signed
identity/tag or a canonical Git object database. Offline verification also
does not regenerate GitHub API receipts, the recorded real-model replay, or
the SBOM from a fresh environment. It does not establish current GitHub state,
human-independent replication, or a Blind/generalization result.

## Exact GitHub publication contract

Publication uses the existing, publicly visible signed annotated tag. The tag
must never be created implicitly by the release API. From the exact signed tag
checkout and the already verified fourteen-asset directory, generate the
request into a new absolute path:

```sh
set -eu
TAG=corelm-portfolio-v13
ASSET_DIR=/absolute/corelm-portfolio-v13-assets
PORTFOLIO_PYTHON=/absolute/locked/python
FFPROBE=/absolute/caller-selected/ffprobe
PUBLICATION_ROOT=/absolute/new-corelm-portfolio-v13-publication
REQUESTS="$PUBLICATION_ROOT/requests"
API_INPUTS="$PUBLICATION_ROOT/api-inputs"
RECEIPTS="$PUBLICATION_ROOT/receipts"
DOWNLOADED="$PUBLICATION_ROOT/downloaded-assets"
test ! -e "$PUBLICATION_ROOT"
mkdir -m 700 "$PUBLICATION_ROOT"
mkdir -m 700 "$REQUESTS" "$API_INPUTS" "$RECEIPTS" \
  "$DOWNLOADED"

CREATE_REQUEST="$REQUESTS/create-draft.json"
CREATE_RESPONSE="$API_INPUTS/create-response.json"
EMPTY_DRAFT_RECEIPT="$RECEIPTS/empty-draft.json"
POPULATED_DRAFT_RECEIPT="$RECEIPTS/populated-draft.json"
PRECREATE_IMMUTABLE_POLICY="$API_INPUTS/precreate-immutable-policy.json"
PRECREATE_POLICY_RECEIPT="$RECEIPTS/precreate-policy.json"
PREPUBLISH_IMMUTABLE_POLICY="$API_INPUTS/prepublish-immutable-policy.json"
PUBLISH_REQUEST="$REQUESTS/publish.json"
TAG_OBJECT=$("$PORTFOLIO_PYTHON" -I -B - \
  "$ASSET_DIR/$TAG-source-identity.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["source"]["tag_object"])
PY
)
SOURCE_COMMIT=$("$PORTFOLIO_PYTHON" -I -B - \
  "$ASSET_DIR/$TAG-source-identity.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["source"]["commit"])
PY
)
publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" verify_portfolio_github_release.py prepare-draft \
  --assets "$ASSET_DIR" \
  --ffprobe "$FFPROBE" \
  --output "$CREATE_REQUEST"
```

The canonical request has exactly these seven keys and values:

```json
{
  "tag_name": "corelm-portfolio-v13",
  "target_commitish": "main",
  "name": "Core LM Portfolio v13 — reproducible real-model KV-cache benchmark",
  "body": "generated exactly from the signed source identity and SHA256SUMS digest",
  "draft": true,
  "prerelease": false,
  "make_latest": "false"
}
```

The on-disk JSON is compact canonical JSON; the expanded object above is only
a readable field contract. The exact body contains the supported engineering
claim, scientific exclusions, source commit/tree/tag object, both CI URLs,
demo hashes, exact `AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`
classification, the pixels-versus-evidence and semantic-privacy boundaries,
`SHA256SUMS` hash, the fourteen-asset verification instruction,
caller-decoder boundary, preservation policy, and the explicit warning that
policy is not GitHub's `immutable` API value.

After a final tag/ref and CI API recheck, the maintainer performs this exact
fail-closed sequence. Immediately before create, fetch the authenticated
immutable-release policy and use `verify-policy` to require exact
`{"enabled":true}` and bind its snapshot SHA in a separate receipt. Then POST
the draft request once, save the response, and verify the empty draft before
uploading any asset:

```sh
set -eu
test -z "$(git status --short)"
test "$(git rev-parse HEAD)" = "$(git rev-parse "$TAG^{commit}")"
gh api "repos/ALLPROTO/core-lm-benchmark/immutable-releases" \
  > "$PRECREATE_IMMUTABLE_POLICY"
publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" verify_portfolio_github_release.py verify-policy \
  --immutable-policy-json "$PRECREATE_IMMUTABLE_POLICY" \
  --receipt "$PRECREATE_POLICY_RECEIPT"
gh api --method POST \
  "repos/ALLPROTO/core-lm-benchmark/releases" \
  --input "$CREATE_REQUEST" \
  > "$CREATE_RESPONSE"
publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" verify_portfolio_github_release.py verify-empty-draft \
  --assets "$ASSET_DIR" \
  --ffprobe "$FFPROBE" \
  --create-response-json "$CREATE_RESPONSE" \
  --receipt "$EMPTY_DRAFT_RECEIPT"
```

`verify-empty-draft` revalidates the signed fourteen-asset input and requires
the saved response's exact positive release ID, tag, name, body, target,
`draft:true`, `prerelease:false`, `immutable:false`, `published_at:null`, empty
asset array, and exact ID-bound upload URL. Any mismatch stops before upload.
Use that verified draft identity to upload exactly fourteen assets one file at
a time with no clobber, then save the authoritative authenticated populated-
draft, tag-ref, tag-object, and commit-object responses. A representative
operator sequence is:

```sh
set -eu
DRAFT_FIELDS=$("$PORTFOLIO_PYTHON" -I -B - "$EMPTY_DRAFT_RECEIPT" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))["github_draft"]
print(value["id"])
print(value["upload_url"])
PY
)
RELEASE_ID=$(printf '%s\n' "$DRAFT_FIELDS" | /usr/bin/sed -n '1p')
UPLOAD_URL=$(printf '%s\n' "$DRAFT_FIELDS" | /usr/bin/sed -n '2p')
test "$UPLOAD_URL" = \
  "https://uploads.github.com/repos/ALLPROTO/core-lm-benchmark/releases/$RELEASE_ID/assets{?name,label}"
for asset in "$ASSET_DIR"/*
do
  gh release upload "$TAG" "$asset" \
    --repo ALLPROTO/core-lm-benchmark
done
gh api "repos/ALLPROTO/core-lm-benchmark/releases/$RELEASE_ID" \
  > "$API_INPUTS/draft-by-id.json"
gh api "repos/ALLPROTO/core-lm-benchmark/git/ref/tags/$TAG" \
  > "$API_INPUTS/draft-tag-ref.json"
gh api "repos/ALLPROTO/core-lm-benchmark/git/tags/$TAG_OBJECT" \
  > "$API_INPUTS/draft-tag-object.json"
gh api "repos/ALLPROTO/core-lm-benchmark/git/commits/$SOURCE_COMMIT" \
  > "$API_INPUTS/draft-commit-object.json"
gh api "repos/ALLPROTO/core-lm-benchmark/immutable-releases" \
  > "$PREPUBLISH_IMMUTABLE_POLICY"

publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" verify_portfolio_github_release.py verify-draft \
  --assets "$ASSET_DIR" \
  --ffprobe "$FFPROBE" \
  --create-response-json "$CREATE_RESPONSE" \
  --draft-json "$API_INPUTS/draft-by-id.json" \
  --tag-ref-json "$API_INPUTS/draft-tag-ref.json" \
  --tag-object-json "$API_INPUTS/draft-tag-object.json" \
  --commit-object-json "$API_INPUTS/draft-commit-object.json" \
  --immutable-policy-json "$PREPUBLISH_IMMUTABLE_POLICY" \
  --publish-request "$PUBLISH_REQUEST" \
  --receipt "$POPULATED_DRAFT_RECEIPT"

gh api --method PATCH \
  "repos/ALLPROTO/core-lm-benchmark/releases/$RELEASE_ID" \
  --input "$PUBLISH_REQUEST" \
  > "$API_INPUTS/release-publish-response.json"
```

`verify-draft` requires the same release ID and upload URL, the exact fourteen
asset names/sizes/digests, signed source/tag/commit bindings, and an immediate
authenticated `/repos/ALLPROTO/core-lm-benchmark/immutable-releases` response
whose exact canonical shape is `{"enabled":true}` with no extra key. It alone emits
the compact canonical seven-key PATCH body, repeating exact metadata with
`draft:false`, `prerelease:false`, and `make_latest:"true"`, and prints the
exact same-ID PATCH endpoint. Do not use `--clobber`. An existing or partial
name, unexpected count, digest mismatch, missing response, or changed ID is a
hard stop. Retain every command, response, receipt, and exit status. Never
delete/recreate, retry a failed stage, retag, or relabel this identity. The
`make_latest` value is only a request; the logged-out `/releases/latest` view
is verified independently after publication.

## Logged-out post-upload verification

Fetch six API views and all fourteen assets without a GitHub token, cookie,
`.netrc`, or curl configuration. Use a new directory and a scrubbed environment;
the exact commit and tag-object SHA come from the signed source identity:

```sh
set -eu
TAG=corelm-portfolio-v13
ASSET_DIR=/absolute/corelm-portfolio-v13-assets
PORTFOLIO_PYTHON=/absolute/locked/python
FFPROBE=/absolute/caller-selected/ffprobe
PUBLICATION_ROOT=/absolute/new-corelm-portfolio-v13-publication
REQUESTS="$PUBLICATION_ROOT/requests"
API_INPUTS="$PUBLICATION_ROOT/api-inputs"
RECEIPTS="$PUBLICATION_ROOT/receipts"
DOWNLOADED="$PUBLICATION_ROOT/downloaded-assets"
EMPTY_DRAFT_RECEIPT="$RECEIPTS/empty-draft.json"
POPULATED_DRAFT_RECEIPT="$RECEIPTS/populated-draft.json"
test -d "$REQUESTS"
test -d "$API_INPUTS"
test -d "$RECEIPTS"
test -d "$DOWNLOADED"

PUBLIC_CURL=(/usr/bin/env -i \
  HOME=/nonexistent LANG=C LC_ALL=C \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  /usr/bin/curl -q --fail --silent --show-error --location \
  --proto '=https' --tlsv1.2 \
  -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2022-11-28')

TAG_OBJECT=$("$PORTFOLIO_PYTHON" -I -B - \
  "$ASSET_DIR/$TAG-source-identity.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["source"]["tag_object"])
PY
)
SOURCE_COMMIT=$("$PORTFOLIO_PYTHON" -I -B - \
  "$ASSET_DIR/$TAG-source-identity.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["source"]["commit"])
PY
)
RELEASE_ID=$("$PORTFOLIO_PYTHON" -I -B - \
  "$EMPTY_DRAFT_RECEIPT" "$POPULATED_DRAFT_RECEIPT" <<'PY'
import json, sys
empty = json.load(open(sys.argv[1], encoding="utf-8"))["github_draft"]["id"]
populated = json.load(open(sys.argv[2], encoding="utf-8"))["github_draft"]["id"]
if type(empty) is not int or empty <= 0 or populated != empty:
    raise SystemExit("draft receipt release IDs do not match")
print(empty)
PY
)

"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/$RELEASE_ID" \
  > "$API_INPUTS/public-release-by-id.json"
"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/tags/$TAG" \
  > "$API_INPUTS/public-release-by-tag.json"
"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/latest" \
  > "$API_INPUTS/public-latest.json"
"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/git/ref/tags/$TAG" \
  > "$API_INPUTS/public-tag-ref.json"
"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/git/tags/$TAG_OBJECT" \
  > "$API_INPUTS/public-tag-object.json"
"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/git/commits/$SOURCE_COMMIT" \
  > "$API_INPUTS/public-commit-object.json"

for name in \
  "REPRODUCE-$TAG.md" \
  allowed_signers \
  corelm-portfolio-signing.pub \
  "$TAG-demo-evidence.tar.gz" \
  "$TAG-demo-poster.png" \
  "$TAG-demo-provenance.json" \
  "$TAG-demo.mp4" \
  "$TAG-direct-dependencies.cdx.json" \
  "$TAG-runtime-assets.json" \
  "$TAG-source-identity.json" \
  "$TAG-source-identity.json.sig" \
  "$TAG-source.tar.gz" \
  SHA256SUMS \
  SHA256SUMS.sig
do
  "${PUBLIC_CURL[@]}" \
    "https://github.com/ALLPROTO/core-lm-benchmark/releases/download/$TAG/$name" \
    --output "$DOWNLOADED/$name"
done
```

The GitHub-boundary verifier creates one private exact-fourteen-asset snapshot,
runs the complete offline signed-artifact verifier on that snapshot, and
derives all API size/hash records from the same snapshot. It refuses PASS if
either detached SSH signature, any artifact gate, or the required caller-side
decoder check fails. Retain the caller-selected `ffprobe` executable SHA-256
and exact first version line written to the receipt; that identity describes
the invocation and is not a release-signing, GitHub, or CI trust root.

```sh
RECEIPT="$RECEIPTS/final-public-release.json"
publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" verify_portfolio_github_release.py verify \
  --assets "$DOWNLOADED" \
  --ffprobe "$FFPROBE" \
  --release-id-json "$API_INPUTS/public-release-by-id.json" \
  --release-tag-json "$API_INPUTS/public-release-by-tag.json" \
  --latest-json "$API_INPUTS/public-latest.json" \
  --tag-ref-json "$API_INPUTS/public-tag-ref.json" \
  --tag-object-json "$API_INPUTS/public-tag-object.json" \
  --commit-object-json "$API_INPUTS/public-commit-object.json" \
  --receipt "$RECEIPT"
```

The verifier requires exact tag, title, body, target branch, `draft:false`,
`prerelease:false`, the same complete body/target/published/asset contract in
`/releases/latest`, annotated tag-object/commit binding, commit-to-tree binding,
fourteen uploaded names, sizes, download URLs, and a mandatory exact
`sha256:<local-hash>` API digest for every asset. A missing/null digest fails.
GitHub's tag `verified` value remains informational; the SSH signature from its
API payload must independently verify in namespace `git` under the attached
`allowed_signers`. All three published release views must report
`immutable:true`; `immutable:false`, a missing value, or disagreement is a hard
failure. The receipt records `GITHUB_API_REPORTED_TRUE` only after that exact
gate. GitHub's value does not change the separate project rule that tags and
assets are never moved or replaced.

The receipt binds the saved-response hashes but cannot prove that the fetch was
logged out or that GitHub is still in the same state; those are transport and
time boundaries. The V13 acceptance contour uses the scrubbed logged-out API
fetches and verifier receipt and has no browser inspection or human-review
gate. A later viewer may inspect the public page, but that observation is not
an input to V13 acceptance and cannot retroactively close independent-
replication gate G10. Keep the receipt and API files in the operator/design or
Zenodo evidence bundle. Do not upload them back into the same fourteen-asset
release, edit its body after verification, or move its tag; doing so would
create a self-reference and invalidate the recorded snapshot.

Draft/publish requests, saved API inputs, verification receipts, and downloaded
assets live in four distinct new directories, all disjoint from the signed
local asset directory. `set -eu` aborts the operator sequence on the first
failed one-file `gh release upload`; `--clobber` is never used. The subsequent
authenticated populated-draft GET and `verify-draft` gate—not an upload CLI
response—authoritatively bind all fourteen remote names, sizes, and digests.
The tool rejects an output path that is equal to, inside, or an ancestor of any
protected input directory; this prevents generated output from contaminating a
verified input set.

## Presentation successor after publication

Call the automation-capable tagged release-source commit C0. C0 owns the
signed source/evidence identity and the immutable fourteen-asset release. The
presentation successor C1 is optional for G12 artifact integrity, but it is
mandatory for G03 and `CV_READY` while the public README has no current
poster/video. C1 adds no evidence and requires no human-review acceptance. It
is allowed only after the saved release and latest APIs both report
`immutable:true`, the signed tag still resolves to C0, and the full C0 artifact
verification passes. C1 must be exactly one signed child of C0 and its public
compare response must contain exactly these changes:

```text
README.md                              modified
docs/media/corelm-result.png           added
```

An ordinary GitHub merge commit would give C1 two parents, while squash or
rebase would replace the locally SSH-signed object. Neither is allowed. Run
the required checks on the exact signed C1 commit, then publish that same
object to `main` only by an explicitly authorized fast-forward from C0. Never
force-push or rewrite C1. The saved GitHub commit response and the verifier
below must still validate its local SSH signature and sole parent C0.

The PNG bytes must equal the released `$TAG-demo-poster.png`. README must
contain exactly once each of the immutable tagged poster and video download
URLs; `/releases/latest/download/`, branch/raw links, additional release-media
URLs, renames, or any third changed path fail. Fetch the public compare and C1
commit responses logged out, retain the existing six C0 API snapshots, and
run:

The verifier does not trust `files[].sha` from that saved compare response as
the source of truth. `SUCCESSOR_ROOT` must be a clean canonical-origin Git
checkout whose exact `HEAD`, `HEAD^{tree}`, sole parent, index, tracked blobs,
modes, and local two-path diff reconstruct the signed C1 object chain. The C1
query disables and rejects replacement refs and legacy grafts, parses the raw
commit object's tree/parent headers, and pins `/usr/bin/ssh-keygen` instead of
trusting repo-local signature-program configuration. The C1
README is deterministic: it is the byte-exact C0 README with only this block
inserted immediately after `# Core LM Benchmark` and its blank line (replace
the shell variables with their exact values; do not edit the wording):

```markdown
<!-- corelm-portfolio-presentation-v1:start -->
## Verified real-model demo

![Core LM benchmark result](https://github.com/ALLPROTO/core-lm-benchmark/releases/download/$TAG/$TAG-demo-poster.png)

[Watch the complete demo video](https://github.com/ALLPROTO/core-lm-benchmark/releases/download/$TAG/$TAG-demo.mp4)

This presentation was recorded from SSH-signed release source [`$SOURCE_COMMIT`](https://github.com/ALLPROTO/core-lm-benchmark/commit/$SOURCE_COMMIT) at annotated tag [`$TAG`](https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/$TAG). It is an `AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION` on pinned public data, classified as `AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`. Signed result and evidence files—not the pixels—support the metrics. Automated checks found no configured violation; semantic pixel privacy and independent review are not claimed. This presentation-only successor does not alter the released source or evidence and is **not** a blind/generalization result, model-weight-compression result, or independent human replication.
<!-- corelm-portfolio-presentation-v1:end -->
```

Any other README edit—including a stronger scientific claim—fails even if a
saved compare response is changed to match those bytes.

```sh
C0="$SOURCE_COMMIT"
: "${C1:?set the exact 40-hex signed successor commit}"
printf '%s\n' "$C1" | grep -Eq '^[0-9a-f]{40}$' || exit 2
SUCCESSOR_ROOT=/absolute/clean-c1-checkout
SUCCESSOR_RECEIPT=/absolute/new-successor-receipts/presentation-successor.json

"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/compare/$C0...$C1" \
  > "$API_INPUTS/compare-c0-c1.json"
"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/commits/$C1" \
  > "$API_INPUTS/successor-commit.json"

publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" verify_portfolio_github_release.py verify-successor \
  --assets "$DOWNLOADED" \
  --ffprobe "$FFPROBE" \
  --release-json "$API_INPUTS/public-release-by-tag.json" \
  --latest-json "$API_INPUTS/public-latest.json" \
  --tag-ref-json "$API_INPUTS/public-tag-ref.json" \
  --tag-object-json "$API_INPUTS/public-tag-object.json" \
  --commit-object-json "$API_INPUTS/public-commit-object.json" \
  --compare-json "$API_INPUTS/compare-c0-c1.json" \
  --successor-commit-json "$API_INPUTS/successor-commit.json" \
  --successor-root "$SUCCESSOR_ROOT" \
  --receipt "$SUCCESSOR_RECEIPT"
```

The verifier checks C1's API signature payload locally with `ssh-keygen -Y
verify -n git`; GitHub's own `verified` boolean is recorded but does not replace
that cryptographic check. C1 is presentation only, never release source or
evidence. The C0 tag must remain unchanged. Keeping media links out of C0
avoids a source-to-release-to-source self-reference. Neither the automated C0
release nor C1 closes G10; that requires a later published clean-clone
replication by a non-author, non-agent person.
