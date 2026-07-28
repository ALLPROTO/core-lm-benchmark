#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUILD_CONFIG=${BUILD_CONFIG:-release}
APP_NAME="CoreLMBenchmark.app"
STAGING_DIR=$(mktemp -d "${TMPDIR:-/tmp}/corelm-app.XXXXXX")
APP_DIR="$STAGING_DIR/$APP_NAME"
FINAL_DIR="$PROJECT_DIR/dist/$APP_NAME"

cleanup() {
    rm -rf "$STAGING_DIR"
}
trap cleanup EXIT

cd "$PROJECT_DIR"
swift build -c "$BUILD_CONFIG"

mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources/BenchmarkCore"
cp "$PROJECT_DIR/.build/$BUILD_CONFIG/CoreLMBenchmarkApp" \
   "$APP_DIR/Contents/MacOS/CoreLMBenchmarkApp"
cp "$PROJECT_DIR/App/Info.plist" "$APP_DIR/Contents/Info.plist"
cp "$PROJECT_DIR/BenchmarkCore/corelm_benchmark.py" \
   "$APP_DIR/Contents/Resources/BenchmarkCore/corelm_benchmark.py"

mkdir -p "$PROJECT_DIR/dist"
if [ -e "$FINAL_DIR" ]; then
    rm -rf "$FINAL_DIR"
fi
mv "$APP_DIR" "$FINAL_DIR"
codesign --force --deep --sign - "$FINAL_DIR"
codesign --verify --deep --strict "$FINAL_DIR"

printf '%s\n' "$FINAL_DIR"
