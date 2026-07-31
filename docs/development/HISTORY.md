# Development history

This is the versioned research and engineering record. Product-facing
documentation deliberately omits these labels so an ordinary user sees one
current compression proof. The identifiers remain here because they are part of
the scientific chronology and byte-level compatibility contract.

## Stage 1 — synthetic trajectory experiment

The registered synthetic suite evaluates the closed-loop residual algorithm
called VoidToken v3. Its canonical interchange container is
`voidtoken-residual-keyframe-v4`; the different numbers describe an algorithm
revision and a wire-format revision, not competing application releases.

The immutable suite contains 115/115 passing runs. The worst registered values
are 4.2353x compression, 0.06089 NRMSE, 0.99821 cosine similarity, 0.04955
relative energy drift, zero invariant violations, and exact replay.

Sources and evidence remain in `BenchmarkCore/`, `benchmark-results/`,
`publication/arxiv/`, and `publication/corelm_voidtoken_v3.pdf`.

## Stage 2 — first real-model pilot

The first real Qwen experiment evaluated VoidToken v4 and a mixed group-quant
baseline. Both preserved negative results:

| Family | Ratio vs BF16 | Delta NLL | Top-1 | Verdict |
|---|---:|---:|---:|---|
| VoidToken v4 | 2.4184x | +0.203580 | 79.88% | FAIL |
| Mixed group quant | 2.0214x | +0.001356 | 97.95% | FAIL |

That pilot was exploratory and is retained unchanged in `real-llm-results/`.

## Stage 3 — adaptive redesign

VoidToken v5 replaced the temporal sparse residual design with per-layer
Walsh-Hadamard group quantization, canonical zigzag coding, complete binary
containers, and fresh-parser replay. Validation blocks 0–31 were used
adaptively and therefore do not count as prospective evidence.

The exact development shards remain in `real-llm-v5-development/` and are
recomputed by `RealLLM/verify_voidtoken_v5_development.py`.

## Stage 4 — frozen selection and holdout

The fixed configuration passed one-shot selection and the later prospective
holdout:

| Phase | Ratio | Delta NLL | Top-1 | Verdict |
|---|---:|---:|---:|---|
| Selection | 2.054320x | +0.000573 | 99.4141% | PASS |
| Holdout | 2.053291x | -0.000061 | 99.3896% | PASS |

The chronology is bound by:

- `voidtoken-v5-selection-protocol-v1`;
- `voidtoken-v5-pretest-v1`;
- `voidtoken-v5-evidence-v1`.

The frozen attempt markers and results remain in `real-llm-v5-results/`.

## Stage 5 — native macOS integration

The source-built application ran the pinned real model on validation blocks
64–71 and retained a 192-entry per-layer manifest. Compression was
2.052383755x, delta NLL was -8.49366188e-06, top-1 agreement was 99.5117%, and
scientific, Swift, and Python verification all passed.

The later challenge-bound proof workflow creates a fresh runtime and binds an
unpredictable nonce to the result, receipt, executable, runner, Python binary,
and runtime manifest. Three same-machine executions reproduced the same
scientific content.

## Publication state

The current immutable publication package is tagged
`voidtoken-v5-paper-v5`. Its versioned paper title, asset names, CFF version,
SBOM component, and archive provenance must remain exact. The default branch
can improve user experience without rewriting that published record.

See [Scientific identifiers](SCIENTIFIC_IDENTIFIERS.md) for the compatibility
boundary and [Release process](RELEASE_PROCESS.md) for maintainer steps.
