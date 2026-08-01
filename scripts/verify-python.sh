#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
PYTHON_BIN=${PYTHON_BIN:-python3}
case "$PYTHON_BIN" in
    /*) PYTHON_EXECUTABLE=$PYTHON_BIN ;;
    *) PYTHON_EXECUTABLE=$(command -v "$PYTHON_BIN" 2>/dev/null || true) ;;
esac
[ -n "$PYTHON_EXECUTABLE" ] && [ -x "$PYTHON_EXECUTABLE" ] || {
    printf 'TEST GATE FAIL: Python executable is missing: %s\n' \
        "$PYTHON_BIN" >&2
    exit 1
}
PYTHON_CACHE=$(mktemp -d "${TMPDIR:-/tmp}/corelm-test-pycache.XXXXXX")
TEST_TMP="$PYTHON_CACHE/tmp"
/bin/mkdir -m 700 "$TEST_TMP"

cleanup() {
    rm -rf "$PYTHON_CACHE"
}
trap cleanup EXIT

if [ "$#" -eq 0 ]; then
    set -- \
        Tests.test_app_real_llm_evidence \
        Tests.test_beacon_launch_runbook \
        Tests.test_beacon_protocol \
        Tests.test_build_provenance \
        Tests.test_local_app_build \
        Tests.test_platform_boundaries \
        Tests.test_real_llm \
        Tests.test_security_supply_chain \
        Tests.test_swift_security_gate \
        Tests.test_voidtoken_v5 \
        Tests.test_voidtoken_v5_development \
        Tests.test_voidtoken_v5_frozen
fi

cd "$SCRIPT_DIR"
/usr/bin/env -i \
    HOME="$HOME" \
    TMPDIR="$TEST_TMP" \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    LANG=C \
    LC_ALL=C \
    "$PYTHON_EXECUTABLE" -I -B -X "pycache_prefix=$PYTHON_CACHE" \
    -c '
import pathlib
import sys
import unittest

root = pathlib.Path(sys.argv[1]).resolve(strict=True)
sys.path.insert(0, str(root))
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[2:])
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
' \
    "$SCRIPT_DIR" \
    "$@"
