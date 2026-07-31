# Release process

This document is for maintainers. End users should start with
`docs/BUILD_AND_VERIFY.md`.

## Immutable evidence channel

Historical evidence tags, publication tags, releases, and uploaded assets are
immutable. Never move a tag, replace an uploaded asset, rewrite a consumed
attempt marker, or change a frozen result in place.

The current publication release uses `voidtoken-v5-paper-v5`. Its CFF version,
manuscript reference, SBOM component, archive provenance, and canonical asset
names are synchronized by tests.

## Candidate checks

Before creating any new release:

1. work from a clean branch and preserve all historical evidence;
2. run the Python and Swift suites;
3. replay registered synthetic and real-model evidence;
4. verify workflow policy, dependency locks, SBOM, secret history, and OSV;
5. build the application and run a fresh challenge-bound proof;
6. verify deterministic archives twice;
7. push the exact commit and wait for branch and pull-request CI;
8. create a new lightweight immutable tag only after CI is green;
9. wait for tag-triggered CI;
10. build final archives from the publicly visible tag and verify checksums.

Detailed publication commands and arXiv submission steps remain in
`publication/README.md`, `publication/reproducibility/README.md`, and the
submission checklist. Those documents intentionally retain versioned names.

## Final and development output

- `.build/` contains Swift development products.
- `dist/CoreLMBenchmark.app` is the locally built final application.
- `output/development/` is the recommended location for preview archives.
- `output/final/<immutable-tag>/` is the recommended location for final tagged
  archives.

Pass an explicit `--output` directory to `publication/build_archives.py`. Do
not rename canonical files inside a published package; consumers and checksum
manifests may depend on them.
