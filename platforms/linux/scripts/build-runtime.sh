#!/bin/sh
set -eu

umask 077
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
PYTHON_REQUEST=${CORELM_LINUX_PYTHON:-python3.12}
RUNTIME_DIR=${CORELM_LINUX_RUNTIME:-"$HOME/.cache/corelm-linux-runtime"}
HF_CACHE=${CORELM_LINUX_HF_HOME:-"$HOME/.cache/corelm-linux-model-assets"}
OFFLINE=${CORELM_OFFLINE:-0}

fail() {
    printf 'LINUX RUNTIME BUILD FAIL: %s\n' "$*" >&2
    exit 1
}

case "$OFFLINE" in 0|1) ;; *) fail "CORELM_OFFLINE must be 0 or 1" ;; esac
for path in "$RUNTIME_DIR" "$HF_CACHE"; do
    case "$path" in /*) ;; *) fail "runtime and cache paths must be absolute" ;; esac
done

CORELM_LINUX_PYTHON="$PYTHON_REQUEST" \
    "$PROJECT_DIR/platforms/linux/scripts/doctor.sh"

case "$PYTHON_REQUEST" in
    /*) PYTHON_BIN=$PYTHON_REQUEST ;;
    *) PYTHON_BIN=$(command -v "$PYTHON_REQUEST") ;;
esac

if [ -e "$RUNTIME_DIR" ] || [ -L "$RUNTIME_DIR" ]; then
    [ -d "$RUNTIME_DIR" ] && [ ! -L "$RUNTIME_DIR" ] \
        || fail "runtime must be a regular directory"
else
    runtime_parent=$(dirname -- "$RUNTIME_DIR")
    if [ ! -e "$runtime_parent" ]; then
        /bin/mkdir -p "$runtime_parent"
        /bin/chmod 700 "$runtime_parent"
    fi
    "$PYTHON_BIN" -I -B -m venv "$RUNTIME_DIR"
    runtime_python="$RUNTIME_DIR/bin/python"
    if [ "$OFFLINE" = 1 ]; then
        fail "first runtime build requires network access to registered wheels"
    fi
    "$runtime_python" -I -B -m pip install \
        --isolated --no-input --disable-pip-version-check --no-cache-dir \
        --only-binary=:all: --index-url https://pypi.org/simple \
        --require-hashes \
        -r "$PROJECT_DIR/.github/locks/pip-bootstrap.txt"
    "$runtime_python" -I -B -m pip install \
        --isolated --no-input --disable-pip-version-check --no-cache-dir \
        --no-deps --only-binary=:all: --index-url https://pypi.org/simple \
        --require-hashes \
        -r "$PROJECT_DIR/.github/locks/real-llm-linux-cpu-py312.txt"
    "$runtime_python" -I -B -m pip install \
        --isolated --no-input --disable-pip-version-check --no-cache-dir \
        --no-deps --only-binary=:all: \
        --index-url https://download.pytorch.org/whl/cpu \
        --require-hashes \
        -r "$PROJECT_DIR/.github/locks/torch-linux-cpu-py312.txt"
fi

[ -x "$RUNTIME_DIR/bin/python" ] || fail "runtime is incomplete"
runtime_python="$RUNTIME_DIR/bin/python"
"$runtime_python" -I -B -m pip check
"$runtime_python" -I -B \
    "$PROJECT_DIR/security/verify_locked_environment.py" \
    --runtime "$RUNTIME_DIR" \
    --lock "$PROJECT_DIR/.github/locks/pip-bootstrap.txt" \
    --lock "$PROJECT_DIR/.github/locks/real-llm-linux-cpu-py312.txt" \
    --lock "$PROJECT_DIR/.github/locks/torch-linux-cpu-py312.txt"

if [ ! -e "$HF_CACHE" ]; then
    /bin/mkdir -p "$HF_CACHE"
fi
[ -d "$HF_CACHE" ] && [ ! -L "$HF_CACHE" ] \
    || fail "model cache must be a regular directory"
/bin/chmod 700 "$HF_CACHE"

if [ "$OFFLINE" = 0 ]; then
    "$runtime_python" -I -B "$PROJECT_DIR/RealLLM/prepare_app_assets.py" \
        --cache "$HF_CACHE"
fi
"$runtime_python" -I -B "$PROJECT_DIR/RealLLM/prepare_app_assets.py" \
    --cache "$HF_CACHE" --offline-only

printf '%s\n' \
    'LINUX RUNTIME BUILD PASS' \
    "Runtime: $RUNTIME_DIR" \
    "Verified model/data cache: $HF_CACHE"
