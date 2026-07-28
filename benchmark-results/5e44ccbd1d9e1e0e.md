# Core LM Benchmark — 5e44ccbd1d9e1e0e

Verdict: **PASS**

Scenario: `gaussian_bounded`, n=96, steps=200, seed=42.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 77184 | 77248 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 9888 | 9965 | 7.806× | 0.011442 | 0.999935 | 0.000131 |
| voidtoken | 13984 | 14219 | 5.519× | 0.044280 | 0.999071 | 0.022184 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
