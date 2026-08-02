#!/bin/sh
set -eu

# Install a fixed owner-local Python runtime without sudo or changes to the
# system Python. The third-party binary archive is accepted only after its
# registered SHA-256 and archive topology have been checked.

umask 077

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
PYTHON_RELEASE=3.12.13
BUILD_RELEASE=20260718
ARCHIVE_NAME="cpython-${PYTHON_RELEASE}+${BUILD_RELEASE}-x86_64-unknown-linux-gnu-install_only.tar.gz"
ARCHIVE_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${BUILD_RELEASE}/${ARCHIVE_NAME}"
ARCHIVE_SHA256=7eea0959fa425c8aff3ea0a1352ee7d01d794b51439ed8f5fcfa017dbc0ec661
ARCHIVE_SIZE=111280988
TARGET_TRIPLE=x86_64-unknown-linux-gnu
CORELM_ROOT="$HOME/.local/share/corelm"
INSTALL_ROOT="$CORELM_ROOT/linux-x86_64"
TARGET="$INSTALL_ROOT/python-${PYTHON_RELEASE}+${BUILD_RELEASE}"
TARGET_PYTHON="$TARGET/bin/python3.12"
RECEIPT_NAME=.corelm-python-bootstrap-v1.json
SYSTEM_PYTHON=/usr/bin/python3
MODE=install
TEMP_DIRECTORY=

fail() {
    printf 'PYTHON BOOTSTRAP FAIL: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: ./corelm linux bootstrap [--harden-installed]

Install the registered Astral python-build-standalone CPython 3.12.13 runtime
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
    [ -n "$TEMP_DIRECTORY" ] || return
    case "$TEMP_DIRECTORY" in
        "$INSTALL_ROOT"/.corelm-python312-stage.*)
            if [ -d "$TEMP_DIRECTORY" ] && [ ! -L "$TEMP_DIRECTORY" ]; then
                /bin/rm -rf -- "$TEMP_DIRECTORY"
            fi
            ;;
        *)
            printf 'PYTHON BOOTSTRAP CLEANUP REFUSED: %s\n' \
                "$TEMP_DIRECTORY" >&2
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

[ "$(uname -s)" = Linux ] || fail "Linux is required"
[ "$(uname -m)" = x86_64 ] || fail "x86_64 is required"
[ -x "$SYSTEM_PYTHON" ] || fail "Ubuntu system Python is required for archive validation"
for utility in curl sha256sum stat tar mktemp; do
    command -v "$utility" >/dev/null 2>&1 \
        || fail "required utility is missing: $utility"
done

require_private_directory() {
    directory=$1
    [ -d "$directory" ] || fail "expected directory is missing: $directory"
    [ ! -L "$directory" ] || fail "refusing symlinked directory: $directory"
    owner=$(/usr/bin/stat -c '%u' "$directory" 2>/dev/null) \
        || fail "could not inspect directory: $directory"
    [ "$owner" -eq "$(/usr/bin/id -u)" ] \
        || fail "directory is not owned by the current user: $directory"
    mode=$(/usr/bin/stat -c '%a' "$directory" 2>/dev/null) \
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

receipt_operation() {
    operation=$1
    runtime=$2
    "$SYSTEM_PYTHON" -I -B - \
        "$operation" \
        "$runtime" \
        "$RECEIPT_NAME" \
        "$PYTHON_RELEASE" \
        "$BUILD_RELEASE" \
        "$TARGET_TRIPLE" \
        "$ARCHIVE_SHA256" <<'PY'
import hashlib
import json
import os
import pathlib
import stat
import sys

operation, root_value, name, release, build, triple, digest = sys.argv[1:]
root = pathlib.Path(root_value)
receipt = root / name


def observe_tree():
    tree_digest = hashlib.sha256()
    entries = [root, *sorted(root.rglob("*"), key=lambda item: item.as_posix())]
    entry_count = 0
    for path in entries:
        if path == receipt:
            continue
        status = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        record = {
            "mode": stat.S_IMODE(status.st_mode),
            "path": relative,
        }
        if stat.S_ISDIR(status.st_mode):
            record["kind"] = "directory"
        elif stat.S_ISLNK(status.st_mode):
            record["kind"] = "symlink"
            record["target"] = os.readlink(path)
        elif stat.S_ISREG(status.st_mode):
            content_digest = hashlib.sha256()
            flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
            descriptor = os.open(path, flags)
            try:
                opened = os.fstat(descriptor)
                if (
                    opened.st_dev != status.st_dev
                    or opened.st_ino != status.st_ino
                    or opened.st_uid != status.st_uid
                    or not stat.S_ISREG(opened.st_mode)
                ):
                    raise SystemExit(f"runtime file changed before hashing: {path}")
                while True:
                    chunk = os.read(descriptor, 1024 * 1024)
                    if not chunk:
                        break
                    content_digest.update(chunk)
                finished = os.fstat(descriptor)
                if (
                    finished.st_size != opened.st_size
                    or finished.st_mtime_ns != opened.st_mtime_ns
                    or finished.st_ctime_ns != opened.st_ctime_ns
                ):
                    raise SystemExit(f"runtime file changed while hashing: {path}")
            finally:
                os.close(descriptor)
            record["kind"] = "file"
            record["sha256"] = content_digest.hexdigest()
            record["size"] = status.st_size
        else:
            raise SystemExit(f"unsupported runtime tree entry: {path}")
        encoded = json.dumps(
            record, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        tree_digest.update(encoded + b"\n")
        entry_count += 1
    return entry_count, tree_digest.hexdigest()


tree_entries, tree_sha256 = observe_tree()
expected = (
    json.dumps(
        {
            "archiveSha256": digest,
            "buildRelease": build,
            "pythonRelease": release,
            "schemaVersion": "corelm-python-bootstrap-v1",
            "targetTriple": triple,
            "treeEntries": tree_entries,
            "treeSha256": tree_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    + b"\n"
)
if operation == "create":
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW
    descriptor = os.open(receipt, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(expected)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
elif operation == "validate":
    status = receipt.lstat()
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_uid != os.getuid()
        or stat.S_IMODE(status.st_mode) != 0o600
        or status.st_size != len(expected)
        or receipt.read_bytes() != expected
    ):
        raise SystemExit("owner-local Python bootstrap receipt is invalid")
else:
    raise SystemExit("unsupported receipt operation")
PY
}

validate_and_harden_runtime_tree() {
    runtime=$1
    "$SYSTEM_PYTHON" -I -B "$PROJECT_DIR/platforms/linux/scripts/runtime_safety.py" \
        harden-owner-tree --root "$runtime" >/dev/null
}

validate_installed_python() {
    require_private_directory "$INSTALL_ROOT"
    require_private_directory "$TARGET"
    validate_and_harden_runtime_tree "$TARGET" \
        || fail "owner-local Python tree validation or hardening failed"
    "$SYSTEM_PYTHON" -I -B - "$PROJECT_DIR" "$TARGET" <<'PY'
import pathlib
import sys

sys.path.insert(0, sys.argv[1])
from platforms.linux.scripts.runtime_safety import _safe_existing_chain

_safe_existing_chain(pathlib.Path(sys.argv[2]))
PY
    receipt_operation validate "$TARGET" \
        || fail "owner-local Python bootstrap receipt or tree digest is invalid"
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
    "$TARGET_PYTHON" -I -B - "$PROJECT_DIR" <<'PY'
import pathlib
import sys

sys.path.insert(0, sys.argv[1])
from platforms.linux.scripts.runtime_safety import _safe_existing_chain

_safe_existing_chain(pathlib.Path(sys.base_prefix))
PY
}

if [ "$MODE" = harden ]; then
    validate_installed_python
    printf 'PYTHON BOOTSTRAP PASS: %s\n' "$TARGET_PYTHON"
    exit 0
fi

if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
    validate_installed_python
    printf 'PYTHON BOOTSTRAP PASS: existing runtime %s\n' "$TARGET_PYTHON"
    exit 0
fi

make_private_directory "$HOME/.local"
make_private_directory "$HOME/.local/share"
make_private_directory "$CORELM_ROOT"
make_private_directory "$INSTALL_ROOT"

TEMP_DIRECTORY=$(mktemp -d "$INSTALL_ROOT/.corelm-python312-stage.XXXXXX") \
    || fail "could not create private Python staging directory"
/bin/chmod 700 "$TEMP_DIRECTORY"
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
[ "$(/usr/bin/stat -c '%s' "$ARCHIVE_PATH")" -eq "$ARCHIVE_SIZE" ] \
    || fail "Python archive byte length does not match the registered value"
actual_sha256=$(/usr/bin/sha256sum "$ARCHIVE_PATH" | /usr/bin/awk '{print $1}')
[ "$actual_sha256" = "$ARCHIVE_SHA256" ] \
    || fail "Python archive SHA-256 does not match the registered value"

"$SYSTEM_PYTHON" -I -B \
    "$PROJECT_DIR/security/validate_python_bootstrap_archive.py" \
    "$ARCHIVE_PATH" \
    || fail "Python archive topology validation failed"

/bin/tar --no-same-owner -xzf "$ARCHIVE_PATH" -C "$EXTRACT_ROOT"
[ -d "$EXTRACT_ROOT/python" ] \
    || fail "Python archive did not contain the expected root"
[ ! -L "$EXTRACT_ROOT/python" ] \
    || fail "Python archive root must not be a symlink"
validate_and_harden_runtime_tree "$EXTRACT_ROOT/python" \
    || fail "extracted Python tree validation or hardening failed"
receipt_operation create "$EXTRACT_ROOT/python" \
    || fail "could not create the exclusive bootstrap receipt"
validate_and_harden_runtime_tree "$EXTRACT_ROOT/python" \
    || fail "receipt changed the hardened runtime unexpectedly"
receipt_operation validate "$EXTRACT_ROOT/python" \
    || fail "new bootstrap receipt or tree digest validation failed"
[ ! -e "$TARGET" ] && [ ! -L "$TARGET" ] \
    || fail "target appeared during bootstrap: $TARGET"
/bin/mv "$EXTRACT_ROOT/python" "$TARGET"
validate_installed_python

printf '%s\n' \
    "SHA-256 PASS: $ARCHIVE_SHA256" \
    'Source: astral-sh/python-build-standalone immutable release 20260718' \
    "PYTHON BOOTSTRAP PASS: $TARGET_PYTHON" \
    'No sudo access or system Python modification was used.'
