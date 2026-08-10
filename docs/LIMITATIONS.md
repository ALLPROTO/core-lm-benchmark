# Limitations

The application is designed to make a narrow compression claim inspectable. It
does not turn that claim into a general model-compression result.

1. The measured target is one pinned Qwen model revision, registered WikiText-2
   windows, canonical BF16 prefill KV cache, teacher-forced replay, and Apple
   MPS. Results do not automatically transfer to other models, datasets,
   sequence lengths, devices, or cache layouts.
2. This is KV-cache compression. It does not compress model weights or prove
   free-running generation quality.
3. The benchmark does not claim lower latency, higher throughput, lower total
   process memory, production-serving readiness, or state-of-the-art status.
4. The application build is path-specific. Its signed manifest covers the exact
   external Python installation and virtual environment used during packaging.
   Moving the app without that runtime is not a supported portable-binary path.
5. Local ad-hoc signing seals the user's own build but does not authenticate a
   binary publisher. No prebuilt application is distributed or notarized.
6. The app is not sandboxed and its verified Python worker runs with the current
   user's privileges. Use only trusted source, model assets, and a trusted local
   machine.
7. Fresh application proofs retain all 192 raw per-layer containers, all 512
   source token IDs per block, and per-prediction baseline/candidate losses and
   top-1 IDs. This makes container parsing, byte accounting, token-slice
   commitments, NLL, and top-1 independently recomputable. It still does not
   retain the much larger full-vocabulary logits or canonical BF16 cache, so an
   offline verifier cannot independently recompute KL or cache-error metrics
   without rerunning the pinned model. The heavyweight verifier reruns the
   pinned model to establish the causal link between decoded containers and all
   retained NLL/top-1 rows, but it still does not independently recompute the
   reported full-distribution KL or cache-error aggregates.
8. The registered prospective result predates the richer per-layer manifest.
   Its complete byte total is protected by immutable artifacts and Git history
   but is not independently reconstructible from that historical JSON.
9. Native application runs use fixed, public validation blocks 64–71. Those
   blocks have been exercised repeatedly and are now an application-regression
   fixture, not a blind sample, holdout, or basis for a generalization claim.
10. The three repeated native runs establish same-machine repeatability of one
    fixed workflow by the author; they are not three independent experiments.
    Independent external execution reproduction requires another person and Mac
    to publish their own receipt; it is not an independent implementation, and
    using blocks 64–71 still would not create new blind evidence.
11. The local challenge guards the trusted-local workflow against accidentally
    selecting a stale result. Because the same user controls the ad-hoc receipt,
    it is not cryptographic proof of freshness or remote execution.
12. The separate selected-window protocol has published its commit, digests,
    parameters, gates, audited eligible pool, immutable server-timestamped
    release, and deterministic future-randomness-beacon selection rule under
    `corelm-beacon-heldout-v1`. The freeze by itself was not a result. Its one
    recorded attempt used the `2026-08-02T18:00:00.000Z` pulse, selected blocks
    512--543, and published terminal **PASS** at evidence commit
    `85c2add1799652a818873a04310b75821728da11`. That result covers one pinned
    Qwen revision and one WikiText-2 window only; it does not establish
    arbitrary-model or corpus-wide generalization. The suite is consumed and
    cannot be invoked again as a scientific attempt. A local marker still
    cannot prove that no private copy ran. The archived
    [launch runbook](BEACON_LAUNCH_RUNBOOK.md), the
    [evidence report](BEACON_EVIDENCE_REPORT.md), and the
    [v1 audit](development/BEACON_V1_AUDIT_AND_V2.md) record the operator
    procedure, terminal outcome, remaining trusted-local limitations, and
    requirements for a stronger successor experiment.
13. Live dependency-advisory results can change after a release. Hash locks,
    SBOM checks, and OSV scanning reduce supply-chain ambiguity but do not prove
    that the operating system, Python distribution, or model files are free of
    all vulnerabilities.
14. The separate cross-model matrix is a public-data diagnostic, not a blind
    trial. Qwen, GPT-2, and BLOOM pass its aggregate thresholds, while the real
    Pythia run executes and verifies but fails both behavioral gates. This
    preserved negative result rules out a universal-transfer claim for the
    unchanged profile; the three positive cells do not prove model-family or
    population generalization.
15. Blind V1 remains an unrun development draft whose registered checkpoint
    elapsed before a complete exact-commit gate. It cannot be frozen or
    launched late under the same suite ID. Its schemas, CI, fixtures, asset
    checks, and development controls are implementation-readiness evidence,
    not a frozen preregistration or scientific result. No confirmatory-model
    forward pass or target-pulse attempt may be inferred from green tests; any
    future blind experiment requires a new suite ID and fully shifted timeline.
16. A portfolio release's deterministic source archive is an exact
    `git archive`, not a rewritten privacy-clean export. It therefore preserves a
    few already-public absolute cache paths in historical result provenance
    and security-test fixtures. Those legacy strings are not credentials, are
    not used by the current runtime, and are excluded from the portfolio demo,
    release metadata, manifests, checksums, and current evidence. Private keys,
    tokens, credential-like bytes, model weights, and new author-local paths
    remain release blockers.
17. `corelm-portfolio-v12` demo pixels are an automatically captured product
    presentation, not metric evidence or independent review. Single-window
    isolation, a
    capture-safe allowlisted view, metadata/byte scans, fixed-frame replay, and
    decoded-frame hashes are checked automatically, but semantic pixel privacy
    is explicitly not claimed. G10 remains open until a non-author, non-agent
    clean-clone replication is published.
18. `corelm-portfolio-v4` is a preserved failed candidate, not a completed
    model run. Its automation stopped in pre-model FFprobe frame-PTS field
    validation before the durable attempt marker was reserved, so no V4 model
    attempt was consumed. Its tag and first-attempt CI are never moved, rerun,
    or relabelled as a later candidate. The earlier V3 tag-push assertion
    failure remains immutable as well.
19. `corelm-portfolio-v5` is another preserved pre-model failure. Its first
    tag-push Linux/macOS CI passed. An anonymous API HTTP 403 stopped the first
    local contour before the marker and was safely retryable. After reset, the
    normative contour fetched the public responses but rejected GitHub run/job
    IDs above the receipt validator's old signed 32-bit ceiling. This also
    happened before `AttemptLog.reserve`; no V5 model attempt was invoked or
    consumed. The V5 tag and first-attempt CI are never moved, rerun, reused,
    or relabelled as a later candidate.
20. `corelm-portfolio-v6` passed its signed first-attempt tag CI and produced
    one honest scientific proof PASS: 2.052384x compression, delta NLL
    -0.00000846, 99.5117% top-1 agreement, and a 1,024/1,024-decision heavy
    replay with zero maximum loss error. Its durable automation state then ended
    `ATTEMPT_FAILED` after `REPLAY_VERIFIED` because the preflight-built
    explanatory-window executable differed from the proof-rebuilt verified app.
    This happened before same-run result capture, media sealing, or collection.
    V6 is never rerun, moved, reused, or relabelled as a later identity.
21. `corelm-portfolio-v7` is a preserved pre-attempt host-admission failure,
    not a model run. Its tag and first-attempt tag CI passed. The three V7 runner
    invocations all stopped strictly before `AttemptLog.reserve`: two failed the
    >=50% available-memory admission after the parallel Swift preflight build
    left less than 50% available memory, and one transient pre-marker public
    tag-CI admission failure had an unretained nested cause; the exact same 8-response
    validation subsequently passed. The durable state and session remained
    absent after all three; no proof or model attempt was consumed. V7 is never
    rerun, moved, reused, or relabelled.
22. `corelm-portfolio-v8` is a preserved pre-attempt host-admission failure.
    Its exact source commit is
    `b1fc746e7f8a5bd1bf826d9f5219779d568fa0c4`, tree is
    `3c9c5d64530e7c706dc1c9b9cf91d00c81a08a3d`, and annotated tag object is
    `64c9d84ddd8aa04b01459447b7c9f3f16f8f6db3`. Exactly one local V8 runner
    invocation occurred. Its first resource admission passed and the release
    build completed with top-level `--jobs 1`, while the observed Swift
    frontend argv retained `-num-threads 8`; that observation does not
    establish that the frontend setting caused the later host-memory result.
    The second unchanged >=50% available-memory admission failed closed with
    the exact PTY line `AUTOMATED PORTFOLIO DEMO FAIL: at least 50% available
    memory is required`. After cleanup the durable state, session, and staging
    directory were absent. `AttemptLog.reserve` was never reached; no proof or
    model attempt was invoked or consumed, and no portfolio media was retained.
    V8 is never rerun, moved, reused, or relabelled. V9 adds the exact Swift
    frontend `-num-threads 1` pin without weakening the 50% available-memory
    threshold. Receipts bind the exact produced app SHA; this does not claim
    byte-deterministic executable builds across scratch roots.
23. `corelm-portfolio-v9` is a preserved consumed post-proof presentation
    failure. Its exact source commit is
    `33d99db9a8cb239732910d96fc18dcaa43b78e3e`, tree is
    `8fb25db8c54fc248e3b6c1b119fc06fb06be300f`, and annotated tag object is
    `ac69a22fef383f78634cda5e7256bca37e914acf`. First-attempt tag CI was green:
    Linux run `31335135716` and macOS run `31335135699`. Exactly one V9 attempt
    was consumed, UUID `57a75c79-f37f-44b0-adc0-ba0762d200b0`. Proof and replay
    passed at 2.0523837550538349x compression, delta NLL
    -8.4598101111055257e-06, top-1 agreement 0.9951171875, and 1,024/1,024
    replay decisions with maximum errors 0. Its exact durable state order was
    `ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL PASS → REPLAY_VERIFIED
    PASS → POST_PROOF_PRESENTATION_SURFACE_READY → ATTEMPT_FAILED`, with state
    SHA-256 `eff033376bb6cc026c11c8a421da3a8834d78b1a4a7ab34580304c86d0646fce`.
    The exact terminal PTY line was `AUTOMATED PORTFOLIO DEMO FAIL: post-proof
    presentation capture failed: raw capture segment duration/topology is invalid`.
    The partial MOV SHA-256 was
    `5814eac71b5d2fb9ecd940a2aef09bfec9722a6d86a85a95ec230f7334c5514a`:
    one frame, 0.028333 seconds, 2400x1540. The proven cause timeline was
    display off at 23:00:00, idle sleep at 23:00:30, capture beginning during
    DarkWake at 23:01:36, maintenance sleep at 23:01:42, human wake at
    23:09:18, and file finalization at 23:09:19. The app remained alive; the
    launcher lacked a display/system-sleep assertion. No result
    capture/readiness asset, final media, automation receipt, or release was
    produced.
    V9 is never rerun, moved, reused, or relabelled. V10 was its distinct
    successor and wrapped the full sterile runner lifetime with exact
    `/usr/bin/caffeinate -dis`; `-u`, `-t`, and `-w` were forbidden, and an
    unavailable wrapper failed before the attempt marker.
24. `corelm-portfolio-v10` is a preserved consumed proof-and-media PASS whose
    collection failed. Its exact source commit is
    `bb53cd81d9e9ece92a078d823e6bf07474ff762b`, tree is
    `d840e2a2112fc5ee0cdae0c1f0bf1e5fb2c875da`, and annotated tag object is
    `27419a0b91934bd76d430ac7c0eadf073389e26c`. First-attempt tag CI was green:
    Linux run `31338205386` and macOS run `31338205397`. Exactly one V10
    attempt was consumed, UUID `7cad5bc5-57dd-4778-b00f-528ae3ba7936`. Its
    sole proof and heavy replay passed at 2.0523837550538349x compression,
    delta NLL -8.4598101111055257e-06, top-1 agreement 0.9951171875, and
    1,024/1,024 replay decisions with maximum errors 0. Its exact durable state
    order was `ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL PASS →
    REPLAY_VERIFIED PASS → POST_PROOF_PRESENTATION_SURFACE_READY →
    POST_PROOF_PRESENTATION_CAPTURED → SAME_RUN_REOPENED → RESULT_CAPTURED →
    MEDIA_SEALED_FOR_COLLECTION`, with state SHA-256
    `2fe562b4026bbbda3944d194e05f9ce20a4ebfebbccf58c769a53a198e13cd24`
    and automation-report SHA-256
    `2183f16f2f81584a7c13a05a2509df4f1b7bbc2a445edcb34fa77d532ace7ee2`.
    All three raw capture hashes were bound in the automation receipt:
    preflight
    `3d6e2cda34e5c0a044c93a28d41160161920cdc75b887e16e7718968760ae22e`,
    post-proof presentation
    `e761c829f153411f6cd2f7b28cbed2d7a6770da24c4450c18c0a110f07c3dc10`,
    and same-run result
    `07c076d38fe3500011526df2a19441fd771b98875fb42f1e76a164881931cdca`.
    Independent FFprobe inspection and full decode passed. The sealed
    30-second, 900-frame 1280x720 MP4 SHA-256 was
    `e353625bbc923916a07746a9cc7cdfca0579f06e5baae36088c09b37b255dc6a`,
    its decoded-frame SHA-256 was
    `10222e090bb6fa9d10a5443b3879337141ce225dc666ae5dcbc4c159705b0646`,
    its PTS SHA-256 was
    `9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`,
    and its fixed poster SHA-256 was
    `d47be9cb975767b5a6f89c0e54d66f5182675c3a0e871245f2838170e8708a61`.
    The later collector stopped before publishing with exact terminal line
    `PORTFOLIO DEMO COLLECTION FAIL: demo MP4 has a truncated atom header`.
    This was a false reject of valid QuickTime
    MOV structure: each raw ScreenCaptureKit MOV's `avc1` sample entry had a
    valid nonempty `avcC` and `colr`, followed by exactly four NUL padding
    bytes at the end of that child region. The generic nested-box parser
    treated those four bytes as another atom header. Top-level atoms ended
    exactly at EOF; FFprobe and full decode passed all raw segments; bound
    hashes matched state/report; and the final MP4 passed atom/decode checks.
    This does not justify generic parser weakening. V10's bound raw segments
    cannot be remuxed, trimmed, or replaced. Failed collection removed
    transient staging; the V10 inputs directory, fourteen-asset directory,
    and GitHub Release remained absent. V10 is never moved, rerun, reused, or
    relabelled. V11 is the distinct corrected identity: it accepts exactly
    four zero padding bytes only at the end of an `avc1` child region while
    requiring a valid nonempty `avcC`; nonzero, wrong-length, misplaced, and
    missing-`avcC` cases remain failures. The generic atom parser and
    `corelm-automated-presentation-v2` contract remain unchanged; V11 requires
    its own signed tag, first-attempt CI, and sole proof.
25. `corelm-portfolio-v11` is a frozen consumed proof/replay/media PASS whose
    collector failed. Exact signed source commit/tree/tag-object IDs are
    `0071b1c9cbfffdb591a103fcc836a250d3d405e1`,
    `4fb72d1dd73b8824f77f562620c16aa6481fc6a4`, and
    `2bddc12667f3fac6901f982969003b38abcc3d3e`; first-attempt tag CI passed in
    Linux run `31371667051` and macOS run `31371667048`. Exactly one V11
    attempt was consumed, UUID `6bc357a8-4fc6-4f7c-b73f-0718af818952`.
    Its sole proof and heavy replay passed at 2.0523837550538349x compression,
    delta NLL -8.4598101111055257e-06, top-1 agreement 0.9951171875, and
    1,024/1,024 decisions with maximum errors 0. Its exact nine-event order was
    `ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL PASS → REPLAY_VERIFIED
    PASS → POST_PROOF_PRESENTATION_SURFACE_READY →
    POST_PROOF_PRESENTATION_CAPTURED → SAME_RUN_REOPENED → RESULT_CAPTURED →
    MEDIA_SEALED_FOR_COLLECTION`. State/report SHA-256 values were
    `9c24a9c629f43b114ddc3766718079a0ba6b7160ff98e0d2c8339a6b53d6d61c` and
    `635a1347ae93365ab5c03e14c56f329938d4164e353fe5b65690ccdd9a6f4675`.
    App, receipt, result, and readiness SHA-256 values were
    `0192341765bf5e30f9a103e5b2b39d46d3eb35278a942b51d1747055ebf3b9fb`,
    `a569802b3a7c76a5ca7283b56227b0730c5f420b80c4d8f2cfb49b727ab78805`,
    `ca671a98c4476de5db1927bf2114693e9901aa96335642b227e55024924dd80d`, and
    `f99b32ce5e47cf26c1abe784c7b992fc448aa3f8faadbfe8432d7baca17def20`.
    Preflight/post-proof/result MOV SHA-256 values were
    `6d9363fee0a84967a4b9ba474743d8d1a5501f3ce7c53fecf57eb0fd65fd6241`,
    `356b96e96d2310cb561ed96bc0246428e30bdcd7ac32ac49e47d0d4d7a014169`, and
    `1661a2c7e087087de3848518eae9c95809c3ea5b10361a50f7817061844ef848`.
    Final MP4/decoded/PTS/poster SHA-256 values were
    `bb7caa9c0874ac17d259de25ac952f13c9cd832b8dd83bceba94d30772ffe744`,
    `7270ca303e891bdd6aaac18a50a518209c7365f794869bb5a974cc5e111f784d`,
    `9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`, and
    `6e5c774b9f6adba9cd5fe68681a246f01a3f7163aac428f36dff29affb9c5919`.
    Collection failed exactly: `PORTFOLIO DEMO COLLECTION FAIL: final video
    bytes are not the exact raw composition`. Retained/replay SHA-256 values
    `bb7caa9c0874ac17d259de25ac952f13c9cd832b8dd83bceba94d30772ffe744`,
    `6e64ff46721b81f8c45e1dfbbac41a6b7595ec8d5b4e101128bbc2f27860ee91`, and
    `131953d94a53bd26e5b8d624267df7c88ee96c96cf86671511eaedd07e597ecc`
    were byte-distinct but had exact 900-frame decoded framemd5 SHA-256
    `7270ca303e891bdd6aaac18a50a518209c7365f794869bb5a974cc5e111f784d`
    and PTS identity; only packet-zero type-6 `user_data_unregistered` SEI
    differed. Cleanup left inputs, fourteen assets, evidence archive, and
    GitHub Release absent. Never move, rerun, reuse, or relabel V11 proof/tag/
    final media. V12 keeps final bytes report-bound and poster replay
    byte-exact. Its replay parser requires a strict per-frame SHA-256 framemd5
    manifest together with exact frame count and PTS SHA-256; MD5 and malformed
    manifests are rejected. This replaces comparison of encoded VideoToolbox
    bytes. Contract and schema/state/report version remain v2; V12 requires its
    own signed tag, first-attempt CI, and sole proof.

The detailed versioned research record is preserved under `docs/development/`
and in immutable publication tags.
