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
| Portfolio software tag | `corelm-portfolio-v9` | Automation-only engineering release identity; signing and public status are verified separately |
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

The V9 automation contour does not close independent-replication gate G10.
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
reused, or relabelled. The current portfolio software identity is the distinct
V9 tag shown in the table. It adds the exact Swift frontend `-num-threads 1`
pin without weakening the 50% available-memory threshold. Receipts bind the
exact produced app SHA; this does not claim byte-deterministic executable builds
across scratch roots. The presentation contract remains v2.

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
