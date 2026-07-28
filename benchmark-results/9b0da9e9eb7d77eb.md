# Core LM Benchmark — 9b0da9e9eb7d77eb

Verdict: **PASS**

Scenario: `gaussian_bounded`, n=256, steps=200, seed=101.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 205824 | 205889 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 15648 | 15726 | 13.153× | 0.013625 | 0.999907 | 0.000186 |
| voidtoken | 36224 | 36459 | 5.682× | 0.051680 | 0.998730 | 0.025422 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
