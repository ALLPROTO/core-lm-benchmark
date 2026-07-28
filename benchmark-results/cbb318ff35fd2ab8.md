# Core LM Benchmark — cbb318ff35fd2ab8

Verdict: **PASS**

Scenario: `gaussian_bounded`, n=96, steps=5000, seed=42.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 1920384 | 1920449 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 163488 | 163566 | 11.746× | 0.163122 | 0.986606 | 0.026609 |
| voidtoken | 375384 | 375618 | 5.116× | 0.016743 | 0.999860 | 0.000527 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
