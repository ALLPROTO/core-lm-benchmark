# Core LM Benchmark — e48d1ffd55aba47e

Verdict: **PASS**

Scenario: `gaussian_bounded`, n=256, steps=200, seed=997.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 205824 | 205889 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 15648 | 15726 | 13.153× | 0.011878 | 0.999929 | 0.000141 |
| voidtoken | 36224 | 36459 | 5.682× | 0.042903 | 0.999141 | 0.023811 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
