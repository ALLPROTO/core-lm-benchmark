#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}

cd "$SCRIPT_DIR"
exec "$PYTHON_BIN" RealLLM/benchmark_real_llm.py "$@"
