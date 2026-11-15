#!/bin/bash
set -euo pipefail
DIAG_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/diagnostic-instrumentation
cd /workspace/corelm-modern-study-20261112
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUBLAS_WORKSPACE_CONFIG=:4096:8
UUID=$(nvidia-smi --query-gpu=uuid --format=csv,noheader | head -1)
# Instrumented diagnostic, NOT performance evidence. Bounded history; validate completeness.
timeout --kill-after=30s 600 runtime/bin/python "$DIAG_DIR/lifecycle_monitor.py" --uuid "$UUID" --output "$PWD/diagnostic-sdpa-allocation/physical" --allocator-history --history-max-entries 100000 --interval-ms 1 -- runtime/bin/python prepared-matrix/implementation/benchmark_matrix.py worker --registry "$PWD/prepared-matrix/registry.json" --out "$PWD/diagnostic-sdpa-allocation" --model qwen05 --length 4096 --mode sdpa --purpose memory --repeat 0
