# Core LM Benchmark — ee25ef4cffaf1eb3

Verdict: **PASS**

Scenario: `uniform_bounded`, n=32, steps=200, seed=7.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 25728 | 25792 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 7584 | 7661 | 3.392× | 0.010994 | 0.999940 | 0.000121 |
| voidtoken | 5120 | 5354 | 5.025× | 0.030985 | 0.999575 | 0.021763 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
