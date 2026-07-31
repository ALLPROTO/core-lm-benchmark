# Security policy

## Supported state

Security fixes are applied to the default branch and, when appropriate, to a
new release. Historical evidence and protocol tags are immutable scientific
records: they are not moved or rewritten after publication.

The latest GitHub release is the only released source artifact considered
active. The macOS application in this repository is a research prototype, not
a sandbox for untrusted models, datasets, Python environments, or result
files.

## Reporting a vulnerability

Use the repository's private vulnerability-reporting form:

<https://github.com/ALLPROTO/core-lm-benchmark/security/advisories/new>

If that form is unavailable, open a minimal public issue asking for a private
contact channel. Do not include credentials, private data, a working exploit,
or an undisclosed model/data integrity bypass in a public issue.

Include the affected commit or release, operating system, reproduction steps,
impact, and any proposed mitigation. Please distinguish a security or artifact
integrity issue from a disagreement about the scientific claim.

## Security and release gates

A release candidate is not ready until all applicable gates pass:

1. The unit suite and independent evidence verifiers pass from a clean Git
   checkout.
2. GitHub Actions references are full commit SHAs and the workflow token has
   read-only repository permissions.
3. CI dependencies install from the platform lock with `--require-hashes`,
   portable core/RealLLM lock closures are hash-complete, and the live OSV
   check reports no advisory for every package in those closures.
4. The deterministic supply-chain policy and reachable-history secret scan
   pass.
5. The checked-in direct-dependency CycloneDX document matches the two source
   requirement manifests.
6. Publication archives reproduce byte-for-byte, and every distributed asset
   is named in the release checksum manifest.
7. The macOS bundle is built from the checked-out sources, its bundled scripts
   match those sources, its signed Python-runtime manifest covers the exact
   loadable base prefix, virtual environment, native libraries, and
   `site-packages` (volatile `__pycache__` is bypassed with a private empty
   `-X pycache_prefix`); and `codesign --verify --deep --strict` passes.
8. Model weights, model configuration/tokenizer assets, and dataset files are
   resolved at registered revisions and verified against registered sizes and
   SHA-256 values before model execution.
9. The sanitized application-run receipt, exact per-layer manifests, scientific
   result, independent Python verifier, source runner, and—when distributed—
   the packaged app all agree under
   `security/verify_app_run_evidence.py`.

The reproducibility release distributes source, not a prebuilt macOS binary.
`build_local_app.sh` therefore uses an explicit local ad-hoc signature and
requires no Apple Developer Program account, paid certificate, Developer ID
identity, or notarization. The signature seals the user's own build but does
not authenticate Ivan Tyshchenko as its binary publisher. Developer ID and
notarization remain an optional, out-of-scope path only if a future maintainer
chooses to distribute a prebuilt application.

## Explicit limitations

- `security/osv_direct_audit.py` queries the live OSV service. CI supplies the
  complete pinned core and RealLLM Python lock closures; this is not a complete
  binary, model-file, or operating-system scan.
- `security/direct-dependencies.cdx.json` is intentionally a deterministic
  direct-dependency SBOM. It does not claim to enumerate the user's external
  Python environment, Apple frameworks, model weights, corpus cache, or every
  transitive RealLLM package.
- The deterministic secret check covers tracked files and reachable Git
  history using high-confidence credential formats. It complements, but does
  not replace, GitHub secret scanning and push protection.
- Passing the security workflow does not strengthen or broaden the scientific
  claims in `EVIDENCE.md` and `KNOWN_LIMITATIONS.md`.
- The application runs local Python code with the current user's privileges.
  It verifies every file and rejects unmanifested additions in the
  build-recorded external runtime before each worker launch. That runtime is
  still path-specific and user-owned rather than bundled, so only a trusted
  local machine and the registered offline Hugging Face cache should be used
  for evidence-bearing runs.
