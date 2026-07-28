# Core LM Benchmark — f2037e6ca0acdbae

Verdict: **PASS**

Scenario: `gaussian_bounded`, n=96, steps=200, seed=101.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 77184 | 77248 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 9888 | 9965 | 7.806× | 0.011562 | 0.999933 | 0.000134 |
| voidtoken | 15384 | 15617 | 5.017× | 0.035769 | 0.999392 | 0.017178 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
