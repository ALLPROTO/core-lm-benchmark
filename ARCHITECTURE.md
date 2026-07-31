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

## Module visibility

The release sidebar reports one state for each proof module:

```text
Qwen model -> Prefill -> KV cache -> VoidToken codec -> Cache rebuild
           -> Continuation -> Metrics -> Verifier
```

The states are `Ready`, `Running`, and `Complete`. Dashboard values come only
from the parsed result produced by the Python worker; the Swift UI does not
synthesize benchmark values.

## Final and development surfaces

Release builds expose only **Compression Proof**. Debug builds also expose the
synthetic trajectory generator, Dense and PCA comparisons, saved development
runs, stability plots, and evidence reports. This preserves the architecture
workbench without presenting experimental stages as alternative product
versions.

The synthetic measurement core remains independent of SwiftUI. It materializes
one deterministic input stream, sends the same dense trajectory to every
method, computes metrics and invariants, and writes canonical JSON/Markdown
records for the development suite.

## Reproducibility boundary

Internal schema, codec, receipt, and protocol identifiers are intentionally
stable and may contain revision numbers. They are machine compatibility keys,
not application branding. Their roles and historical chronology are documented
under [Scientific identifiers](docs/development/SCIENTIFIC_IDENTIFIERS.md).
