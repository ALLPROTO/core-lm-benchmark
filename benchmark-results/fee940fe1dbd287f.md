# Core LM Benchmark — fee940fe1dbd287f

Verdict: **PASS**

Scenario: `repeating_structured`, n=256, steps=200, seed=101.

Core arithmetic: `fixed-order-f64-v1`.
Core state SHA-256: `07761bee73fba214744e4328b60d802595208c641fde36984500e61872ff59f7`.
VoidToken payload SHA-256: `a9502e877490e615d379693ea99e6de4f57b1c04f61332d742925475cd1f151a`.
VoidToken container SHA-256: `62f9772027c14d4ed435f2e62594fb779879b7d0000cd3ca9e8bb462a9bbe161`.
VoidToken reconstruction SHA-256: `afaab3eae0a33c05c7f1fcfa4af375e502ae3c2a7671fa6f5d5038169306f61f`.

| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |
|---|---:|---:|---:|---:|---:|---:|
| dense | 205824 | 205889 | 1.000× | 0.000000 | 1.000000 | 0.000000 |
| pca | 15648 | 15726 | 13.153× | 0.007106 | 0.999975 | 0.000050 |
| voidtoken | 36224 | 36502 | 5.682× | 0.038991 | 0.999276 | 0.018529 |

Invariant violations: 0.
Deterministic replay: True.

## Verdict reasons

- All configured PASS thresholds were satisfied.
