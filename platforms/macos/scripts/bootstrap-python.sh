#!/bin/sh
set -eu

# Install a fixed owner-local Python runtime without sudo or changes to the
# system Python. The third-party binary archive is accepted only after its
# registered SHA-256 and archive topology have been checked.

umask 077

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
PYTHON_RELEASE=3.12.13
BUILD_RELEASE=20260718
ARCHIVE_NAME="cpython-${PYTHON_RELEASE}+${BUILD_RELEASE}-aarch64-apple-darwin-install_only.tar.gz"
ARCHIVE_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${BUILD_RELEASE}/${ARCHIVE_NAME}"
ARCHIVE_SHA256=62aeee6161d57303a71a138b75fd5cc6fb8c89c4b1d9c7f0a052d89fa0b6652b
INSTALL_ROOT="$HOME/.local/share/corelm"
TARGET="$INSTALL_ROOT/python-$PYTHON_RELEASE"
TARGET_PYTHON="$TARGET/bin/python3.12"
MODE=install
TEMP_DIRECTORY=
ARCHIVE_PATH=

fail() {
    printf 'PYTHON BOOTSTRAP FAIL: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: ./corelm macos bootstrap [--harden-installed]

Install the registered Astral python-build-standalone CPython 3.12 runtime
under ~/.local/share/corelm without sudo. --harden-installed performs no
download and only revalidates/hardens the exact existing owner-local runtime.
EOF
}

case "${1:-}" in
    '') ;;
    --harden-installed) MODE=harden ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
esac
[ "$#" -le 1 ] || fail "too many arguments"

cleanup() {
    if [ -n "$TEMP_DIRECTORY" ] && [ -d "$TEMP_DIRECTORY" ]; then
        /bin/rm -rf "$TEMP_DIRECTORY"
    fi
}
trap cleanup EXIT

[ "$(uname -s)" = Darwin ] || fail "macOS is required"
[ "$(uname -m)" = arm64 ] || fail "Apple Silicon (arm64) is required"
[ -x /usr/bin/python3 ] || fail \
    "Apple Command Line Tools are required first; run xcode-select --install"

require_private_directory() {
    directory=$1
    [ -d "$directory" ] || fail "expected directory is missing: $directory"
    [ ! -L "$directory" ] || fail "refusing symlinked directory: $directory"
    owner=$(/usr/bin/stat -f '%u' "$directory" 2>/dev/null) \
        || fail "could not inspect directory: $directory"
    [ "$owner" -eq "$(/usr/bin/id -u)" ] \
        || fail "directory is not owned by the current user: $directory"
    mode=$(/usr/bin/stat -f '%Lp' "$directory" 2>/dev/null) \
        || fail "could not inspect directory permissions: $directory"
    case "$mode" in
        *[2367][0-7]|*[0-7][2367])
            fail "directory is group/world-writable: $directory" ;;
    esac
}

make_private_directory() {
    directory=$1
    if [ -e "$directory" ]; then
        require_private_directory "$directory"
    else
        /bin/mkdir "$directory"
        /bin/chmod 700 "$directory"
    fi
}

validate_installed_python() {
    require_private_directory "$INSTALL_ROOT"
    require_private_directory "$TARGET"
    [ -x "$TARGET_PYTHON" ] \
        || fail "owner-local Python is incomplete: $TARGET_PYTHON"
    "$TARGET_PYTHON" -I -B -c '
import pathlib
import sys

expected = pathlib.Path(sys.argv[1]).resolve(strict=True)
actual = pathlib.Path(sys.base_prefix).resolve(strict=True)
if sys.version_info[:3] != (3, 12, 13):
    raise SystemExit("owner-local runtime is not Python 3.12.13")
if actual != expected:
    raise SystemExit(f"Python base prefix {actual} does not match {expected}")
' "$TARGET" || fail "owner-local Python identity check failed"
    /bin/chmod -RP go-w "$TARGET"
    "$TARGET_PYTHON" -I -B -c '
import pathlib
import sys

project = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(project))
from security.manage_local_runtime import _safe_existing_chain

_safe_existing_chain(pathlib.Path(sys.base_prefix))
' "$PROJECT_DIR" || fail "owner-local Python permission chain is unsafe"
}

if [ "$MODE" = harden ]; then
    validate_installed_python
    printf 'PYTHON BOOTSTRAP PASS: %s\n' "$TARGET_PYTHON"
    exit 0
fi

if [ -e "$TARGET" ]; then
    validate_installed_python
    printf 'PYTHON BOOTSTRAP PASS: existing runtime %s\n' "$TARGET_PYTHON"
    exit 0
fi

make_private_directory "$HOME/.local"
make_private_directory "$HOME/.local/share"
make_private_directory "$INSTALL_ROOT"

TEMP_DIRECTORY=$(mktemp -d "${TMPDIR:-/tmp}/corelm-python312.XXXXXX")
ARCHIVE_PATH="$TEMP_DIRECTORY/$ARCHIVE_NAME"
EXTRACT_ROOT="$TEMP_DIRECTORY/extracted"
/bin/mkdir "$EXTRACT_ROOT"

printf 'Downloading registered owner-local Python from %s\n' "$ARCHIVE_URL"
/usr/bin/curl \
    --fail \
    --location \
    --proto '=https' \
    --proto-redir '=https' \
    --connect-timeout 30 \
    --max-time 600 \
    --retry 2 \
    --output "$ARCHIVE_PATH" \
    "$ARCHIVE_URL" \
    || fail "could not download the fixed Python archive"
actual_sha256=$(/usr/bin/shasum -a 256 "$ARCHIVE_PATH" | /usr/bin/awk '{print $1}')
[ "$actual_sha256" = "$ARCHIVE_SHA256" ] \
    || fail "Python archive SHA-256 does not match the registered value"

# Check paths, link semantics, duplicate entries, and special files before
# extraction. The fixed digest is the primary authenticity boundary; this
# validation prevents archive traversal if extraction behavior changes.
/usr/bin/python3 -I -B \
    "$PROJECT_DIR/security/validate_python_bootstrap_archive.py" \
    "$ARCHIVE_PATH" \
    || fail "Python archive topology validation failed"

/usr/bin/tar -xzf "$ARCHIVE_PATH" -C "$EXTRACT_ROOT"
[ -d "$EXTRACT_ROOT/python" ] \
    || fail "Python archive did not contain the expected root"
[ ! -L "$EXTRACT_ROOT/python" ] \
    || fail "Python archive root must not be a symlink"

# Resolve every extracted symlink after extraction and reject anything outside
# the private staging root before the tree can be installed.
/usr/bin/python3 -I -B - "$EXTRACT_ROOT/python" <<'PY'
import pathlib
import os
import stat
import sys

root = pathlib.Path(sys.argv[1]).resolve(strict=True)
for path in root.rglob("*"):
    status = path.lstat()
    mode = status.st_mode
    if status.st_uid != os.getuid():
        raise SystemExit(f"extracted path has an unexpected owner: {path}")
    if stat.S_ISLNK(mode):
        resolved = path.resolve(strict=True)
        if resolved != root and root not in resolved.parents:
            raise SystemExit(f"extracted symlink escapes runtime: {path}")
    elif not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
        raise SystemExit(f"unsupported extracted file type: {path}")
PY

/bin/chmod -RP go-w "$EXTRACT_ROOT/python"
/bin/mv "$EXTRACT_ROOT/python" "$TARGET"
validate_installed_python

printf '%s\n' \
    "SHA-256 PASS: $ARCHIVE_SHA256" \
    'Source: astral-sh/python-build-standalone immutable release 20260718' \
    "PYTHON BOOTSTRAP PASS: $TARGET_PYTHON" \
    'No sudo access or system Python modification was used.'
