# Causal-LM compatibility inventory

Core LM separates a proven model profile from architecture admission. This is
why the repository does not advertise “all LLMs supported”: causal language
models differ in cache layout, tokenizer, model code, license, memory use, and
sliding-window behavior, while encoder-decoder, multimodal, mixture-of-experts,
and remote-code models have materially different execution surfaces.

The current levels are:

| Level | Meaning |
|---|---|
| Registered evidence model | Exact pinned `Qwen/Qwen2.5-0.5B` revision, assets, WikiText input, compression profile, result, and independent replay |
| Known metadata adapter | A local `config.json` has a closed causal-LM architecture and internally consistent KV geometry; no weights were loaded and no result was produced |
| Unsupported | The configuration is unknown, ambiguous, unsafe, or outside the current cache contract |

The metadata inventory currently recognizes Qwen2, Llama-shaped models such as
SmolLM2, Mistral, GPT-NeoX/Pythia, GPT-2, OPT, and Gemma. Except for the exact
registered Qwen profile, these entries are **admission candidates**, not claims
that arbitrary checkpoints pass compression or even fit the current machine.

## Inspect the closed inventory

After installing the registered Python 3.12.13 runtime for the host:

```sh
./corelm models list
```

The command emits one canonical JSON object. It has no network or model-runtime
dependencies and explicitly records:

```text
modelExecuted = false
acceptedAsBenchmarkEvidence = false
countsTowardScientificVerdict = false
classification = MODEL_METADATA_ADMISSION_NOT_BENCHMARK_EVIDENCE
```

Inspect one already-local Hugging Face configuration with:

```sh
./corelm models inspect-config /absolute/private/path/config.json
```

The input must be an owner-controlled, non-symlinked, non-hardlinked regular
file no larger than 1 MiB. The inspector rejects duplicate JSON keys, remote
code maps, quantization metadata, encoder-decoder or cross-attention models,
multimodal fields, mixture-of-experts fields, unknown architecture pairs, and
inconsistent attention/KV dimensions. It never opens a tokenizer, weights,
dataset, or output file.

## What is covered

Known adapters describe only the metadata needed to plan a future
`Transformers DynamicCache` admission:

- exact architecture and model-type pair;
- number of layers, hidden size, attention heads, KV heads, and head dimension;
- vocabulary and context bounds; and
- full-context versus explicit Mistral sliding-window cache policy.

For a new real model to advance beyond metadata inspection, a future change
must add a separate exact profile with repository, full 40-hex revision,
license, every required asset path/size/SHA-256, tokenizer-bound input digest,
memory bound, and an independent continuation/cache-rebuild check. A known
adapter never inherits Qwen's bit schedule, thresholds, or PASS verdict.

## Demo boundary

The interactive macOS full-system demo continues to run the real registered
Qwen proof because it is the only complete scientific profile. The metadata
inventory can be displayed alongside that demo from a terminal, but it is not
fed into the V15 result, automated capture, collector, release builder, or
portfolio assets. A future evidence-producing multi-model experiment requires
new versioned result/event schemas and independent verifiers.

The Linux and RunPod commands have the same execution boundary: “all
registered execution profiles” currently means the one pinned Qwen profile.
The recorded RunPod execution used CPU-only Torch even though its pod had an
A40, and it does not promote the seven known metadata adapters to runnable or
evidence-producing models.

Deterministic tiny configuration objects for every known adapter are exercised
only in isolated unit tests. They produce no benchmark values and never enter
an evidence directory, as required by the repository real-data policy.
