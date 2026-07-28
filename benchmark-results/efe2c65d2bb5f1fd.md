# Core LM Benchmark — efe2c65d2bb5f1fd

Verdict: **PASS**

Scenario: `uniform_bounded`, n=96, steps=200, seed=42.

Core arithmetic: `fixed-order-f64-v1`.
Core state SHA-256: `e91d6d3291c0ab952383740bc31482b0f30f373af92e0b2667baddca96671045`.
VoidToken payload SHA-256: `21187c321fba991e24daf8b98a3795e6f203656da70f1db5efaacd30ffd370fa`.
VoidToken container SHA-256: `7adbf96cd778b859927970f95ca55cc1cdc764d4f5f99b69af900aaee1b89344`.
VoidToken reconstruction SHA-256: `38a023b198053513e6c21b44e4a9f72d30ddafa6610191bb8d4fa9f5ae507555`.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 77184 | 77248 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 9888 | 9965 | 7.806× | 0.015407 | 0.999881 | 0.000237 |
| voidtoken | 15384 | 15660 | 5.017× | 0.037449 | 0.999330 | 0.017227 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
