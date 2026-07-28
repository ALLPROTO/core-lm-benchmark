# Core LM Benchmark — d24e7ecada2a8dc5

Verdict: **PASS**

Scenario: `impulse`, n=32, steps=200, seed=7.

Core arithmetic: `fixed-order-f64-v1`.
Core state SHA-256: `69dd03c39d9778063e9fe412368370b908c556b15365e774f567f6df989b2432`.
VoidToken payload SHA-256: `b7d2d6c9288f6a843996c083d57d2958478cdb5877aab2d9a89524432a53a8f0`.
VoidToken container SHA-256: `7970ff2f813942d26ba83e5d54ee869b90c09a687940abff61c52b6fe56f7b85`.
VoidToken reconstruction SHA-256: `5b494de46b36019f4936b6406a52f72843decc6ac3b53614b1a35152b2e8d988`.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 25728 | 25792 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 7584 | 7661 | 3.392× | 0.000663 | 1.000000 | 0.000000 |
| voidtoken | 5120 | 5397 | 5.025× | 0.050832 | 0.998998 | 0.049548 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
