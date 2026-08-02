# Linux real-Qwen regression

Linux provides a command-line CPU build, not the macOS SwiftUI application.
It creates an isolated hash-locked Python runtime, verifies the pinned Qwen and
WikiText bytes, executes public validation blocks 64-71, retains the raw cache
containers and token decisions, and independently verifies them.

Requirements: Ubuntu 24.04 x86_64, 8 GiB available memory, and 6 GiB free disk
space. A pinned owner-local Python 3.12.13 bootstrap is included.

## Run in a fresh clone

```sh
./corelm linux bootstrap
./corelm linux doctor
./corelm linux build
./corelm linux run
```

The bootstrap downloads the immutable Astral `python-build-standalone`
CPython 3.12.13+20260718 x86_64 Linux archive and requires SHA-256
`7eea0959fa425c8aff3ea0a1352ee7d01d794b51439ed8f5fcfa017dbc0ec661`
before safe extraction under `~/.local/share/corelm/`. It rejects path
traversal, escaping links, unexpected owners, and special files. It uses no
`sudo` and does not modify the system Python. Users may instead provide a
trusted Python 3.12.13 with `CORELM_LINUX_PYTHON=/absolute/path/python3.12`.
The Linux bootstrap has its own platform-qualified location,
`~/.local/share/corelm/linux-x86_64/python-3.12.13+20260718`, so it cannot
collide with the separate macOS bootstrap in a shared home directory. Reuse
requires the exclusive exact bootstrap receipt; an arbitrary pre-existing
directory is rejected.
The receipt also binds the post-hardening tree entry count and canonical tree
SHA-256; every implicit reuse recomputes both before executing that runtime.

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

The three destinations must be canonical, private, and non-overlapping. The
doctor checks free space on every filesystem that will actually hold them,
rather than only checking the source checkout. A new runtime is installed into
a private sibling staging directory and published with one rename only after
its packages, ownership marker, Python 3.12.13 prefix, and exact lock closure
pass verification. An interrupted or failed first build removes only that
staging directory. A reused runtime must pass the same owner, mode, marker,
base-prefix, Python-version, and package checks; an incomplete or foreign
directory is never repaired in place.

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
