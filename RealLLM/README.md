# Real-model core and protocols

`RealLLM/` contains the shared Python implementation used by the real-data
benchmark, the registered protocol files, and their independent verifiers. It
is not a separate application target. Ordinary users should invoke the public
[`./corelm`](../corelm) dispatcher and follow the
[documentation index](../docs/README.md).

## Pinned target

The supported proof path uses the public Apache-2.0
[`Qwen/Qwen2.5-0.5B`](https://huggingface.co/Qwen/Qwen2.5-0.5B) model at immutable
revision `060db6499f32faf8b98477b0a26969ef7d8b9987`. Model weights are downloaded
from the pinned upstream repository and are not redistributed here.

Each registered evaluation:

1. creates a 383-token prefill cache from all 24 layers;
2. canonicalizes the reference through BF16 storage;
3. compresses every layer into a complete VTL5 container;
4. parses those bytes through a fresh decoder;
5. rebuilds a Hugging Face cache; and
6. compares 128 teacher-forced continuation decisions per block.

The compression denominator is the canonical dense BF16 cache at exactly two
bytes per scalar. Framing, metadata, scales, and codes all count toward the
compressed size.

## Active application core

- `app_proof_core.py` — fixed real-model extraction, cache, compression, and
  metric logic packaged into the macOS proof.
- `app_proof_runner.py` — bounded production worker for the native app.
- `prepare_app_assets.py` — hash-checks the pinned model and public validation
  data and proves offline resolution.
- `voidtoken_v5.py` — canonical VTL5 encoder, strict parser, and decoder.
- `codecs.py` — shared cache and legacy codec helpers required by registered
  evidence paths.

The macOS build packages only its allowlisted production subset. Linux uses the
same registered Qwen/VTL5 implementation through its independent platform
scripts. Neither active platform imports or packages `BenchmarkCore`.

## Recorded evidence lanes

### Exploratory pilot

- `registration.json` and `PROTOCOL.md` define the first real-Qwen pilot.
- `benchmark_real_llm.py` runs that historical experiment.
- `verify_real_llm_evidence.py` verifies the preserved aggregate in
  [`real-llm-results/`](../real-llm-results/).

The pilot contains negative results and remains exploratory.

### Registered prospective result

- `v5_registration.json` and `V5_PROTOCOL.md` define the frozen configuration
  and consumed selection/holdout sequence.
- `develop_voidtoken_v5.py` and `verify_voidtoken_v5_development.py` cover the
  adaptive validation-only shards in
  [`real-llm-v5-development/`](../real-llm-v5-development/).
- `run_voidtoken_v5_frozen.py` is the consumed historical one-shot runner.
- `verify_voidtoken_v5_evidence.py` verifies the immutable artifacts in
  [`real-llm-v5-results/`](../real-llm-v5-results/).

These phase results must be verified, never rerun or rewritten.

### Beacon-selected heldout protocol

- `BEACON_HELDOUT_PROTOCOL.md` is the normative protocol.
- `beacon_registration.json`, `beacon_window_ledger.json`, and
  `beacon_freeze.json` bind the suite, eligible pool, and 26-file freeze.
- `beacon_protocol.py` authenticates the exact signed pulse and deterministic
  selection.
- `run_beacon_one_shot.py` and `run_beacon_regression.py` must be invoked only
  from a clean detached checkout of the immutable tag.
- `verify_beacon_evidence.py` verifies the retained outcome and raw evidence.

The evolving branch exposes only `./corelm beacon verify-tag`. It reads frozen
Git objects and cannot prepare assets, resolve a pulse, launch inference, or
write an outcome. The maintained non-normative operator checklist is the
current-branch [launch runbook](../docs/BEACON_LAUNCH_RUNBOOK.md); the frozen
protocol, registration, freeze manifest, and tagged commands remain
authoritative.

## Verification boundary

Fast verifiers independently parse retained containers and recompute token
commitments, complete-byte accounting, NLL, top-1 agreement, and gates. The
heavyweight verifier in [`security/verify_primary_replay.py`](../security/verify_primary_replay.py)
retokenizes the pinned source, independently decodes VTL5, rebuilds both cache
paths, and reruns the registered decisions through the model.

Current app and Linux runs use fixed public validation blocks 64–71. They are
real-data regression fixtures, not blind samples or new generalization
evidence. See [Results](../docs/RESULTS.md) for the current evidence ledger and
[Limitations](../docs/LIMITATIONS.md) for the exact claim boundary.
