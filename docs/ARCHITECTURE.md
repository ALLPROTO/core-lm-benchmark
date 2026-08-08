# Architecture

The benchmark has a shared real-Qwen and codec core with two active platform
frontends plus one read-only compatibility contour. macOS builds the native
source-verified application; Linux builds a CPU-only command-line runtime and
evidence bundle; beacon verifies immutable Git objects but cannot launch from
the evolving branch.

```text
                         RealLLM shared core
                       /                    \
          macOS SwiftUI + MPS          Linux CLI + CPU
          signed local receipt         raw verified evidence

       immutable tag blobs -> beacon compatibility boundary (read-only)
```

The native release UI shows one evidence path and exposes the current state of
every major module.

```text
Pinned source assets
        |
        v
Qwen model -> Prefill -> BF16 KV cache -> VoidToken codec -> Fresh parser
                                                        |          |
                                                        +----> Cache rebuild
                                                                   |
                                                                   v
Teacher-forced continuation -> Metrics -> Regression gates -> Swift verifier
                                                               |
                                                               v
                                    Trusted-local stale-run binding and receipt
                                                               |
                                                               v
                                             Independent Python verification
```

## Final application

`./corelm macos build` creates a release build at
`dist/CoreLMBenchmark.app`. The build:

1. creates or validates a dedicated Python runtime;
2. installs only hash-locked dependencies;
3. verifies the exact installed distribution closure;
4. downloads the pinned model and dataset assets and checks their sizes and
   SHA-256 digests;
5. proves that the assets resolve with network access disabled;
6. packages the Swift executable, fixed production runner, generated minimal
   proof core, VoidToken backend and its codec helpers, and deterministic
   runtime manifest;
7. applies a local ad-hoc signature; and
8. verifies the bundle before launch.

Before each worker launch, the app checks the signed manifest of the external
Python base installation and virtual environment. Unlisted loadable files,
changed native libraries, unsafe symlinks, writable path components, or an
unexpected Python executable cause a fail-closed rejection.

The packaged `app_proof_runner.py` accepts only the registered frozen
compression profile, validation-only input, Apple MPS, offline assets, and
bounded proof arguments; the release app supplies the registered validation
block range. Its `app_proof_core.py` is generated mechanically from the frozen
real-model engine. Packaging verifies its semantic AST independently of
host-Python formatting; source comparison, build provenance, and the bundle
signature then bind the exact checked-in bytes. The exploratory pilot CLI,
development runner, alternative-backend execution, candidate-grid execution,
and beacon compatibility source remain source-only and are rejected if they
appear in the release bundle.

The real-model worker creates its own process group before importing NumPy,
PyTorch, or Transformers; the Swift parent confirms that group before accepting
the launch. It runs with bounded CPU-library concurrency and conservative MPS
allocation watermarks. Independent in-app and shell watchdogs stop the full
worker process group on critical memory pressure or after five minutes. The
outer proof also records recursively discovered worker groups so cleanup still
reaches the model process if the GUI exits first.

## Module visibility

The release sidebar reports one state for each proof module:

```text
Qwen model -> Prefill -> KV cache -> VoidToken codec -> Cache rebuild
           -> Continuation -> Metrics -> Verifier
```

The states are `Ready`, `Running`, and `Complete`. Dashboard values come only
from the parsed result produced by the Python worker; the Swift UI does not
invent benchmark values.

## Final application surface

The application target exposes only **Compression Proof**. Registered real-data
development and result records are retained for provenance, but they are not
compiled into the application or run by the ordinary-user proof workflow. The
retired complete synthetic suite and results exist only in an immutable
historical tag. One byte-identical compatibility source, including its dormant
unsupported historical CLI, remains at its registered legacy path because
published digests include that path; it is not part of either platform build
or the `./corelm` surface. The chronology is documented in the
[development record](development/HISTORY.md), and platform ownership is
defined in [`platforms/README.md`](../platforms/README.md).

## Reproducibility boundary

The application always evaluates fixed, public validation blocks 64–71. They
have been exercised repeatedly and therefore form an application-regression
fixture: the pipeline can demonstrate that the app, codec, evidence retention,
and verifiers still work, but it cannot turn those blocks into a blind sample,
holdout, or generalization experiment. Repeated executions on that fixture are
repeatability checks, not independent experiments. The local challenge binds a
receipt to the current trusted-local invocation so the workflow does not
accidentally select an older result; it is not remote freshness attestation.

The separately registered beacon-selected held-out experiment is a different
architecture path. `RealLLM/BEACON_HELDOUT_PROTOCOL.md` fixes its commit/digest
freeze, parameters, gates, eligible unreported-window pool, and deterministic
future-NIST-beacon selection before resolution. That freeze is already public
and immutable at tag commit
`0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44`. Its one terminal **PASS** is
published at evidence commit `85c2add1799652a818873a04310b75821728da11`;
the path is now a closed, read-only evidence contour and cannot be revived.

```text
Clean detached frozen tag -> Administrative preflights -> Durable attempt marker
                                                               |
                                                               v
Exact signed NIST pulse -> Deterministic window resolution -> 32-block MPS run
                                                               |
                                                               v
                PASS | FAIL_GATES | FAIL_EXECUTION | CONSUMED_INCOMPLETE
                                                               |
                                                               v
                    Independent verification -> Unchanged public artifacts
```

The attempt marker is written before beacon retrieval or selected-data
resolution. It allows one recorded execution. Only after terminal `PASS` or
`FAIL_GATES` may a later execution be labelled regression-only;
`FAIL_EXECUTION` and an incomplete attempt forbid a retry. The operator runs on
AC power under an external macOS `caffeinate` assertion because the frozen
one-shot does not acquire the application's idle-sleep assertion. The exact
target `2026-08-02T18:00:00.000Z`, deadline
`2026-08-04T18:00:00.000Z`, checkout, execution, and publication procedure is
the [beacon launch runbook](BEACON_LAUNCH_RUNBOOK.md).

## Identifier boundary

Internal schema, codec, receipt, and protocol identifiers are intentionally
stable and may contain revision numbers. They are machine compatibility keys,
not application branding. Their roles and historical chronology are documented
under [Scientific identifiers](development/SCIENTIFIC_IDENTIFIERS.md).
