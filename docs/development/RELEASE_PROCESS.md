# Release process

This document is for maintainers. End users should start with
`platforms/macos/BUILD_AND_VERIFY.md`.

## Preserved artifact channels

Historical evidence and protocol tags/releases are frozen scientific records.
Publication tags, releases, and uploaded assets are likewise preserved by
project policy. Never move a tag, replace an uploaded asset, rewrite a consumed
attempt marker, or change a frozen result in place. GitHub's per-release
`immutable` API flag is a separate platform property and must be checked rather
than inferred from this preservation policy.

The existing publication snapshot uses `voidtoken-v5-paper-v5`. Its CFF
version, manuscript reference, SBOM component, archive provenance, and
canonical asset names are synchronized by tests. Check GitHub's live
`immutable` API field before making a platform-immutability statement; do not
derive it from the project policy alone. Regardless of that field, do not
modify the existing snapshot: publish corrections under a new unique tag and
release instead. The beacon protocol uses the separate
`corelm-beacon-heldout-v1` release channel and is not superseded by whichever
release GitHub labels “Latest.”

## Candidate checks

Before creating any new release:

1. work from a clean branch and preserve all historical evidence;
2. run the Python and Swift suites;
3. integrity-check preserved historical artifacts without regenerating them,
   and execute or replay only registered real-model evidence;
4. verify workflow policy, dependency locks, SBOM, secret history, and OSV;
5. build the application and run a fresh challenge-bound proof;
6. verify deterministic archives twice;
7. push the exact commit and wait for branch and pull-request CI;
8. create a new, never-used lightweight tag only after CI is green;
9. wait for tag-triggered CI;
10. build final archives from the publicly visible tag and verify checksums.

Detailed publication commands and arXiv submission steps remain in
`publication/README.md`, `publication/reproducibility/README.md`, and the
submission checklist. Those documents intentionally retain versioned names.

## Final and development output

- `.build/` contains Swift development products.
- `dist/CoreLMBenchmark.app` is the locally built final application.
- `output/development/` is the recommended location for preview archives.
- `output/final/<release-tag>/` is the recommended location for final tagged
  archives.

Pass an explicit `--output` directory to `publication/build_archives.py`. Do
not rename canonical files inside a published package; consumers and checksum
manifests may depend on them.
