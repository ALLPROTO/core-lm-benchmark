# Core LM engineering case study

Core LM is a source-distributed macOS/Linux benchmark for one narrow systems
question: can a complete, serialized KV-cache container be reduced to about
half of canonical BF16 storage while a real language model continues from the
decoded cache with bounded behavioral change?

The current application result is a **regression on fixed public validation
blocks**, not a new blind or generalization result. It compresses KV cache, not
model weights, source text, or the whole application. The useful engineering
artifact is the end-to-end chain: pinned inputs -> model prefill -> canonical
container -> fresh parse -> cache rebuild -> model continuation -> retained
evidence -> separate verification.

## Five-part code tour

### 1. Codec format: bytes are part of the claim

Start with [`RealLLM/voidtoken_v5.py`](../RealLLM/voidtoken_v5.py), especially
`VoidTokenV5Backend.encode()`, `from_bytes()`, and `_parse_container()`.
The wire format is deliberately small and explicit:

```text
b"VTL5" | uint32_le(metadata_length) | canonical_json | binary_payload
```

The format supports an optional deterministic sign rotation followed by a
normalized Walsh-Hadamard transform, group quantization, float16 scales,
packed codes, and optional canonical zlib level 9. The current application
profile explicitly uses `signMode: none`, so its sign transform is the
identity. Metadata binds the shape, bit schedule, transforms, payload digest,
input digest, and decoded reconstruction digest. The parser rejects
non-canonical JSON/zlib, invalid lengths, unused codes, non-finite scales, and
oversized decoded matrices.

[`RealLLM/app_proof_core.py`](../RealLLM/app_proof_core.py) then serializes and
fresh-parses every layer with `VoidTokenV5Backend.from_bytes()`. It requires a
byte-identical round trip before accepting reconstructed cache data. Reported
compression is
`sum(canonical dense BF16 cache bytes) / sum(complete VTL5 container bytes)`;
metadata and framing are included, rather than reporting payload-only size.

**Engineering decision:** a compact algorithm without a canonical bounded
format is difficult to archive, fuzz, or verify independently. Core LM makes
the serialized representation—not an in-memory estimate—the accounting unit.

### 2. Real-model replay: decoded cache must affect real inference

The production macOS worker is
[`RealLLM/app_proof_runner.py`](../RealLLM/app_proof_runner.py). It resolves the
exact Qwen2.5-0.5B revision and WikiText validation file by size and SHA-256,
requires local-only assets, disables remote model code, fixes runtime versions
and seeds, and runs on Apple MPS.

The central path is `_evaluate_block()` in
[`RealLLM/app_proof_core.py`](../RealLLM/app_proof_core.py):

1. Run a real Qwen prefill and extract all KV layers.
2. Establish exact flatten/rebuild and canonical-BF16 baselines.
3. Encode each layer, parse its VTL5 bytes again, and reconstruct the cache.
4. Build a new Transformers `DynamicCache` from the decoded arrays.
5. Continue Qwen with that cache and retain per-token baseline/candidate loss
   and top-1 IDs.

One application regression covers eight known validation blocks, 1,024
teacher-forced decisions, and 192 complete containers. The native integration
result is approximately `2.052384x`, delta NLL `-0.00000849` nat/token, and
`99.5117%` top-1 agreement. Because blocks 64-71 have been used repeatedly,
these numbers establish repeatability of this fixed workflow only.

The public entrypoints are intentionally short:

```sh
./corelm macos doctor
./corelm macos proof

./corelm linux bootstrap
./corelm linux doctor
./corelm linux build
./corelm linux run
```

The macOS command builds and visibly runs the SwiftUI application. The Linux
command executes a separate CPU regression; CPU and MPS results are not
required to be bit-identical.

### 3. Verifier separation: do not trust the producer's parser

The evidence producer writes raw containers and token rows through
`PrimaryEvidenceWriter` in
[`RealLLM/app_proof_core.py`](../RealLLM/app_proof_core.py). Three other paths
check the result:

- [`platforms/macos/App/Sources/PrimaryEvidenceValidation.swift`](../platforms/macos/App/Sources/PrimaryEvidenceValidation.swift)
  validates bounded evidence, hashes, container ordering, and metric
  recomputation inside the native UI.
- [`security/verify_primary_evidence.py`](../security/verify_primary_evidence.py)
  uses only the Python standard library. It intentionally imports neither the
  writer nor the codec and independently parses all 192 containers and
  recomputes byte accounting, NLL, top-1, and gates.
- [`security/verify_primary_replay.py`](../security/verify_primary_replay.py)
  independently decodes the retained VTL5 bytes, reconstructs the registered
  token slice, rebuilds both caches, and reruns all 1,024 Qwen decisions.

[`security/verify_local_app_run.py`](../security/verify_local_app_run.py) also
binds the receipt to the exact application executable, source/build
provenance, runner, runtime manifest, result, and primary evidence. The
orchestrator in
[`platforms/macos/scripts/run-proof.sh`](../platforms/macos/scripts/run-proof.sh)
does not print end-to-end PASS until the app, structural verifier, and heavy
model replay have all returned successfully.

This is **implementation/process separation**, not independent scientific
review. The project is currently author-operated and
`AUTHOR_SELF_VERIFICATION`; no independent human reviewer or independent
external replication has completed the same evidence chain.

### 4. Failure-state semantics: execution success is not metric success

The macOS proof uses a private fresh runtime, an exclusive lock, a challenge
nonce, a unique result-directory check, process-group cleanup, a five-minute
timeout, and a memory-pressure watchdog. Timeout, low memory, stale/multiple
results, non-zero worker exit, or verifier disagreement terminate the command
as failure. The Linux path in
[`platforms/linux/scripts/run-regression.sh`](../platforms/linux/scripts/run-regression.sh)
requires a clean Git checkout and a new output directory, forbids beacon state,
records a regression-only pre-run contract, applies a hard timeout, and writes
the final run manifest only after raw evidence verification succeeds.

The cross-model project demonstrates why metric and execution states must stay
separate. Its public
[`RESULTS.md`](https://github.com/ALLPROTO/core-lm-cross-model-lab/blob/main/RESULTS.md)
records a real Pythia-410M-deduped run that executed and verified correctly but
produced `2.059581758x` compression with `+0.270073175` delta NLL and only
`74.9023438%` top-1 agreement: **FAIL**. The negative cell is not dropped,
replaced, or averaged away. It directly rules out a universal transfer claim
for the unchanged Qwen-derived profile.

**Engineering decision:** an infrastructure error is not evidence that the
codec fails behaviorally, and a successfully executed negative metric result
is not an infrastructure error. Preserving that distinction makes retries,
incident analysis, and scientific boundaries auditable.

### 5. Supply-chain threat model: reproduce inputs, not just commands

The policy is implemented primarily in
[`security/verify_supply_chain.py`](../security/verify_supply_chain.py),
[`security/generate_build_provenance.py`](../security/generate_build_provenance.py),
[`security/generate_python_runtime_manifest.py`](../security/generate_python_runtime_manifest.py),
and [`SECURITY.md`](../SECURITY.md).

Controls cover several concrete threats:

- GitHub Actions must use full commit SHAs and read-only repository
  permissions; risky workflow triggers and duplicate YAML keys fail closed.
- Python requirements are exact and hash-locked; deterministic direct SBOM and
  live OSV checks cover their stated scopes.
- The secret scanner checks the worktree plus reachable commit/tag history for
  high-confidence credentials.
- Build provenance records commit, tree, clean/dirty state, remote, exact tag,
  toolchain, architecture, SDK, and Swift compiler identity.
- The app's signed runtime manifest covers the external Python base prefix,
  virtual environment, native libraries, and package bytes.
- Model, tokenizer, and corpus files are revision-, size-, and SHA-256-bound
  before inference, then used offline for evidence-bearing execution.

The local app is ad-hoc signed: this seals a user's build but does not
authenticate Ivan Tyshchenko as a binary publisher. The prototype is not a
sandbox for hostile Python, models, datasets, the operating system, or the
current user, and its checks do not prove the absence of every vulnerability.
Source—not a portable prebuilt app—is the supported reproducibility artifact.

Verify the public codec source tag and repository gates with:

```sh
git -c gpg.ssh.allowedSignersFile=signing/allowed_signers \
  verify-tag corelm-codec-source-2e8d3b-v1
./corelm verify
```

## Ownership and claim boundary

Ivan Tyshchenko directed the project and is responsible for its architecture,
claims, releases, and mistakes. Implementation, testing, adversarial audits,
and documentation were developed with substantial AI/Codex assistance. AI
agents are tools, not coauthors, independent human reviewers, or external
replicators. A reviewer should therefore evaluate ownership by asking Ivan to
explain and modify the five paths above without agent assistance.

What the project supports today: a working source-built macOS UI, Linux CPU
path, canonical KV-cache format, real-Qwen replay, retained evidence, separate
verifiers, and transparent positive and negative regression results. It does
not support claims of universal LLM generalization, model-weight compression,
free-running generation quality, lower latency or memory, production-serving
readiness, state of the art, independent human validation, or completed Blind
V1 confirmation.

For exact result scope, continue with [`RESULTS.md`](RESULTS.md) and
[`LIMITATIONS.md`](LIMITATIONS.md).
