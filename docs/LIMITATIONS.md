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
17. `corelm-portfolio-v15` demo pixels are an automatically captured product
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
    final media.
26. The signed `corelm-portfolio-v12` identity is frozen at source commit
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
    The fail-closed successor rule was explicit: there is no delete/recreate, retry,
    retag, or V12 relabel.

    The signed `corelm-portfolio-v13` identity is frozen at source commit
    `b1fa1298971548eef8c2e0afa00d8c661812b16f`, tree
    `29ee5d1b152bc8f2ef156664023ae4cd878dea2f`, and annotated tag object
    `908c0913d5e7ca98dfb217287430fd251fa13994`. First tag CI Linux run `31398790350`
    and macOS run `31398790626` passed on attempt 1. Exactly one V13 attempt was
    consumed, UUID `51c4ebae-44ee-4cc8-b4e3-4a57fc170d83`, as its sole proof/model
    invocation.

    That sole run completed `END-TO-END PROOF PASS` and 1,024/1,024 heavy-replay
    decisions at `2.052383755053835x`, delta NLL `-8.459810111105526e-06`, and top-1
    `0.9951171875`, with zero maximum baseline/candidate loss error. Its proof
    receipt is `1a3444f223cab3a95a626d2061def0c9a2814fadc22c173d1881e1803e3f3694`,
    result `ad8724e0270be366703f38c874bb43dc1eed4387fd44e8b86e9a5cea7684a8e1`, and
    app executable
    `504c0d137da22c4d39c6d380ca39126f0b82b855e3ff6a9873ee123f3b2a96f9`.

    The exact state order is `ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL →
    REPLAY_VERIFIED → POST_PROOF_PRESENTATION_SURFACE_READY →
    POST_PROOF_PRESENTATION_CAPTURED → SAME_RUN_REOPENED → RESULT_CAPTURED →
    MEDIA_SEALED_FOR_COLLECTION`; state, automation-receipt, and readiness SHA-256
    values are respectively
    `35d149c1c0e7cd5342153b69c37d09b3630489a687e0c63fcfe4de3c8d5d326b`,
    `58a58a069a9327c969a7ee58f1f86bd9e0ff7be1e8fdceec8161bd76fb0220ea`, and
    `8f05d45aa7a3847bdf557437b9da3d69ba507038cba3656c6a1a0ba909b3be07`.

    Raw preflight, post-proof-presentation, and same-run MOV identities are
    `afb6f14ad49a09be84c68a89e09183852805d1411b0cdf7baa2e8b2c61ef757c` (56 frames),
    `bc0f549683c0a510f38302de9b89db273461bab1c18da044fc86ef03ac16177b` (685 frames),
    and `7c6bdc3a18d691e6172df4815af4aa0b0e654377798c3376f7a2e9cdac50fad7` (1,027
    frames). Final video/poster SHA-256 values are
    `4e23449ff2be2ad8c0dc868f85d768f0867cc393a45f9c0b04ff8475c67787f1` and
    `1328d02715a7926612b3547f8fdd01697c1fc3d087a36f134fe399dec3022fda`; exact strict
    per-frame SHA-256 framemd5 and PTS identities are
    `391fd7b93d0a619240b55ad343bc310d69419f43a5f8ec0add58de5b3c3ec84d` and
    `9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`.

    Collector and builder both passed, retaining evidence
    `123dcf8fbf0833fcac1a634952807151bed69b4dbded482331a04843a108f2d4`, provenance
    `d2aca3293107bbca9f1648a0c36fd3f56f81d9efb0ca528217d4f7c9085e2bcd`, runtime
    `a0243322187fb29fb475b63b910ffef699ea1386b3caff71b65649c0a389e8d3`, private
    release-input manifest
    `c765cf5584d1271bbfaa335bd42517ff0cbc315f18cf5766eab95cb97dfc385f`, and exactly
    fourteen signed local assets with `SHA256SUMS`
    `f30f6d60c4ca27bab7cbbde10d5428b27cea2501fd9f80f3ef18dfe7caef963a`. The
    independent offline verifier returned exact-fourteen-asset PASS.

    The exact canonical create-draft request bytes were derived at SHA-256
    `521ed09b11c5946a2728384d6052e37ee1ee424d330fec48a8af96e05ccae919`. Before any
    POST, the authenticated immutable-policy GET returned exact raw JSON
    `{"enabled":true,"enforced_by_owner":false}` with SHA-256
    `f4b2b8919d556de186d7b4afe009126b30c99e3edefb005e4e56ab17069b52dd`. The frozen
    V13 verifier rejected that official two-field response and exited 2 with exact
    terminal line `PORTFOLIO GITHUB RELEASE FAIL: GitHub immutable-releases policy
    response must be exact enabled:true`.

    No precreate policy receipt, draft, GitHub Release, upload, PATCH, or
    publication receipt was produced. There was no retry, deletion, retag, rerun,
    reuse, or relabel. The fourteen signed local assets remain retained, and no
    conforming fourteen-asset GitHub release receipt was produced.

    V14 is the distinct corrected identity. It keeps presentation contract and
    schema/state/report version v2. Its media gate retains the exact frame count,
    PTS identity, and strict per-frame SHA-256 framemd5 manifest; MD5 and malformed
    manifests are rejected.

    Its GitHub operator boundary accepts an immutable-policy response with exactly
    the keys `enabled` and `enforced_by_owner`. Both values must be strict JSON
    booleans, `enabled` must be `true`, and `enforced_by_owner` may honestly be
    either boolean; missing, extra, projected, or non-boolean fields fail. The raw
    snapshot SHA-256 and both values are bound into the precreate and
    populated-draft operator receipts, whose schema version is 2. Public portfolio
    schemas and automation/presentation contract v2 do not change.

    The fail-closed staged publication remains `prepare-draft` → fresh authenticated
    precreate policy GET and `verify-policy` → one saved draft POST →
    `verify-empty-draft` → exactly fourteen no-clobber uploads → fresh authenticated
    prepublish policy GET and `verify-draft` → same-ID seven-field publish PATCH →
    logged-out by-ID/by-tag/latest/download verification. The empty-draft snapshot
    binds `draft:true`, `prerelease:false`, `immutable:false`, and `published_at:null`;
    the publish request binds `make_latest:"true"`. In that flow, logged-out final
    verification binds by-ID, by-tag, latest, and all downloads. Any mismatch or partial
    operation stops; there is no delete/recreate, retry, retag, or V13 relabel. V14
    requires its own signed tag, first-attempt CI, and sole proof.

    The signed `corelm-portfolio-v14` identity is frozen at source commit
    `3d3273674d854a825636ec49ddc18be04cb82b05`, tree
    `df363235a8945838a3f1aadd936df78498e471c8`, and annotated tag object
    `7b92d0cd5852a2f75fa72d664965a7b51b9c6217`. First tag CI Linux run
    `31408473142` and macOS run `31408473015` passed on attempt 1. Exactly one
    V14 attempt was consumed, UUID `2b098099-1588-438e-922c-b88eae2b1803`, as
    its sole proof/model invocation.

    That sole run completed `END-TO-END PROOF PASS` and 1,024/1,024 heavy-replay
    decisions at `2.0523837550538349x`, delta NLL `-8.4598101111055257e-06`,
    and top-1 `0.9951171875`, with zero maximum baseline/candidate loss error.
    Its proof receipt is
    `a74fe758ea8de046dd14cc492669e7b096e0d0619c8e0ec5042f208944e8f315`,
    result `3605fefa0916a0d5e88d537f3138c7e28fa69dbd21cf7521d63d86f5f9d7429a`,
    and app executable
    `be274ee658294f6b24d660ddfe879abb6865ba67d2de4fa84994af412750ff53`.

    The exact state order is `ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL →
    REPLAY_VERIFIED → POST_PROOF_PRESENTATION_SURFACE_READY →
    POST_PROOF_PRESENTATION_CAPTURED → SAME_RUN_REOPENED → RESULT_CAPTURED →
    MEDIA_SEALED_FOR_COLLECTION`; state, automation-receipt, and readiness
    SHA-256 values are respectively
    `ac342977affbde1bb0c2d7ef1cb206799d44d6582f3faa2c3e3622948fcfa58c`,
    `cdf5c0ba4b5f6a09bea66045dd6dfa2fb56fb1af758206cbae350da817b4c25e`,
    and `d110fc2d9fb23407043a6f9ca382a50646002789e4e3531d6e8f7b2cd580595c`.

    Raw preflight, post-proof-presentation, and same-run MOV identities are
    `5aeffe89b450dfe47e46a017487909a11fc160f25146b1db335a5b004b1bdd75`
    (58 frames),
    `1cd8880d169f6897c9a199b899b5140ba3a95a61c009ced1728dc3fcdc6c8405`
    (685 frames), and
    `4ad3d8fc5471289cb96354c41c26efc3529267e7b672b544d46fac447c8fd184`
    (1,030 frames). Final video/poster SHA-256 values are
    `db790f6518a9fea5533dff1744d5889f7bad0b332dba3080014f32ebe3164618`
    and `b84fee40f7093b7a062d36ec332ff1a4bb0461e1cea4675c12c9e1f1a626ebb1`;
    exact strict per-frame SHA-256 framemd5 and PTS identities are
    `6a21df99c238d365a88d0aede78c3b3daeb79d6e277cc90e69179d56938cd23d`
    and `9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153`.

    Collector and builder both passed, retaining evidence
    `37703b9e727ff4568cd3504aa49ef9e0bac6abeb2668372dab7d4deb6751a33c`,
    provenance
    `05232ae09a61976a701acd685fa1321bb5cb38d14bf30474812928185705bd67`,
    runtime
    `3870bd9d1cf64f9123994e2e205a393c5b92c0e7639694d8ada646a8dbc9d1a0`,
    private release-input manifest
    `1fb631d76c0057a7ad5144f061ecd8408b7a4d9764ee8e99a761c6396ed9b4c6`,
    and exactly fourteen signed local assets with `SHA256SUMS`
    `8c505e0e6e1ed0f727c75d9602054b060158b6fcc8c3fe1462b17bf3ff7de89c`.
    The independent offline verifier returned exact-fourteen-asset PASS.

    The canonical create-draft request SHA-256 was
    `a5955010e5002d466677d2b4e495c9d4c157edfdbd495dc364dfcf511838d0e9`;
    its exact body SHA-256 was
    `83fd1800d6bacb3d2882df73ff499c78827f90ad1d51b19cccdc7eb03fb2d036`.
    The authenticated precreate immutable-policy snapshot was exact raw JSON
    `{"enabled":true,"enforced_by_owner":false}` at
    `f4b2b8919d556de186d7b4afe009126b30c99e3edefb005e4e56ab17069b52dd`,
    and its schema-v2 receipt was
    `f306618afaf01d1becc80c42a9a327d6465b1bdaef1ce68bd59df638051bd781`.
    One POST created draft ID `368090960`; create response
    `5e9db42406e4b4a4d95a741270544c696874a11071c8bdcaf8f8d7639b97a68c`
    and empty-draft receipt
    `fc1df0643d987e86aa695fa3f84daf531d63d9588189d91e3f22aacb7f7bd010`
    passed before upload.

    Exactly fourteen no-clobber uploads completed. The authenticated populated
    draft snapshot
    `be3b0937acdf0515f0ad97743f62bf3d468257dbca7c6beaea3b1f578273f2a0`
    remained `draft:true`, `prerelease:false`, `immutable:false`, and
    `published_at:null`. All fourteen unique assets were `uploaded` with exact
    names, sizes, and `sha256:` digests and no missing, extra, or partial asset.
    Tag-ref, tag-object, and commit-object snapshots were respectively
    `b403017080419bc7e3613df4027312928a7de6e9cadf4be1da9078afe9b4c46a`,
    `1040c4bb9e730d20602bf4d9774d65582dbc7c8c89bf7a1ca9151f137034ced4`,
    and `634c98fe6e23bde35fab60235daec42298dd5074fad58eedb38292788009e74d`;
    the fresh prepublish policy snapshot repeated the exact
    `f4b2b8919d556de186d7b4afe009126b30c99e3edefb005e4e56ab17069b52dd`
    bytes.

    GitHub truthfully assigned the common draft download slug
    `untagged-b7af7777ad2ad1f2cd20` to all fourteen
    `browser_download_url` values. The signed V14 verifier prematurely required
    the final tagged URL form at the mandatory prepublish gate and failed with
    exact terminal line `PORTFOLIO GITHUB RELEASE FAIL: GitHub populated draft
    asset URL differs: allowed_signers`. This was the sole populated-draft
    mismatch; every scalar and non-URL asset field passed independently.

    No `publish.json`, populated-draft receipt, PATCH, publish response, logged-out
    download, public GitHub Release, or conforming fourteen-asset GitHub release
    receipt was produced. The exact14 draft and local assets remain retained and
    unmodified. There was no retry, deletion, recreation, metadata edit, retag,
    rerun, reuse, relabel, or V14 publication. V14 will never be moved, rerun,
    published, or relabelled.

    V15 is the distinct corrected identity. It keeps presentation contract and
    schema/state/report version v2. Its media gate retains the exact frame count,
    PTS identity, and strict per-frame SHA-256 framemd5 manifest; MD5 and malformed
    manifests are rejected.

    Its GitHub operator boundary accepts an immutable-policy response with exactly
    the keys `enabled` and `enforced_by_owner`. Both values must be strict JSON
    booleans, `enabled` must be `true`, and `enforced_by_owner` may honestly be
    either boolean; missing, extra, projected, or non-boolean fields fail. The raw
    snapshot SHA-256 and both values are bound into the precreate and
    populated-draft operator receipts, whose schema version is 2. Public portfolio
    schemas and automation/presentation contract v2 do not change.

    The V15 draft URL gate distinguishes authenticated prepublication URLs from
    public postpublication URLs without weakening either boundary. Both the saved
    create response and populated draft must expose one exact canonical
    `html_url` slug matching `untagged-[0-9a-f]{20}`; those slugs must be
    identical, and every one of the exact fourteen draft
    `browser_download_url` values must use that same slug and its exact asset
    name. Mixed slugs, tagged draft URLs, a wrong host/prefix/path, or a changed
    create/populated slug fail closed. The final logged-out verifier still requires
    exact tagged `corelm-portfolio-v15` download URLs. Empty-draft receipt schema
    v1 and populated-draft receipt schema v2 remain unchanged because their raw API
    snapshot digests already bind the URL facts.

    The fail-closed staged publication remains `prepare-draft` → fresh authenticated
    precreate policy GET and `verify-policy` → one saved draft POST →
    `verify-empty-draft` → exactly fourteen no-clobber uploads → fresh authenticated
    prepublish policy GET and `verify-draft` → same-ID seven-field publish PATCH →
    logged-out by-ID/by-tag/latest/download verification. The empty-draft snapshot
    binds `draft:true`, `prerelease:false`, `immutable:false`, and `published_at:null`;
    the publish request binds `make_latest:"true"`. In that flow, logged-out final
    verification binds by-ID, by-tag, latest, and all downloads. Any mismatch or partial
    operation stops; there is no delete/recreate, retry, retag, or V14 relabel. V15
    requires its own signed tag, first-attempt CI, and sole proof.

The detailed versioned research record is preserved under `docs/development/`
and in immutable publication tags.
