# Frozen Qwen2.5-0.5B KV-cache pilot protocol

This document is normative for the repository's `qwen2.5-0.5b-kv-v1` pilot. If
an implementation detail conflicts with this document or `registration.json`,
the run is not part of that pilot.

This was not independently preregistered: there was no external timestamp or
separate public Git commit before the first test execution. Validation and test
were kept separate, and the validation-selected configuration was held fixed
for test, but the result must be interpreted as exploratory evidence.

## 1. Immutable sources

### Model

- Repository: `Qwen/Qwen2.5-0.5B`
- Revision: `060db6499f32faf8b98477b0a26969ef7d8b9987`
- License: Apache-2.0
- `model.safetensors` size: 988,097,824 bytes
- `model.safetensors` SHA-256:
  `88c142557820ccad55bb59756bfcfcf891de9cc6202816bd346445188a0ed342`

The loader must use `trust_remote_code=False`. The complete pinned snapshot has
ten files, including `tokenizer.json`, `merges.txt`, and `vocab.json`. Before
model execution, the implementation verifies the registered weight SHA-256 and
both registered parquet SHA-256 values. The pinned revision plus the token-ID
digests in each result anchor the tokenizer files.

### Corpus

- Repository: `Salesforce/wikitext`
- Revision: `b08601e04326c79dfdd32d625aee71d232d685c3`
- Configuration: `wikitext-2-raw-v1`
- Validation parquet SHA-256:
  `204929b7ff9d6184953f867dedb860e40aa69c078fc1e54b3baaa8fb28511c4c`
- Test parquet SHA-256:
  `5f1bea067869d04849c0f975a2b29c4ff47d867f484f5010ea5e861eab246d91`
- Dataset licenses: CC BY-SA 3.0 and GFDL, as declared by the pinned dataset
  repository.

Validation and test remain separate. Validation may select codec parameters;
test may only evaluate the already selected parameters.

## 2. Deterministic corpus construction

For each split independently:

1. Read rows in their stored dataset order.
2. Use each `text` value exactly as stored; do not strip, normalize, or filter
   rows.
3. Join the row values with exactly two line-feed characters (`"\n\n"`).
4. Tokenize the joined text once with the pinned Qwen tokenizer and
   `add_special_tokens=False`.
5. Divide the token stream into non-overlapping blocks of exactly 512 tokens,
   starting at token offset zero.
6. Validation uses blocks `validation-000` through `validation-003`.
7. Test starts at source block 8 and uses `test-008` through `test-015`.

The result record stores the SHA-256 of the little-endian uint32 token IDs for
its block. Any token digest change invalidates the run ID.

## 3. Recorded pilot runtime

The recorded pilot uses:

- Python 3.12;
- model parameters and computation in float32;
- `model.eval()` and `torch.inference_mode()`;
- eager attention;
- `use_cache=True`;
- deterministic algorithms requested in warn-only mode;
- no sampling, dropout, compilation, or autocast; and
- explicit recording of the resolved device and software environment.

With `--device auto`, the implementation selects MPS, then CUDA, then CPU. The
recorded artifact remains a pilot on its recorded device. It is not expected
to reproduce exact PyTorch logits across devices or CPU architectures, and no
canonical CPU run is claimed by this protocol.

## 4. Prefill and cache extraction

For a token block `x[0:512]`:

1. Prefill with `x[0:383]`.
2. Obtain `outputs.past_key_values`.
3. Require exactly 24 layers.
4. At each layer `l`, require both K and V to have shape `[1, 2, 383, 64]`.
5. Convert K and V to contiguous CPU float32.
6. Squeeze the batch axis, transpose to token-major order, and concatenate K and
   V on the last axis:

   ```text
   K_l, V_l: [1, 2, 383, 64]
   token_major(K_l), token_major(V_l): [383, 2, 64]
   Z_l = concat(flatten(K_l), flatten(V_l)): [383, 256]
   ```

Layers are never concatenated before compression. Each layer is one independent
trajectory, preventing a global top-k or scale from creating competition
between unrelated layers.

## 5. Canonical bfloat16 reference

The extracted float32 cache is rounded once through `torch.bfloat16`, then
converted back to contiguous little-endian float32:

```text
native FP32 cache -> bfloat16 -> FP32 = canonical reference cache
```

Both the dense reference continuation and every codec receive this identical
canonical cache. The uncompressed storage denominator remains the bfloat16
representation at exactly two bytes per scalar:

```text
24 layers × 383 tokens × 256 values × 2 bytes = 4,706,304 bytes per case
```

The run separately reports the native-FP32-to-canonical-bfloat16 change in NLL,
logits, and top-1 decisions. That diagnostic is not attributed to either codec.

## 6. Exact structural replay

Before lossy compression, every `[383, 256]` trajectory is split back into K and
V, reshaped to `[1, 2, 383, 64]`, and assembled by ordered
`DynamicCache.update(K, V, layerIndex)` calls. This is the public API exposed by
the pinned Transformers version.

The structural replay gate requires:

- a SHA-256 anchor for the canonical bfloat16 cache;
- zero maximum logit difference between continuation from the original
  framework `DynamicCache` and continuation from the independently flattened
  and rebuilt FP32 cache;
- zero maximum logit difference between two independent rebuilds from the same
  canonical layer trajectories;
- identical continuation token decisions; and
- zero unexpected shape, dtype, layer-count, or finite-value violations.

This gate isolates cache-layout mistakes from compression error.

## 7. Registered codec families

### VoidToken

The primary research method is
`voidtoken-residual-keyframe-v4` with canonicalization
`fixed-order-v1`. Each layer is encoded and decoded by the existing independent
binary codec. Full `CLMB` container bytes, not only the payload, count toward
compressed storage. The trajectory used for model replay comes from a fresh
`EncodedRepresentation.from_bytes(container)` parse.

The registered validation grid is:

```text
topK=32, qmax=127, keyframeInterval=32
topK=32, qmax=127, keyframeInterval=64
topK=48, qmax=127, keyframeInterval=64
topK=64, qmax=127, keyframeInterval=64
topK=64, qmax=127, keyframeInterval=128
```

### Packed group quantization

`packed-group-quant-v1` is a separate strong baseline. It is never described as
VoidToken. Each row is divided along axis 1 into contiguous groups. A group uses
symmetric max-absolute quantization, ties-to-even rounding, a little-endian
float16 scale, offset-binary signed codes, and an LSB-first packed bitstream.
The registered 7-bit/group-16 candidate stores the scale section with
deterministic zlib level 9; decompression is exact and the compressed scale
bytes are included in the container digest and byte count.
Each layer must round-trip through the `RLGQ` container and independent parser
before evaluation. Packed values, scales, headers, canonical JSON metadata,
padding, and per-layer container overhead all count toward storage.
The model receives only the reconstruction returned by that fresh parser, never
the encoder's in-memory reconstruction.

The payload size is:

```text
storedScaleBytes + ceil(codeCount × bits / 8)
```

The container is:

```text
"RLGQ" | uint32-LE metadata length | canonical JSON | payload
```

The validation grid is:

```text
bits=4, groupSize=16, scaleCompression=none
bits=4, groupSize=32, scaleCompression=none
bits=5, groupSize=16, scaleCompression=none
bits=5, groupSize=32, scaleCompression=none
bits=6, groupSize=16, scaleCompression=none
bits=6, groupSize=32, scaleCompression=none
bits=7, groupSize=16, scaleCompression=zlib-9
bits=7, groupSize=32, scaleCompression=none
bits=7, groupSize=64, scaleCompression=none
bitsByLayer=top16-sensitive:8/rest:5, groupSize=16, scaleCompression=zlib-9
bitsByLayer=top17-sensitive:8/rest:5, groupSize=16, scaleCompression=zlib-9
```

For the two mixed-precision candidates, sensitivity is frozen from a
validation-only intervention: quantize one layer at a time to 6 bits, measure
mean continuation KL on validation blocks 0–3, then sort descending by KL. The
registered order is:

```text
8, 0, 1, 4, 16, 9, 2, 20, 11, 21, 3, 14,
22, 13, 17, 12, 19, 10, 15, 23, 5, 7, 6, 18
```

The first 16 or 17 layers in that order use 8 bits; every remaining layer uses
5 bits. This order is fixed before any registered test block is evaluated.

Unsupported combinations must be rejected rather than silently substituted.

### Selection rule

Selection is performed independently for each codec family on the four
validation cases:

1. discard configurations with any structural/invariant failure;
2. retain configurations whose aggregate compression against dense bfloat16 is
   at least 2.0x;
3. prefer candidates that pass all three validation quality gates;
4. if a family has no validation PASS, keep its best eligible candidate as a
   declared negative control;
5. minimize mean KL divergence from baseline logits;
6. break ties by higher top-1 agreement, then fewer total compressed bytes, then
   lexicographic configuration ID.

The selected configuration is computed before test execution and remains fixed
while test runs. The final aggregate records that selection after the run. This
pilot did not create an independently timestamped pre-test selection artifact;
test results may not change the recorded selection.

## 8. Continuation replay

Create independent clones of the canonical dense cache and each reconstructed
cache because Hugging Face cache objects can be mutated during inference.

For both baseline and candidate:

1. use cache positions `383` through `510`;
2. feed continuation inputs `x[383:511]`;
3. compare the resulting 128 logits to target tokens `x[384:512]`.

This yields exactly 128 teacher-forced next-token predictions whose attention
depends on the supplied prefill cache.

## 9. Metrics and byte accounting

Each case and codec family records:

- total dense bfloat16 bytes;
- total compressed container bytes;
- compression ratio;
- cache NRMSE, cosine similarity, and maximum absolute error;
- baseline and reconstructed NLL in natural units per token;
- `deltaNll = reconstructedNll - baselineNll`;
- `perplexityRatio = exp(deltaNll)`;
- mean KL divergence from baseline to reconstructed logits;
- baseline top-1 token agreement rate;
- encode/decode and continuation time as non-deterministic diagnostics;
- one domain-separated SHA-256 over all 24 ordered layer containers.

Exact SHA-256 gates cover the registered token IDs, canonical input cache, and
the ordered encoded containers produced from that cache. A fresh model
extraction on different hardware is compared with declared numerical
tolerances; the protocol does not promise bit-identical PyTorch model inference
across CPU architectures.

## 10. Independent verdicts

The following gates apply separately to VoidToken and packed group quantization:

```text
compressionRatio >= 2.0
deltaNll <= 0.01 nat/token
top1Agreement >= 0.99
structuralReplay == PASS
```

The three numerical gates are evaluated over the complete registered test
aggregate. Structural replay must pass for every block. A group-quant PASS
cannot mask a VoidToken FAIL. Negative results remain in the aggregate and
publication.

## 11. Pilot disclosure and claim boundary

The machine-readable evidence class retains the repository identifier
`registered-real-llm-pilot`; it does not mean independently preregistered. An
Apple-Silicon/MPS result may receive the two pilot verdicts, but it is not a
cross-platform exactness result. A later CPU replication must identify itself
as a distinct environmental replication and must not silently replace this
artifact.

The evidence applies only to the pinned Qwen revision, WikiText-2 cases, context
split, cache canonicalization, codec implementations, and thresholds above. It
does not establish universal compression of arbitrary models, long contexts,
free-running generation, or production serving workloads.
