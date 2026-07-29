# Core LM publication package

This directory contains the publication materials for the Core LM benchmark and
the VoidToken v3 closed-loop residual codec.

The public reproducibility repository is
`https://github.com/ALLPROTO/core-lm-benchmark`.

## Contents

- `arxiv/` — self-contained LaTeX source prepared for arXiv.
- `reproducibility/` — instructions for rebuilding the evidence package.
- `corelm_voidtoken_v3.pdf` — visually inspected paper PDF.

The paper deliberately reports a validated operating region rather than a
universal language-model quality claim. Its aggregate values are generated from
`benchmark-results/aggregate.json`, which identifies the exact 115 run files
used in the evaluation.

The current paper scope is VoidToken v3 plus the 115-run synthetic benchmark.
The real-LLM VoidToken v5 development and prospective protocol are separate
repository artifacts. They must not be described as an arXiv v5 result until
the frozen phases are complete and a revised or separate paper is prepared.

`python3 publication/build_archives.py` produces preview archives and
`output/SHA256SUMS`. Repeated builds from identical inputs are byte-for-byte
identical; CI checks this property. A preview from a dirty working tree is
labelled as such in `PROVENANCE.json` and is not upload-ready.

For a final distribution, first publish a lightweight release tag, then build
from its clean public commit:

```sh
RELEASE_TAG=v0.4.0
git status --short
git tag "$RELEASE_TAG"
git push origin HEAD
git push origin "refs/tags/$RELEASE_TAG"
git ls-remote --exit-code origin "refs/tags/$RELEASE_TAG"
python3 publication/build_archives.py \
  --release-tag "$RELEASE_TAG" \
  --verify-determinism
python3 publication/build_archives.py --release-tag "$RELEASE_TAG"
(cd output && shasum -a 256 -c SHA256SUMS)
```

The release preflight rejects a dirty tree, annotated/non-HEAD tag, wrong
origin, unpublished tag, untracked input, or file whose bytes differ from
`HEAD`.

## Before submission

Open `arxiv/SUBMISSION_CHECKLIST.md`, verify the affiliation, choose an arXiv
license, and add the assigned arXiv identifier after submission.
