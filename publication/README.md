# Core LM publication package

This directory contains the publication materials for the Core LM benchmark and
the VoidToken v3 closed-loop residual codec.

The public reproducibility repository is
`https://github.com/ALLPROTO/core-lm-benchmark`.

## Contents

- `arxiv/` — self-contained LaTeX source submitted to arXiv.
- `reproducibility/` — instructions for rebuilding the evidence package.
- `corelm_voidtoken_v3.pdf` — visually inspected paper PDF.
- `arxiv/` — the exact source from which the PDF and arXiv upload are built.

The paper deliberately reports a validated operating region rather than a
universal language-model quality claim. Its aggregate values are generated from
`benchmark-results/aggregate.json`, which identifies the exact 115 run files
used in the evaluation.

`python3 publication/build_archives.py` produces the arXiv source archive, the
reproducibility archive, and `output/SHA256SUMS`. Repeated builds from identical
inputs are byte-for-byte identical; CI checks this property.

## Before submission

Open `arxiv/SUBMISSION_CHECKLIST.md`, verify the affiliation, choose an arXiv
license, and add the assigned arXiv identifier after submission.
