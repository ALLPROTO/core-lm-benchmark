#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}
PYTHON_CACHE=$(mktemp -d "${TMPDIR:-/tmp}/corelm-test-pycache.XXXXXX")

cleanup() {
    rm -rf "$PYTHON_CACHE"
}
trap cleanup EXIT

cd "$SCRIPT_DIR"
"$PYTHON_BIN" -B -X "pycache_prefix=$PYTHON_CACHE" \
    -m unittest -v \
    Tests.test_app_real_llm_evidence \
    Tests.test_local_app_build \
    Tests.test_real_llm \
    Tests.test_security_supply_chain \
    Tests.test_swift_security_gate \
    Tests.test_voidtoken_v5 \
    Tests.test_voidtoken_v5_development \
    Tests.test_voidtoken_v5_frozen
