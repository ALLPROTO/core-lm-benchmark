#!/bin/sh
set -eu

umask 077

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BOOTSTRAP_PYTHON=${CORELM_BOOTSTRAP_PYTHON:-python3.12}
RUNTIME_DIR=${CORELM_REAL_LLM_VENV:-"$HOME/.cache/corelm-app-runtime"}
CACHE_DIR="$HOME/.cache/corelm-model-assets"
BUILD_CONFIG=${BUILD_CONFIG:-release}
SKIP_RUNTIME_INSTALL=${CORELM_SKIP_RUNTIME_INSTALL:-0}
SKIP_ASSET_PREPARATION=${CORELM_SKIP_ASSET_PREPARATION:-0}
ASSETS_OFFLINE_ONLY=${CORELM_ASSETS_OFFLINE_ONLY:-0}
SKIP_MPS_CHECK=${CORELM_SKIP_MPS_CHECK:-0}
SKIP_SMOKE_TEST=${CORELM_SKIP_SMOKE_TEST:-0}
APP_PATH="$PROJECT_DIR/dist/CoreLMBenchmark.app"
PYTHON_CACHE=$(mktemp -d "${TMPDIR:-/tmp}/corelm-build-pycache.XXXXXX")

cleanup() {
    rm -rf "$PYTHON_CACHE"
}
trap cleanup EXIT

fail() {
    printf 'LOCAL APP BUILD FAIL: %s\n' "$*" >&2
    exit 1
}

require_boolean() {
    case "$2" in
        0|1) ;;
        *) fail "$1 must be 0 or 1" ;;
    esac
}

require_boolean CORELM_SKIP_RUNTIME_INSTALL "$SKIP_RUNTIME_INSTALL"
require_boolean CORELM_SKIP_ASSET_PREPARATION "$SKIP_ASSET_PREPARATION"
require_boolean CORELM_ASSETS_OFFLINE_ONLY "$ASSETS_OFFLINE_ONLY"
require_boolean CORELM_SKIP_MPS_CHECK "$SKIP_MPS_CHECK"
require_boolean CORELM_SKIP_SMOKE_TEST "$SKIP_SMOKE_TEST"

[ "$(uname -s)" = "Darwin" ] || fail "macOS is required"
[ "$(uname -m)" = "arm64" ] || fail "Apple Silicon (arm64) is required"

macos_version=$(sw_vers -productVersion)
macos_major=${macos_version%%.*}
case "$macos_major" in
    ''|*[!0-9]*) fail "could not determine the macOS version" ;;
esac
[ "$macos_major" -ge 14 ] || fail "macOS 14 or newer is required"

command -v swift >/dev/null 2>&1 \
    || fail "Swift is missing; run xcode-select --install"
command -v codesign >/dev/null 2>&1 \
    || fail "codesign is missing; run xcode-select --install"

bootstrap_path=$(command -v "$BOOTSTRAP_PYTHON" 2>/dev/null || true)
[ -n "$bootstrap_path" ] \
    || fail "Python 3.12 is missing; set CORELM_BOOTSTRAP_PYTHON"
"$bootstrap_path" -I -B -X "pycache_prefix=$PYTHON_CACHE" -c '
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit("CORELM_BOOTSTRAP_PYTHON must be Python 3.12")
'

case "$RUNTIME_DIR" in
    /*) ;;
    *) fail "CORELM_REAL_LLM_VENV must be an absolute path" ;;
esac
runtime_state=$(
    "$bootstrap_path" -I -B -X "pycache_prefix=$PYTHON_CACHE" \
        "$PROJECT_DIR/security/manage_local_runtime.py" \
        --path "$RUNTIME_DIR" \
        --project "$PROJECT_DIR" \
        --mode preflight
) || fail "dedicated Python runtime path failed validation"
case "$runtime_state" in
    new|existing) ;;
    *) fail "dedicated Python runtime preflight returned an invalid state" ;;
esac

if [ "$SKIP_RUNTIME_INSTALL" = "0" ]; then
    if [ "$runtime_state" = "new" ]; then
        printf 'Creating the dedicated Python runtime at %s\n' "$RUNTIME_DIR"
        "$bootstrap_path" -I -B -X "pycache_prefix=$PYTHON_CACHE" \
            -m venv "$RUNTIME_DIR"
        "$bootstrap_path" -I -B -X "pycache_prefix=$PYTHON_CACHE" \
            "$PROJECT_DIR/security/manage_local_runtime.py" \
            --path "$RUNTIME_DIR" \
            --project "$PROJECT_DIR" \
            --mode initialize >/dev/null \
            || fail "new dedicated Python runtime failed initialization"
    fi
    "$RUNTIME_DIR/bin/python" -I -B -X \
        "pycache_prefix=$PYTHON_CACHE" -m pip install \
        --isolated \
        --no-input \
        --disable-pip-version-check \
        --only-binary=:all: \
        --index-url https://pypi.org/simple \
        --require-hashes \
        -r "$PROJECT_DIR/.github/locks/pip-bootstrap.txt"
    "$RUNTIME_DIR/bin/python" -I -B -X \
        "pycache_prefix=$PYTHON_CACHE" -m pip install \
        --isolated \
        --no-input \
        --disable-pip-version-check \
        --only-binary=:all: \
        --index-url https://pypi.org/simple \
        --require-hashes \
        -r "$PROJECT_DIR/RealLLM/requirements.lock"
elif [ "$runtime_state" != "existing" ]; then
    fail "CORELM_SKIP_RUNTIME_INSTALL=1 requires an initialized runtime"
fi

APP_PYTHON="$RUNTIME_DIR/bin/python"
[ -x "$APP_PYTHON" ] || fail "dedicated Python runtime is incomplete"
"$APP_PYTHON" -I -B -X "pycache_prefix=$PYTHON_CACHE" -c '
import pathlib, sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit("app runtime must use Python 3.12")
expected = pathlib.Path(sys.argv[1]).resolve(strict=True)
actual = pathlib.Path(sys.prefix).resolve(strict=True)
if actual != expected:
    raise SystemExit(f"app runtime prefix {actual} does not match {expected}")
' "$RUNTIME_DIR"
"$APP_PYTHON" -I -B -X "pycache_prefix=$PYTHON_CACHE" -m pip check
"$APP_PYTHON" -I -B -X "pycache_prefix=$PYTHON_CACHE" \
    "$PROJECT_DIR/security/verify_locked_environment.py" \
    --runtime "$RUNTIME_DIR" \
    --lock "$PROJECT_DIR/.github/locks/pip-bootstrap.txt" \
    --lock "$PROJECT_DIR/RealLLM/requirements.lock"
if [ "$SKIP_MPS_CHECK" = "0" ]; then
    "$APP_PYTHON" -I -B -X "pycache_prefix=$PYTHON_CACHE" -c '
import torch
if not torch.backends.mps.is_built() or not torch.backends.mps.is_available():
    raise SystemExit("PyTorch MPS is unavailable on this Mac")
'
fi

if [ "$SKIP_ASSET_PREPARATION" = "0" ]; then
    if [ "$ASSETS_OFFLINE_ONLY" = "1" ]; then
        "$APP_PYTHON" -I -B -X "pycache_prefix=$PYTHON_CACHE" \
            "$PROJECT_DIR/RealLLM/prepare_app_assets.py" \
            --cache "$CACHE_DIR" \
            --offline-only
    else
        "$APP_PYTHON" -I -B -X "pycache_prefix=$PYTHON_CACHE" \
            "$PROJECT_DIR/RealLLM/prepare_app_assets.py" \
            --cache "$CACHE_DIR"
    fi
fi

CORELM_REAL_LLM_PYTHON="$APP_PYTHON" \
BUILD_CONFIG="$BUILD_CONFIG" \
ALLOW_ADHOC_SIGNING=1 \
DEVELOPER_ID_APPLICATION= \
REQUIRE_DEVELOPER_ID=0 \
    "$PROJECT_DIR/package_app.sh"

"$PROJECT_DIR/security/verify_app_bundle.sh" "$APP_PATH"

if [ "$SKIP_SMOKE_TEST" = "0" ]; then
    "$APP_PATH/Contents/MacOS/CoreLMBenchmarkApp" --smoke-run
fi

printf '%s\n' \
    "LOCAL APP BUILD PASS: $APP_PATH" \
    "No Apple Developer account, certificate, or notarization was used." \
    "Open it with: open \"$APP_PATH\"" \
    "Open Compression Proof and click Run Compression Proof."
