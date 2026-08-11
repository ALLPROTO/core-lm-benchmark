# Run the complete Linux regression on RunPod

This guide runs the repository's complete Linux CPU contour in a RunPod
Secure Cloud managed Docker container: bootstrap the pinned Python, build the
hash-locked runtime, verify the pinned model and dataset assets, execute the
real `Qwen/Qwen2.5-0.5B` validation regression, and verify the retained raw
evidence.

This is a CPU-only public-validation regression. Selecting a GPU for the pod
does not make this contour a GPU run: the Linux lock installs PyTorch CPU
wheels and the runner fixes `--device cpu`. A RunPod pod is also a container,
not the booted hardware VM required by `verify-vm-host.sh`.

## Prepare the pod and private paths

Use an Ubuntu 24.04 x86_64 image with at least 8 GiB available memory and 6
GiB free disk. A larger allowance is useful while downloads and evidence
coexist. Start from a fresh, exact Git clone and keep the checkout clean; the
runner refuses tracked modifications and untracked files.

RunPod's pod volume can survive a stop/restart of the same pod, but it is
deleted when the pod is terminated. Use a network-volume mount if the runtime,
model cache, or evidence must survive termination. For a cold root, require
that the destination is absent, create it owner-only, and resolve it to its
physical absolute path before exporting the three disjoint destinations. This
example uses ephemeral home storage; replace it with the canonical network-
volume path when persistence is required:

```sh
CORELM_E2E_ROOT="$HOME/corelm-e2e"
test ! -e "$CORELM_E2E_ROOT"
install -d -m 700 "$CORELM_E2E_ROOT"
CORELM_E2E_ROOT=$(CDPATH= cd -- "$CORELM_E2E_ROOT" && pwd -P)

export CORELM_LINUX_RUNTIME="$CORELM_E2E_ROOT/runtime"
export CORELM_LINUX_HF_HOME="$CORELM_E2E_ROOT/model-assets"
export CORELM_RUN_DIR="$CORELM_E2E_ROOT/run-cold-001"
```

Do not put any destination inside the source checkout. Each value must be a
canonical absolute path with no symlink or `..` alias. The destinations must
not exist as unsafe shared paths, overlap one another, or be group/world
writable. `CORELM_RUN_DIR` must name a new path for every run.

The default Python bootstrap lives below `$HOME/.local/share/corelm/`. A new
pod can reuse a persisted runtime only if that exact owner-local bootstrap is
also present and its receipt still verifies, or if
`CORELM_LINUX_PYTHON=/absolute/path/python3.12` names the same trusted Python
3.12.13 installation used to build it. Persisting only the virtual environment
is not sufficient.

## Cold build and first real-model run

Run these commands from the repository root:

```sh
./corelm linux bootstrap
./corelm linux doctor
./corelm linux build
CORELM_OFFLINE=1 ./corelm linux run
```

`bootstrap` and the first `build` require network access. The build downloads
only the registered, hash-checked Python wheels, Qwen revision, and WikiText
validation asset. The final command revalidates the prepared runtime and
assets with `CORELM_OFFLINE=1`, then executes Qwen locally with Hugging Face
and Transformers offline flags. `CORELM_OFFLINE=1` is an application control,
not proof that the container had no network interface; enforce a pod-level
network boundary separately if that stronger property is required.

A successful run ends with `LINUX REAL-QWEN REGRESSION PASS` and leaves the
evidence at the exact `CORELM_RUN_DIR`. It contains 192 raw cache containers,
1,024 token decisions, `validation-064-071.json`, `run-manifest.json`,
`primary-evidence/`, logs, environment facts, and `SHA256SUMS`.

## Warm and offline reruns

Never reuse a completed run directory. For a warm rerun in the same pod, keep
the verified runtime and asset cache and choose a new evidence path:

```sh
export CORELM_RUN_DIR="$CORELM_E2E_ROOT/run-warm-002"
./corelm linux doctor
CORELM_OFFLINE=1 ./corelm linux run
```

To test the complete cached build boundary before another offline inference,
again use a new run path:

```sh
export CORELM_RUN_DIR="$CORELM_E2E_ROOT/run-offline-003"
CORELM_OFFLINE=1 ./corelm linux build
CORELM_OFFLINE=1 ./corelm linux run
```

A truly cold offline build is intentionally unsupported: the exact Python
bootstrap, locked wheel closure, model bytes, and dataset bytes must already be
present and valid. Terminating a pod deletes its pod volume; only a separately
attached network volume can retain those prerequisites across termination.

## Verify and retain the evidence

The runner invokes both checks before reporting PASS. Run them again after a
copy or download to verify the retained directory at its new location:

```sh
"$CORELM_LINUX_RUNTIME/bin/python" -I -B \
  security/verify_primary_evidence.py "$CORELM_RUN_DIR"
(
  cd "$CORELM_RUN_DIR"
  sha256sum -c SHA256SUMS
)
```

The separate verifier should report `PRIMARY EVIDENCE PASS: 192 raw
containers and 1024 token decisions independently agree.` The checksum command
must report every listed file as `OK`.

For an audit, retain the complete run directory rather than only the terminal
metrics. At minimum, record these `run-manifest.json` fields:

- `schemaVersion`, `evidenceClass`, and `countsTowardScientificVerdict`;
- `modelExecuted`, `testDataOpened`, and `beaconExecuted`;
- `sourceCommit`, `resultSHA256`, and `selectedTokenIdsSHA256`;
- `containerCount` and `predictionTokens`;
- `compressionRatioVsBF16`, `deltaNLLNatPerToken`, `top1Agreement`, and
  `metricVerdict`.

Also retain `environment.txt`, `pre-run-contract.json`, `command.txt`,
`runner-exit-code.txt`, `verification.txt`, `end-time.txt`, the complete
`primary-evidence` tree, and `SHA256SUMS`. Record the container image by digest
before execution if an image-hermetic claim matters; an image tag alone is
mutable.

## Scope of the claim

This command executes one complete registered model profile: the pinned Qwen
checkpoint on already-public WikiText validation blocks 64–71. It does not run
every metadata adapter listed by `./corelm models list`; those entries do not
load weights and have no inherited Qwen PASS verdict. The output is not a new
blind result, independent replication, GPU result, or VM-portability result.

See the [recorded 2026-08-11 RunPod execution](RECORDED_RUN_2026-08-11_RUNPOD.md)
for one author-operated audit record and its exact limitations.
