# Real Qwen regression on Linux

This workflow runs the real pinned `Qwen/Qwen2.5-0.5B` model on the registered
WikiText validation data in an Ubuntu 24.04 x86_64 VM. It is an environmental
repeatability check of public validation blocks 64-71 and candidate 32.

It is **regression-only**. It is not blind, held out, prospective, or eligible
to support a new generalization claim. It does not execute or consume the
beacon one-shot.

## GitHub-hosted VM

Run the `Real Qwen Linux CPU Regression` workflow manually. The workflow:

1. checks out source commit
   `aaae33c744fe1b384877079c600fe4833966e74a`;
2. builds a dedicated Python 3.12.13 environment from the hash-complete
   Ubuntu CPU locks, including the official PyTorch CPU-only wheel;
3. downloads and digest-verifies only the pinned model and real validation
   parquet, then proves both resolve offline;
4. executes eight real Qwen blocks on CPU;
5. retains 192 `.vtl5` containers and 1,024 per-token decisions;
6. independently verifies the raw evidence with the standard-library verifier;
7. uploads the result, logs, environment, run contract, and `SHA256SUMS` as one
   immutable Actions artifact for that run attempt.

The workflow has read-only repository permissions. It writes all model assets
and evidence under the ephemeral runner directory, never into a scientific
result channel in the checkout.

## Equivalent command in another Linux VM

Use Ubuntu 24.04 x86_64 with Python 3.12.13, at least 8 GiB available memory,
and at least 6 GiB free disk after installing the locked runtime. Prepare the
pinned assets online and prove offline reuse before inference:

The Linux runtime is the union of
`.github/locks/real-llm-linux-cpu-py312.txt` and
`.github/locks/torch-linux-cpu-py312.txt`. The latter must be installed only
from `https://download.pytorch.org/whl/cpu`; both installs retain
`--require-hashes`, `--only-binary=:all:`, and `--no-deps`.

```sh
export HF_HOME=/absolute/private/corelm-real-qwen-cache
export CORELM_RUN_DIR=/absolute/private/corelm-linux-cpu-regression
install -d -m 700 "$HF_HOME" "$CORELM_RUN_DIR"

python -I -B RealLLM/prepare_app_assets.py --cache "$HF_HOME"
python -I -B RealLLM/prepare_app_assets.py \
  --cache "$HF_HOME" --offline-only
```

Then disconnect model/data resolution from the network and execute the fixed
regression without changing its range or candidate:

```sh
HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 \
TOKENIZERS_PARALLELISM=false \
OMP_NUM_THREADS=2 \
OPENBLAS_NUM_THREADS=2 \
MKL_NUM_THREADS=2 \
NUMEXPR_NUM_THREADS=2 \
python -I -B RealLLM/develop_voidtoken_v5.py \
  --device cpu \
  --validation-start-block 64 \
  --validation-blocks 8 \
  --candidate-index 32 \
  --local-files-only \
  --output "$CORELM_RUN_DIR/validation-064-071.json" \
  --primary-evidence-directory "$CORELM_RUN_DIR/primary-evidence"

python -I -B security/verify_primary_evidence.py "$CORELM_RUN_DIR"
```

The required source-token digest is
`1bb36c91d441379596361ae779ca0542c85457e9902a290a6ab6945cb2513453`.
A complete run contains exactly 192 containers and 1,024 token decisions, and
its result has `testDataOpened: false`.

CPU values need not be bit-identical to Apple MPS values. Report the observed
metrics without tuning, and never describe this run as a new scientific
one-shot.

## Recorded Linux CPU regression

The first complete public Linux CPU execution finished on 2026-08-01:

- [workflow run 30710142923](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30710142923)
  and [job 91396042691](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30710142923/job/91396042691);
- workflow commit
  `177cd53b595f15614b40c724c74ce8da0630e06b`;
- exact benchmark source commit
  `aaae33c744fe1b384877079c600fe4833966e74a`, tree
  `ec7087bb88a024a65ea90ec6171d8e48e7fd00ed`;
- Python 3.12.13, Torch 2.13.0+cpu, x86_64 Ubuntu 24.04 runner;
- eight real blocks, 1,024 predictions, and 192 retained containers;
- compression `2.052389237x`, delta NLL `+0.0000223219`, top-1 agreement
  `99.609375%`, all three registered gates `PASS`;
- result SHA-256
  `9575998655ba2dc728f0856ba16d34fa9cbe23f918d3cc4155c5f898cebc5ada`;
- selected-token SHA-256
  `1bb36c91d441379596361ae779ca0542c85457e9902a290a6ab6945cb2513453`;
- [Actions artifact 8821614426](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30710142923/artifacts/8821614426),
  ZIP SHA-256
  `d618ee6addad3d62d2d9db479d6c7f2f737fa30ba9491322b1f17f7a0172c4ef`.

The model execution took 54.08 seconds and reached 3,380,064 KiB maximum
resident memory. The independent verifier recomputed the result from the raw
artifact and reported `PRIMARY EVIDENCE PASS: 192 raw containers and 1024 token
decisions independently agree.` The run manifest records
`countsTowardScientificVerdict: false`, `testDataOpened: false`, and
`beaconExecuted: false`.

Three preceding workflow attempts are retained rather than hidden:

- [30709855291](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30709855291)
  failed workflow validation before a VM job existed;
- [30709905602](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30709905602)
  stopped at hash-locked dependency resolution before model/data preparation;
- [30710067688](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30710067688)
  stopped because the separate Linux locks were not present in the exact
  source checkout, again before model/data preparation.

None of those three setup attempts executed Qwen or opened model-evaluation
data. They are engineering failures, not model results and not scientific
attempts.
