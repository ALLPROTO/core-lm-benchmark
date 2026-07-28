# Core LM Benchmark — b4cf38dd6cb5b32e

Verdict: **PASS**

Scenario: `uniform_bounded`, n=96, steps=200, seed=101.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 77184 | 77248 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 9888 | 9965 | 7.806× | 0.012646 | 0.999920 | 0.000160 |
| voidtoken | 15384 | 15617 | 5.017× | 0.035716 | 0.999384 | 0.014319 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
