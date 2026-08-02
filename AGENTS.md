# Real-data execution policy

All benchmark, application-proof, model-evaluation, and scientific-evidence
runs in this repository must execute the pinned pretrained Qwen model on the
registered real WikiText inputs.

Synthetic, generated, toy, or mocked inputs must not produce current benchmark
metrics, evidence, PASS/FAIL claims, or publication results. The retired
complete synthetic suite is available only through its immutable historical
Git tag and must not be restored to the default-branch runtime or cited as
model evidence. The frozen compatibility source retained for published hashes
must not be exposed through `./corelm` or either platform build.

Deterministic generated or mocked values are permitted only inside isolated
unit, parser, security, and protocol-control tests. Their outputs are test-only
and must never enter an evidence or result directory.

Never run a frozen holdout or beacon command as a substitute for a regression.
Use only the explicitly documented public validation range for repeatability
checks, and label every repeated execution as regression-only.

The beacon one-shot must be executed only from the clean detached immutable
freeze tag named by its runbook. Do not modify the 26 normative frozen files
before that experiment completes.

`platforms/macos/` and `platforms/linux/` are independent active build
contours and must not import, package, or execute the registered legacy
`BenchmarkCore` payload. `platforms/beacon/` is read-only compatibility
tooling: it may inspect immutable Git objects but must not expose a build,
model, data, NIST, result-writing, or one-shot command. The canonical
`BenchmarkCore/corelm_benchmark.py` file must remain a regular byte-identical
file at its registered legacy path because published digests include that path.
