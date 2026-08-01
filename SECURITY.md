# Security policy

## Supported state

Security fixes are applied to the default branch and, when appropriate, to a
new uniquely tagged release. Historical evidence and protocol tags are frozen
scientific records: they are not moved or rewritten after publication.
Publication snapshots are also preserved by project policy; GitHub's separate
per-release `immutable` API flag must not be inferred from that policy.

GitHub Releases serve distinct artifact channels. Publication/evidence
packages and the separately frozen beacon-protocol package remain relevant by
their named tags; GitHub's moving “Latest” pointer does not supersede either
channel. The active supported source is the default branch, while a report
about a released artifact must name its exact tag. The macOS application in
this repository is a research prototype, not a sandbox for untrusted models,
datasets, Python environments, or result files.

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
`./corelm macos build` therefore uses an explicit local ad-hoc signature and
requires no Apple Developer Program account, paid certificate, Developer ID
identity, or notarization. The signature seals the user's own build but does
not authenticate Ivan Tyshchenko as its binary publisher. Developer ID and
notarization remain an optional, out-of-scope path only if a future maintainer
chooses to distribute a prebuilt application.

## Local bootstrap, mirrors, and offline inputs

`./corelm macos doctor` is a read-only readiness check, not an evidence verifier. It fails
before large downloads when the Mac, Swift toolchain, Python trust chain, free
space, GUI login, required utilities, or configured endpoints are unsuitable.
The full path requires at least 8 GB physical memory and 6 GiB free under the
user profile.

The optional `./corelm macos bootstrap` installs no system package and uses
no administrator access. It downloads one immutable Apple Silicon CPython
3.12.13+20260718 archive from `astral-sh/python-build-standalone`, requires
SHA-256
`62aeee6161d57303a71a138b75fd5cc6fb8c89c4b1d9c7f0a052d89fa0b6652b`,
rejects unsafe archive paths and links, and installs below the current owner's
`~/.local/share/corelm/`. This is a disclosed third-party binary trust root
rather than a build-from-source claim. The packaged app subsequently seals the
complete base interpreter and virtual environment in its signed runtime
manifest. A user who does not accept that bootstrap trust root may provide a
different trusted Python 3.12 via `CORELM_BOOTSTRAP_PYTHON`; the same path and
manifest checks still apply.

An offline proof requires an owner-controlled wheelhouse and the registered
Hugging Face cache. Wheels install with `--no-index`,
`--only-binary=:all:`, and `--require-hashes`; model and dataset resolution is
local-only and repeats the registered byte-size and SHA-256 checks.
Configurable PyPI and Hugging Face endpoints must use HTTPS and cannot weaken
those hash gates.

The proof challenge is an operational stale-run guard in the trusted-local-Mac
threat model. The locally ad-hoc-signed application and JSON receipt do not
authenticate a publisher or provide remote attestation; an adversary who can
rewrite the local result tree can also rewrite its nonce. Do not present the
challenge alone as cryptographic proof of freshness to a remote auditor.
`./corelm macos prepare-offline` creates and immediately exercises those caches
while connected; `CORELM_OFFLINE=1` makes the later proof fail closed if either
cache is absent or invalid.

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
  claims in `docs/RESULTS.md` and `docs/LIMITATIONS.md`.
- The application runs local Python code with the current user's privileges.
  It verifies every file and rejects unmanifested additions in the
  build-recorded external runtime before each worker launch. That runtime is
  still path-specific and user-owned rather than bundled, so only a trusted
  local machine and the registered offline Hugging Face cache should be used
  for evidence-bearing runs.
