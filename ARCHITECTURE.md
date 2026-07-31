# Architecture

The final application is a source-built compression proof. Its release UI shows
one evidence path and exposes the current state of every major module.

```text
Pinned source assets
        |
        v
Qwen model -> Prefill -> BF16 KV cache -> VoidToken codec -> Fresh parser
                                                        |          |
                                                        +----> Cache rebuild
                                                                   |
                                                                   v
Teacher-forced continuation -> Metrics -> Scientific gates -> Swift verifier
                                                               |
                                                               v
                                           Challenge-bound result and receipt
                                                               |
                                                               v
                                             Independent Python verification
```

## Final application

`build_local_app.sh` creates a release build at
`dist/CoreLMBenchmark.app`. The build:

1. creates or validates a dedicated Python runtime;
2. installs only hash-locked dependencies;
3. verifies the exact installed distribution closure;
4. downloads the pinned model and dataset assets and checks their sizes and
   SHA-256 digests;
5. proves that the assets resolve with network access disabled;
6. packages the Swift executable, Python runner, and deterministic runtime
   manifest;
7. applies a local ad-hoc signature; and
8. verifies the bundle before launch.

Before each worker launch, the app checks the signed manifest of the external
Python base installation and virtual environment. Unlisted loadable files,
changed native libraries, unsafe symlinks, writable path components, or an
unexpected Python executable cause a fail-closed rejection.

The real-model worker runs with bounded CPU-library concurrency and conservative
MPS allocation watermarks. Independent in-app and shell watchdogs stop the full
worker process group on critical memory pressure or after five minutes.

## Module visibility

The release sidebar reports one state for each proof module:

```text
Qwen model -> Prefill -> KV cache -> VoidToken codec -> Cache rebuild
           -> Continuation -> Metrics -> Verifier
```

The states are `Ready`, `Running`, and `Complete`. Dashboard values come only
from the parsed result produced by the Python worker; the Swift UI does not
synthesize benchmark values.

## Final application surface

The application target exposes only **Compression Proof**. Historical experiment
sources and records are retained for provenance, but they are not compiled into
the application, bundled as executable resources, or run by the ordinary-user
proof workflow. Their chronology is documented in the
[development record](docs/development/HISTORY.md).

## Reproducibility boundary

Internal schema, codec, receipt, and protocol identifiers are intentionally
stable and may contain revision numbers. They are machine compatibility keys,
not application branding. Their roles and historical chronology are documented
under [Scientific identifiers](docs/development/SCIENTIFIC_IDENTIFIERS.md).
