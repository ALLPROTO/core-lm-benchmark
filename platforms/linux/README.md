# Linux real-Qwen regression

Linux provides a command-line CPU build, not the macOS SwiftUI application.
It creates an isolated hash-locked Python runtime, verifies the pinned Qwen and
WikiText bytes, executes public validation blocks 64-71, retains the raw cache
containers and token decisions, and independently verifies them.

Requirements: Ubuntu 24.04 x86_64, Python 3.12.13, 8 GiB available memory, and
6 GiB free disk space.

```sh
./corelm linux doctor
./corelm linux build
./corelm linux run
```

The default runtime, asset cache, and run evidence are stored under
`~/.cache/corelm/linux/` rather than in the checkout. Override them with the
absolute paths `CORELM_LINUX_RUNTIME`, `CORELM_LINUX_HF_HOME`, and
`CORELM_RUN_DIR`.

This is a regression on real, already-public validation input. It is not a
blind, held-out, prospective, or beacon-selected scientific result.
