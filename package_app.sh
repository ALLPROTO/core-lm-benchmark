#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUILD_CONFIG=${BUILD_CONFIG:-release}
DEVELOPER_ID_APPLICATION=${DEVELOPER_ID_APPLICATION:-}
ALLOW_ADHOC_SIGNING=${ALLOW_ADHOC_SIGNING:-0}
APP_NAME="CoreLMBenchmark.app"
STAGING_DIR=$(mktemp -d "${TMPDIR:-/tmp}/corelm-app.XXXXXX")
PYTHON_CACHE_DIR="$STAGING_DIR/python-pycache"
APP_DIR="$STAGING_DIR/$APP_NAME"
FINAL_DIR="$PROJECT_DIR/dist/$APP_NAME"
REAL_LLM_PYTHON=${CORELM_REAL_LLM_PYTHON:-"$HOME/.cache/corelm-app-runtime/bin/python"}
EXPECTED_PYTHON_SHA256=${CORELM_REAL_LLM_PYTHON_SHA256:-}

cleanup() {
    rm -rf "$STAGING_DIR"
}
trap cleanup EXIT

cd "$PROJECT_DIR"
swift build -c "$BUILD_CONFIG"

mkdir -m 700 "$PYTHON_CACHE_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources/RealLLM"
cp "$PROJECT_DIR/.build/$BUILD_CONFIG/CoreLMBenchmarkApp" \
   "$APP_DIR/Contents/MacOS/CoreLMBenchmarkApp"
cp "$PROJECT_DIR/App/Info.plist" "$APP_DIR/Contents/Info.plist"
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

mkdir -p "$PROJECT_DIR/dist"
if [ -e "$FINAL_DIR" ]; then
    rm -rf "$FINAL_DIR"
fi
mv "$APP_DIR" "$FINAL_DIR"

printf '%s\n' "$FINAL_DIR"
