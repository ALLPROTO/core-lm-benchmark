# arXiv submission metadata

## Title

Closed-Loop Residual Tokenization for Stable Compression of Dynamical State
Trajectories

## Authors

Ivan Tyshchenko

ORCID: https://orcid.org/0009-0000-7935-6090

Confirm the affiliation in the arXiv form.

## Recommended categories

- Primary: `cs.LG` (Machine Learning)
- Possible cross-list: `cs.AI` (Artificial Intelligence)

Category selection and endorsement remain subject to the author's arXiv account
and moderator decision.

## Abstract

Stateful model architectures produce dense trajectories whose storage cost grows
linearly with both state dimension and sequence length. Directly sparsifying and
quantizing consecutive state deltas appears attractive, but the decoder does not
possess the dense state used by the encoder; consequently, discarded components
accumulate as open-loop reconstruction error. We present VoidToken v3, a
closed-loop residual representation that computes each residual against the
state actually reconstructed by the decoder. Sparse top-k residual components
are norm-scaled and quantized, while an automatic keyframe schedule is selected
from an explicit byte budget. We evaluate the method in Core LM, a reproducible
discrete-time dynamical benchmark, against dense float32 storage and PCA. The
evaluation contains 115 runs spanning three state dimensions, five random seeds,
five perturbation classes, short and long trajectories, three sparsity levels,
and two quantization levels. Under predeclared acceptance thresholds, all
115 runs pass. The minimum observed compression ratio is 4.2353x, the worst
normalized root-mean-square error is 0.06089, the minimum cosine similarity is
0.99821, and the maximum relative mean-energy drift is 0.04955. The result
establishes a reproducible operating region for the tested dynamical system; it
does not claim universal performance on arbitrary learned-model states or
task-level language-model quality.

## Comments

Paper with four figures, reproducibility archive, benchmark implementation, and
machine-readable evidence. 115/115 registered benchmark runs satisfy the
predeclared acceptance criteria.

## Artifact

https://github.com/ALLPROTO/core-lm-benchmark

## License

Choose the arXiv distribution license during submission. Confirm that all
authors agree and that the selected license is compatible with any later venue.
