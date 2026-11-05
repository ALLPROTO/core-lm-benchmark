# Clean-clone verification checklist

This checklist is the short, non-inference verification path for a reviewer.
It checks that a fresh public checkout can install the pinned core dependency
closure and run the repository's regression and supply-chain checks.

It is not a claim of independent scientific replication, a new model result,
or generalization beyond the registered workload. A full fresh model proof is a
separate, optional path at the end of this document.

## Scope and prerequisites

Use an Apple Silicon Mac with macOS 14 or later, Python 3.12, and Apple Command
Line Tools or Xcode. This core check does not download the model or dataset;
the optional full proof does.

Start from an empty working directory:

```sh
git clone https://github.com/ALLPROTO/core-lm-benchmark.git
cd core-lm-benchmark
git status --short
git rev-parse HEAD
```

`git status --short` must print nothing. Record the resulting commit ID in any
review note; it identifies the exact source bytes that were checked.

## Reproduce the core verification

Create a local environment, then install only the hash-locked macOS core
closure. Do not substitute unpinned packages or turn off hash checking.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install \
  --isolated --no-input --disable-pip-version-check --only-binary=:all: \
  --require-hashes -r .github/locks/pip-bootstrap.txt
.venv/bin/python -m pip install \
  --isolated --no-input --disable-pip-version-check --only-binary=:all: \
  --require-hashes -r .github/locks/core-macos-arm64-py312.txt
.venv/bin/python -m pip check
PYTHON_BIN="$PWD/.venv/bin/python" ./run_tests.sh
.venv/bin/python -I -B security/verify_supply_chain.py
.venv/bin/python -I -B security/generate_direct_sbom.py \
  --check security/direct-dependencies.cdx.json
.venv/bin/python -I -B security/osv_direct_audit.py \
  .github/locks/pip-bootstrap.txt \
  .github/locks/core-linux-py312.txt \
  .github/locks/core-macos-arm64-py312.txt \
  requirements.lock \
  RealLLM/requirements.lock
```

Expected signals are a successful `pip check`, an `OK` summary from
`run_tests.sh`, and `PASS` summaries from the supply-chain, SBOM, and OSV
checks. One test may be skipped when no local packaged application already
exists; that is expected on a new clone.

For Linux, resolve the matching
`.github/locks/core-linux-py312.txt` closure in a Linux Python 3.12
environment. Do not try to install the Linux lock on macOS: the lock correctly
contains Linux-specific wheel hashes and should fail closed on the wrong
platform.

## Optional full local proof

On the same supported Mac, the following path downloads and verifies the
registered assets, builds a local app, executes the pinned Qwen workload on
Apple MPS, and verifies a new challenge-bound receipt:

```sh
./run_local_app_proof.sh
```

Read [Build and verify](BUILD_AND_VERIFY.md) first. The full proof needs
network access during initial asset preparation, roughly 6 GB free disk space,
and can take materially longer than the core check. A PASS receipt is limited
to the pinned model, data, protocol, and machine; it does not establish an
arbitrary-model, serving, latency, or production claim.

## What to record

An external reviewer can share a concise, non-sensitive replication note:

- source commit ID and `git status --short` result;
- operating-system and Python 3.12 version;
- whether the core check and optional full proof passed, failed, or was not
  attempted;
- the complete command output or a redacted log containing no local paths,
  credentials, or model-cache identifiers;
- for a full proof only, the generated receipt digest and its stated limits.

Do not publish credentials, absolute home paths, unredacted environment
variables, or copied model files. A successful run by the repository author
or a reviewer is still evidence about that particular run; independent human
replication is stronger but remains a separate milestone.
