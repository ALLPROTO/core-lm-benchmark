# Core LM Benchmark — 7fe4fffbc6bc9a7e

Verdict: **PASS**

Scenario: `gaussian_bounded`, n=96, steps=200, seed=7.

Core arithmetic: `fixed-order-f64-v1`.
Core state SHA-256: `50def7d9e96b1542662155883993d2d1195292990d1416f6bf65cf43ee4cc955`.
VoidToken payload SHA-256: `33ef51c6a2595f9ef864120c87006fe15cc05716b877811a7e6a109cac697910`.
VoidToken container SHA-256: `d47c6cdf83c1961a73298a14412e3730de7dc7ff9613749fd3c9a1a494228bf7`.
VoidToken reconstruction SHA-256: `e4b42a058a417cf48cc00f70c7b2a40255a06a2aedb1ce8a6abc2e00b9492b99`.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 77184 | 77248 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 9888 | 9965 | 7.806× | 0.013434 | 0.999910 | 0.000180 |
| voidtoken | 13284 | 13560 | 5.810× | 0.050267 | 0.998784 | 0.022006 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
