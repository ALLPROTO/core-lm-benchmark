#!/bin/sh
set -eu

PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH
unset SWIFT_EXEC SDKROOT TOOLCHAINS CC CXX CPP CFLAGS CPPFLAGS CXXFLAGS \
    LDFLAGS LD_LIBRARY_PATH DYLD_LIBRARY_PATH DYLD_FRAMEWORK_PATH \
    DYLD_INSERT_LIBRARIES SWIFTPM_CUSTOM_BIN_DIR SWIFTPM_BUILD_DIR

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
BUILD_CONFIG=${BUILD_CONFIG:-release}
DEVELOPER_ID_APPLICATION=${DEVELOPER_ID_APPLICATION:-}
ALLOW_ADHOC_SIGNING=${ALLOW_ADHOC_SIGNING:-0}
APP_NAME="CoreLMBenchmark.app"
STAGING_DIR=$(mktemp -d "${TMPDIR:-/tmp}/corelm-app.XXXXXX")
PYTHON_CACHE_DIR="$STAGING_DIR/python-pycache"
APP_DIR="$STAGING_DIR/$APP_NAME"
FINAL_DIR="$PROJECT_DIR/dist/$APP_NAME"
DIST_DIR="$PROJECT_DIR/dist"
REAL_LLM_PYTHON=${CORELM_REAL_LLM_PYTHON:-"$HOME/.cache/corelm-app-runtime/bin/python"}
EXPECTED_PYTHON_SHA256=${CORELM_REAL_LLM_PYTHON_SHA256:-}
SOURCE_ARCHIVE_MANIFEST=${CORELM_SOURCE_ARCHIVE_MANIFEST:-}
ALLOW_DIRTY_SOURCE=${CORELM_ALLOW_DIRTY_SOURCE:-0}
PROVENANCE_BEFORE="$STAGING_DIR/build-provenance.before.json"
PROVENANCE_AFTER="$STAGING_DIR/build-provenance.after.json"
PROVENANCE_FINAL="$STAGING_DIR/build-provenance.final.json"
SWIFT_BUILD_DIR="$STAGING_DIR/swift-build"
BUILD_TMP_DIR="$STAGING_DIR/tmp"
TRASHED_PREVIOUS_APP=

fail() {
    printf 'APP PACKAGE FAIL: %s\n' "$*" >&2
    exit 1
}

require_owned_directory() {
    label=$1
    directory=$2
    [ -d "$directory" ] || fail "$label is not a directory: $directory"
    [ ! -L "$directory" ] || fail "$label must not be a symlink: $directory"
    owner=$(/usr/bin/stat -f '%u' "$directory" 2>/dev/null) \
        || fail "could not inspect $label ownership"
    [ "$owner" -eq "$(/usr/bin/id -u)" ] \
        || fail "$label is not owned by the current user"
    mode=$(/usr/bin/stat -f '%Lp' "$directory" 2>/dev/null) \
        || fail "could not inspect $label permissions"
    case "$mode" in
        *[2367][0-7]|*[0-7][2367])
            fail "$label is group/world-writable: $directory" ;;
    esac
}

prepare_dist_directory() {
    if [ -e "$DIST_DIR" ] || [ -L "$DIST_DIR" ]; then
        require_owned_directory "dist directory" "$DIST_DIR"
    else
        /bin/mkdir -m 700 "$DIST_DIR"
    fi
    resolved_dist=$(CDPATH= cd -- "$DIST_DIR" && pwd -P) \
        || fail "could not resolve dist directory"
    [ "$resolved_dist" = "$DIST_DIR" ] \
        || fail "dist directory escapes the physical project root"
}

trash_previous_app() {
    [ ! -L "$FINAL_DIR" ] \
        || fail "existing application must not be a symlink"
    require_owned_directory "existing application" "$FINAL_DIR"
    trash_directory="$HOME/.Trash"
    if [ -e "$trash_directory" ] || [ -L "$trash_directory" ]; then
        require_owned_directory "user Trash" "$trash_directory"
    else
        /bin/mkdir -m 700 "$trash_directory"
    fi
    trash_name="CoreLMBenchmark-previous-$(/bin/date -u +%Y%m%dT%H%M%SZ)-$$.app"
    TRASHED_PREVIOUS_APP="$trash_directory/$trash_name"
    [ ! -e "$TRASHED_PREVIOUS_APP" ] \
        && [ ! -L "$TRASHED_PREVIOUS_APP" ] \
        || fail "previous-app Trash destination already exists"
    /bin/mv "$FINAL_DIR" "$TRASHED_PREVIOUS_APP"
}

cleanup() {
    rm -rf "$STAGING_DIR"
}
trap cleanup EXIT
/bin/mkdir -m 700 "$BUILD_TMP_DIR"
prepare_dist_directory

cd "$PROJECT_DIR"
case "$ALLOW_DIRTY_SOURCE" in
    0|1)
        ;;
    *)
        printf '%s\n' 'CORELM_ALLOW_DIRTY_SOURCE must be 0 or 1.' >&2
        exit 1
        ;;
esac
set -- --project "$PROJECT_DIR"
if [ -n "$SOURCE_ARCHIVE_MANIFEST" ]; then
    set -- "$@" --archive-manifest "$SOURCE_ARCHIVE_MANIFEST"
fi
if [ "$ALLOW_DIRTY_SOURCE" = "1" ]; then
    set -- "$@" --allow-dirty
fi
/usr/bin/env -i \
    HOME="$HOME" \
    TMPDIR="$BUILD_TMP_DIR" \
    PATH="$PATH" \
    LANG=C \
    LC_ALL=C \
    /usr/bin/python3 -I -B \
    "$PROJECT_DIR/security/generate_build_provenance.py" \
    "$@" --output "$PROVENANCE_BEFORE"

/usr/bin/env -i \
    HOME="$HOME" \
    TMPDIR="$BUILD_TMP_DIR" \
    PATH="$PATH" \
    LANG=C \
    LC_ALL=C \
    /usr/bin/xcrun --sdk macosx swift build \
    -c "$BUILD_CONFIG" --scratch-path "$SWIFT_BUILD_DIR"

/usr/bin/env -i \
    HOME="$HOME" \
    TMPDIR="$BUILD_TMP_DIR" \
    PATH="$PATH" \
    LANG=C \
    LC_ALL=C \
    /usr/bin/python3 -I -B \
    "$PROJECT_DIR/security/generate_build_provenance.py" \
    "$@" --output "$PROVENANCE_AFTER"
if ! cmp -s "$PROVENANCE_BEFORE" "$PROVENANCE_AFTER"; then
    printf '%s\n' \
        'Source or Apple toolchain identity changed while building the app.' >&2
    exit 1
fi

mkdir -m 700 "$PYTHON_CACHE_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources/RealLLM"
cp "$SWIFT_BUILD_DIR/$BUILD_CONFIG/CoreLMBenchmarkApp" \
   "$APP_DIR/Contents/MacOS/CoreLMBenchmarkApp"
cp "$PROJECT_DIR/App/Info.plist" "$APP_DIR/Contents/Info.plist"
cp "$PROVENANCE_BEFORE" \
   "$APP_DIR/Contents/Resources/build-provenance.json"
for real_llm_file in \
    __init__.py \
    benchmark_real_llm.py \
    codecs.py \
    develop_voidtoken_v5.py \
    voidtoken_v5.py
do
    cp "$PROJECT_DIR/RealLLM/$real_llm_file" \
       "$APP_DIR/Contents/Resources/RealLLM/$real_llm_file"
done
if [ -n "$EXPECTED_PYTHON_SHA256" ]; then
    "$REAL_LLM_PYTHON" -I -B -X "pycache_prefix=$PYTHON_CACHE_DIR" \
        "$PROJECT_DIR/security/generate_python_runtime_manifest.py" \
        --python "$REAL_LLM_PYTHON" \
        --output "$APP_DIR/Contents/Resources/python-runtime-manifest.json" \
        --expected-python-sha256 "$EXPECTED_PYTHON_SHA256"
else
    "$REAL_LLM_PYTHON" -I -B -X "pycache_prefix=$PYTHON_CACHE_DIR" \
        "$PROJECT_DIR/security/generate_python_runtime_manifest.py" \
        --python "$REAL_LLM_PYTHON" \
        --output "$APP_DIR/Contents/Resources/python-runtime-manifest.json"
fi

# The bundle reads source files after compilation (the Python worker and
# manifests). Recheck once more after every source-dependent copy so a change
# in that interval cannot be signed into an app carrying stale provenance.
/usr/bin/env -i \
    HOME="$HOME" \
    TMPDIR="$BUILD_TMP_DIR" \
    PATH="$PATH" \
    LANG=C \
    LC_ALL=C \
    /usr/bin/python3 -I -B \
    "$PROJECT_DIR/security/generate_build_provenance.py" \
    "$@" --output "$PROVENANCE_FINAL"
if ! cmp -s "$PROVENANCE_BEFORE" "$PROVENANCE_FINAL"; then
    printf '%s\n' \
        'Source or Apple toolchain identity changed while staging the app.' >&2
    exit 1
fi

find "$APP_DIR" -type d -exec chmod 755 {} +
find "$APP_DIR/Contents/Resources" -type f -exec chmod 644 {} +
chmod 644 "$APP_DIR/Contents/Info.plist"
chmod 755 "$APP_DIR/Contents/MacOS/CoreLMBenchmarkApp"

if [ -n "$DEVELOPER_ID_APPLICATION" ]; then
    case "$DEVELOPER_ID_APPLICATION" in
        "Developer ID Application:"*)
            ;;
        *)
            printf '%s\n' \
                'DEVELOPER_ID_APPLICATION must name a Developer ID Application identity.' >&2
            exit 1
            ;;
    esac
    codesign --force --options runtime --timestamp \
        --sign "$DEVELOPER_ID_APPLICATION" "$APP_DIR"
elif [ "$ALLOW_ADHOC_SIGNING" = "1" ]; then
    codesign --force --options runtime --timestamp=none --sign - "$APP_DIR"
else
    printf '%s\n' \
        'Refusing an ambiguous package: set DEVELOPER_ID_APPLICATION for a public build' \
        'or explicitly set ALLOW_ADHOC_SIGNING=1 for a local/CI research build.' >&2
    exit 1
fi

codesign --verify --deep --strict "$APP_DIR"
"$PROJECT_DIR/security/verify_app_bundle.sh" "$APP_DIR"

if [ -e "$FINAL_DIR" ] || [ -L "$FINAL_DIR" ]; then
    trash_previous_app
fi
if ! /bin/mv "$APP_DIR" "$FINAL_DIR"; then
    if [ -n "$TRASHED_PREVIOUS_APP" ] \
        && [ -d "$TRASHED_PREVIOUS_APP" ] \
        && [ ! -e "$FINAL_DIR" ]
    then
        /bin/mv "$TRASHED_PREVIOUS_APP" "$FINAL_DIR" || true
    fi
    fail "could not install the newly staged application"
fi

if [ -n "$TRASHED_PREVIOUS_APP" ]; then
    printf 'Previous application moved to Trash: %s\n' \
        "$TRASHED_PREVIOUS_APP"
fi

printf '%s\n' "$FINAL_DIR"
