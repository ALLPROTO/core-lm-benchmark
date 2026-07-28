# Core LM Benchmark — 3ecee6ce4c2ba6b4

Verdict: **PASS**

Scenario: `repeating_structured`, n=96, steps=200, seed=17.

Core arithmetic: `fixed-order-f64-v1`.
Core state SHA-256: `a584250966e27610d3185470660325ec2898172eac9037d0992fb1ba48e2c312`.
VoidToken payload SHA-256: `86978f7df30e89016e4645ef22a558ab9b069953218fe75e45ea74b5f8f2f08d`.
VoidToken container SHA-256: `31a1b12f1838cb975ce3e5a71bdc78c966bfecbfdcd57f8554a41b017a9671ba`.
VoidToken reconstruction SHA-256: `79e59f5e26d1541d10a3373eaa05f13820e10f84ca5ca413df5f08591213a10b`.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 77184 | 77248 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 9888 | 9965 | 7.806× | 0.006579 | 0.999978 | 0.000043 |
| voidtoken | 15384 | 15660 | 5.017× | 0.032493 | 0.999497 | 0.015147 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
