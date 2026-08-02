#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
RUNTIME_DIR=${CORELM_LINUX_RUNTIME:-"$HOME/.cache/corelm/linux/runtime"}
HF_CACHE=${CORELM_LINUX_HF_HOME:-"$HOME/.cache/corelm/linux/model-assets"}
RUN_ROOT=${CORELM_LINUX_RUN_ROOT:-"$HOME/.cache/corelm/linux/runs"}
RUN_TARGET=${CORELM_RUN_DIR:-"$RUN_ROOT"}
SKIP_MEMORY_CHECK=0
MINIMUM_AVAILABLE_KIB=8388608
MINIMUM_FREE_KIB=6291456
SAFETY_SCRIPT="$PROJECT_DIR/platforms/linux/scripts/runtime_safety.py"
PYTHON_FINDER="$PROJECT_DIR/platforms/linux/scripts/find-python312.sh"

fail() {
    printf 'LINUX DOCTOR FAIL: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: ./corelm linux doctor [--skip-memory-check]

CORELM_LINUX_PYTHON may name an exact Python 3.12.13 executable. Runtime,
model-cache, and run paths must be absolute, canonical, private, and disjoint.
If Python is missing, run ./corelm linux bootstrap first.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --skip-memory-check) SKIP_MEMORY_CHECK=1 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown argument: $1" ;;
    esac
    shift
done

[ "$(uname -s)" = Linux ] || fail "Linux is required"
[ "$(uname -m)" = x86_64 ] || fail "the published locks require x86_64"

PYTHON_BIN=$("$PYTHON_FINDER") \
    || fail "trusted Python 3.12.13 resolution failed"
version=$("$PYTHON_BIN" -I -B -c \
    'import platform; print(platform.python_version())')
[ "$version" = 3.12.13 ] \
    || fail "Python 3.12.13 is required; found $version"
"$PYTHON_BIN" -I -B -m venv --help >/dev/null 2>&1 \
    || fail "the Python venv module is unavailable"

for utility in git sha256sum timeout mktemp; do
    command -v "$utility" >/dev/null 2>&1 \
        || fail "required utility is missing: $utility"
done

if [ "$SKIP_MEMORY_CHECK" = 0 ]; then
    available_kib=$(/usr/bin/awk '/MemAvailable:/ {print $2}' /proc/meminfo)
    case "$available_kib" in
        ''|*[!0-9]*) fail "cannot determine available memory" ;;
    esac
    [ "$available_kib" -ge "$MINIMUM_AVAILABLE_KIB" ] \
        || fail "at least 8 GiB available memory is required"
fi

"$PYTHON_BIN" -I -B "$SAFETY_SCRIPT" validate-paths \
    --project "$PROJECT_DIR" \
    --runtime "$RUNTIME_DIR" \
    --cache "$HF_CACHE" \
    --run "$RUN_TARGET" \
    --minimum-free-kib "$MINIMUM_FREE_KIB" >/dev/null \
    || fail "runtime, cache, run, or target-volume validation failed"

printf '%s\n' \
    "LINUX DOCTOR PASS: Linux x86_64, Python $version" \
    "Resolved Python: $PYTHON_BIN" \
    "Validated runtime target: $RUNTIME_DIR" \
    "Validated model-cache target: $HF_CACHE" \
    "Validated run target: $RUN_TARGET"
