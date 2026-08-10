# Scientific and compatibility identifiers

Core LM Benchmark previously exposed several unrelated version spaces in the
same user-facing page. They are now confined to development and provenance
documentation.

| Identifier space | Example | Purpose |
|---|---|---|
| Algorithm revision | `VoidToken v3`, `VoidToken v5` | Research chronology |
| Wire/codec format | `voidtoken-residual-keyframe-v4` | Parser compatibility |
| Historical result schema | `corelm-voidtoken-v5-validation-development-v2` | Published manifest-only evidence |
| Current app result schema | `corelm-voidtoken-v5-validation-development-v3` | Raw-container and token-metric evidence |
| Backend/configuration | `voidtoken-v5`, candidate `32` | Frozen measurement identity |
| Historical challenge receipt | `corelm-macos-app-real-llm-run-v3` | Pre-primary-evidence app/result binding |
| Historical primary-evidence app receipt | `corelm-macos-app-real-llm-run-v4` | Legacy app/result/primary-evidence binding |
| Current app regression receipt | `corelm-macos-app-real-llm-run-v5` | Explicit public-validation-regression role plus app/result/primary-evidence binding |
| Current app failure receipt | `corelm-macos-app-real-llm-failure-v1` | Non-evidence diagnostic record; never accepted as a result receipt |
| Evidence tags | `voidtoken-v5-evidence-v1` | Public scientific chronology |
| Beacon held-out suite | `qwen2.5-0.5b-kv-voidtoken-v5-beacon-heldout-v1` | Separate one-shot evidence identity |
| Beacon freeze tag | `corelm-beacon-heldout-v1` | Public pre-reveal protocol anchor |
| Beacon artifacts | `corelm-beacon-attempt-v1`, `corelm-beacon-resolution-v1`, `corelm-beacon-outcome-v1` | Irreversible state and result compatibility |
| Publication tag | `voidtoken-v5-paper-v5` | Immutable archive provenance |
| Portfolio software tag | `corelm-portfolio-v12` | Automation-only engineering release identity; signing and public status are verified separately |
| Automated presentation contract | `corelm-automated-presentation-v2` | Deterministic post-proof explanatory and exact-result capture, assembly, and validation with no required human acceptance step |
| Portfolio media classification | `AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE` | Author-controlled presentation bytes; scientific evidence remains the receipt, result, retained containers, and replay reports |
| Bundle metadata | `CFBundleShortVersionString`, `CFBundleVersion` | macOS identity and receipt field |
| Dependency versions | Python, Swift, Torch, Transformers, NumPy | Runtime reproducibility |

These identifiers must not be renamed in frozen JSON, schemas, parsers,
receipts, registration files, evidence directories, publication source, tags,
or checksum manifests. They are included in digests and are checked by tests.

The upstream model identifier `Qwen/Qwen2.5-0.5B` must also remain visible. It
identifies the exact model family being measured and is not application
branding.

The V12 automation contour does not close independent-replication gate G10.
That gate remains **OPEN** until a non-author, non-agent person completes and
publishes the specified clean-clone replication. Automated capture and
verification remove a required human acceptance step from media production;
they do not turn pixels into machine evidence or create an independent human
replication.

`corelm-portfolio-v3` remains an immutable historical failed candidate: its
first tag-push admission failed before the substantive gates. It is not the
current software identity and is never rerun, moved, or reused as evidence.

`corelm-portfolio-v4` is also an immutable historical failed candidate. Its
tag CI passed, but its automated contour stopped at a pre-model FFprobe
frame-PTS field-validation failure before `AttemptLog.reserve`; no V4 model attempt
was invoked or consumed. It is never rerun, moved, reused, or relabelled as a
later candidate.

`corelm-portfolio-v5` is the next immutable historical failed candidate. Its
first-attempt tag-push CI passed. The first local contour received an anonymous
GitHub API HTTP 403 before the durable marker and was safely retryable. After
the rate limit reset, the normative contour fetched the exact responses but
the tag-CI receipt validator rejected GitHub run/job identifiers above its old
signed 32-bit ceiling. That rejection preceded `AttemptLog.reserve`; no V5
model attempt was invoked or consumed. V5 is never rerun, moved, reused, or
relabelled as a later candidate.

`corelm-portfolio-v6` is the next immutable historical failed candidate. Its
signed tag and first-attempt tag CI passed. Its one scientific proof honestly
passed at 2.052384x compression, delta NLL -0.00000846, and 99.5117% top-1
agreement; the heavy replay matched all 1,024 decisions with zero maximum loss
error. The durable automation state then ended `ATTEMPT_FAILED` after
`REPLAY_VERIFIED` because the preflight-built explanatory-window executable
differed from the proof-rebuilt verified app. Same-run result capture,
media sealing, and collection never occurred. V6 is never rerun, moved, reused,
or relabelled as a later identity.

`corelm-portfolio-v7` is the next immutable historical failed candidate. Its
signed tag and first-attempt tag CI passed. The three V7 runner invocations all
stopped strictly before `AttemptLog.reserve`: two failed the >=50%
available-memory admission after the parallel Swift preflight build left less
than 50% available memory, and one transient pre-marker public tag-CI admission
failure had an unretained nested cause; the exact same 8-response validation
subsequently passed. The durable state and session remained absent after all
three; no proof or model attempt was consumed. V7 is never rerun, moved, reused,
or relabelled.

`corelm-portfolio-v8` is the next immutable historical failed candidate. Its
exact source commit is `b1fc746e7f8a5bd1bf826d9f5219779d568fa0c4`, tree is
`3c9c5d64530e7c706dc1c9b9cf91d00c81a08a3d`, and annotated tag object is
`64c9d84ddd8aa04b01459447b7c9f3f16f8f6db3`. Exactly one local V8 runner
invocation occurred. Its first resource admission passed and the release build
completed with top-level `--jobs 1`; the observed Swift frontend argv retained
`-num-threads 8`. That observation does not establish that the frontend
setting caused the later host-memory result. The second unchanged >=50%
available-memory admission failed closed with the exact PTY line `AUTOMATED
PORTFOLIO DEMO FAIL: at least 50% available memory is required`. After cleanup
the durable state, session, and staging directory were absent.
`AttemptLog.reserve` was never reached; no proof or model attempt was invoked
or consumed, and no portfolio media was retained. V8 is never rerun, moved,
reused, or relabelled. The distinct V9 identity added the exact Swift frontend `-num-threads 1`
pin without weakening the 50% available-memory threshold. Receipts bind the
exact produced app SHA; this does not claim byte-deterministic executable builds
across scratch roots.

`corelm-portfolio-v9` is the next immutable historical failed candidate. Its
exact source commit is `33d99db9a8cb239732910d96fc18dcaa43b78e3e`, tree is
`8fb25db8c54fc248e3b6c1b119fc06fb06be300f`, and annotated tag object is
`ac69a22fef383f78634cda5e7256bca37e914acf`. First-attempt tag CI was green in
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
automation receipt, or release was produced. V9 is never rerun, moved, reused, or
relabelled. V10 was its distinct successor. Exact `/usr/bin/caffeinate -dis`
wrapped its full sterile runner lifetime; `-u`, `-t`, and `-w` were forbidden,
and an unavailable wrapper failed before the attempt marker.

`corelm-portfolio-v10` is the next immutable historical candidate. Its exact
source commit is `bb53cd81d9e9ece92a078d823e6bf07474ff762b`, tree is
`d840e2a2112fc5ee0cdae0c1f0bf1e5fb2c875da`, and annotated tag object is
`27419a0b91934bd76d430ac7c0eadf073389e26c`. First-attempt tag CI was green in
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
final MP4 passed atom/decode validation. This does not justify generic parser
weakening. V10's bound raw segments cannot be remuxed, trimmed, or replaced.
Failed collection removed transient staging; the V10 inputs directory,
fourteen-asset directory, and GitHub Release remained absent. V10 is never
moved, rerun, reused, or relabelled.

V11 was the distinct corrected identity shown in the frozen history below.
Its collector accepts exactly four zero padding bytes only at the end of
an `avc1` child region while requiring a valid nonempty `avcC`; nonzero,
wrong-length, misplaced, and missing-`avcC` cases fail. The generic parser and
presentation contract v2 remain unchanged. V11 requires its own signed tag,
first-attempt CI, and sole proof.

The frozen `corelm-portfolio-v11` source commit/tree/tag-object IDs are
`0071b1c9cbfffdb591a103fcc836a250d3d405e1`,
`4fb72d1dd73b8824f77f562620c16aa6481fc6a4`, and
`2bddc12667f3fac6901f982969003b38abcc3d3e`; first-attempt Linux/macOS tag-CI
runs `31371667051`/`31371667048` passed. Its sole consumed attempt UUID was
`6bc357a8-4fc6-4f7c-b73f-0718af818952`; proof/replay passed at
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
relabel V11 proof/tag/final media. V12 retains final byte/report binding and
byte-exact poster replay. Its replay parser requires a strict per-frame SHA-256
framemd5 manifest together with exact frame count and PTS SHA-256; MD5 and
malformed manifests are rejected. Contract and schema/state/report version stay
v2. V12 requires its own signed identity, tag, first-attempt CI, and sole proof.

## User-facing rule

The release application and ordinary-user documentation use:

- **Core LM Benchmark** for the product;
- **Compression Proof** for the end-to-end workflow;
- **VoidToken codec** for the measured codec module;
- **frozen compression profile** for the registered configuration.

Historical synthetic executables, exploratory pilot entry points, and the
development runner remain source-only; the application does not expose or
bundle them. Stable schema identifiers, the registered profile, and historical
grid metadata remain in evidence for compatibility and audit. The executable
application surface presents only the registered proof workflow.
