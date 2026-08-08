# Core LM publication package

This directory contains the current real-model paper and its reproducibility
package.

## Contents

- `arxiv-v5/` - current prospective real-model VoidToken v5 paper source.
- `corelm_voidtoken_v5.pdf` - visually inspected current v5 PDF.
- `reproducibility/` - instructions for verifying the real-model evidence.
- `build_archives.py` - deterministic v5 arXiv and reproducibility archive
  builder.
- `PORTFOLIO_RELEASE.md` - fail-closed 14-asset portfolio release and public
  verification contract.

The retired synthetic paper and its 115-run data are deliberately absent from
the default branch. Their exact historical bytes remain recoverable from the
immutable `voidtoken-v5-paper-v5` Git tag. They are not part of this package.

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

A separate selected-window protocol published its commit, hashes,
parameters, gates, audited eligible pool, and deterministic future-public-
beacon selection rule under tag and GitHub Release
`corelm-beacon-heldout-v1`. Its release summary names four key normative
artifacts; the authoritative `RealLLM/beacon_freeze.json` enumerates and hashes
the complete 26-path normative source set. The freeze preceded the target
pulse; the single recorded execution later selected blocks 512--543 and
published terminal **PASS** at evidence commit
`85c2add1799652a818873a04310b75821728da11`, tag and release
`corelm-beacon-heldout-v1-evidence`. The suite is consumed. This result covers
one pinned Qwen revision and one WikiText-2 window, not arbitrary-model or
corpus-wide generalization. Raw beacon evidence assets are not duplicated in
the current paper package; their immutable evidence ref remains canonical, and
the reproducibility archive includes the evidence/CI report and exact
identities.

## Separate release-tag contours

Two tag families have different contracts and must never be substituted for
one another:

- `voidtoken-v5-paper-vN` is the lightweight historical paper archive contour.
  `publication/build_archives.py --release-tag` accepts only this exact family,
  requires it to equal the one `version` in `CITATION.cff`, verifies that the
  tag is lightweight, points to clean `HEAD`, and is visible on the canonical
  public origin.
- `corelm-portfolio-vN` is the SSH-signed annotated portfolio and independent-
  replication contour. It is verified by `tools/independent_replication.py`
  against the pinned signer policy and canonical remote. The archive builder
  rejects it as the wrong contour.

A paper archive may be linked from a portfolio release, but its provenance
continues to name its own `voidtoken-v5-paper-vN` tag. A portfolio tag does not
retroactively sign or rename a historical paper archive, and a lightweight
paper tag cannot satisfy the independent-replication source gate.

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

## Create a new historical paper archive release

Corrections or new publication assets require a new, never-used lightweight
`voidtoken-v5-paper-vN` tag and a separate GitHub Release. Never reuse
`voidtoken-v5-paper-v5` or `voidtoken-v5-evidence-v1`, and never replace assets
attached to an existing release. First update and test the CFF, manuscript,
SBOM, and archive identity so the exact `CITATION.cff` version equals the new
tag. Then set `NEW_RELEASE_TAG` explicitly before running:

```sh
: "${NEW_RELEASE_TAG:?set a new, never-used publication tag}"
printf '%s\n' "$NEW_RELEASE_TAG" \
  | grep -Eq '^voidtoken-v5-paper-v[1-9][0-9]*$' \
  || { echo 'publication tag must be voidtoken-v5-paper-vN' >&2; exit 1; }
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

The release preflight rejects a dirty worktree, annotated or non-HEAD paper
tag, any tag outside `voidtoken-v5-paper-vN` (including
`corelm-portfolio-vN`), a tag that differs from `CITATION.cff`, wrong origin,
unpublished tag, untracked input, or bytes that differ from `HEAD`. Do not
create the new tag until the exact branch commit has passed CI.

## Before arXiv submission

Open `arxiv-v5/SUBMISSION_CHECKLIST.md`. The author must still confirm the
category, optional email, arXiv account and endorsement status, distribution
license, and final arXiv-generated PDF preview.
