# Beacon-selected one-shot held-out-window protocol

This document is normative for
`qwen2.5-0.5b-kv-voidtoken-v5-beacon-heldout-v1`. It is a new evidence line;
it does not alter or extend the consumed historical VoidToken v5 suite.

## Evidence status before execution

The fixed public validation blocks 64–71 are a repeatedly exercised
application-regression fixture. They demonstrate that a source build can run
the real Qwen model, serialize and parse VTL5 containers, replay the decoded
cache, and retain verifiable artifacts. They are not blind, are not a holdout,
and cannot support a new generalization result.

The earlier public history is disclosed in
`beacon_window_ledger.json`: validation 0–31 was adaptive development,
validation 32–63 was the consumed one-shot v5 selection, test 8–15 was an
exploratory pilot, test 384–415 was the consumed prospective v5 holdout, and
test 416–447 was its disclosed reserve. The reserve is excluded rather than
repurposed after the v5 result became known.

This new experiment is a **post-freeze, future-beacon-selected held-out-window
evaluation**. WikiText-2 is public and its complete parquet was tokenized in
earlier workflows. The protocol therefore does not claim that eligible text
was unread, secret, or impossible to evaluate privately. “Eligible” means that
the repository audit found no published metric result for that window.

## Frozen inputs and metric gates

The model, tokenizer, corpus revision, 512-token block construction, float32
model execution, BF16 cache canonicalization, 383-token prefill, 128
teacher-forced predictions, VoidToken v5 candidate 32, complete-container byte
accounting, MPS runtime versions, and all seven gates are exactly specified in
`beacon_registration.json`.

The configuration is fixed before the selected source window is known. Its
canonical SHA-256 is
`4c7be8c836aa725722b51f66dce78af7a5094e887432e622b5322f7ca2cf0af8`.
No CLI option can change a source index, window size, model, revision,
configuration, seed, or gate.

The registered Wilson and Student-t quantities are deterministic descriptive
gates, not assumption-free population guarantees. Adjacent tokens and adjacent
512-token blocks can be autocorrelated, and the beacon chooses one contiguous
window rather than 32 independent corpus samples. The `95%` labels identify
the frozen formulas and critical values; they do not upgrade this one-window
experiment into a calibrated generalization claim for all WikiText or all LLMs.

## Content-independent range inventory

Before preregistration, the pinned test parquet was verified and tokenized only
to determine its length. No model, codec, cache, or quality metric was run.
The frozen construction produced 299,078 token IDs: 584 complete blocks plus
70 unused tokens. The ordered uint32-LE token-ID stream has SHA-256
`b44603066a92719a20e2dc18d6c5f7f5342b1877c20c1e2bdd92deca662d3d56`.

The ordered eligible pool contains fifteen disjoint 32-block windows:

```text
16, 48, 80, 112, 144, 176, 208, 240, 272, 304, 336,
448, 480, 512, 544
```

Each number is an inclusive test `startBlock`; the window ends 32 blocks later.
The exact ledger artifact digest is committed by the registration. An invalid,
missing, overlapping, reordered, or digest-mismatched ledger fails closed.

## Public freeze before reveal

The protocol, registration, ledger, runner, verifier, schemas, tests, codec,
and dependency locks are committed first as the `protocolCommit` recorded by
`beacon_freeze.json`. The freeze manifest records, before reveal:

- the full protocol commit;
- the physical and canonical registration SHA-256 values;
- the ledger SHA-256;
- a length- and path-delimited SHA-256 over every normative source file; and
- every individual normative file SHA-256 and byte length.

The manifest is added in a second commit without changing any normative file.
The second commit must be the direct child of the protocol commit and must add
exactly one regular Git blob: `RealLLM/beacon_freeze.json`. That commit must be
the publicly visible lightweight Git tag
`corelm-beacon-heldout-v1` at
`https://github.com/ALLPROTO/core-lm-benchmark`.

Before the beacon, GitHub release immutability must be enabled and a
non-draft, non-prerelease **immutable release** must be published for that exact
tag. The runner fetches the public GitHub API record, requires
`immutable=true`, and requires GitHub's server-side `published_at` to be earlier
than the beacon. An immutable release locks the associated tag to its commit;
the runner additionally checks the official unauthenticated GitHub REST tag-ref
endpoint returns a lightweight `commit` object whose SHA equals frozen HEAD.
It does not trust local Git URL/proxy rewrite configuration for that binding.
The exact two-commit shape, every frozen digest, and a clean checkout are also
required.

The maintainer creates the manifest only after the protocol commit is clean:

```sh
python -I -B RealLLM/prepare_beacon_freeze.py --write-manifest
```

Shell redirection into the repository is intentionally unnecessary: it would
make the clean-tree preflight observe its own output file. The generated
manifest is the sole content of the second commit.

Publishing the tag, hashes, or release after the beacon time does not satisfy
this protocol. A self-declared Git or JSON timestamp is not accepted as proof
of pre-reveal publication. An independent archive snapshot of the immutable
release can further strengthen the timestamp record.

## Future NIST beacon and deterministic selection

The only accepted randomness is the exact NIST Randomness Beacon v2 pulse at
`2026-08-02T18:00:00.000Z` (Unix milliseconds `1785693600000`):

```text
https://beacon.nist.gov/beacon/2.0/pulse/time/1785693600000
```

No latest, nearest, adjacent, local-random, delayed, or alternate-beacon
fallback is allowed. The runner verifies the exact timestamp, period, status,
chain/URI structure, SHA-512 certificate identifier, RSA PKCS#1 v1.5 SHA-512
pulse signature, and NIST output-value construction before selection.

Let `S` be the exact committed bytes of `beacon_registration.json`, `R` the
64-byte beacon `outputValue`, `D` the registered binary domain separator, and
`N=15`. For counter `c=0,1,...`, compute:

```text
H_c = SHA-512(D || uint64be(len(S)) || S || R || uint64be(c))
```

Interpret `H_c` as an unsigned 512-bit big-endian integer `x`. Let
`L = 2^512 - (2^512 mod N)`. Reject `x >= L`; otherwise select ordered candidate
`x mod N`. The resolution records the pulse, certificate, verification values,
counter, digest, candidate index, and selected window. Anyone can recompute it.

This follows the public-beacon pattern of committing a deterministic statement
before randomness from a future time. The NIST service documents 512-bit,
timestamped, signed, hash-chained pulses and this commit-before-future-randomness
procedure.

## Irreversible one-shot execution

The registered state sequence is:

```text
PREREGISTERED_AWAITING_BEACON
              |
              v
ATTEMPT_STARTED_BEACON_AND_DATA_UNRESOLVED
              |
              v
BEACON_RESOLVED_BEFORE_MODEL_DATA
              |
              v
PASS | FAIL_GATES | FAIL_EXECUTION
```

Before the attempt marker, the runner performs administrative preflights: the
time window, artifact absence, clean repository and public freeze, exact package
versions and environment, MPS availability, memory headroom, and exclusive
proof lock. Those checks do not open model/corpus assets, fetch the NIST pulse,
tokenize data, or resolve a selected range. It refuses to start before the target
time or after `2026-08-04T18:00:00.000Z`.
That timestamp is also the completion deadline for a scientific PASS or
FAIL_GATES. Crossing it produces a terminal protocol/execution failure; it is
not described as a publication timestamp, because publication is a subsequent
external action that the local runner cannot attest.

The exact pinned model files and complete test parquet may be downloaded and
digest-verified in advance with `prepare_beacon_assets.py`. That preparation is
content-independent with respect to the future choice: it does not tokenize the
corpus, resolve or read a selected block range, load the model, run the codec,
or calculate a metric. The scientific runner is strictly `--local-files-only`,
so pre-caching prevents an ordinary download failure from consuming the suite.

After every preflight passes, it durably creates
`real-llm-beacon-results/attempt.json` with exclusive creation, file `fsync`,
and directory `fsync` where supported. Only then may it fetch the beacon,
resolve the selected window, resolve model/corpus files, or execute inference.
The marker is never removed or replaced.

An existing marker consumes the suite. A crash, power loss, network error,
beacon verification failure, model error, or integrity failure after marker
creation cannot be retried. When possible the runner writes the terminal
`FAIL_EXECUTION` outcome. A marker without an outcome is
`CONSUMED_INCOMPLETE` and must be published unchanged. Scientific gate failure
is terminal `FAIL_GATES`, not a reason to tune or retry. Exit codes are 0 for
PASS, 2 for FAIL_GATES, and 1 for execution/integrity failure.

The real run retains 768 raw VTL5 containers and per-token metrics for the
32 selected blocks. `verify_beacon_evidence.py` independently verifies beacon
authenticity and selection, artifact hashes, raw wire containers, complete-byte
accounting, per-token loss/agreement arithmetic, aggregate confidence bounds,
and the seven gates.

Blocks are evaluated one at a time and the MPS cache is released after each
block. This bounds peak memory on the target Mac; it does not change the frozen
block order or aggregate arithmetic.

The target requires at least 8 GiB unified memory and at least 15% free system
memory at start. The runner fixes thread limits and conservative MPS allocator
watermarks before importing PyTorch, rejects unregistered MPS environment
knobs, shares the application's exclusive proof lock, and forbids a concurrent
application proof. Memory-heavy applications should remain closed throughout
the one-shot run.

## Regression-only repeats

After a published terminal PASS or FAIL_GATES, any later execution must use
`run_beacon_regression.py`. It reuses the exact resolved window and writes only
under `real-llm-beacon-results/regressions/` with:

```text
evidenceClass = regression-only
countsTowardScientificVerdict = false
```

A regression cannot supply a missing normative outcome, select another window,
change the first verdict, or create a second prospective observation.

## Claim boundary

A complete PASS establishes that the frozen cache-compression/replay gates pass
on one future-beacon-selected, previously unreported WikiText-2 test window. It
is limited evidence of transfer to a member of the registered eligible-window
pool, not a corpus-wide generalization result. It does not establish general LLM
compression, unseen-corpus generalization, free-running generation quality,
latency, energy, or production readiness.

The future beacon makes the selected candidate unpredictable at the public
freeze time and makes the selection auditable. It cannot prove the absence of
undisclosed private runs over a public small corpus. The attempt marker is a
durable local procedural control, not a remote trusted-execution attestation;
therefore the repository can prove which public artifact is normative but
cannot cryptographically prove that its author never ran another private copy.
A stronger claim would require data released after preregistration, independent
execution, or a suitable remotely attested execution environment.

The retained token losses, top-1 IDs, and structural-replay flags bind the
published producer output and allow exact arithmetic/container inspection.
They are not by themselves cryptographic proof that honest model inference
occurred. A full heavyweight causal replay of the selected evidence, or an
independent source run, is required for that stronger verification statement.
