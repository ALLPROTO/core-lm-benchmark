#!/bin/sh
set -eu

# Resolve a usable Python 3.12 without importing site packages or writing
# bytecode. An explicit override is authoritative: an invalid override must not
# silently fall back to another interpreter.

is_python312() {
    candidate=$1
    [ -x "$candidate" ] || return 1
    "$candidate" -I -B -c '
import sys
raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)
' >/dev/null 2>&1
}

resolve_candidate() {
    candidate=$1
    case "$candidate" in
        /*) resolved=$candidate ;;
        *) resolved=$(command -v "$candidate" 2>/dev/null || true) ;;
    esac
    [ -n "$resolved" ] || return 1
    is_python312 "$resolved" || return 1
    printf '%s\n' "$resolved"
}

if [ "${CORELM_BOOTSTRAP_PYTHON+x}" = x ]; then
    [ -n "$CORELM_BOOTSTRAP_PYTHON" ] || exit 1
    resolve_candidate "$CORELM_BOOTSTRAP_PYTHON"
    exit $?
fi

for candidate in \
    "$HOME/.local/share/corelm/python-3.12.13/bin/python3.12" \
    python3.12 \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
    /opt/homebrew/bin/python3.12 \
    /usr/local/bin/python3.12 \
    python3
do
    if resolve_candidate "$candidate"; then
        exit 0
    fi
done

exit 1
