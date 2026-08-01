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

The default branch no longer carries that synthetic runtime or its 115 result
pairs. Exact source, evidence, and paper bytes remain recoverable from the
immutable
[`voidtoken-v5-paper-v5`](https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/voidtoken-v5-paper-v5)
tag at commit `e77175759dde47dfb7b56f4013c04686ffb7ddc9`.

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

The source-built application ran the pinned real model on fixed public
validation blocks 64–71 and retained a 192-entry per-layer manifest.
Compression was 2.052383755x, delta NLL was -8.49366188e-06, top-1 agreement
was 99.5117%, and scientific, Swift, and Python verification all passed.

The later proof workflow creates a fresh runtime and binds a trusted-local
unpredictable nonce to the result, receipt, executable, runner, Python binary,
and runtime manifest. Three same-machine executions reproduced the same
scientific content. Because blocks 64–71 are public and repeatedly exercised,
these executions are application-regression/repeatability checks, not three
independent experiments and not a new blind, holdout, or generalization result.
The nonce protects the trusted-local workflow against accidentally selecting a
stale run; it does not prove cryptographic freshness to a remote observer.

## Stage 6 — registered beacon-selected held-out protocol

`RealLLM/BEACON_HELDOUT_PROTOCOL.md` prepares a separate suite with a
two-commit public freeze, exact implementation and artifact hashes, fifteen
eligible previously unreported test windows, and deterministic selection from
an exact future NIST beacon pulse. The selected input may be run once without
post-result tuning; every subsequent run is regression-only. The suite is
frozen at tag commit `0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44` and was
published as the immutable `corelm-beacon-heldout-v1` release at
`2026-08-01T01:18:09Z`, before the registered pulse. It still has no result.
The target is `2026-08-02T18:00:00.000Z` and the completion deadline is
`2026-08-04T18:00:00.000Z`. Validation blocks 64–71 are excluded by their
prior repeated use. The non-normative operator procedure is recorded in the
[beacon launch runbook](../BEACON_LAUNCH_RUNBOOK.md).

## Publication state

The current immutable publication package is tagged
`voidtoken-v5-paper-v5`. Its versioned paper title, asset names, CFF version,
SBOM component, and archive provenance must remain exact. The default branch
can improve user experience without rewriting that published record.

See [Scientific identifiers](SCIENTIFIC_IDENTIFIERS.md) for the compatibility
boundary and [Release process](RELEASE_PROCESS.md) for maintainer steps.
