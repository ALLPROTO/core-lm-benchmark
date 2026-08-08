#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
if [ "${PYTHON_BIN+x}" = x ]; then
    PYTHON_REQUEST=$PYTHON_BIN
else
    case "$(/usr/bin/uname -s)" in
        Darwin)
            PLATFORM_RUNTIME=${CORELM_REAL_LLM_VENV:-"$HOME/.cache/corelm/macos/runtime"}
            ;;
        Linux)
            PLATFORM_RUNTIME=${CORELM_LINUX_RUNTIME:-"$HOME/.cache/corelm/linux/runtime"}
            ;;
        *) PLATFORM_RUNTIME= ;;
    esac
    if [ -n "$PLATFORM_RUNTIME" ] && [ -x "$PLATFORM_RUNTIME/bin/python" ]; then
        PYTHON_REQUEST=$PLATFORM_RUNTIME/bin/python
    else
        PYTHON_REQUEST=python3
    fi
fi
case "$PYTHON_REQUEST" in
    /*) PYTHON_EXECUTABLE=$PYTHON_REQUEST ;;
    *) PYTHON_EXECUTABLE=$(command -v "$PYTHON_REQUEST" 2>/dev/null || true) ;;
esac
[ -n "$PYTHON_EXECUTABLE" ] && [ -x "$PYTHON_EXECUTABLE" ] || {
    printf 'TEST GATE FAIL: Python executable is missing: %s\n' \
        "$PYTHON_REQUEST" >&2
    exit 1
}
PYTHON_VERSION=$(
    "$PYTHON_EXECUTABLE" -I -B -c \
        'import platform; print(platform.python_version())'
)
[ "$PYTHON_VERSION" = 3.12.13 ] || {
    printf '%s\n' \
        "TEST GATE FAIL: Python 3.12.13 is required; found $PYTHON_VERSION at $PYTHON_EXECUTABLE" \
        'Build the platform runtime first or set PYTHON_BIN to its exact interpreter.' >&2
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
        Tests.test_beacon_publication_audit \
        Tests.test_beacon_protocol \
        Tests.test_build_provenance \
        Tests.test_independent_replication \
        Tests.test_linux_runtime_hardening \
        Tests.test_local_app_build \
        Tests.test_platform_boundaries \
        Tests.test_portfolio_release \
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
