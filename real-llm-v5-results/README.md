# Prospective VoidToken v5 evidence

This directory is reserved for the two frozen phase results and their durable
attempt markers for
`qwen2.5-0.5b-kv-voidtoken-v5-prospective-v1`.

Current status: the public selection freeze is
`voidtoken-v5-selection-protocol-v1` at commit
`467538875402265b2ca915768376e2a5548f3069`. The one-shot selection completed
with a scientific PASS and both immutable artifacts are present:
`selection.attempt.json` and `selection.json`. The passing selection was then
published as `voidtoken-v5-pretest-v1` at commit
`34fbd0556bd4e8fb889e628ae35175ff596818af`. The prospective holdout completed
once from that exact public tag with a scientific PASS, and its immutable
`holdout.attempt.json` and `holdout.json` artifacts are present. The independent
Git-provenance verifier accepts both frozen phases.

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

## Frozen sequence

1. Commit and publish the normative files. Create and publish the lightweight
   protocol tag, and confirm that the public remote returns the exact commit:

   ```sh
   git tag voidtoken-v5-selection-protocol-v1
   git push origin HEAD
   git push origin refs/tags/voidtoken-v5-selection-protocol-v1
   git ls-remote --exit-code origin \
     refs/tags/voidtoken-v5-selection-protocol-v1
   ```

2. In a clean disposable checkout with no local Python bytecode, run the
   one-shot selection on validation blocks 32–63:

   ```sh
   HF_HOME=/path/to/cache python -I -B \
     RealLLM/run_voidtoken_v5_frozen.py selection --local-files-only
   ```

   Exit `0` means a recorded scientific PASS. Exit `2` means a correctly
   recorded, terminal scientific FAIL; publish
   `real-llm-v5-results/selection.attempt.json` and
   `real-llm-v5-results/selection.json`, then **stop permanently**. Do not
   create the pretest tag and do not run holdout. Exit `1` after the attempt
   marker exists means `CONSUMED_INCOMPLETE`; publish the marker and stop.
   None of these states permits a retry of this suite.

3. Only after selection PASS, commit both selection files, create the
   lightweight pretest tag, push it, and confirm its public commit:

   ```sh
   git add real-llm-v5-results/selection.attempt.json \
     real-llm-v5-results/selection.json
   git commit -m "Record frozen VoidToken v5 selection"
   git tag voidtoken-v5-pretest-v1
   git push origin HEAD
   git push origin refs/tags/voidtoken-v5-pretest-v1
   git ls-remote --exit-code origin refs/tags/voidtoken-v5-pretest-v1
   ```

4. Only from a clean disposable checkout of that exact public pretest tag, run
   the prospective holdout:

   ```sh
   HF_HOME=/path/to/cache python -I -B \
     RealLLM/run_voidtoken_v5_frozen.py holdout --local-files-only
   ```

5. Publish holdout PASS (`0`) or scientific FAIL (`2`) unchanged. Exit `1`
   after `holdout.attempt.json` exists is a terminal incomplete attempt:
   publish that marker unchanged and do not retry.

The holdout runner cannot accept alternate source indices, block counts,
configuration, gates, model, dataset, or device. It refuses to resolve the test
split until the public pretest tag and passing selection artifact are verified.
Each `*.attempt.json` is created durably before its split is resolved. If a
machine or process fails after that point, the attempt is consumed and the
incomplete marker is published; it is never deleted to retry the same suite.

Verify all artifacts currently present without loading the model. In a full
clone with tags, require Git provenance:

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
