# Core LM Benchmark — dcc3ca3c1c176dcd

Verdict: **PASS**

Scenario: `impulse`, n=256, steps=5000, seed=42.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 5121024 | 5121090 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 169248 | 169327 | 30.258× | 0.053448 | 0.998571 | 0.002857 |
| voidtoken | 881024 | 881260 | 5.813× | 0.008854 | 0.999961 | 0.000247 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
