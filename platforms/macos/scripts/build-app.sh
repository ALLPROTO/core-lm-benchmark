#!/bin/sh
set -eu

umask 077

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
RUNTIME_DIR=${CORELM_REAL_LLM_VENV:-"$HOME/.cache/corelm/macos/runtime"}
CACHE_DIR="$HOME/.cache/corelm/macos/model-assets"
BUILD_CONFIG=${BUILD_CONFIG:-release}
OFFLINE=${CORELM_OFFLINE:-0}
WHEELHOUSE=${CORELM_WHEELHOUSE:-}
PYPI_INDEX_URL=${CORELM_PYPI_INDEX_URL:-https://pypi.org/simple}
HF_ENDPOINT=${CORELM_HF_ENDPOINT:-https://huggingface.co}
SKIP_RUNTIME_INSTALL=${CORELM_SKIP_RUNTIME_INSTALL:-0}
SKIP_ASSET_PREPARATION=${CORELM_SKIP_ASSET_PREPARATION:-0}
ASSETS_OFFLINE_ONLY=${CORELM_ASSETS_OFFLINE_ONLY:-$OFFLINE}
SKIP_MEMORY_CHECK=${CORELM_SKIP_MEMORY_CHECK:-0}
SKIP_MPS_CHECK=${CORELM_SKIP_MPS_CHECK:-0}
SKIP_APP_LAUNCH_CHECK=${CORELM_SKIP_APP_LAUNCH_CHECK:-0}
APP_PATH="$PROJECT_DIR/dist/CoreLMBenchmark.app"
PYTHON_CACHE=

cleanup() {
    if [ -n "$PYTHON_CACHE" ] && [ -d "$PYTHON_CACHE" ]; then
        rm -rf "$PYTHON_CACHE"
    fi
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
require_boolean CORELM_OFFLINE "$OFFLINE"
require_boolean CORELM_SKIP_MEMORY_CHECK "$SKIP_MEMORY_CHECK"
require_boolean CORELM_SKIP_MPS_CHECK "$SKIP_MPS_CHECK"
require_boolean CORELM_SKIP_APP_LAUNCH_CHECK "$SKIP_APP_LAUNCH_CHECK"

case "$RUNTIME_DIR" in
    /*) ;;
    *) fail "CORELM_REAL_LLM_VENV must be an absolute path" ;;
esac

if [ "$OFFLINE" = 1 ]; then
    [ "$ASSETS_OFFLINE_ONLY" = 1 ] \
        || fail "CORELM_OFFLINE=1 requires CORELM_ASSETS_OFFLINE_ONLY=1"
    if [ "$SKIP_RUNTIME_INSTALL" = 0 ]; then
        [ -n "$WHEELHOUSE" ] \
            || fail "CORELM_OFFLINE=1 requires CORELM_WHEELHOUSE"
    fi
fi

set --
[ "$SKIP_APP_LAUNCH_CHECK" = 1 ] && set -- "$@" --no-gui
[ "$SKIP_MEMORY_CHECK" = 1 ] && set -- "$@" --skip-memory-check
[ "$SKIP_RUNTIME_INSTALL" = 1 ] && set -- "$@" --skip-packages
[ "$SKIP_ASSET_PREPARATION" = 1 ] && set -- "$@" --skip-assets
CORELM_OFFLINE="$OFFLINE" \
CORELM_ASSETS_OFFLINE_ONLY="$ASSETS_OFFLINE_ONLY" \
CORELM_WHEELHOUSE="$WHEELHOUSE" \
CORELM_PYPI_INDEX_URL="$PYPI_INDEX_URL" \
CORELM_HF_ENDPOINT="$HF_ENDPOINT" \
    "$PROJECT_DIR/platforms/macos/scripts/doctor.sh" "$@"

bootstrap_path=$("$PROJECT_DIR/security/find_python312.sh" || true)
[ -n "$bootstrap_path" ] || fail \
    "Python 3.12.13 is missing; run ./corelm macos bootstrap or set CORELM_BOOTSTRAP_PYTHON"
PYTHON_CACHE=$(mktemp -d "${TMPDIR:-/tmp}/corelm-build-pycache.XXXXXX")
"$bootstrap_path" -I -B -X "pycache_prefix=$PYTHON_CACHE" -c '
import sys
if sys.version_info[:3] != (3, 12, 13):
    raise SystemExit("CORELM_BOOTSTRAP_PYTHON must be Python 3.12.13")
'

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
    if [ -n "$WHEELHOUSE" ]; then
        "$RUNTIME_DIR/bin/python" -I -B -X \
            "pycache_prefix=$PYTHON_CACHE" -m pip install \
            --isolated \
            --no-input \
            --disable-pip-version-check \
            --only-binary=:all: \
            --no-index \
            --find-links "$WHEELHOUSE" \
            --require-hashes \
            -r "$PROJECT_DIR/.github/locks/pip-bootstrap.txt"
        "$RUNTIME_DIR/bin/python" -I -B -X \
            "pycache_prefix=$PYTHON_CACHE" -m pip install \
            --isolated \
            --no-input \
            --disable-pip-version-check \
            --only-binary=:all: \
            --no-index \
            --find-links "$WHEELHOUSE" \
            --require-hashes \
            -r "$PROJECT_DIR/RealLLM/requirements.lock"
    else
        "$RUNTIME_DIR/bin/python" -I -B -X \
            "pycache_prefix=$PYTHON_CACHE" -m pip install \
            --isolated \
            --no-input \
            --disable-pip-version-check \
            --only-binary=:all: \
            --index-url "$PYPI_INDEX_URL" \
            --require-hashes \
            -r "$PROJECT_DIR/.github/locks/pip-bootstrap.txt"
        "$RUNTIME_DIR/bin/python" -I -B -X \
            "pycache_prefix=$PYTHON_CACHE" -m pip install \
            --isolated \
            --no-input \
            --disable-pip-version-check \
            --only-binary=:all: \
            --index-url "$PYPI_INDEX_URL" \
            --require-hashes \
            -r "$PROJECT_DIR/RealLLM/requirements.lock"
    fi
elif [ "$runtime_state" != "existing" ]; then
    fail "CORELM_SKIP_RUNTIME_INSTALL=1 requires an initialized runtime"
fi

APP_PYTHON="$RUNTIME_DIR/bin/python"
[ -x "$APP_PYTHON" ] || fail "dedicated Python runtime is incomplete"
"$APP_PYTHON" -I -B -X "pycache_prefix=$PYTHON_CACHE" -c '
import pathlib, sys
if sys.version_info[:3] != (3, 12, 13):
    raise SystemExit("app runtime must use Python 3.12.13")
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
            --cache "$CACHE_DIR" \
            --endpoint "$HF_ENDPOINT"
    fi
fi

CORELM_REAL_LLM_PYTHON="$APP_PYTHON" \
BUILD_CONFIG="$BUILD_CONFIG" \
    "$PROJECT_DIR/platforms/macos/scripts/package-app.sh"

"$PROJECT_DIR/security/verify_app_bundle.sh" "$APP_PATH"

if [ "$SKIP_APP_LAUNCH_CHECK" = "0" ]; then
    "$APP_PATH/Contents/MacOS/CoreLMBenchmarkApp" --app-launch-check
fi

printf '%s\n' \
    "LOCAL APP BUILD PASS: $APP_PATH" \
    "No Apple Developer account, certificate, or notarization was used." \
    "Open it with: open \"$APP_PATH\"" \
    "Open Compression Proof and click Run Compression Proof."
