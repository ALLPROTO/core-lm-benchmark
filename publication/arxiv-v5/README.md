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
The manuscript explicitly discloses that the consumed historical v1 artifacts
did not retain per-layer container manifests: their compression totals are
digest/provenance-protected runner records, not independently reconstructed
byte accounting.

Current source adds a separate application-regression proof path on fixed public
validation blocks 64–71. It retains 192 raw VTL5 containers plus source-token
and per-token metric evidence, then runs a fast standard-library byte/metric
verifier and a heavyweight clean-room replay that independently retokenizes
pinned WikiText, decodes without RealLLM codec imports, rebuilds both KV caches,
and checks all 1,024 Qwen decisions. Blocks 64–71 have been exercised
repeatedly: these executions demonstrate same-machine repeatability and provide
a path for external execution reproduction of the application pipeline, not an
independent implementation, independent experiments, a
revision of the registered v1 selection/holdout, or new blind/generalization
evidence.

The manuscript states that any future selected-window claim requires a separate
prepublished commit, hashes, parameters, gates, a pool with no metric result
found in the audited public repository, and a deterministic future-public-
randomness-beacon selection rule, followed by one run without post-result
tuning. No result from such a protocol is reported.
