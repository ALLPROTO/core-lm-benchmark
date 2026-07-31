# Current verified results

Core LM Benchmark separates the registered prospective result from the native
application integration proof. Both pass, but they answer different questions.

## Registered prospective holdout

| Measure | Result |
|---|---:|
| Blocks / predictions | 32 / 4,096 |
| Canonical BF16 cache bytes | 150,601,728 |
| Complete compressed-container bytes | 73,346,513 |
| Storage reduction | 51.30% |
| Compression ratio | 2.053291x |
| Delta NLL | -0.000061 nat/token |
| Top-1 agreement | 99.3896% |
| Registered scientific gates | 7/7 PASS |

This is the prospective quality result. Its configuration was fixed before the
holdout was opened. The historical record protects the complete byte total with
exact file and Git digests, but that consumed result did not retain every
per-layer container manifest. The total is therefore integrity-protected but
not independently reconstructible from the old JSON alone.

## Native application integration

| Measure | Result |
|---|---:|
| Blocks / predictions | 8 / 1,024 |
| Per-layer container entries | 192 |
| Compression ratio | 2.052383755x |
| Delta NLL | -0.00000849366 nat/token |
| Top-1 agreement | 99.51171875% |
| Scientific verdict | PASS |
| Swift structural verification | PASS |
| Independent Python verification | PASS |

This run proves that the source-built macOS app launches the real worker,
compresses and fresh-parses real cache containers, feeds the decoded cache back
into Qwen, displays the measured values, and writes a verifiable receipt.

Three separate same-machine challenge-bound executions from the unchanged app
bundle reproduced the same scientific content and container geometry. Expected
runtime timestamps and timing measurements differed.

## What PASS means

For the native proof, PASS requires all of the following:

- at least 2x compression against canonical BF16 storage;
- delta NLL no greater than 0.01 nat/token;
- at least 99% top-1 agreement;
- exact structural cache replay;
- a canonical result digest;
- Swift verification of the parsed document;
- independent Python recomputation and receipt/app/runtime binding.

## Evidence status

The repository contains the author's same-machine repeated proof and a public
path for anyone to reproduce it. It is not yet an independently published
cross-machine reproduction. A third party should run
`./run_local_app_proof.sh` and publish the resulting sanitized receipt to create
that stronger evidence.

Historical scientific chronology and exact internal identifiers are kept in
the [development history](development/HISTORY.md).
