# Real-LLM KV-cache evidence

This directory contains the recorded experiments and current proof path for a
real pretrained causal language model. Historical studies remain isolated from
the native application's registered Qwen/VoidToken workflow.

The original exploratory pilot in this directory was not independently
preregistered or externally timestamped before first test execution. Its
validation and test cases were separated and the chosen configuration was held
fixed during test, but that pilot result remains exploratory. The later v5 and
beacon protocols below have their own prospective freeze records.

## Pinned target

The target is the public Apache-2.0
[`Qwen/Qwen2.5-0.5B`](https://huggingface.co/Qwen/Qwen2.5-0.5B) model at the
immutable revision
[`060db6499f32faf8b98477b0a26969ef7d8b9987`](https://huggingface.co/Qwen/Qwen2.5-0.5B/tree/060db6499f32faf8b98477b0a26969ef7d8b9987).

- Architecture: `Qwen2ForCausalLM`
- Layers: 24
- Hidden size: 896
- Attention heads: 14
- KV heads: 2
- Head dimension: 64
- `model.safetensors`: 988,097,824 bytes
- Weight SHA-256:
  `88c142557820ccad55bb59756bfcfcf891de9cc6202816bd346445188a0ed342`

The weights are downloaded from the pinned repository and are not redistributed
in this project.

## What is measured

For every evaluation case, the benchmark:

1. runs a 383-token prefill;
2. extracts `outputs.past_key_values` from all 24 layers;
3. converts each layer's K and V tensors from `[1, 2, T, 64]` into one
   `[T, 256]` trajectory;
4. rounds the reference cache through bfloat16 and back to float32, so both
   codecs receive the same canonical input;
5. compresses every layer independently;
6. reconstructs a Hugging Face `DynamicCache`;
7. feeds that cache back into Qwen for 128 teacher-forced continuation
   predictions; and
8. compares bytes, cache error, logits, NLL, perplexity, and token decisions.

The strict storage denominator is the canonical dense bfloat16 cache at exactly
two bytes per scalar. Container metadata and all per-layer overhead count toward
the compressed size.

## Two separate codec claims

The experiment does not select the best-looking codec after test execution.
It registers and reports two independent families:

- `voidtoken-residual-keyframe-v4` — the existing closed-loop sparse residual
  codec;
- `packed-group-quant-v1` — a conventional packed group-quantization baseline.

Each family is tuned only on the validation split, frozen, and then receives its
own test verdict. A PASS by group quantization does not make VoidToken pass, and
a VoidToken failure remains part of the published evidence.

## Files

- `registration.json` — pinned model, dataset, runtime, cases, selection rule,
  thresholds, and claim boundary.
- `PROTOCOL.md` — normative extraction, canonicalization, reconstruction, and
  evaluation procedure.
- `requirements.txt` — pinned direct Python dependencies for review.
- `requirements.lock` — hash-complete dependency closure for the heavy replay.
- `../schemas/real-llm-result.schema.json` — strict schema for the recorded
  aggregate, including all block-level records and both family verdicts.

Install the separate environment with:

```sh
python3.12 -m pip install --require-hashes -r RealLLM/requirements.lock
```

The output is explicitly a repository-recorded exploratory pilot, not an
independently preregistered or cross-platform production claim. A pilot PASS
requires an aggregate that validates against the schema and passes the
independent evidence verifier.

## Separate prospective v5 suite

The negative v1 pilot above remains immutable. A separate VoidToken v5
redesign and prospective protocol live in:

- `voidtoken_v5.py` — canonical transform/group codec and strict byte parser;
- `develop_voidtoken_v5.py` — validation-only engineering runner;
- `v5_registration.json` and `V5_PROTOCOL.md` — frozen prospective protocol;
- `run_voidtoken_v5_frozen.py` — locked one-shot selection/holdout runner;
- `verify_voidtoken_v5_development.py` — recomputation of the four published
  validation-only development shards;
- `verify_voidtoken_v5_evidence.py` — full Git-provenance verifier in a tagged
  clone and explicitly limited artifact-self-consistency verifier in a tar;
- `../real-llm-v5-development/` — exact adaptive development artifacts; and
- `../real-llm-v5-results/` — v5 phase results and durable attempt markers.

Development blocks 0–31 do not count toward the prospective verdict. The
configuration, statistical confidence gates, later source blocks, MPS runtime,
and public protocol tag are fixed before the one-shot acceptance. The passing
selection result and its marker must then be public under the pretest tag before
holdout. Both frozen modes require `python -I -B`; once a marker is created before
split access, a crash consumes that phase and retry is forbidden.

A selection FAIL is also a valid terminal scientific artifact: it is published
unchanged and permanently forbids the pretest tag and holdout. Runner exit code
`2` means recorded scientific FAIL, not an execution crash.

## Local macOS application proof

On an Apple-Silicon Mac, `./corelm macos build` prepares the hash-locked
Python environment, uses `prepare_app_assets.py` to download and digest-check
only the pinned model plus validation data, and creates a locally ad-hoc signed
app without an Apple Developer account. `./corelm macos proof` then runs
candidate 32 on fixed public validation blocks 64–71 through the visible app and
passes the resulting regression evidence to
`../security/verify_local_app_run.py`. Those blocks have been exercised
repeatedly; they are not blind, held out, or eligible to support a new
generalization claim.

Every new application proof retains a `primary-evidence/` tree beside its
result: 192 deterministic `.vtl5` containers, all 512 source token IDs per
block, and the 128 per-prediction baseline/candidate losses and top-1 IDs. The
stdlib-only `../security/verify_primary_evidence.py` deliberately imports no
writer or codec module; it parses the raw headers, canonical metadata and zlib
streams, recomputes token commitments and quality metrics, and rejects missing,
extra, symlinked, or digest-mismatched artifacts.

The token-metric schema defines NLL reduction as ordered IEEE-754 binary64
addition in increasing prediction offset, divided by 128. Aggregate NLL applies
the same ordered addition to the eight block means. This cross-language rule
can differ in the last few decimal places from a framework's parallel
`reduction="mean"`; it does not change the logits, token decisions, or gate.

`../security/verify_primary_replay.py` is the heavyweight causal check. It also
imports no benchmark or codec code: it verifies and tokenizes the pinned
WikiText parquet, loads the hash-verified pinned Qwen snapshot, independently
decodes zlib, bit packing, zigzag values, float16 scales and inverse Hadamard,
rebuilds both BF16 baseline and decoded candidate caches, and reruns all 1,024
MPS predictions sequentially. Every top-1 ID must match exactly. Every retained
loss must match with absolute tolerance `2e-5` and relative tolerance `2e-6`;
the verified same-machine run matched with zero observed difference.

This integration run is deliberately separate from the immutable prospective
holdout. It provides a path for another user to execute the real model and
test the container accounting and quality gates without trusting the author's
historical app executable. External reproduction is established only when
another user actually completes and publishes that run. Multiple executions on
blocks 64–71 are repeatability/regression checks, not independent experiments.
The receipt challenge only protects a trusted-local workflow from accidentally
selecting a stale run; it is not cryptographic remote-freshness evidence.

## Registered next held-out-window suite

`BEACON_HELDOUT_PROTOCOL.md`, `beacon_registration.json`, and
`beacon_window_ledger.json` define a separate post-freeze,
future-beacon-selected held-out-window experiment. Before selection, the public
record must fix the exact commit and digests, all parameters and gates, the
eligible pool, and the deterministic NIST-beacon rule. The selected window may
then be evaluated once with no post-result tuning. A later execution is
regression only and is permitted solely after terminal `PASS` or `FAIL_GATES`;
`FAIL_EXECUTION` and an incomplete attempt cannot be retried. No result is
reported yet, and blocks 64–71 are excluded.
The freeze is accepted only if GitHub reports an immutable release for the
registered tag with a server-side publication time earlier than the beacon.

The normative one-shot command is intentionally locked until the required tag
is public and the registered pulse time has arrived:

```sh
./corelm macos build

HF_HOME="$HOME/.cache/corelm-model-assets" \
"$HOME/.cache/corelm-app-runtime/bin/python" -I -B \
    RealLLM/prepare_beacon_assets.py \
    --cache "$HOME/.cache/corelm-model-assets"

HF_HOME="$HOME/.cache/corelm-model-assets" \
"$HOME/.cache/corelm-app-runtime/bin/python" -I -B \
    RealLLM/prepare_beacon_assets.py \
    --cache "$HOME/.cache/corelm-model-assets" --offline-only
```

The preparation step downloads and verifies only the frozen model files and
test parquet. It deliberately performs no tokenization, model inference, codec
execution, source-window selection, or metric calculation, so it may be run
before the beacon. It is worth doing in advance: the one-shot runner forbids
network access to model/data assets after the irreversible marker exists.
The second command proves that the same cache resolves and verifies with the
network disabled before the one-shot marker can be created.

The frozen protocol's earliest start remains `2026-08-02T18:00:00.000Z` and
its deadline remains `2026-08-04T18:00:00.000Z`. A separate non-normative
operator rule announced before reveal forbids invoking the one-shot before
`2026-08-02T18:15:00.000Z`. Execute exactly once from a clean checkout of the
public frozen tag, using the executable time, AC-power, `caffeinate`, integrity,
and artifact checks in
[`docs/BEACON_LAUNCH_RUNBOOK.md`](../docs/BEACON_LAUNCH_RUNBOOK.md). Do not use
an abbreviated direct command from another document.

The first command has no source, configuration, or gate overrides. Existing
`attempt.json` consumes the suite even if execution was interrupted. Only after
a terminal scientific outcome may a later check run as:

```sh
HF_HOME="$HOME/.cache/corelm-model-assets" \
"$HOME/.cache/corelm-app-runtime/bin/python" -I -B \
    RealLLM/run_beacon_regression.py --local-files-only
```

All 32 selected blocks are evaluated sequentially, and the runner releases the
MPS cache after each block. It does not batch the full window into Mac memory.

## Claim boundary

This P0 experiment tests compression of Qwen2.5-0.5B prefill KV cache on pinned
WikiText-2 windows and measures its direct effect on a teacher-forced
continuation. It is not evidence for every model, context length, dataset,
sampling policy, GPU kernel, or free-running generation regime. The recorded
run is an MPS-capable pilot; exact cross-platform PyTorch logits are not claimed.
