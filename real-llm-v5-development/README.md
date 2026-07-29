# VoidToken v5 adaptive development evidence

These four JSON shards are the exact validation-only runs used to report the
development observation for the frozen VoidToken v5 configuration. They cover
source blocks 0–31 in four disjoint eight-block ranges. Every shard records
`testDataOpened: false`, the pinned model/dataset revisions, full candidate
grid, complete-container byte accounting, baselines, per-block records, and a
canonical result SHA-256.

These files are published for auditability. They are adaptive engineering data,
not prospective evidence and not the final v5 verdict. The machine-readable
mapping from paths to ranges, result digests, file digests, and the combined
observation is in `manifest.json`. The manifest carries its own canonical
SHA-256 (computed with only `manifestSHA256` omitted), and the frozen
registration pins both its canonical and raw-file digests.

Verify the four artifacts and recompute their combined metrics without loading
the model:

```sh
python RealLLM/verify_voidtoken_v5_development.py
```

The verifier carries its own canonical-JSON, aggregate, Student-t, Wilson, and
gate formulas instead of calling the benchmark writer's implementations.

To reproduce one shard with the registered environment and cached inputs:

```sh
HF_HOME=/path/to/cache python \
  RealLLM/develop_voidtoken_v5.py \
  --device mps \
  --validation-start-block 0 \
  --validation-blocks 8 \
  --candidate-index 32 \
  --local-files-only \
  --output replay-validation-000-007.json
```

Repeat with start blocks 8, 16, and 24. Development candidate index 32 is the
frozen `group-kl-top-2-9bit-rest-8bit` configuration.

Offline verification proves the integrity and arithmetic self-consistency of
these recorded files. It cannot independently prove the original process's
data-access history; in particular, `testDataOpened: false` is a signed-off
disclosure rather than a fact derivable from the shard bytes alone.
