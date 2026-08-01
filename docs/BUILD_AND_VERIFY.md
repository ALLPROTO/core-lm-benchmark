# Build and verify on your Mac

This is the ordinary-user path from a fresh public clone to a locally verified
macOS application.

## Requirements

- Apple Silicon (`arm64`).
- macOS 14 or newer.
- Python 3.12 from a trusted owner-controlled installation.
- Swift 6 or newer from Apple's free Command Line Tools or Xcode
  (`xcode-select --install`). Older Command Line Tools are insufficient for the
  Swift security test gate even if they can compile part of the application.
- An active macOS desktop login belonging to the user running the command. A
  headless SSH or CI session cannot execute the visible proof.
- At least 8 GB of unified memory. Close memory-heavy applications before the
  two sequential Qwen stages; the proof fails safely instead of swapping the
  Mac into an unresponsive state.
- At least 6 GiB free for the Python runtime, model assets, caches, and build.
- Network access for each fresh package runtime and the first asset
  preparation, unless the offline inputs described below have been prepared.

The Qwen model name contains its upstream model revision family. That is the
identity of the measured input, not the version of Core LM Benchmark.

No Apple Developer Program membership, paid certificate, Developer ID
identity, notarization, or paid Apple license is required. The locally built
application is ad-hoc signed and verified on the same Mac.

## One-command proof

Clone the source, then run the filesystem read-only doctor. Its HTTPS probes
transfer no package, model, or dataset files:

```sh
git clone https://github.com/ALLPROTO/core-lm-benchmark.git
cd core-lm-benchmark
./doctor.sh
```

It checks macOS and CPU compatibility, Swift 6, signing tools, a trusted Python
3.12 chain, free disk space, the active GUI login, required macOS utilities, and
the package/model endpoints. A failure occurs before the roughly gigabyte-scale
runtime or model downloads begin.

Then run:

```sh
./run_local_app_proof.sh
```

If Python is installed under another command name, resolve it explicitly:

```sh
CORELM_BOOTSTRAP_PYTHON="$(command -v python3.12)" \
  ./run_local_app_proof.sh
```

The resolver first checks the repository's owner-local location, then standard
python.org, Homebrew, and PATH locations. For a machine without Python 3.12,
the repository provides an opt-in bootstrap:

```sh
./bootstrap_python312_macos.sh
./doctor.sh
```

It downloads the immutable Astral `python-build-standalone` CPython 3.12.13
build `20260718` Apple Silicon archive. The registered archive SHA-256 is:

```text
62aeee6161d57303a71a138b75fd5cc6fb8c89c4b1d9c7f0a052d89fa0b6652b
```

The script verifies that digest before extraction,
rejects unsafe paths, escaping links, and special archive entries, and installs
it at `~/.local/share/corelm/python-3.12.13`. No `sudo`, package installer, or
system Python modification is used. This is an explicitly disclosed third-party
binary bootstrap artifact rather than a Python Software Foundation macOS
installer. The final application's signed manifest covers every loadable file
in both this base runtime and the proof virtual environment. To revalidate and
remove group/world write permissions from that exact existing local copy:

```sh
./bootstrap_python312_macos.sh --harden-installed
```

The proof deliberately creates a new runtime under
`~/.cache/corelm-proof-runtimes/` and retains it for audit. Model and dataset
assets are stored under `~/.cache/corelm-model-assets/` after their registered
sizes and SHA-256 digests have been checked.

This command verifies the current public checkout. Exact reproduction of a
frozen publication additionally requires checking out its recorded release tag
and validating the archive checksums; see the
[reproducibility archive instructions](../publication/reproducibility/README.md).

## What happens

1. The script checks the operating system, architecture, Swift toolchain,
   signing utility, Python interpreter, and available proof paths.
2. A fresh isolated Python runtime is created.
3. Hash-locked packages are installed and the complete installed distribution
   set is verified.
4. The exact pinned model and dataset files are downloaded and verified.
5. Offline resolution is tested before the app is packaged.
6. The release application is built and locally ad-hoc signed.
7. Python and Swift regression/security gates run.
8. The visible application executes the pinned Qwen compression workload on
   fixed public validation blocks 64–71 using Apple MPS.
9. A random challenge binds the trusted-local invocation to the new receipt so
   an older local run is not selected accidentally.
10. The app retains all 192 raw containers, the full source token slices, and
    per-token baseline/candidate losses and top-1 IDs in the run directory.
11. An independent standard-library verifier parses those container bytes,
    recomputes compression/NLL/top-1, and checks the result, receipt, app
    executable, bundled runner, Python executable, and runtime manifest.
12. A separate heavyweight clean-room decoder retokenizes pinned WikiText,
    rebuilds baseline and decoded candidate caches, and reruns all 1,024 Qwen
    decisions sequentially on MPS. Top-1 IDs must match exactly and every loss
    must match within absolute tolerance `2e-5` or relative tolerance `2e-6`.

A successful run ends with:

```text
END-TO-END PROOF PASS
```

The application is located at:

```text
dist/CoreLMBenchmark.app
```

The fresh result and receipt are written below:

```text
~/Library/Application Support/CoreLMBenchmark/real-llm-results/
```

## Build without the automatic real-model run

```sh
./build_local_app.sh
open dist/CoreLMBenchmark.app
```

The reusable manual-build runtime is stored at
`~/.cache/corelm-app-runtime/`. In the application, press **Run Compression
Proof** with fixed public validation blocks 64–71 shown in the toolbar. This
range has been exercised repeatedly and is an application-regression fixture,
not blind or held-out input.

A manual run proves internal consistency. The one-command workflow is stronger
operationally because it creates a challenge after its run marker and rejects a
receipt that does not contain that exact value. This guards against accidental
reuse on the trusted local Mac; it is not cryptographic proof to a remote
auditor that the unsigned, ad-hoc receipt was created after the command began.
A malicious local user can edit both a receipt and its nonce. Remote freshness
would require an independently trusted signature or attestation channel.

Only one full proof may run for a user at a time. The script holds a stale-aware
lock below `~/.cache/corelm-proof-runtimes/` before creating a runtime. This
prevents two applications from racing over the shared result and build paths.

Another observer may supply the challenge instead of using the local random
number generation. It must be exactly 64 lowercase hexadecimal characters and
is passed unchanged into the application receipt; this still provides only
trusted-local stale-run binding, not remote freshness:

```sh
CORELM_PROOF_CHALLENGE=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  ./run_local_app_proof.sh
```

Every execution of this command evaluates the same public blocks 64–71.
Multiple executions are regression/repeatability checks of the app and
evidence pipeline, not independent scientific experiments. They cannot support
a new blind, holdout, or generalization claim.

## Prepare and use the offline path

While connected, run:

```sh
./prepare_offline_inputs.sh
```

This command downloads only binary wheels named by the two lock files, verifies
their registered hashes, immediately installs from that wheelhouse with
`--no-index`, and downloads and digest-verifies the pinned model and validation
data. The default locations are:

```text
~/.cache/corelm-wheelhouse/
~/.cache/corelm-model-assets/
```

Disconnect the network if desired, then create a fresh runtime and run the real
application proof entirely from those inputs:

```sh
CORELM_OFFLINE=1 \
CORELM_WHEELHOUSE="$HOME/.cache/corelm-wheelhouse" \
  ./run_local_app_proof.sh
```

Offline mode fails closed when either directory is missing or unsafe. Package
installation uses `--no-index --only-binary=:all: --require-hashes`; model and
dataset resolution uses local-only mode and repeats the registered size and
SHA-256 checks. It is not a flag that skips dependency or asset verification.

To store wheels elsewhere, use an absolute, non-symlinked, owner-controlled
directory for `CORELM_WHEELHOUSE` during both preparation and proof.

## HTTPS mirrors

Connected builds may use HTTPS-compatible mirrors:

```sh
CORELM_PYPI_INDEX_URL=https://pypi.example/simple \
CORELM_HF_ENDPOINT=https://huggingface.example \
  ./run_local_app_proof.sh
```

URLs containing inline credentials, query strings, fragments, or non-HTTPS
schemes are rejected. Python packages must still match every lock-file hash;
model and dataset files must still match the registered revision, size, and
SHA-256. `--isolated` prevents ambient pip configuration from silently changing
the selected index. The proof deliberately starts build and replay processes
with a minimal environment, so ambient proxy, credential, and custom-CA
variables are not inherited. If an organization requires those settings, use
them only while running `./prepare_offline_inputs.sh` on the approved network,
then run the proof with `CORELM_OFFLINE=1`; do not place secrets in endpoint
variables or command history.

## Expected duration

The first build downloads roughly 1 GB of model/data assets and installs a
separate machine-learning runtime. Network and CPU speed dominate setup time.
The visible application run and the subsequent independent heavy replay each
have their own five-minute hard safety limit. Later manual builds can reuse
verified assets; the full proof still creates a new Python runtime by design.

## Mac safety limits

The worker runs at utility quality of service with CPU library thread counts
limited to two. PyTorch MPS allocation watermarks are capped below the default,
the app stops the worker on critical macOS memory pressure, and the outer proof
script independently stops it if system free memory falls below 15%. The app
run and independent heavy replay each enforce a 300-second limit and terminate
their process group if a limit is reached. A safety stop is a failed proof; it
never produces a PASS receipt.

## Boundary for a future prospective experiment

Do not use `run_local_app_proof.sh` or blocks 64–71 to claim a new blind result.
A separate future protocol must first publish its exact commit, source and
configuration digests, parameters, gates, a pool for which the audited public
repository contains no metric result, and a deterministic selection rule tied
to a future public randomness beacon.
Only after that beacon is available may the selected window be resolved and run
once, without post-result tuning. A later regression is allowed only after
terminal `PASS` or `FAIL_GATES`; `FAIL_EXECUTION` or an incomplete attempt cannot
be retried. This repository does not claim a result from that future protocol.

## Cleanup

Each full proof prints the exact UUID-named runtime directory it created below
`~/.cache/corelm-proof-runtimes/`. When you no longer need to rerun or audit
that particular app build, move that specific directory to the Trash in
Finder. Do not remove the parent directory blindly: every retained app bundle
is bound to the exact runtime recorded when it was packaged and will stop
working if that runtime is removed.

The shared verified model assets under `~/.cache/corelm-model-assets/` may be
kept for later builds. Removing them is safe only if you accept downloading and
verifying them again.

## Troubleshooting

- **Python 3.12 is missing:** install a trusted Python 3.12 distribution and set
  `CORELM_BOOTSTRAP_PYTHON` to its absolute executable, or run the authenticated
  bootstrap above.
- **Swift is older than 6:** update Command Line Tools or select a newer Xcode
  with `xcode-select`.
- **The GUI check fails:** sign in at the Mac desktop and run the command from
  that same user, not from SSH or a background launch daemon.
- **A package/model endpoint is unreachable:** check HTTPS proxy and firewall
  policy, configure approved mirrors, or prepare the offline inputs while a
  trusted network is available.
- **Another proof is running:** wait for it to finish. The lock automatically
  replaces a stale PID after an interrupted or crashed process.
- **MPS is unavailable:** confirm the Mac is Apple Silicon and PyTorch can see
  the Apple MPS backend.
- **Command Line Tools are missing:** run `xcode-select --install`.
- **A runtime path is rejected:** do not reuse or manually modify a proof
  runtime. Run the proof again so it creates a fresh directory.
- **A digest check fails:** remove only the affected model cache through a
  recoverable operation, then let the asset preparer download it again. Do not
  bypass the registered digest.

For security details, see [Security policy](../SECURITY.md). For the exact claim
boundary, see [Limitations](LIMITATIONS.md).
