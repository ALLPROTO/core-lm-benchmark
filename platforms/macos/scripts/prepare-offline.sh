#!/bin/sh
set -eu

# Run once while connected. This fills a hash-checked local wheelhouse and the
# registered Hugging Face cache so a later fresh proof can run without network.

umask 077

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
WHEELHOUSE=${CORELM_WHEELHOUSE:-"$HOME/.cache/corelm/macos/wheelhouse"}
PYPI_INDEX_URL=${CORELM_PYPI_INDEX_URL:-https://pypi.org/simple}
DOWNLOADER_DIR=

fail() {
    printf 'OFFLINE INPUT PREPARATION FAIL: %s\n' "$*" >&2
    exit 1
}

cleanup_downloader() {
    [ -n "$DOWNLOADER_DIR" ] || return 0
    case "$DOWNLOADER_DIR" in
        "$WHEELHOUSE"/.corelm-pip-download.*)
            /bin/rm -rf -- "$DOWNLOADER_DIR"
            DOWNLOADER_DIR=
            ;;
        *) fail "refusing cleanup outside the temporary downloader directory" ;;
    esac
}

stop_downloader() {
    trap - EXIT HUP INT TERM
    cleanup_downloader
    exit 130
}

trap cleanup_downloader EXIT
trap stop_downloader HUP INT TERM

prepare_wheelhouse() {
    DOWNLOADER_DIR=$(mktemp -d "$WHEELHOUSE/.corelm-pip-download.XXXXXX") \
        || fail "cannot create private downloader staging directory"
    /bin/chmod 700 "$DOWNLOADER_DIR"
    downloader_runtime="$DOWNLOADER_DIR/runtime"
    downloader_python="$downloader_runtime/bin/python"
    downloader_state=$(
        "$bootstrap_path" -I -B "$PROJECT_DIR/security/manage_local_runtime.py" \
            --path "$downloader_runtime" --project "$PROJECT_DIR" --mode preflight
    ) || fail "temporary downloader path failed ownership validation"
    [ "$downloader_state" = new ] || fail "temporary downloader must be fresh"
    "$bootstrap_path" -I -B -m venv "$downloader_runtime"
    "$bootstrap_path" -I -B "$PROJECT_DIR/security/manage_local_runtime.py" \
        --path "$downloader_runtime" --project "$PROJECT_DIR" --mode initialize

    # The venv initially contains the trusted Python bootstrap's bundled pip.
    # Limit that older installer to one pinned, hash-checked official PyPI wheel.
    # Never use an optional mirror or install into the base Python environment.
    PIP_CONFIG_FILE=/dev/null "$downloader_python" -I -B -m pip install \
        --isolated --no-input --disable-pip-version-check --no-cache-dir \
        --no-deps --only-binary=:all: --index-url https://pypi.org/simple \
        --require-hashes -r "$PROJECT_DIR/.github/locks/pip-maintained.txt"
    PIP_CONFIG_FILE=/dev/null "$downloader_python" -I -B -m pip check
    "$downloader_python" -I -B "$PROJECT_DIR/security/verify_locked_environment.py" \
        --runtime "$downloader_runtime" \
        --lock "$PROJECT_DIR/.github/locks/pip-maintained.txt"

    printf 'Downloading only registered hash-locked wheels into %s\n' "$WHEELHOUSE"
    PIP_CONFIG_FILE=/dev/null "$downloader_python" -I -B -m pip download \
        --isolated --no-input --disable-pip-version-check --no-cache-dir \
        --only-binary=:all: --index-url "$PYPI_INDEX_URL" \
        --require-hashes --dest "$WHEELHOUSE" \
        -r "$PROJECT_DIR/.github/locks/pip-maintained.txt" \
        -r "$PROJECT_DIR/.github/locks/real-llm-portable-py312.txt"
    cleanup_downloader
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
physical_wheelhouse=$(CDPATH= cd -- "$WHEELHOUSE" && pwd -P) \
    || fail "cannot resolve the wheelhouse"
[ "$physical_wheelhouse" = "$WHEELHOUSE" ] \
    || fail "wheelhouse must be canonical and contain no symlink aliases"

CORELM_WHEELHOUSE="$WHEELHOUSE" \
CORELM_ASSETS_OFFLINE_ONLY=1 \
    "$PROJECT_DIR/platforms/macos/scripts/doctor.sh" --no-gui --skip-assets

bootstrap_path=$("$PROJECT_DIR/security/find_python312.sh" || true)
[ -n "$bootstrap_path" ] \
    || fail "Python 3.12.13 is missing; run ./corelm macos bootstrap"

prepare_wheelhouse

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
