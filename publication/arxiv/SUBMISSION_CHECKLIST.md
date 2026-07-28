# arXiv submission checklist

## Author actions required

- [x] Confirm publication name: `Ivan Tyshchenko`.
- [ ] Add affiliation, email, and ORCID if desired.
- [ ] Confirm primary category and any cross-list.
- [ ] Select the arXiv distribution license.
- [x] Add public source repository: `https://github.com/ALLPROTO/core-lm-benchmark`.
- [ ] Confirm that all authors approve the final text and submission.

## Package checks completed locally

- [x] Top-level file is `main.tex`.
- [x] Source uses PDFLaTeX-compatible PDF figures.
- [x] File names use arXiv-safe ASCII characters.
- [x] Internal file references match case exactly.
- [x] Bibliography source is included.
- [x] Generated `.bbl` is included in the final archive.
- [x] No absolute local paths are embedded in TeX.
- [x] Submission archive excludes build logs and temporary files.
- [x] PDF was rendered to images and visually inspected.
- [x] Reproducibility archive is separate from the TeX submission archive.

## arXiv web steps

1. Sign in with the submitting author's registered arXiv account.
2. Start a new submission and upload `corelm_arxiv_source.tar.gz`.
3. Confirm PDFLaTeX and `main.tex` as the top-level source.
4. Review arXiv's file analysis and compilation log.
5. Preview every page of the generated PDF.
6. Paste metadata from `submission_metadata.md`.
7. Choose category, license, and authors.
8. Complete endorsement if the account or category requires it.
9. Submit only after the final preview matches the local verified PDF.
