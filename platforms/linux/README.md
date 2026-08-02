# Linux real-Qwen regression

Linux provides a command-line CPU build, not the macOS SwiftUI application.
It creates an isolated hash-locked Python runtime, verifies the pinned Qwen and
WikiText bytes, executes public validation blocks 64-71, retains the raw cache
containers and token decisions, and independently verifies them.

Requirements: Ubuntu 24.04 x86_64, Python 3.12.13, 8 GiB available memory, and
6 GiB free disk space.

## Run in a fresh clone

```sh
./corelm linux doctor
./corelm linux build
./corelm linux run
```

The default runtime, asset cache, and run evidence are stored under
`~/.cache/corelm/linux/` rather than in the checkout. Override them with the
absolute paths `CORELM_LINUX_RUNTIME`, `CORELM_LINUX_HF_HOME`, and
`CORELM_RUN_DIR`.

```sh
CORELM_LINUX_RUNTIME=/absolute/private/corelm-runtime \
CORELM_LINUX_HF_HOME=/absolute/private/corelm-model-cache \
CORELM_RUN_DIR=/absolute/private/corelm-run \
  ./corelm linux run
```

The build uses the hash-complete Linux dependency closure and the official
PyTorch CPU-only wheel lock. Installation retains `--require-hashes`,
`--only-binary=:all:`, and `--no-deps`. Model and validation assets are checked
by size and SHA-256 and must resolve offline before inference.

The runner requires a clean checkout, writes a pre-run contract, fixes the
public validation range and compression configuration, verifies the complete
raw evidence, and produces `SHA256SUMS`. A complete run contains 192 containers
and 1,024 token decisions.

This is a regression on real, already-public validation input. It is not a
blind, held-out, prospective, or beacon-selected scientific result.

See the [recorded public CPU run](RECORDED_RUN_2026-08-01.md) for provenance,
metrics, retained evidence, and the disclosed setup-only failures that preceded
the successful execution.
