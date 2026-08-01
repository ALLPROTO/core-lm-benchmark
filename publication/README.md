# Core LM publication package

This directory preserves two separate papers and one shared reproducibility
package.

## Contents

- `arxiv/` - historical VoidToken v3 synthetic trajectory paper source.
- `corelm_voidtoken_v3.pdf` - visually inspected historical v3 PDF.
- `arxiv-v5/` - current prospective real-model VoidToken v5 paper source.
- `corelm_voidtoken_v5.pdf` - visually inspected current v5 PDF.
- `reproducibility/` - instructions for verifying both evidence lines.
- `build_archives.py` - deterministic v5 arXiv and reproducibility archive
  builder.

The two papers must not be conflated. The v3 paper reports the registered
115-run synthetic dynamical benchmark. The v5 paper reports the separately
frozen Qwen2.5-0.5B prefill KV-cache selection and prospective holdout.

The historical v1 runner recorded 150,601,728 canonical BF16 bytes and
73,346,513 complete-container bytes (`2.0532909x`) for the v5 holdout, with
delta NLL `-0.0000609346`, top-1 agreement `4071/4096`, and all seven
registered gates passing. Those immutable v1 artifacts did not retain
per-layer container manifests, so their compression total is protected by
result/file/Git digests but is not independently reconstructible. The evidence
is bounded to the registered model revision, WikiText-2 windows,
teacher-forced replay, and MPS runtime.

The current-source native-app proof is deliberately separate from those
historical claims. Each run uses fixed public validation blocks 64–71 and
retains 192 raw VTL5 containers, the eight 512-token source slices, and 1,024
token-level metric rows. A fast standard-library verifier recomputes container
bytes, compression, NLL, top-1 agreement, and digests; a heavyweight clean-room
replay retokenizes the pinned WikiText input, decodes VTL5 without importing
the RealLLM codec, rebuilds both KV paths, and reruns all 1,024 Qwen decisions.
This improves application-regression reproducibility but does not reconstruct
the immutable v1 containers or independently regenerate full-distribution KL
and cache-error aggregates. Blocks 64–71 have been exercised repeatedly, so
these runs are repeatability checks, not independent experiments or new blind,
holdout, or generalization evidence.

A separate selected-window protocol has now published its commit, hashes,
parameters, gates, audited eligible pool, and deterministic future-public-
beacon selection rule under tag and GitHub Release
`corelm-beacon-heldout-v1`. Its release summary names four key normative
artifacts; the authoritative `RealLLM/beacon_freeze.json` enumerates and hashes
the complete 26-path normative source set. The freeze is complete, but the
registered target pulse has not produced a checked-in result. The protocol
permits one run without post-result tuning. A later regression is allowed only
after `PASS` or `FAIL_GATES`; `FAIL_EXECUTION` and an incomplete attempt forbid
retry. No beacon result is part of the current publication package.

## Generate and preview

Regenerate the v5 tables and vector figures from checked-in JSON:

```sh
python3 publication/arxiv-v5/generate_figures.py
```

Build preview archives:

```sh
python3 publication/build_archives.py --verify-determinism
python3 publication/build_archives.py
(cd output && shasum -a 256 -c SHA256SUMS)
```

The current archive names are:

- `corelm_voidtoken_v5_arxiv_source.tar.gz`
- `corelm_reproducibility.tar.gz`
- `corelm_voidtoken_v5.pdf`
- `SHA256SUMS` covering all three artifacts above

A preview from a dirty working tree is intentionally not upload-ready.
`PROVENANCE.json` records the source-state mode.

## Reproduce the existing tagged package

Use a separate clean clone or worktree at the already published
`voidtoken-v5-paper-v5` tag. Reproduction fetches and checks out the existing
tag; it must not create, move, or push that tag again.

```sh
RELEASE_TAG=voidtoken-v5-paper-v5
git fetch origin \
  "refs/tags/$RELEASE_TAG:refs/tags/$RELEASE_TAG"
git switch --detach "$RELEASE_TAG"
git status --short
python3 publication/build_archives.py \
  --release-tag "$RELEASE_TAG" \
  --verify-determinism
python3 publication/build_archives.py --release-tag "$RELEASE_TAG"
(cd output && shasum -a 256 -c SHA256SUMS)
```

## Create a new publication release

Corrections or new publication assets require a new, never-used lightweight
tag and a separate GitHub Release. Never reuse `voidtoken-v5-paper-v5` or
`voidtoken-v5-evidence-v1`, and never replace assets attached to an existing
release. Set `NEW_RELEASE_TAG` explicitly to the new identifier before running:

```sh
: "${NEW_RELEASE_TAG:?set a new, never-used publication tag}"
git status --short
if git show-ref --verify --quiet "refs/tags/$NEW_RELEASE_TAG"; then
  echo "local tag already exists: $NEW_RELEASE_TAG" >&2
  exit 1
fi
if [ -n "$(git ls-remote origin "refs/tags/$NEW_RELEASE_TAG")" ]; then
  echo "public tag already exists: $NEW_RELEASE_TAG" >&2
  exit 1
fi
git push origin HEAD
# Wait until the branch and pull-request CI runs are green.
git tag "$NEW_RELEASE_TAG"
git push origin "refs/tags/$NEW_RELEASE_TAG"
git ls-remote --exit-code origin "refs/tags/$NEW_RELEASE_TAG"
# Wait until the tag-triggered CI run is green.
python3 publication/build_archives.py \
  --release-tag "$NEW_RELEASE_TAG" \
  --verify-determinism
python3 publication/build_archives.py --release-tag "$NEW_RELEASE_TAG"
(cd output && shasum -a 256 -c SHA256SUMS)
```

The release preflight rejects a dirty worktree, annotated or non-HEAD tag,
wrong origin, unpublished tag, untracked input, or bytes that differ from
`HEAD`. Do not create the new tag until the exact branch commit has passed CI.

## Before arXiv submission

Open `arxiv-v5/SUBMISSION_CHECKLIST.md`. The author must still confirm the
category, optional email, arXiv account and endorsement status, distribution
license, and final arXiv-generated PDF preview.
