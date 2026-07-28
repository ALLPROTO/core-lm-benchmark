# Core LM Benchmark — 7c6cc5a3aaff42c2

Verdict: **PASS**

Scenario: `impulse`, n=96, steps=5000, seed=42.

Core arithmetic: `fixed-order-f64-v1`.
Core state SHA-256: `899cdc4d0c89d2e24d925824d205d51aaff3d54df71df2cafa37479f6b812dd3`.
VoidToken payload SHA-256: `2c9a187e446e4cbd2a3ac4e6ac60b924c208f58d4ca7d9f15ca6c5b39479df74`.
VoidToken container SHA-256: `b44f2e815d0a1fedbaa797792d4c1c930d7527c154021cde76919687e9030a84`.
VoidToken reconstruction SHA-256: `72109f38792ecc6371d29be31637bbfe1d755ad0f88b87d1c38006df30914525`.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 1920384 | 1920449 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 163488 | 163566 | 11.746× | 0.102829 | 0.994699 | 0.010574 |
| voidtoken | 375384 | 375661 | 5.116× | 0.014218 | 0.999899 | 0.000560 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
