#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
BOOTSTRAP_ROOT="$HOME/.local/share/corelm/linux-x86_64/python-3.12.13+20260718"
BOOTSTRAP_PYTHON="$HOME/.local/share/corelm/linux-x86_64/python-3.12.13+20260718/bin/python3.12"
SYSTEM_PYTHON=/usr/bin/python3
EXPECTED_BOOTSTRAP_ROOT=

fail() {
    printf 'LINUX PYTHON RESOLUTION FAIL: %s\n' "$*" >&2
    exit 1
}

[ "$(uname -s)" = Linux ] || fail "Linux is required"
[ -x "$SYSTEM_PYTHON" ] || fail "Ubuntu system Python is required for validation"

if [ "${CORELM_LINUX_PYTHON+x}" = x ]; then
    [ -n "$CORELM_LINUX_PYTHON" ] \
        || fail "CORELM_LINUX_PYTHON is explicitly empty"
    request=$CORELM_LINUX_PYTHON
else
    if [ -e "$BOOTSTRAP_ROOT" ] || [ -L "$BOOTSTRAP_ROOT" ]; then
        "$PROJECT_DIR/platforms/linux/scripts/bootstrap-python.sh" \
            --harden-installed >/dev/null \
            || fail "owner-local Python bootstrap validation failed"
        request=$BOOTSTRAP_PYTHON
        EXPECTED_BOOTSTRAP_ROOT=$BOOTSTRAP_ROOT
    else
        request=python3.12
    fi
fi

case "$request" in
    /*) candidate=$request ;;
    *) candidate=$(command -v "$request" 2>/dev/null || true) ;;
esac
[ -n "$candidate" ] && [ -x "$candidate" ] \
    || fail "Python executable is missing: $request; run ./corelm linux bootstrap"
resolved=$(/usr/bin/readlink -f -- "$candidate") \
    || fail "cannot resolve Python executable: $candidate"
[ -n "$resolved" ] && [ -f "$resolved" ] && [ -x "$resolved" ] \
    || fail "resolved Python is not an executable regular file: $resolved"

# Validate the executable and its ancestors with the trusted OS Python before
# starting the requested interpreter.
"$SYSTEM_PYTHON" -I -B - \
    "$PROJECT_DIR" "$resolved" "$EXPECTED_BOOTSTRAP_ROOT" <<'PY'
import pathlib
import sys

sys.path.insert(0, sys.argv[1])
from platforms.linux.scripts.runtime_safety import (
    _safe_existing_chain,
    _safe_regular_file,
)

executable = pathlib.Path(sys.argv[2])
expected_root_value = sys.argv[3]
if executable.resolve(strict=True) != executable:
    raise SystemExit("resolved Python path is not canonical")
_safe_regular_file(executable, current_owner=False)
_safe_existing_chain(executable.parent)
if expected_root_value:
    expected_root = pathlib.Path(expected_root_value)
    if expected_root.resolve(strict=True) != expected_root:
        raise SystemExit("pinned bootstrap root is not canonical")
    if executable != expected_root and expected_root not in executable.parents:
        raise SystemExit("pinned Python executable escaped bootstrap root")
PY

"$resolved" -I -B - \
    "$PROJECT_DIR" "$resolved" "$EXPECTED_BOOTSTRAP_ROOT" <<'PY'
import pathlib
import platform
import sys

sys.path.insert(0, sys.argv[1])
from platforms.linux.scripts.runtime_safety import (
    _safe_directory,
    _safe_existing_chain,
)

expected_executable = pathlib.Path(sys.argv[2])
expected_root_value = sys.argv[3]
actual_executable = pathlib.Path(sys.executable).resolve(strict=True)
if actual_executable != expected_executable:
    raise SystemExit("Python executable identity changed during launch")
if platform.python_version() != "3.12.13":
    raise SystemExit(
        f"Python 3.12.13 is required; found {platform.python_version()}"
    )
base_prefix = pathlib.Path(sys.base_prefix)
if base_prefix.resolve(strict=True) != base_prefix:
    raise SystemExit("Python base prefix is not canonical")
_safe_existing_chain(base_prefix)
_safe_directory(base_prefix, current_owner=False)
if expected_root_value:
    expected_root = pathlib.Path(expected_root_value)
    if base_prefix != expected_root:
        raise SystemExit(
            f"pinned Python base prefix {base_prefix} does not match "
            f"{expected_root}"
        )
PY

printf '%s\n' "$resolved"
