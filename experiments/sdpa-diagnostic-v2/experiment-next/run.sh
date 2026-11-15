#!/bin/bash
set -euo pipefail
cd /workspace/corelm-modern-study-20261112
export HF_HOME="$PWD/hf-cache" HF_HUB_DISABLE_TELEMETRY=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false CUBLAS_WORKSPACE_CONFIG=:4096:8 TRITON_CACHE_DIR="$PWD/triton-cache"
for stage in probe quality matrix; do
 extra=()
 if [ "$stage" = matrix ]; then
 extra=(--quality-root "$PWD/inplace-quality" --probe-root "$PWD/inplace-probe" --monitor "$PWD/prepared-matrix/instrumentation/lifecycle_monitor.py" --uuid "$(nvidia-smi --query-gpu=uuid --format=csv,noheader | head -1)" --interval-ms 1)
 fi
 timeout --kill-after=30s 2400 runtime/bin/python prepared-matrix/implementation/benchmark_inplace.py "$stage" --model qwen05 --length 4096 --registry "$PWD/prepared-matrix/registry.json" --out "$PWD/inplace-$stage" "${extra[@]}"
 echo "STAGE_DONE $stage $(date -u +%FT%TZ)"
done
