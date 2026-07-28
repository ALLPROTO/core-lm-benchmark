# Core LM Benchmark — a8b4acea70ada206

Verdict: **PASS**

Scenario: `gaussian_bounded`, n=96, steps=200, seed=17.

Core arithmetic: `fixed-order-f64-v1`.
Core state SHA-256: `9f20c3a822f7f4c61344eccd42f65fbddcecf12268b672305de9e8696287a431`.
VoidToken payload SHA-256: `72b4448bbdd7a50fedcf47c8ab85b8e0cc9027efbcae3d6075c9f71856801d46`.
VoidToken container SHA-256: `e520f520e75ee68b914524018a0a2454cf75bbef494f9c61790257d509933df2`.
VoidToken reconstruction SHA-256: `74e68a9f45668fe1a3880523a627aa0909c43fb564c6cc9b48f925e269d03be6`.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 77184 | 77248 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 9888 | 9965 | 7.806× | 0.011903 | 0.999929 | 0.000142 |
| voidtoken | 18224 | 18504 | 4.235× | 0.026436 | 0.999674 | 0.014334 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
