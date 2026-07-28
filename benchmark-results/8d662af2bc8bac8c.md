# Core LM Benchmark — 8d662af2bc8bac8c

Verdict: **PASS**

Scenario: `gaussian_bounded`, n=96, steps=200, seed=17.

Core arithmetic: `fixed-order-f64-v1`.
Core state SHA-256: `9f20c3a822f7f4c61344eccd42f65fbddcecf12268b672305de9e8696287a431`.
VoidToken payload SHA-256: `a0fce55dd84a0c3abe053a565a03724e735ad0abbd6f88c7e7293b9f88578b36`.
VoidToken container SHA-256: `ab273ea7c394eb79d8361b3b14d8cafc6a35b24fb82a9d50fe67a6907660f4b9`.
VoidToken reconstruction SHA-256: `03cf900bbb3341b2d16cf594e4272a37d87257842e2c43a2d7cec50504afa71e`.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 77184 | 77248 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 9888 | 9965 | 7.806× | 0.011903 | 0.999929 | 0.000142 |
| voidtoken | 13284 | 13560 | 5.810× | 0.043668 | 0.999115 | 0.025052 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
