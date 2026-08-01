# VoidToken v5 arXiv submission checklist

## Author decisions

- [x] Publication name: `Ivan Tyshchenko`.
- [x] ORCID: `0009-0000-7935-6090`.
- [x] Manuscript affiliation currently says `Independent researcher`.
- [ ] Confirm whether to expose an email address.
- [ ] Confirm primary category `cs.CL` and cross-list `cs.LG`.
- [ ] Create or activate the submitting arXiv account.
- [ ] Complete category endorsement if arXiv requests it.
- [ ] Select the arXiv distribution license; this is separate from MIT code
      licensing.
- [ ] Approve the final title, abstract, and manuscript text.

## Scientific checks

- [x] Development is labelled adaptive and not prospective evidence.
- [x] Selection is labelled one-shot acceptance, not final evidence.
- [x] Holdout uses registered test blocks 384--415.
- [x] Complete-container bytes include framing, metadata, scales, and codes.
- [x] The baseline is the canonical bfloat16-rounded prefill KV cache.
- [x] All seven verdicts are recomputed from unrounded JSON values; displayed
      manuscript values are rounded.
- [x] Negative holdout delta NLL is not claimed as a model improvement.
- [x] Earlier test-parquet access and disjoint v1 blocks are disclosed.
- [x] Reserve blocks are described as unscored, not unread or secret.
- [x] Validation blocks 64--71 are labelled fixed, public, repeatedly exercised
      application-regression input, not blind/holdout/generalization evidence.
- [x] Three same-machine application runs are labelled repeatability checks,
      not three independent experiments.
- [x] The local challenge is labelled trusted-local stale-run binding, not
      cryptographic remote freshness or attestation.
- [x] Accompanying repository documentation identifies the separately
      registered beacon-selected one-shot protocol as publicly frozen under
      `corelm-beacon-heldout-v1` and awaiting execution; the manuscript claims
      no unperformed result.
- [x] The paper makes no full-model, SOTA, latency, serving, or free-running
      claim.
- [x] Canonical result hashes are distinguished from physical file hashes.
- [x] Final evidence tag points to commit `531e4ab8...`, not the earlier
      holdout-artifact commit.

## Local package checks

- [x] Retired synthetic source is excluded from the current submission and
      remains recoverable only from the immutable historical Git tag.
- [x] Top-level v5 source is `main.tex`.
- [x] File names and TeX source use arXiv-safe ASCII.
- [x] All figures are vector PDF files.
- [x] Tables and figures are generated from checked-in JSON evidence.
- [x] `main.bbl` is generated and included.
- [x] Local PDF compiles without errors or unresolved references.
- [x] PDF text extraction contains the expected title, metrics, and hashes.
- [x] Every rendered page has been visually inspected.
- [x] The v5 source archive contains only required submission files.
- [x] Deterministic archive rebuild produces byte-identical SHA-256 values.
- [ ] Final archives are built from a clean public lightweight publication tag.

## arXiv web steps

1. Sign in with the submitting author's arXiv account.
2. Start a new submission and upload
   `corelm_voidtoken_v5_arxiv_source.tar.gz`.
3. Select `main.tex` as the top-level source.
4. Review arXiv's file analysis and compilation log.
5. Preview every page of arXiv's generated PDF.
6. Paste and verify `submission_metadata.md`.
7. Confirm author identity, ORCID, categories, comments, and license.
8. Complete endorsement if requested.
9. Submit only after the arXiv preview matches the locally verified PDF.
