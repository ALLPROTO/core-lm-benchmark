# Beacon v1 audit and v2 hardening requirements

This document records the final pre-execution architecture audit of
`qwen2.5-0.5b-kv-voidtoken-v5-beacon-heldout-v1`. It is non-normative and does
not modify the frozen protocol, selection rule, implementation, parameters, or
gates.

## Frozen v1 status

- Freeze tag: `corelm-beacon-heldout-v1`
- Freeze commit: `0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44`
- Protocol commit: `b34bc4d06c00c86b99076b117049e2d590d73bcd`
- Target pulse: `2026-08-02T18:00:00.000Z`
- Execution deadline: `2026-08-04T18:00:00.000Z`
- Frozen implementation SHA-256:
  `bf8dea05e7b6dbf726d0a857d2e9f78219bf28c24a949c8a93f21891eac83d56`

The immutable pre-beacon release and all 26 entries in
`RealLLM/beacon_freeze.json` were verified before execution. Those files must
not be edited, replaced, retagged, or silently patched. A v1 execution remains
valid only for the narrow claim stated in the frozen protocol.

At `2026-08-01T10:08:12Z`, before the target pulse, the release notes were
clarified to call their four listed paths “Key normative artifacts” and to
point to the complete 26-file manifest. GitHub's `published_at`, tag, assets,
manifest, and all frozen files remained unchanged; the notes-only `updated_at`
is recorded here and in the launch runbook for transparency.

## What v1 can establish

A terminal `PASS` establishes that the frozen KV-cache codec and
teacher-forced replay gates passed on one NIST-beacon-selected member of the
registered WikiText-2 test-window pool. This is prospective evidence of
transfer within that pool.

It is not evidence of full-model compression, free-running generation quality,
corpus-wide generalization, latency, energy efficiency, remote attestation, or
state of the art. It also does not cryptographically prove that no undisclosed
private run occurred.

## Accepted v1 trust boundaries

The pre-execution audit found no fail-open defect in the attempt marker,
authenticated NIST-pulse resolution, deterministic window selection, frozen
configuration/gates, or no-retry state machine. The following limitations
remain and must accompany any v1 result:

1. **Trusted local runtime.** The one-shot verifies registered package version
   strings and the process environment, but it does not bind a file-by-file
   Python runtime manifest into `attempt.json` and `outcome.json`. A locally
   modified package that reports the expected version is outside the v1 threat
   model.
2. **No independent process supervisor.** Memory and deadline checks occur at
   controlled points around block evaluation. A kernel, MPS, or process hang
   cannot be converted reliably into a complete terminal outcome by the frozen
   runner. An interrupted attempt is `CONSUMED_INCOMPLETE` and cannot be retried.
3. **Arithmetic evidence, not attested inference.** The verifier authenticates
   the selection and recomputes container and token-metric arithmetic. It does
   not cryptographically attest that the retained outputs came from honest
   model inference. A heavyweight replay or independent execution is needed for
   that stronger statement.
4. **Vocabulary bound omitted in the frozen verifier.** Token IDs are bounded
   as unsigned 32-bit integers, rather than to the registered Qwen vocabulary
   size of 151,936. Honest producer output is vocabulary-bounded, but the
   verifier alone does not prove this property.
5. **Regression evidence is secondary.** The frozen regression runner cannot
   change the normative verdict and has no equally complete standalone public
   schema/verifier. Regression artifacts must not be presented as a second
   prospective observation.
6. **Local timestamps.** The NIST pulse prevents early selection, but execution
   timestamps and the deadline check rely on the local system clock rather than
   a remote trusted timestamp.
7. **Same-user asset race.** Frozen asset hashes are checked before model
   loading. A malicious same-user process that changes cache files between
   verification and loading is outside the trusted-local execution model.
8. **Raw terminal errors.** A `FAIL_EXECUTION` may retain an exception message.
   The launch environment therefore must not contain secrets in paths, command
   arguments, or environment variables. A terminal artifact must be published
   unchanged even when its message is inconvenient.

Operational precautions such as AC power, an active macOS sleep assertion,
private verified asset caches, a clean detached tag checkout, and an accurate
clock reduce accidental failure. They do not strengthen the scientific claim
or change the frozen protocol.

## Required v2 changes

A future stronger protocol must use a new suite identifier, a new public
pre-reveal freeze, a new tag/release, and a new future selection event. It must
not replace or reinterpret v1. Before a v2 freeze:

1. generate a hash-locked file manifest for the complete executable Python
   runtime and bind its digest into registration, attempt, outcome, and
   verification;
2. execute inference in a supervised child process with a hard wall-clock
   deadline, continuous memory monitoring, explicit process-group ownership,
   and durable terminal-failure recording;
3. validate every source, target, and top-1 token ID against the registered
   tokenizer vocabulary size;
4. provide a strict regression schema and verifier that first verifies the
   complete normative outcome and public freeze;
5. eliminate the asset verification/load race by loading from a private,
   immutable verified snapshot or equivalent file-descriptor-bound mechanism;
6. either fail on unsupported deterministic operations or preregister the
   allowed numerical nondeterminism and cross-run tolerance;
7. bind execution time to a public timestamp source when deadline enforcement
   is part of the claim;
8. sanitize operator-controlled paths before execution while retaining any
   terminal evidence unchanged; and
9. use independent execution, newly released data, or suitable remote
   attestation if the claim is strengthened beyond trusted-local evidence.

Until those requirements are frozen prospectively, v1 must be described only
with its registered claim boundary.
