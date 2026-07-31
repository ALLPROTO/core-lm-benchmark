# Build and verify on your Mac

This is the ordinary-user path from a fresh public clone to a locally verified
macOS application.

## Requirements

- Apple Silicon (`arm64`).
- macOS 14 or newer.
- Python 3.12 from a trusted owner-controlled installation.
- Apple's free Command Line Tools or Xcode (`xcode-select --install`).
- At least 6 GB free for the Python runtime, model assets, caches, and build.
- Network access during the first asset preparation.

The Qwen model name contains its upstream model revision family. That is the
identity of the measured input, not the version of Core LM Benchmark.

## One-command proof

```sh
git clone https://github.com/ALLPROTO/core-lm-benchmark.git
cd core-lm-benchmark
./run_local_app_proof.sh
```

If Python is not available as `python3.12`, provide its absolute path:

```sh
CORELM_BOOTSTRAP_PYTHON=/absolute/path/to/python3.12 \
  ./run_local_app_proof.sh
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
   Apple MPS.
9. A random challenge is bound into the new receipt.
10. An independent verifier checks the result, receipt, app executable, bundled
    runner, Python executable, and runtime manifest.

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
Proof** with the registered validation slice shown in the toolbar.

A manual run proves internal consistency. The one-command workflow is stronger
because its unpredictable challenge also proves that the receipt was created
after the command began.

## Expected duration

The first build downloads roughly 1 GB of model/data assets and installs a
separate machine-learning runtime. Network and CPU speed dominate setup time.
The visible real-model run can take up to ten minutes. Later manual builds can
reuse verified assets; the full proof still creates a new Python runtime by
design.

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
  `CORELM_BOOTSTRAP_PYTHON` to its absolute executable.
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
