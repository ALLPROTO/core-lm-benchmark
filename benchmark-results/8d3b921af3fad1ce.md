# Core LM Benchmark — 8d3b921af3fad1ce

Verdict: **PASS**

Scenario: `gaussian_bounded`, n=32, steps=200, seed=42.

Core arithmetic: `fixed-order-f64-v1`.
Core state SHA-256: `18ace4bdf9737852746769d31f6f98f80b44971b44780a5ed52fde47c67908f4`.
VoidToken payload SHA-256: `e0a591ebe0632ac6fb5cd50528d45d6426bd8963a937534eff7fad83bb553522`.
VoidToken container SHA-256: `2dd00be219826eaa8c91b55937b53dec90f117c130015ca87914b6d4218440cd`.
VoidToken reconstruction SHA-256: `77594c11f0febc6a4c59bdf8e6078299d1926201b74786772abf36a4f1d13f32`.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 25728 | 25792 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 7584 | 7661 | 3.392× | 0.008223 | 0.999966 | 0.000068 |
| voidtoken | 5120 | 5397 | 5.025× | 0.034035 | 0.999469 | 0.020551 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
