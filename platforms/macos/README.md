# macOS application

The macOS target is the native SwiftUI application. It builds locally from
source, packages the pinned real-Qwen worker, applies an ad-hoc signature, and
runs on Apple MPS. No Apple developer account, paid certificate, Developer ID,
or notarization is required.

Requirements: Apple Silicon, macOS 14 or newer, Swift 6 or newer, Python
3.12.13, 8 GB unified memory, and 6 GiB free disk space.

```sh
./corelm macos doctor
./corelm macos proof
```

Useful separate stages:

```sh
./corelm macos bootstrap
./corelm macos build
open dist/CoreLMBenchmark.app
./corelm macos prepare-offline
```

`App/` and `Tests/` are macOS-only Swift sources. The scripts in `scripts/`
are internal platform entrypoints; ordinary users should invoke them through
`./corelm` from the repository root.
