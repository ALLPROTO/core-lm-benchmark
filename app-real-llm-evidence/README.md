# macOS application real-LLM integration evidence

This directory records a post-development integration run made through
`CoreLMBenchmark.app` on 2026-07-30. The application launched its separately
identified Python worker, loaded the pinned `Qwen/Qwen2.5-0.5B` revision
offline, ran the registered VoidToken codec on Apple MPS, verified the returned
document in Swift, and wrote the sanitized application receipt.

This is **not** a new preregistered or untouched holdout result. Validation
blocks 64–71 are the public development/smoke-test reserve. The artifact is
useful as evidence that the macOS application path executes the real model and
the same exact container accounting as the command-line runner; it must not be
used to strengthen the historical prospective claim.

## Recorded result

- Model revision: `060db6499f32faf8b98477b0a26969ef7d8b9987`
- Device: Apple MPS
- Blocks / prediction tokens: 8 / 1,024
- Compression versus dense BF16: `2.052383755053835×`
- Delta NLL: `-8.493661880493164e-06` nat/token
- Top-1 agreement: `0.9951171875`
- Exact per-layer container entries: 192 (8 blocks × 24 layers)
- Scientific verdict: `PASS`
- Swift structural verification: `PASS`
- Independent Python shard verification: `PASS`

The canonical result digest is
`5b464de8f094a33a90dfdbc2c69ac318bc62a4397b171b5db69ae93d5d39d3c2`.
The byte-level file digests are in `SHA256SUMS`.

## Verification

From the repository root, with the locked Python environment active:

```bash
python -I -B security/verify_app_run_evidence.py
(cd app-real-llm-evidence && shasum -a 256 -c SHA256SUMS)
```

`app-run-receipt.json` intentionally contains no absolute user, cache, result,
or repository paths. It binds the run to the application executable, signed
runtime manifest, Python executable, runner resource, result file, and
canonical result through SHA-256 digests. The original application binary is
not distributed, so a new local build is expected to have a different
executable digest. Use `security/verify_local_app_run.py` to bind a newly
compiled app to its own fresh result and receipt.
