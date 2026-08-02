# Prospective VoidToken v5 evidence

This directory is reserved for the two frozen phase results and their durable
attempt markers for
`qwen2.5-0.5b-kv-voidtoken-v5-prospective-v1`.

Current status: the public selection freeze is
`voidtoken-v5-selection-protocol-v1` at commit
`467538875402265b2ca915768376e2a5548f3069`. The recorded one-shot selection
completed with a scientific PASS and both frozen artifacts are present:
`selection.attempt.json` and `selection.json`. The passing selection was then
published as `voidtoken-v5-pretest-v1` at commit
`34fbd0556bd4e8fb889e628ae35175ff596818af`. The recorded prospective holdout
execution from that exact public tag has a scientific PASS, and its frozen
`holdout.attempt.json` and `holdout.json` artifacts are present. The
Git-provenance verifier accepts both frozen phases.

Accounting limitation: these already-consumed phase artifacts use the
historical v1 result format, which did not record per-layer container
manifests. Their complete-container totals and compression gates are
runner-recorded and bound to immutable canonical result digests, physical file
SHA-256 values, execution commits, and public Git tags, but cannot be
independently reconstructed per layer. They must not be rerun or rewritten.
Any mutation fails the legacy digest/provenance allowlist. Quality metrics and
aggregate/gate arithmetic remain independently recomputed. The separately
registered beacon-heldout suite is designed to retain raw per-layer containers
for a reconstructible compression result, but its future outcome cannot repair
or replace these historical artifacts.

| Metric | Frozen selection result |
|---|---:|
| Complete-container ratio vs BF16 | 2.054320× |
| ΔNLL | +0.000573 nat/token |
| One-sided 95% upper ΔNLL | +0.001222 |
| Top-1 agreement | 4072 / 4096 = 99.4141% |
| One-sided 95% blockwise top-1 lower bound | 99.1762% |
| One-sided 95% Wilson lower | 99.1827% |
| Mean KL | 0.00013673 nat |

Selection result SHA-256:
`11329a941051073bae9e2aec3f483f5fc6acf7449ed18457d020f4693c1b1876`.

| Metric | Prospective holdout result |
|---|---:|
| Complete-container ratio vs BF16 | 2.053291× |
| ΔNLL | −0.000061 nat/token |
| One-sided 95% upper ΔNLL | +0.000549 |
| Top-1 agreement | 4071 / 4096 = 99.3896% |
| One-sided 95% blockwise top-1 lower bound | 99.2472% |
| One-sided 95% Wilson lower | 99.1543% |
| Mean KL | 0.00013431 nat |

Holdout result SHA-256:
`d1c16e88655c1fbc9884324742dee3f0b9b4bc86d973c2bf38df3a02cc090eaa`.

Exact holdout artifact SHA-256 values:

- `holdout.attempt.json`:
  `7f6bc0867db1e3d633c3ecb68aa968be94c73c818b2a5163793495cfb63c17a0`
- `holdout.json`:
  `499c067d6ccff4bf1ac4a9f98436a52fa6c414ccced495719532347b89b46167`

## Development result — not prospective evidence

VoidToken v5 was engineered on WikiText-2 validation source blocks 0–31. The
final frozen configuration uses 9 bits at layers 0 and 8, 8 bits at every other
layer, 128-wide normalized Walsh-Hadamard blocks, float16 group scales, zigzag
codes, and canonical zlib-9 streams.

| Metric | Development observation |
|---|---:|
| Complete-container ratio vs BF16 | 2.055836× |
| ΔNLL | +0.000804 nat/token |
| One-sided 95% upper ΔNLL | +0.001378 |
| Top-1 agreement | 4078 / 4096 = 99.5605% |
| One-sided 95% blockwise top-1 lower bound | 99.3638% |
| One-sided 95% Wilson lower | 99.3548% |
| Mean KL | 0.00013695 nat |

These values are useful engineering evidence but are not the final claim. The
four exact shards and their digest/range manifest are published in
[`../real-llm-v5-development/`](../real-llm-v5-development/). Verify them with:

```sh
python RealLLM/verify_voidtoken_v5_development.py
```

## Verification only

Both one-shot phases are consumed. The historical runner remains in source for
audit and tagged reproducibility, but invoking it again cannot create another
scientific observation and must not be presented as a rerun of the suite.

Verify the immutable artifacts without loading the model. In a full clone with
tags, require Git provenance:

```sh
git fetch --tags --force
python RealLLM/verify_voidtoken_v5_evidence.py --require-git-provenance
```

The same verifier automatically uses artifact-self-consistency mode in an
extracted reproducibility tar that contains no Git metadata. That mode checks
schemas, hashes, ranges, marker/result links, metrics, gates, and verdicts, but
explicitly does **not** claim verification of Git tags or a public timestamp.

See [`../RealLLM/V5_PROTOCOL.md`](../RealLLM/V5_PROTOCOL.md) and
[`../RealLLM/v5_registration.json`](../RealLLM/v5_registration.json).
