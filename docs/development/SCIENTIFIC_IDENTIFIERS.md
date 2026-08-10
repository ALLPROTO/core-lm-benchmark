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
| Portfolio software tag | `corelm-portfolio-v11` | Automation-only engineering release identity; signing and public status are verified separately |
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

The V11 automation contour does not close independent-replication gate G10.
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

The current portfolio software identity is the distinct V11 tag shown in the
table. Its collector accepts exactly four zero padding bytes only at the end of
an `avc1` child region while requiring a valid nonempty `avcC`; nonzero,
wrong-length, misplaced, and missing-`avcC` cases fail. The generic parser and
presentation contract v2 remain unchanged. V11 requires its own signed tag,
first-attempt CI, and sole proof.

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
