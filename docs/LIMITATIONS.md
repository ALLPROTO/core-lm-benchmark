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

The detailed versioned research record is preserved under `docs/development/`
and in immutable publication tags.
