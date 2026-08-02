# Current verified results

Each evidence lane answers a different question. A regression PASS confirms
that an implementation still reproduces its registered behavior; it does not
create another prospective observation.

| Evidence lane | Class | Current state | What it establishes |
|---|---|---|---|
| Registered holdout | Prospective result | PASS | Frozen Qwen/WikiText claim on the registered holdout |
| macOS application | Integration regression | PASS | Native app, MPS worker, containers, and independent replay work together |
| Linux CPU | Cross-platform regression | PASS | The same registered real-data path executes and verifies on Ubuntu CPU |
| Beacon-heldout | Preregistered one-shot | Awaiting outcome | No result until the immutable one-shot publishes an outcome |

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
| Registered regression gate | PASS |
| Swift structural verification | PASS |
| Independent Python verification | PASS |

This run proves that the source-built macOS app launches the real worker,
compresses and fresh-parses real cache containers, feeds the decoded cache back
into Qwen, displays the measured values, and writes a verifiable receipt.

The application always uses fixed, public validation blocks 64–71. Because
those blocks have been exercised repeatedly, this is an application-regression
fixture, not a blind sample, holdout, or new evidence of generalization. Three
same-machine executions bound to a trusted-local challenge from the unchanged
app bundle reproduced the same scientific content and container geometry. They
are three repeatability checks of one fixed workflow, not three independent
experiments.
Expected runtime timestamps and timing measurements differed.

## Linux CPU regression

| Measure | Result |
|---|---:|
| Blocks / predictions | 8 / 1,024 |
| Per-layer container entries | 192 |
| Compression ratio | 2.052389237x |
| Delta NLL | +0.0000223219 nat/token |
| Top-1 agreement | 99.609375% |
| Registered regression gate | PASS |
| Independent raw-evidence verification | PASS |

The public Ubuntu 24.04 CPU run used the same fixed validation blocks 64–71
and produced complete raw evidence. CPU and Apple MPS values are not required
to be bit-identical. This is environmental repeatability, not another
scientific holdout. Exact provenance and the disclosed setup-only attempts are
recorded in the [Linux run report](../platforms/linux/RECORDED_RUN_2026-08-01.md).

## What macOS integration PASS means

For the native proof, PASS requires all of the following:

- at least 2x compression against canonical BF16 storage;
- delta NLL no greater than 0.01 nat/token;
- at least 99% top-1 agreement;
- exact structural cache replay;
- a canonical result digest;
- Swift verification of the parsed document, all retained container hashes,
  source-token commitments, and per-token NLL/top-1 metrics;
- independent standard-library Python parsing of all 192 retained container
  byte streams and recomputation of compression, NLL, and top-1;
- heavyweight independent decoding and pinned-Qwen replay of all 1,024
  token decisions, with exact top-1 comparison and bounded per-token loss
  tolerance; and
- receipt/app/runtime/primary-evidence binding.

## Evidence status

The repository contains the author's same-machine repeated proof and a public
path for anyone to reproduce it. It is not yet an independently published
cross-machine reproduction. A third party should run
`./corelm macos proof` and publish the resulting sanitized receipt to create
that stronger external, cross-machine execution reproduction. It still uses the
same implementation, and because the input remains public validation blocks
64–71, even an external repeat would not create a new blind or generalization
result.

## Frozen next held-out-window experiment

The separate [beacon-selected protocol](../RealLLM/BEACON_HELDOUT_PROTOCOL.md)
fixes the commit/digest freeze, all parameters and gates, fifteen eligible
previously unreported test windows, and a deterministic rule tied to an exact
future NIST beacon pulse. The required immutable release is already public as
[`corelm-beacon-heldout-v1`](https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/corelm-beacon-heldout-v1),
with tag commit `0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44` and server
publication time `2026-08-01T01:18:09Z`. Its release body lists four key
artifacts; the complete normative inventory is the 26 entries in
`RealLLM/beacon_freeze.json`.

The exact pulse is `2026-08-02T18:00:00.000Z`, and a scientific outcome must
complete by `2026-08-04T18:00:00.000Z`. The protocol permits one recorded run
with no post-result tuning. A later regression is allowed only after terminal
`PASS` or `FAIL_GATES`; an execution failure or incomplete attempt cannot be
retried. No result from that suite is reported on this page, and blocks 64–71
are ineligible for it. See the public
[launch and publication runbook](BEACON_LAUNCH_RUNBOOK.md).

Historical scientific chronology and exact internal identifiers are kept in
the [development history](development/HISTORY.md).
