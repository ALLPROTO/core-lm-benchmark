#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}
PYTHON_CACHE=$(mktemp -d "${TMPDIR:-/tmp}/corelm-test-pycache.XXXXXX")

cleanup() {
    rm -rf "$PYTHON_CACHE"
}
trap cleanup EXIT

"$PYTHON_BIN" -B -X "pycache_prefix=$PYTHON_CACHE" \
    -m unittest discover -s "$SCRIPT_DIR/Tests" -p 'test_*.py' -v
