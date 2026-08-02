#!/bin/sh
set -eu

# Filesystem read-only preflight for the complete local macOS proof. Network
# probes issue HTTPS GET requests but do not download model or package files.

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
OFFLINE=${CORELM_OFFLINE:-0}
ASSETS_OFFLINE_ONLY=${CORELM_ASSETS_OFFLINE_ONLY:-$OFFLINE}
WHEELHOUSE=${CORELM_WHEELHOUSE:-}
PYPI_INDEX_URL=${CORELM_PYPI_INDEX_URL:-https://pypi.org/simple}
HF_ENDPOINT=${CORELM_HF_ENDPOINT:-https://huggingface.co}
CACHE_DIR="$HOME/.cache/corelm/macos/model-assets"
SKIP_GUI=0
SKIP_MEMORY_CHECK=0
CHECK_PACKAGES=1
CHECK_ASSETS=1
MINIMUM_FREE_GB=6
MINIMUM_MEMORY_GB=8

fail() {
    printf 'DOCTOR FAIL: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: ./corelm macos doctor [--no-gui] [--skip-memory-check] [--skip-packages] [--skip-assets]

Checks whether this Mac can run the complete local application proof. The
check does not install packages, create directories, or modify the repository.

Environment:
  CORELM_BOOTSTRAP_PYTHON  explicit Python 3.12.13 executable
  CORELM_OFFLINE=1         require a local wheelhouse and cached HF assets
  CORELM_WHEELHOUSE        absolute owner-controlled wheel directory
  CORELM_PYPI_INDEX_URL    HTTPS Python package index (online mode)
  CORELM_HF_ENDPOINT       HTTPS Hugging Face-compatible endpoint
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --no-gui) SKIP_GUI=1 ;;
        --skip-memory-check) SKIP_MEMORY_CHECK=1 ;;
        --skip-packages) CHECK_PACKAGES=0 ;;
        --skip-assets) CHECK_ASSETS=0 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown argument: $1" ;;
    esac
    shift
done

require_boolean() {
    case "$2" in
        0|1) ;;
        *) fail "$1 must be 0 or 1" ;;
    esac
}

validate_https_url() {
    label=$1
    value=$2
    "$bootstrap_path" -I -B - "$value" <<'PY' >/dev/null 2>&1 || fail \
        "$label must be an HTTPS URL without credentials, query, or fragment"
import sys
from urllib.parse import urlsplit

value = sys.argv[1]
parsed = urlsplit(value)
try:
    parsed.port
except ValueError:
    raise SystemExit(1)
valid = (
    parsed.scheme == "https"
    and parsed.hostname
    and parsed.username is None
    and parsed.password is None
    and not parsed.query
    and not parsed.fragment
    and "\\" not in value
    and not any(ord(character) <= 32 or ord(character) == 127 for character in value)
)
raise SystemExit(0 if valid else 1)
PY
}

require_private_directory() {
    label=$1
    directory=$2
    case "$directory" in
        /*) ;;
        *) fail "$label must be an absolute path" ;;
    esac
    [ -d "$directory" ] || fail "$label directory is missing: $directory"
    [ ! -L "$directory" ] || fail "$label must not be a symlink: $directory"
    canonical=$(
        "$bootstrap_path" -I -B -c \
            'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' \
            "$directory"
    ) || fail "could not resolve $label path"
    [ "$canonical" = "$directory" ] \
        || fail "$label path must be canonical and contain no symlink aliases"
    owner=$(/usr/bin/stat -f '%u' "$directory" 2>/dev/null) \
        || fail "could not inspect $label ownership"
    [ "$owner" -eq "$(/usr/bin/id -u)" ] \
        || fail "$label is not owned by the current user"
    mode=$(/usr/bin/stat -f '%Lp' "$directory" 2>/dev/null) \
        || fail "could not inspect $label permissions"
    case "$mode" in
        *[2367][0-7]|*[0-7][2367])
            fail "$label must not be group/world-writable: $directory" ;;
    esac
}

probe_https() {
    label=$1
    url=$2
    status=$(
        /usr/bin/curl \
            --silent \
            --show-error \
            --location \
            --proto '=https' \
            --proto-redir '=https' \
            --connect-timeout 10 \
            --max-time 20 \
            --output /dev/null \
            --write-out '%{http_code}' \
            "$url" 2>/dev/null || true
    )
    case "$status" in
        2??|3??) ;;
        *) fail "$label is unreachable over HTTPS (HTTP ${status:-none}): $url" ;;
    esac
    printf '  PASS  %s is reachable (HTTP %s)\n' "$label" "$status"
}

require_boolean CORELM_OFFLINE "$OFFLINE"
require_boolean CORELM_ASSETS_OFFLINE_ONLY "$ASSETS_OFFLINE_ONLY"
require_boolean internal-gui-check "$SKIP_GUI"
require_boolean internal-memory-check "$SKIP_MEMORY_CHECK"
require_boolean internal-package-check "$CHECK_PACKAGES"
require_boolean internal-asset-check "$CHECK_ASSETS"

[ "$(uname -s)" = Darwin ] || fail "macOS is required"
[ "$(uname -m)" = arm64 ] || fail "Apple Silicon (arm64) is required"
macos_version=$(sw_vers -productVersion)
macos_major=${macos_version%%.*}
case "$macos_major" in
    ''|*[!0-9]*) fail "could not determine the macOS version" ;;
esac
[ "$macos_major" -ge 14 ] || fail "macOS 14 or newer is required"
printf '  PASS  macOS %s on Apple Silicon\n' "$macos_version"

command -v swift >/dev/null 2>&1 \
    || fail "Swift is missing; run xcode-select --install"
swift_version=$(swift --version 2>&1 | /usr/bin/awk '
    match($0, /Swift version [0-9]+\.[0-9]+/) {
        value = substr($0, RSTART, RLENGTH)
        sub(/^Swift version /, "", value)
        print value
        exit
    }
')
case "$swift_version" in
    ''|*[!0-9.]*) fail "could not determine the Swift version" ;;
esac
swift_major=${swift_version%%.*}
[ "$swift_major" -ge 6 ] \
    || fail "Swift 6 or newer is required; update Command Line Tools or Xcode"
command -v codesign >/dev/null 2>&1 \
    || fail "codesign is missing; run xcode-select --install"
printf '  PASS  Swift %s and codesign are available\n' "$swift_version"

bootstrap_path=$("$PROJECT_DIR/security/find_python312.sh" || true)
[ -n "$bootstrap_path" ] || fail \
    "Python 3.12.13 is missing; run ./corelm macos bootstrap or set CORELM_BOOTSTRAP_PYTHON"
"$bootstrap_path" -I -B -c '
import pathlib
import sys

project = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(project))
from security.manage_local_runtime import _safe_existing_chain

_safe_existing_chain(pathlib.Path(sys.base_prefix))
' "$PROJECT_DIR" || fail \
    "Python 3.12.13 base prefix is writable or untrusted; run ./corelm macos bootstrap for the pinned owner-local runtime"
python_version=$("$bootstrap_path" -I -B -c \
    'import platform; print(platform.python_version())')
printf '  PASS  trusted Python %s at %s\n' \
    "$python_version" "$bootstrap_path"

available_kb=$(df -Pk "$HOME" 2>/dev/null | /usr/bin/awk 'NR == 2 {print $4}')
case "$available_kb" in
    ''|*[!0-9]*) fail "could not determine free disk space for HOME" ;;
esac
required_kb=$((MINIMUM_FREE_GB * 1024 * 1024))
[ "$available_kb" -ge "$required_kb" ] || fail \
    "at least ${MINIMUM_FREE_GB} GiB free is required under HOME"
available_gb=$((available_kb / 1024 / 1024))
printf '  PASS  %s GiB free under HOME (minimum %s GiB)\n' \
    "$available_gb" "$MINIMUM_FREE_GB"
project_available_kb=$(df -Pk "$PROJECT_DIR" 2>/dev/null \
    | /usr/bin/awk 'NR == 2 {print $4}')
case "$project_available_kb" in
    ''|*[!0-9]*) fail "could not determine free disk space for the checkout" ;;
esac
[ "$project_available_kb" -ge $((1024 * 1024)) ] \
    || fail "at least 1 GiB free is required on the checkout filesystem"
if [ "$SKIP_MEMORY_CHECK" = 1 ]; then
    printf '%s\n' \
        '  SKIP  installed-memory check was explicitly disabled for build-only packaging'
else
    physical_memory_bytes=$(/usr/sbin/sysctl -n hw.memsize 2>/dev/null || true)
    case "$physical_memory_bytes" in
        ''|*[!0-9]*) fail "could not determine installed physical memory" ;;
    esac
    minimum_memory_bytes=$((MINIMUM_MEMORY_GB * 1024 * 1024 * 1024))
    [ "$physical_memory_bytes" -ge "$minimum_memory_bytes" ] \
        || fail "at least ${MINIMUM_MEMORY_GB} GiB unified memory is required"
    physical_memory_gb=$((physical_memory_bytes / 1024 / 1024 / 1024))
    printf '  PASS  %s GiB unified memory (minimum %s GiB)\n' \
        "$physical_memory_gb" "$MINIMUM_MEMORY_GB"
fi

if [ "$SKIP_GUI" = 0 ]; then
    current_uid=$(/usr/bin/id -u)
    console_uid=$(/usr/bin/stat -f '%u' /dev/console 2>/dev/null || true)
    [ "$console_uid" = "$current_uid" ] \
        || fail "run from the currently logged-in macOS desktop user"
    /bin/launchctl print "gui/$current_uid" >/dev/null 2>&1 \
        || fail "an active macOS GUI session is required"
    printf '  PASS  active GUI session belongs to the current user\n'
fi

for utility in /usr/bin/memory_pressure /usr/bin/openssl /usr/bin/shlock; do
    [ -x "$utility" ] || fail "required macOS utility is missing: $utility"
done

if [ "$CHECK_PACKAGES" = 0 ]; then
    printf '  SKIP  package source check was explicitly disabled\n'
elif [ -n "$WHEELHOUSE" ]; then
    require_private_directory "wheelhouse" "$WHEELHOUSE"
    printf '  PASS  hash-locked wheelhouse is available at %s\n' "$WHEELHOUSE"
elif [ "$OFFLINE" = 1 ]; then
    fail "CORELM_OFFLINE=1 requires CORELM_WHEELHOUSE"
else
    validate_https_url CORELM_PYPI_INDEX_URL "$PYPI_INDEX_URL"
    probe_https "Python package index" "$PYPI_INDEX_URL"
fi

if [ "$CHECK_ASSETS" = 0 ]; then
    printf '  SKIP  model/data source check was explicitly disabled\n'
elif [ "$OFFLINE" = 1 ] || [ "$ASSETS_OFFLINE_ONLY" = 1 ]; then
    require_private_directory "model cache" "$CACHE_DIR"
    printf '  PASS  offline model cache is available at %s\n' "$CACHE_DIR"
else
    validate_https_url CORELM_HF_ENDPOINT "$HF_ENDPOINT"
    probe_https "model/data endpoint" "$HF_ENDPOINT"
fi

printf '%s\n' \
    'DOCTOR PASS: this Mac satisfies the early proof prerequisites.' \
    "Resolved Python: $bootstrap_path"
