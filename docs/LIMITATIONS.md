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
7. Fresh proof results retain exact per-layer container manifests and digests,
   but not the raw transient container bytes. Offline verification reconstructs
   manifest-derived totals and checks digest commitments; it cannot parse bytes
   that were deliberately not retained.
8. The registered prospective result predates the richer per-layer manifest.
   Its complete byte total is protected by immutable artifacts and Git history
   but is not independently reconstructible from that historical JSON.
9. The three repeated native runs establish same-machine repeatability by the
   author. Independent external reproduction requires another person and Mac to
   publish their own receipt.
10. Live dependency-advisory results can change after a release. Hash locks,
    SBOM checks, and OSV scanning reduce supply-chain ambiguity but do not prove
    that the operating system, Python distribution, or model files are free of
    all vulnerabilities.

The detailed versioned research record is intentionally preserved in
`EVIDENCE.md`, `KNOWN_LIMITATIONS.md`, and `docs/development/`.
