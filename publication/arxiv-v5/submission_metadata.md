# arXiv submission metadata: VoidToken v5

## Title

VoidToken v5: Prospectively Frozen Evidence for KV-Cache Compression on a
Real Language Model

## Authors

Ivan Tyshchenko (Independent researcher)

- Affiliation in manuscript: Independent researcher
- ORCID: https://orcid.org/0009-0000-7935-6090
- Repository: https://github.com/ALLPROTO/core-lm-benchmark

## Recommended categories

- Primary: `cs.CL` (Computation and Language)
- Cross-list: `cs.LG` (Machine Learning)

The submitting author must confirm the categories in arXiv. Category
availability and endorsement are controlled by arXiv.

## Abstract

We report an auditable, prospectively frozen evaluation of a serialized
key-value (KV) cache codec on a pinned real language model. VoidToken v5
applies independent normalized Walsh-Hadamard transforms to the key and value
halves of each layer cache, token-wise max-absolute scaling, symmetric
quantization at 8 bits except 9 bits for layers 0 and 8, and canonical zlib
compression. The complete wire containers, including framing, metadata,
scales, and codes, are counted. The protocol fixes Qwen2.5-0.5B, WikiText-2
source windows, a canonical bfloat16 cache, wire-format byte accounting,
statistical gates, and one-shot execution rules before frozen selection and
the prospective holdout. On the registered
32-block holdout (4,096 teacher-forced predictions), complete containers
reduced canonical bfloat16 prefill-cache storage from 150,601,728 to
73,346,513 bytes (2.05329x; 51.30% fewer bytes). Relative to canonical
bfloat16-cache replay, the decoded cache produced delta NLL of
-6.09e-5 nat/token and 99.3896% top-1 agreement. The one-sided 95% block
upper bound for delta NLL was 0.000549, the block lower bound for agreement was
99.2472%, and the Wilson lower bound was 99.1543%; all seven prespecified gates
passed. This is a bounded artifact result for one model revision, short
teacher-forced windows, and one Apple-Silicon/MPS runtime. It is not a claim
about full-model compression, free-running generation, latency, production
serving, or state-of-the-art KV-cache quantization.

## Comments

7 pages, 3 figures. Code and evidence:
https://github.com/ALLPROTO/core-lm-benchmark . Final evidence tag:
voidtoken-v5-evidence-v1.

## License

Select the arXiv distribution license in the submission form. The choice is
separate from the repository's MIT software license and should be made by the
author after reviewing arXiv's current license text.
