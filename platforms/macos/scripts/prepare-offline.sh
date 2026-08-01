#!/bin/sh
set -eu

# Run once while connected. This fills a hash-checked local wheelhouse and the
# registered Hugging Face cache so a later fresh proof can run without network.

umask 077

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
WHEELHOUSE=${CORELM_WHEELHOUSE:-"$HOME/.cache/corelm/macos/wheelhouse"}
PYPI_INDEX_URL=${CORELM_PYPI_INDEX_URL:-https://pypi.org/simple}

fail() {
    printf 'OFFLINE INPUT PREPARATION FAIL: %s\n' "$*" >&2
    exit 1
}

[ "${CORELM_OFFLINE:-0}" = 0 ] \
    || fail "run this preparation command while connected with CORELM_OFFLINE=0"
case "$WHEELHOUSE" in
    /*) ;;
    *) fail "CORELM_WHEELHOUSE must be an absolute path" ;;
esac

# Check the package endpoint before creating anything. Asset endpoint and GUI
# availability are checked by the normal build below.
CORELM_WHEELHOUSE= \
CORELM_ASSETS_OFFLINE_ONLY=1 \
    "$PROJECT_DIR/platforms/macos/scripts/doctor.sh" --no-gui --skip-assets

if [ -e "$WHEELHOUSE" ]; then
    [ -d "$WHEELHOUSE" ] || fail "wheelhouse path is not a directory"
    [ ! -L "$WHEELHOUSE" ] || fail "wheelhouse must not be a symlink"
    owner=$(/usr/bin/stat -f '%u' "$WHEELHOUSE" 2>/dev/null) \
        || fail "could not inspect the wheelhouse"
    [ "$owner" -eq "$(/usr/bin/id -u)" ] \
        || fail "wheelhouse is not owned by the current user"
else
    /bin/mkdir -p "$WHEELHOUSE"
fi
/bin/chmod 700 "$WHEELHOUSE"

CORELM_WHEELHOUSE="$WHEELHOUSE" \
CORELM_ASSETS_OFFLINE_ONLY=1 \
    "$PROJECT_DIR/platforms/macos/scripts/doctor.sh" --no-gui --skip-assets

bootstrap_path=$("$PROJECT_DIR/security/find_python312.sh" || true)
[ -n "$bootstrap_path" ] \
    || fail "Python 3.12 is missing; run ./corelm macos bootstrap"

printf 'Downloading only registered hash-locked wheels into %s\n' "$WHEELHOUSE"
"$bootstrap_path" -I -B -m pip download \
    --isolated \
    --no-input \
    --disable-pip-version-check \
    --only-binary=:all: \
    --index-url "$PYPI_INDEX_URL" \
    --require-hashes \
    --dest "$WHEELHOUSE" \
    -r "$PROJECT_DIR/.github/locks/pip-bootstrap.txt" \
    -r "$PROJECT_DIR/RealLLM/requirements.lock"

# Installing exclusively from the new wheelhouse exercises it immediately;
# the same build also downloads and digest-verifies the pinned model/data.
CORELM_WHEELHOUSE="$WHEELHOUSE" \
CORELM_OFFLINE=0 \
CORELM_ASSETS_OFFLINE_ONLY=0 \
    "$PROJECT_DIR/platforms/macos/scripts/build-app.sh"

printf '%s\n' \
    'OFFLINE INPUT PREPARATION PASS' \
    "Wheelhouse: $WHEELHOUSE" \
    "Model/data cache: $HOME/.cache/corelm/macos/model-assets" \
    'Run a network-free fresh proof with:' \
    "CORELM_OFFLINE=1 CORELM_WHEELHOUSE=\"$WHEELHOUSE\" ./corelm macos proof"
