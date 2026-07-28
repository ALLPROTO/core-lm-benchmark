# Core LM Benchmark — bdfccf635abb743a

Verdict: **PASS**

Scenario: `gaussian_bounded`, n=256, steps=200, seed=997.

Core arithmetic: `fixed-order-f64-v1`.
Core state SHA-256: `1a3ca6ed803133c51fa03e351cfc8bb6c191ec5dfef3a0498083db2f79393674`.
VoidToken payload SHA-256: `bab34aa52ab6524af438343685a5b1d9f7e1cc4044fe5b9575a7b84db3bd224b`.
VoidToken container SHA-256: `649ed1b5f5f04551655167a1cc963c32a727026351ec925087cacfa9f7a15f83`.
VoidToken reconstruction SHA-256: `18c216a6ea36aeeeedd40e44ebd2d3002e02dbea6547db8739e65c18ee205585`.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 205824 | 205889 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 15648 | 15726 | 13.153× | 0.011878 | 0.999929 | 0.000141 |
| voidtoken | 36224 | 36502 | 5.682× | 0.042903 | 0.999141 | 0.023811 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
