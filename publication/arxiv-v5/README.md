# VoidToken v5 paper source

This directory is the independent arXiv source tree for the prospective
VoidToken v5 real-model artifact study. It does not replace the historical
VoidToken v3 trajectory-compression paper under `publication/arxiv/`.

Generate tables and vector figures from the checked-in evidence:

```sh
python3 publication/arxiv-v5/generate_figures.py
```

Then compile `main.tex` with an arXiv-compatible TeX engine. The deterministic
submission archive is built by `publication/build_archives.py` and is named
`corelm_voidtoken_v5_arxiv_source.tar.gz`.

The manuscript cites frozen evidence tag `voidtoken-v5-evidence-v1` and
canonical holdout result SHA-256
`d1c16e88655c1fbc9884324742dee3f0b9b4bc86d973c2bf38df3a02cc090eaa`.
