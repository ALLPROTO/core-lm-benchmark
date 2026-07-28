# Core LM Benchmark — e5bc6be9efa1c8a1

Verdict: **PASS**

Scenario: `repeating_structured`, n=32, steps=200, seed=17.

Core arithmetic: `fixed-order-f64-v1`.
Core state SHA-256: `c77bc21b95e7daebc32de2f0e7eead4e5bed6521b09d2aaa23d7b7d630f27ffe`.
VoidToken payload SHA-256: `c5c25166db81b71521b96c5795b371b4043bb38f149598edc87f95cd6121a824`.
VoidToken container SHA-256: `c01e9ff5f0e2e95fa187226b8243181868710270c25256cffa9b7d36914e272e`.
VoidToken reconstruction SHA-256: `2f2589ca170c163a77636bea92e3439db5c5c63b06ce0e25354bd4f199061638`.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 25728 | 25792 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 7584 | 7661 | 3.392× | 0.003474 | 0.999994 | 0.000012 |
| voidtoken | 5120 | 5397 | 5.025× | 0.032938 | 0.999503 | 0.020010 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
