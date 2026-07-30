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

The v5 holdout compressed 150,601,728 canonical BF16 bytes to 73,346,513
complete-container bytes (`2.0532909x`) with delta NLL
`-0.0000609346`, top-1 agreement `4071/4096`, and all seven registered
gates passing. The evidence is bounded to the registered model revision,
WikiText-2 windows, teacher-forced replay, and MPS runtime.

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

A preview from a dirty working tree is intentionally not upload-ready.
`PROVENANCE.json` records the source-state mode.

## Build the final tagged package

After the paper commit is public, create a new lightweight publication tag.
Do not move or reuse `voidtoken-v5-evidence-v1`; that tag identifies the
earlier frozen scientific evidence state.

```sh
RELEASE_TAG=voidtoken-v5-paper-v2
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

The release preflight rejects a dirty worktree, annotated or non-HEAD tag,
wrong origin, unpublished tag, untracked input, or bytes that differ from
`HEAD`.

## Before arXiv submission

Open `arxiv-v5/SUBMISSION_CHECKLIST.md`. The author must still confirm the
category, optional email, arXiv account and endorsement status, distribution
license, and final arXiv-generated PDF preview.
