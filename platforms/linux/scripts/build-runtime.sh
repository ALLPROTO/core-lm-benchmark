#!/bin/sh
set -eu

umask 077
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
PYTHON_REQUEST=${CORELM_LINUX_PYTHON:-python3.12}
RUNTIME_DIR=${CORELM_LINUX_RUNTIME:-"$HOME/.cache/corelm/linux/runtime"}
HF_CACHE=${CORELM_LINUX_HF_HOME:-"$HOME/.cache/corelm/linux/model-assets"}
OFFLINE=${CORELM_OFFLINE:-0}
SAFETY_SCRIPT="$PROJECT_DIR/platforms/linux/scripts/runtime_safety.py"
STAGING_DIR=
RUNTIME_PARENT=

fail() {
    printf 'LINUX RUNTIME BUILD FAIL: %s\n' "$*" >&2
    exit 1
}

cleanup() {
    if [ -z "$STAGING_DIR" ]; then
        return
    fi
    case "$STAGING_DIR" in
        "$RUNTIME_PARENT"/.corelm-linux-runtime-stage.*)
            if [ -e "$STAGING_DIR" ] || [ -L "$STAGING_DIR" ]; then
                /bin/rm -rf -- "$STAGING_DIR"
            fi
            ;;
        *)
            printf 'LINUX RUNTIME BUILD CLEANUP REFUSED: %s\n' \
                "$STAGING_DIR" >&2
            ;;
    esac
}

on_signal() {
    trap - EXIT HUP INT TERM
    cleanup
    exit 130
}

trap cleanup EXIT
trap on_signal HUP INT TERM

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
    "$PYTHON_BIN" -I -B "$SAFETY_SCRIPT" validate-runtime \
        --runtime "$RUNTIME_DIR" >/dev/null \
        || fail "existing runtime failed ownership, marker, or Python validation"
else
    [ "$OFFLINE" = 0 ] \
        || fail "first runtime build requires network access to registered wheels"
    RUNTIME_PARENT=$(dirname -- "$RUNTIME_DIR")
    if [ ! -e "$RUNTIME_PARENT" ]; then
        /bin/mkdir -p "$RUNTIME_PARENT"
        /bin/chmod 700 "$RUNTIME_PARENT"
    fi
    STAGING_DIR=$(mktemp -d \
        "$RUNTIME_PARENT/.corelm-linux-runtime-stage.XXXXXX") \
        || fail "cannot create private runtime staging directory"
    /bin/chmod 700 "$STAGING_DIR"
    "$PYTHON_BIN" -I -B -m venv "$STAGING_DIR"
    runtime_python="$STAGING_DIR/bin/python"
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

    "$PYTHON_BIN" -I -B "$SAFETY_SCRIPT" initialize-runtime \
        --runtime "$STAGING_DIR" >/dev/null \
        || fail "cannot initialize the runtime ownership marker"
    "$PYTHON_BIN" -I -B "$SAFETY_SCRIPT" validate-runtime \
        --runtime "$STAGING_DIR" >/dev/null \
        || fail "staged runtime failed ownership, marker, or Python validation"
    "$runtime_python" -I -B -m pip check
    "$runtime_python" -I -B \
        "$PROJECT_DIR/security/verify_locked_environment.py" \
        --runtime "$STAGING_DIR" \
        --lock "$PROJECT_DIR/.github/locks/pip-bootstrap.txt" \
        --lock "$PROJECT_DIR/.github/locks/real-llm-linux-cpu-py312.txt" \
        --lock "$PROJECT_DIR/.github/locks/torch-linux-cpu-py312.txt"

    "$PYTHON_BIN" -I -B "$SAFETY_SCRIPT" publish-runtime \
        --staging "$STAGING_DIR" \
        --destination "$RUNTIME_DIR" >/dev/null \
        || fail "cannot atomically publish the verified runtime"
    STAGING_DIR=
fi

[ -x "$RUNTIME_DIR/bin/python" ] || fail "runtime is incomplete"
runtime_python="$RUNTIME_DIR/bin/python"
"$PYTHON_BIN" -I -B "$SAFETY_SCRIPT" validate-runtime \
    --runtime "$RUNTIME_DIR" >/dev/null \
    || fail "published runtime failed ownership, marker, or Python validation"
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
