# Scientific and compatibility identifiers

Core LM Benchmark previously exposed several unrelated version spaces in the
same user-facing page. They are now confined to development and provenance
documentation.

| Identifier space | Example | Purpose |
|---|---|---|
| Algorithm revision | `VoidToken v3`, `VoidToken v5` | Research chronology |
| Wire/codec format | `voidtoken-residual-keyframe-v4` | Parser compatibility |
| Result schema | `corelm-voidtoken-v5-validation-development-v2` | Strict JSON validation |
| Backend/configuration | `voidtoken-v5`, candidate `32` | Frozen measurement identity |
| Receipt schema | `corelm-macos-app-real-llm-run-v3` | App/result binding |
| Evidence tags | `voidtoken-v5-evidence-v1` | Public scientific chronology |
| Publication tag | `voidtoken-v5-paper-v5` | Immutable archive provenance |
| Bundle metadata | `CFBundleShortVersionString`, `CFBundleVersion` | macOS identity and receipt field |
| Dependency versions | Python, Swift, Torch, Transformers, NumPy | Runtime reproducibility |

These identifiers must not be renamed in frozen JSON, schemas, parsers,
receipts, registration files, evidence directories, publication source, tags,
or checksum manifests. They are included in digests and are checked by tests.

The upstream model identifier `Qwen/Qwen2.5-0.5B` must also remain visible. It
identifies the exact model family being measured and is not application
branding.

## User-facing rule

The release application and ordinary-user documentation use:

- **Core LM Benchmark** for the product;
- **Compression Proof** for the end-to-end workflow;
- **VoidToken codec** for the measured codec module;
- **frozen compression profile** for the registered configuration.

Historical synthetic tools and versioned protocol details remain in this
development record, but no application build exposes or bundles them. The
application presents only the registered proof workflow.
