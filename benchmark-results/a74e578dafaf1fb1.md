# Core LM Benchmark — a74e578dafaf1fb1

Verdict: **PASS**

Scenario: `repeating_structured`, n=256, steps=200, seed=42.

Core arithmetic: `fixed-order-f64-v1`.
Core state SHA-256: `b261b41d487880d88db195edd7e07f01b7e4a30c038a0f769a524a8d7a312b86`.
VoidToken payload SHA-256: `aa34d9bbd13b9a098691033c85a5c1f41423e90cbf00780205cea0b67f2da495`.
VoidToken container SHA-256: `3213a47a8b73994c6943f4faccb9c1aa9cbc7515d220bf6d43c1fd5e05b1fd57`.
VoidToken reconstruction SHA-256: `b41265225e4c57211518cfcbcc96a9aee17637698b9e381f4999f38e9a345528`.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 205824 | 205889 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 15648 | 15726 | 13.153× | 0.006718 | 0.999977 | 0.000045 |
| voidtoken | 36224 | 36502 | 5.682× | 0.036695 | 0.999358 | 0.017190 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
