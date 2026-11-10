# Reproduce Core LM

Core LM measures **serialized KV-cache compression**, not model-weight
compression. Current repeatability commands use pinned Qwen on public
WikiText validation blocks 64–71. They are not blind experiments. Do not run
the historical holdout or beacon one-shot to reproduce the demo.

## Choose a machine

- Linux: Ubuntu 24.04 **x86_64**, at least 8 GiB available RAM and 6 GiB free
  disk. This path uses CPU, not CUDA; renting a GPU is unnecessary.
- macOS: Apple Silicon, macOS 14+, Swift 6, 8 GB unified memory, 6 GiB free
  disk, and a signed-in desktop session. This path uses Apple MPS.
- Windows, Linux ARM, Intel Macs, and older distributions are not validated
  targets. Use a supported machine rather than bypassing the preflight checks.

Install Git first. Linux also needs system Python 3, curl, CA certificates,
GNU coreutils and tar. On a minimal Ubuntu image, an administrator can install
these with `sudo apt-get update` followed by
`sudo apt-get install git python3 curl ca-certificates coreutils tar`.
On macOS install Apple's Command Line Tools (`xcode-select --install`) if
missing. The project bootstrap installs its pinned Python locally, without
replacing the system Python.

Initial setup needs HTTPS access to GitHub/release assets, PyPI, the PyTorch
CPU wheel index (Linux), and Hugging Face/model storage. Budget additional
space for repeated evidence bundles and time for first-time downloads.

## Choose the source explicitly

For current fixes and ordinary regression runs:

```sh
git clone https://github.com/ALLPROTO/core-lm-benchmark.git
cd core-lm-benchmark
git rev-parse HEAD
git status --porcelain=v1 --untracked-files=all
./corelm --help
```

Save the printed commit ID **outside** the clone. `main` moves; include this ID
in any reproduction report. The status command must print nothing. Use a real
Git clone, not GitHub's Download ZIP. Do not store notes, logs, virtualenvs or
results inside the checkout. A later run of an exact known commit can use
`git checkout --detach <saved-commit-id>` in a fresh clone.

For the exact published v15 demo, instead detach the immutable release source:

```sh
git checkout --detach corelm-portfolio-v15
git rev-parse HEAD
```

Expected commit: `d3782b887cc07bee8074cccab79981c6d21767c6`.
See [v15 release assets](https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/corelm-portfolio-v15)
for its source, evidence, and reproduction instructions. An immutable tag does
not receive later fixes. On that historical Linux source, the bootstrap may
print PASS yet return status 1 on reuse; use current source for the corrected
bootstrap, or explicitly select the already-verified exact interpreter with
`CORELM_LINUX_PYTHON` as documented in the Linux guide. Never ignore a failed
hash, ownership, runtime-identity, or evidence check.

Independent-human replication has additional signed-tag and prospective
attestation requirements: follow [its guide](INDEPENDENT_REPLICATION.md)
instead. An AI-assisted run cannot satisfy that human independence requirement.

## Linux: build, run, inspect

From the clean clone, run each command only after the preceding one succeeds:

```sh
./corelm linux bootstrap
./corelm linux doctor
./corelm linux build
./corelm linux run
```

The runner prints the output directory, normally a unique directory beneath
`~/.cache/corelm/linux/runs/`. Inspect `run-manifest.json` for `metricVerdict`,
`compressionRatioVsBF16`, `deltaNLLNatPerToken`, and `top1Agreement`.
`verification.txt` records the separate raw-evidence verifier. Preserve the
**entire directory**, including 192 containers, 1,024 decisions and
`SHA256SUMS`, not just a screenshot or PASS line. Check its file hashes with
`(cd /absolute/path/to/run && sha256sum -c SHA256SUMS)`.

A completed process and a scientific metric PASS are different claims. Read
the metric verdict. Small numerical differences across CPU/MPS environments
are expected; do not require exact equality to the README's rounded values.
See [Linux details](../platforms/linux/README.md) for destination overrides,
lock verification, retained artifacts and the historical measured reference.

## macOS: build and prove

```sh
./corelm macos bootstrap
./corelm macos doctor
./corelm macos proof
```

The proof builds `dist/CoreLMBenchmark.app`, applies a local ad-hoc signature,
runs real Qwen and verifies/replays evidence. No paid Apple certificate is
needed. Retain the output and runtime paths printed by the proof: the app is
bound to that runtime. See the [macOS walkthrough](../platforms/macos/BUILD_AND_VERIFY.md)
for output files, offline preparation and cleanup.

## Troubleshooting and reporting

- **Wrong Python:** exact 3.12.13 is intentional. Use the pinned bootstrap;
  do not silently substitute another patch version or edit the locks.
- **Dirty checkout:** use `git status` and a new clone. Do not discard local
  work just to make the check pass.
- **Rejected directories:** use private, canonical, disjoint destinations
  outside the clone. Do not disable ownership or symlink checks.
- **Downloads fail:** check the endpoint/network and retry setup. Do not
  remove hashes, install unpinned replacements, or disable TLS verification.
- **Interrupted run:** keep its logs; the next ordinary regression gets a new
  output directory. Do not overwrite evidence or restart a historical one-shot.
- **Metric FAIL:** preserve and report it, with source commit, OS/architecture,
  command and verifier output. Do not tune the registered public run to hide it.

After building the locked runtime, `./corelm verify` runs repository tests.
These tests are not a fresh real-model measurement. Before posting logs in a
[GitHub issue](https://github.com/ALLPROTO/core-lm-benchmark/issues), remove
credentials, personal paths and host identifiers; share only the necessary
failure context. Do not claim a supported platform passed if it was not run.

## Maintained dependencies versus release replay

The development branch uses separately maintained runtime locks and fresh runtime
directories. Signed historical releases keep their original dependency bytes and
may include known vulnerabilities. See [dependency maintenance](DEPENDENCY_MAINTENANCE.md)
for exact scope, validation status, and why old numerical results do not validate
a new dependency environment.
