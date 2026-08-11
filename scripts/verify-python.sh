#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(/usr/bin/dirname -- "$0")/.." && pwd -P)
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
        printf '%s\n' \
            'TEST GATE FAIL: the managed platform runtime is unavailable; set PYTHON_BIN to its absolute interpreter path' >&2
        exit 1
    fi
fi
case "$PYTHON_REQUEST" in
    /*) ;;
    *)
        printf '%s\n' 'TEST GATE FAIL: PYTHON_BIN must be an absolute path' >&2
        exit 1
        ;;
esac
PYTHON_DIRECTORY=$(CDPATH= cd -- \
    "$(/usr/bin/dirname -- "$PYTHON_REQUEST")" && pwd -P) || {
    printf '%s\n' 'TEST GATE FAIL: Python executable directory is unavailable' >&2
    exit 1
}
PYTHON_EXECUTABLE="$PYTHON_DIRECTORY/$(/usr/bin/basename -- "$PYTHON_REQUEST")"
[ "$PYTHON_EXECUTABLE" = "$PYTHON_REQUEST" ] || {
    printf '%s\n' 'TEST GATE FAIL: PYTHON_BIN must be a canonical path' >&2
    exit 1
}
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
TEST_TMP_ROOT=${TMPDIR:-/tmp}
case "$TEST_TMP_ROOT" in
    /*) ;;
    *)
        printf '%s\n' 'TEST GATE FAIL: TMPDIR must be an absolute directory' >&2
        exit 1
        ;;
esac
TEST_TMP_ROOT=$(CDPATH= cd -- "$TEST_TMP_ROOT" && pwd -P) || {
    printf '%s\n' 'TEST GATE FAIL: TMPDIR is unavailable' >&2
    exit 1
}
case "$TEST_TMP_ROOT/" in
    "$SCRIPT_DIR/"|"$SCRIPT_DIR/"*)
        printf '%s\n' \
            'TEST GATE FAIL: test caches must be outside the source checkout' >&2
        exit 1
        ;;
esac
PYTHON_CACHE=$(/usr/bin/mktemp -d \
    "$TEST_TMP_ROOT/corelm-test-pycache.XXXXXX")
PYTHON_CACHE=$(CDPATH= cd -- "$PYTHON_CACHE" && pwd -P)
TEST_TMP="$PYTHON_CACHE/tmp"
/bin/mkdir -m 700 "$TEST_TMP"

cleanup() {
    /bin/rm -rf -- "$PYTHON_CACHE"
}
trap cleanup EXIT

if [ "$#" -eq 0 ]; then
    set -- \
        Tests.test_app_real_llm_evidence \
        Tests.test_automated_media \
        Tests.test_automated_portfolio_demo \
        Tests.test_automated_window_capture \
        Tests.test_beacon_launch_runbook \
        Tests.test_beacon_publication_audit \
        Tests.test_beacon_protocol \
        Tests.test_build_provenance \
        Tests.test_independent_replication \
        Tests.test_linux_runpod_documentation \
        Tests.test_linux_runtime_hardening \
        Tests.test_linux_vm_host \
        Tests.test_live_proof_events \
        Tests.test_local_app_build \
        Tests.test_macos_operator \
        Tests.test_model_compatibility \
        Tests.test_platform_boundaries \
        Tests.test_paper_v5_release_receipt \
        Tests.test_portfolio_demo_collector \
        Tests.test_portfolio_github_release \
        Tests.test_portfolio_python_launcher \
        Tests.test_portfolio_release \
        Tests.test_portfolio_tag_ci \
        Tests.test_real_llm \
        Tests.test_security_supply_chain \
        Tests.test_swift_security_gate \
        Tests.test_strict_git_checkout \
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
    PYTHONDONTWRITEBYTECODE=1 \
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
