#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
PYTHON_REQUEST=${CORELM_LINUX_PYTHON:-python3.12}
SKIP_MEMORY_CHECK=0
MINIMUM_AVAILABLE_KIB=8388608
MINIMUM_FREE_KIB=6291456

fail() {
    printf 'LINUX DOCTOR FAIL: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: ./corelm linux doctor [--skip-memory-check]

CORELM_LINUX_PYTHON may name an exact Python 3.12.13 executable.
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

case "$PYTHON_REQUEST" in
    /*) PYTHON_BIN=$PYTHON_REQUEST ;;
    *) PYTHON_BIN=$(command -v "$PYTHON_REQUEST" 2>/dev/null || true) ;;
esac
[ -n "$PYTHON_BIN" ] && [ -x "$PYTHON_BIN" ] \
    || fail "Python executable is missing: $PYTHON_REQUEST"
PYTHON_BIN=$("$PYTHON_BIN" -I -B -c \
    'import pathlib,sys; print(pathlib.Path(sys.executable).resolve(strict=True))') \
    || fail "cannot resolve Python executable"
version=$("$PYTHON_BIN" -I -B -c \
    'import platform; print(platform.python_version())')
[ "$version" = 3.12.13 ] \
    || fail "Python 3.12.13 is required; found $version"
"$PYTHON_BIN" -I -B -m venv --help >/dev/null 2>&1 \
    || fail "the Python venv module is unavailable"

for utility in git sha256sum timeout; do
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

free_kib=$(df -Pk "$PROJECT_DIR" | /usr/bin/awk 'NR == 2 {print $4}')
case "$free_kib" in
    ''|*[!0-9]*) fail "cannot determine free disk space" ;;
esac
[ "$free_kib" -ge "$MINIMUM_FREE_KIB" ] \
    || fail "at least 6 GiB free disk space is required"

printf '%s\n' \
    "LINUX DOCTOR PASS: Linux x86_64, Python $version" \
    "Resolved Python: $PYTHON_BIN"
