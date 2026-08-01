# Platform boundaries

The repository has three deliberately separate contours. macOS and Linux are
active build targets. Beacon is a read-only compatibility boundary for the
already published immutable experiment.

| Contour | Sources and locks | Runtime and model cache | Output |
|---|---|---|---|
| macOS | `Package.swift`, `platforms/macos/`, `RealLLM/requirements.lock` | `~/.cache/corelm/macos/runtime`, `~/.cache/corelm/macos/model-assets` | `dist/CoreLMBenchmark.app` and macOS Application Support |
| Linux | `platforms/linux/`, Linux CPU locks, shared current `RealLLM/` code | `~/.cache/corelm/linux/runtime`, `~/.cache/corelm/linux/model-assets` | `~/.cache/corelm/linux/runs/` |
| Beacon | Git blobs from immutable tag `corelm-beacon-heldout-v1` | Frozen paths documented by the tagged runbook | `real-llm-beacon-results/` inside the detached tagged checkout |

Use `./corelm macos ...` and `./corelm linux ...` for active builds. The only
current-tree beacon command is `./corelm beacon verify-tag`; it reads Git
objects and cannot launch an experiment.

`BenchmarkCore/corelm_benchmark.py` is physically retained at its historical
registered path because both its bytes and path are inputs to published
digests. It belongs logically to the beacon compatibility contour, but moving,
copying, or symlinking it would invalidate those digests. Active platform
builds do not import or package it.
