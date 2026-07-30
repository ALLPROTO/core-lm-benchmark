# Frozen prospective VoidToken v5 protocol

This document is normative for
`qwen2.5-0.5b-kv-voidtoken-v5-prospective-v1`. The machine-readable
`v5_registration.json` and the frozen runner must agree with it. A result from
different source blocks, parameters, thresholds, or code is not part of this
suite.

## Evidence status

VoidToken v5 was engineered adaptively on WikiText-2 validation source blocks
0–31. Those blocks are development data and never count as prospective
evidence. The four exact eight-block artifacts, their file/result SHA-256
values, and the recomputed combined observation are mapped by
`real-llm-v5-development/manifest.json` and checked by
`RealLLM/verify_voidtoken_v5_development.py`. The recorded
`testDataOpened: false` field and content hashes are integrity disclosures, not
an offline proof of how the original process accessed data.

The selected configuration is frozen before two later phases:

1. one-shot acceptance on validation source blocks 32–63;
2. a prospective holdout on test source blocks 384–415.

Test source blocks 416–447 are a reserve. The frozen runner has no mode that
can score them.

Corpus construction tokenizes the complete public parquet before slicing the
registered windows. The reserve is therefore unscored, not unread or secret.
If the pinned split does not contain every registered 512-token block, the
attempt is consumed and stops; indices are never shifted or shortened.

The earlier v1 exploratory pilot read the public test parquet and evaluated
source blocks 8–15. That history is not hidden. The v5 holdout is disjoint and
its configuration, code, gates, and exact source indices must first be
published under the lightweight Git tag
`voidtoken-v5-selection-protocol-v1` before the one-shot validation phase.
The completed validation attempt and result must then be published under
`voidtoken-v5-pretest-v1` before the first v5 holdout execution, but only if
the selection verdict is PASS. A selection FAIL or incomplete attempt is
published unchanged and permanently ends this suite without a pretest tag or
holdout.

## Immutable sources

The model is `Qwen/Qwen2.5-0.5B` at revision
`060db6499f32faf8b98477b0a26969ef7d8b9987`. The runner verifies the
988,097,824-byte `model.safetensors` file against SHA-256
`88c142557820ccad55bb59756bfcfcf891de9cc6202816bd346445188a0ed342`.
The runner also verifies the registered SHA-256 and byte length of
`config.json`, `generation_config.json`, `tokenizer.json`,
`tokenizer_config.json`, `merges.txt`, and `vocab.json` before model loading.

The corpus is `Salesforce/wikitext`, configuration `wikitext-2-raw-v1`, at
revision `b08601e04326c79dfdd32d625aee71d232d685c3`. The validation and test
parquet sizes and SHA-256 values are frozen in `v5_registration.json`.

Rows are read in stored order, joined by exactly `"\n\n"`, tokenized once with
`add_special_tokens=False`, and divided into non-overlapping 512-token blocks.
There is no filtering, stripping, normalization, or overlap.

## Cache extraction and replay

Each case uses tokens 0–382 for prefill. Qwen must return exactly 24 K/V cache
layers with shape `[1, 2, 383, 64]`. At each layer, K and V are converted to
token-major `[383, 128]` matrices and concatenated to `[383, 256]`.

The native float32 cache is rounded once through bfloat16 and back to float32.
This canonical cache is the shared input to the dense reference and codec.
The dense storage denominator is always:

```text
24 × 383 × 256 × 2 = 4,706,304 bytes per block
```

Before any lossy result is accepted, flattening and independent
`DynamicCache.update` reconstruction must reproduce direct-cache continuation
with zero maximum logit difference and identical top-1 decisions. A second
independent reconstruction of the canonical cache must also be exact.

Continuation inputs are tokens 383–510 and targets are tokens 384–511. Each
block therefore contributes 128 teacher-forced predictions that depend on the
supplied prefill cache.

## Frozen VoidToken v5 configuration

Each `[383, 256]` layer is transformed in independent 128-wide K and V blocks
with the normalized Walsh-Hadamard transform. No pseudo-random sign rotation is
used. Each 128-wide group has one float16 max-absolute scale.

Layers 0 and 8 use 9-bit symmetric quantization. The other 22 layers use 8
bits. Signed integers use the frozen zigzag mapping. Scales and packed codes
are compressed independently with canonical zlib level 9.

The full canonical configuration SHA-256 is
`4c7be8c836aa725722b51f66dce78af7a5094e887432e622b5322f7ca2cf0af8`.

Every layer is serialized as:

```text
"VTL5" | uint32-LE canonical-JSON length | canonical JSON | payload
```

All 24 complete containers, including framing and metadata, count toward
compressed storage. Model replay receives only reconstructions returned by a
fresh strict parse of those bytes, not encoder-side in-memory state. Ordered
container lengths and bytes are covered by SHA-256. The parser is a separate
entry path over serialized bytes, but it intentionally shares the canonical
payload-decoding routine with the encoder's self-check; it is not claimed as a
second independent implementation.

Every current v5 candidate record must also contain an ordered, exactly
24-entry `containerManifest`. Each entry records the layer index, the exact
canonical codec metadata object, payload bytes, complete container bytes, and
complete-container SHA-256. `containerManifestSHA256` covers the canonical
manifest JSON. v2/current verifiers independently validate the codec layout, reconstruct
each byte count as `8 + canonical_metadata_bytes + payload_bytes`, reject
impossible zlib lengths, and require the per-layer payload/container sums to
equal the record and aggregate totals. Payload bodies are not duplicated in
JSON; their SHA-256 commitments remain in the metadata. Development v1 shards
without this manifest remain immutable legacy adaptive observations and are
explicitly non-gating; they cannot satisfy current v5 result verification.

The already-consumed historical selection and holdout were emitted as v1
before `containerManifest` existed and cannot be rerun without violating the
one-shot protocol. They are accepted only as byte-identical legacy exceptions:
the verifier pins each canonical result digest, physical artifact SHA-256,
execution commit, historical implementation digest, and registration digest,
then checks the original Git/tag provenance. Any mutation is rejected even if
an attacker recomputes the embedded digest. For those two historical artifacts,
the complete-container byte totals and compression gate are therefore
**runner-recorded, not independently reconstructible per layer**. Their
quality metrics, aggregate arithmetic, gates, and artifact/provenance links are
still independently recomputed. The prospective claim must carry this storage
accounting limitation; only a future, separately registered v2 suite can claim
independent per-layer container accounting.

## Fixed gates

Both the one-shot selection phase and holdout must independently satisfy every
gate:

```text
actual complete-container ratio vs dense BF16 >= 2.0
aggregate delta NLL <= 0.01 nat/token
one-sided 95% Student-t upper bound for block delta NLL <= 0.01
aggregate top-1 agreement >= 0.99
one-sided 95% Student-t lower bound over 32 block top-1 rates >= 0.99
one-sided 95% Wilson lower bound for top-1 agreement >= 0.99
exact structural replay on every block
```

For 32 equal-sized blocks, the registered Student-t critical value is
1.6955187825458675 with 31 degrees of freedom. The Wilson calculation uses
`z=1.6448536269514715`. No rounding is used for verdicts.

Adjacent teacher-forced token decisions are correlated. The Wilson bound is a
frozen workflow gate over token decisions, not a claim that those decisions
are independent Bernoulli samples. The separate Student-t lower bound over the
32 block agreement rates is the registered cluster-aware backstop.

## Prospective execution lock

The selection mode can resolve only the validation parquet and has no test
code path. It will not start unless the clean `HEAD` is already the public
lightweight tag `voidtoken-v5-selection-protocol-v1`. It records that commit
and a digest of every normative implementation file.

The holdout mode refuses to resolve test data unless all of the following are
true:

- the fixed selection artifact exists and passes every registered gate;
- the selection result and its exact attempt marker are committed under
  `voidtoken-v5-pretest-v1`;
- the current clean `HEAD` equals that tag;
- the tag exists on the configured public `origin`;
- the normative implementation digest equals the selection-time digest; and
- the current registration digest equals the selection artifact.

There are no CLI arguments for source indices, block counts, configuration,
thresholds, model revision, dataset revision, or device.

Both phases run from a clean disposable checkout, require Python isolated mode
(`python -I -B`), reject Python injection environment variables, disable bytecode
creation, and refuse local `*.pyc`/`*.pyo` files. After all public-freeze,
clean-worktree, runtime, and device checks—but before resolving the registered
split—the runner durably creates the phase's fixed `*.attempt.json` file with
exclusive creation, file `fsync`, and directory `fsync` where supported. It
never removes or replaces that marker.

An existing marker consumes the phase even when no result exists. A crash,
power loss, model error, or integrity failure after marker creation is
`CONSUMED_INCOMPLETE`; the same suite cannot be rerun. The incomplete marker
must be published. A new attempt would require a new suite ID, registration,
artifact paths, and public tags.

Runner exit code `0` is a recorded scientific PASS, exit code `2` is a
recorded and terminal scientific FAIL, and exit code `1` is an execution or
integrity error. If exit `1` occurs after marker creation, the marker is the
terminal `CONSUMED_INCOMPLETE` artifact. Scientific FAIL is not a reason to
retry.

Immediately before the exclusive result write, the runner rechecks `HEAD`,
the registration digest, every normative source digest, and the exact marker
bytes. The result links both the canonical marker digest and its file-byte
digest. JSON Schema validation and independent metric recomputation must pass
before the result is written.

A local file cannot cryptographically prove that a person never deleted it or
ran a modified copy elsewhere. Accordingly, the first publicly committed
attempt marker for this suite is normative, including an incomplete attempt;
the protocol does not claim stronger append-only guarantees than GitHub's
public history provides.

## Claim boundary

A holdout PASS supports only the pinned Qwen revision, canonical BF16 cache,
registered WikiText-2 windows, teacher-forced replay, and MPS environment. Its
historical v1 compression ratio uses integrity-protected but runner-recorded
complete-container totals; it is not an independently reconstructed storage
measurement. It is not a claim about other
models, long contexts, free-running generation, latency, energy, production
serving, or exact cross-device logits. A FAIL is published unchanged.
