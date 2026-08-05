# Beacon-heldout evidence and CI closure

This page records the first and only normative `corelm-beacon-heldout-v1`
attempt and explains the historical red `Verify` jobs without rewriting them.

| Item | Value |
|---|---|
| Frozen tag / commit | `corelm-beacon-heldout-v1` / `0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44` |
| Protocol commit | `b34bc4d06c00c86b99076b117049e2d590d73bcd` |
| Evidence tag / commit | `corelm-beacon-heldout-v1-evidence` / `85c2add1799652a818873a04310b75821728da11` |
| Evidence release | [`corelm-beacon-heldout-v1-evidence`](https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/corelm-beacon-heldout-v1-evidence) |
| Implementation SHA-256 | `bf8dea05e7b6dbf726d0a857d2e9f78219bf28c24a949c8a93f21891eac83d56` |
| Canonical outcome SHA-256 | `49b8c5d8ca2a96931258fb4c674e3c8548edfe70bbbffda6ca79a2fb8cc81a61` |
| Published `outcome.json` file SHA-256 | `9c63b8d8f70d190f409841f22a089f0ddffeb482328c59db2cfee0e81f861247` |

The attempt marker was written at `2026-08-02T18:15:46Z`, after the registered
NIST pulse, and declares `rerunPermitted=false`. The deterministic rule selected
test blocks 512–543. The terminal outcome was written at
`2026-08-02T18:18:20Z`.

| Measure | Result |
|---|---:|
| Blocks / predictions | 32 / 4,096 |
| Canonical BF16 cache bytes | 150,601,728 |
| Complete compressed-container bytes | 73,309,625 |
| Compression ratio | 2.054324081x |
| Delta NLL | +0.000159341 nat/token |
| Top-1 agreement | 99.4140625% |
| Registered gates | 7/7 PASS |
| Scientific verdict | **PASS** |

The read-only
[`Audit Immutable Beacon Evidence` run 30771472012](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30771472012)
completed successfully. It recomputed the registered window and verdict and
ran the frozen independent verifier without model inference, a new NIST fetch,
or a new scientific attempt.

The branch and tag publication workflows
[`30771389615`](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30771389615)
and
[`30771400739`](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30771400739)
both passed Python-core and supply-chain but failed the same macOS fixture
setup. The frozen Swift test tried to create a directory below a missing local
`.build` parent before the runtime-manifest validator ran. This is a test-harness
path failure, not a failed compression gate or rejected scientific verdict.
The evolving source corrected the fixture later; the frozen evidence remains
unchanged.

The frozen and evidence tags are lightweight, and the evidence commit has no
Git signature. They therefore do not provide a standalone author-signature
supply-chain proof. Verification must bind the exact commits and published
hashes above to the release record and independent audit. This result covers
one beacon-selected WikiText-2 window and one pinned Qwen revision; it does not
establish arbitrary-model or arbitrary-corpus generalization.
