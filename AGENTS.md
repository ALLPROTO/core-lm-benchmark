# Real-data execution policy

All benchmark, application-proof, model-evaluation, and scientific-evidence
runs in this repository must execute the pinned pretrained Qwen model on the
registered real WikiText inputs.

Synthetic, generated, toy, or mocked inputs must not produce benchmark
metrics, evidence, PASS/FAIL claims, or publication results. Historical
synthetic artifacts are provenance-only: preserve and integrity-check them,
but do not rerun them or cite them as current model evidence.

Deterministic generated or mocked values are permitted only inside isolated
unit, parser, security, and protocol-control tests. Their outputs are test-only
and must never enter an evidence or result directory.

Never run a frozen holdout or beacon command as a substitute for a regression.
Use only the explicitly documented public validation range for repeatability
checks, and label every repeated execution as regression-only.
