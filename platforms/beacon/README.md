# Beacon compatibility boundary

This is the third repository contour beside `platforms/macos/` and
`platforms/linux/`. It is not a build target and contains no model runner,
dataset resolver, NIST client, result writer, or scientific verifier.

The published beacon implementation hashes both source bytes and registered
path strings. Consequently, the canonical compatibility payload must remain
at `BenchmarkCore/corelm_benchmark.py`; a move, copy, or symlink here would not
be equivalent. macOS and Linux builds neither import nor package that payload.

The single safe command exposed from the evolving branch is read-only:

```sh
./corelm beacon verify-tag
```

It verifies the exact lightweight tag, its protocol parent, the frozen
manifest, and all 26 normative Git blobs without importing frozen Python or
accessing the model, dataset, NIST beacon, or result directory. Its output is
repository-integrity information, not a scientific result.

The one-shot experiment must still be run only from a clean detached checkout
of `corelm-beacon-heldout-v1` by following
[`docs/BEACON_LAUNCH_RUNBOOK.md`](../../docs/BEACON_LAUNCH_RUNBOOK.md).
That runbook was added after the immutable tag and is a non-normative
current-branch operator checklist. The tagged protocol, registration, and
freeze manifest remain authoritative.
