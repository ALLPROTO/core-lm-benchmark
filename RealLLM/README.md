# Real-LLM KV-cache evidence

This directory defines a separately recorded exploratory experiment on a real
pretrained causal language model. It does not replace, rewrite, or re-index the
115-run synthetic Core LM evidence suite.

The protocol was not independently preregistered or externally timestamped
before first test execution. Validation and test were separated and the chosen
configuration was held fixed during test, but the result is exploratory.

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
- `requirements.txt` — pinned direct Python dependencies for the heavy replay.
- `../schemas/real-llm-result.schema.json` — strict schema for the recorded
  aggregate, including all block-level records and both family verdicts.

Install the separate environment with:

```sh
python3.12 -m pip install -r RealLLM/requirements.txt
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

## Claim boundary

This P0 experiment tests compression of Qwen2.5-0.5B prefill KV cache on pinned
WikiText-2 windows and measures its direct effect on a teacher-forced
continuation. It is not evidence for every model, context length, dataset,
sampling policy, GPU kernel, or free-running generation regime. The recorded
run is an MPS-capable pilot; exact cross-platform PyTorch logits are not claimed.
