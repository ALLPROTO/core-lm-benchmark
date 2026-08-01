#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
APP_PATH=${1:-"$PROJECT_DIR/dist/CoreLMBenchmark.app"}

if [ ! -d "$APP_PATH/Contents" ]; then
    printf 'missing application bundle: %s\n' "$APP_PATH" >&2
    exit 1
fi

PLIST="$APP_PATH/Contents/Info.plist"
EXECUTABLE="$APP_PATH/Contents/MacOS/CoreLMBenchmarkApp"
RUNTIME_MANIFEST="$APP_PATH/Contents/Resources/python-runtime-manifest.json"
BUILD_PROVENANCE="$APP_PATH/Contents/Resources/build-provenance.json"

plutil -lint "$PLIST"
test -x "$EXECUTABLE"
test -s "$RUNTIME_MANIFEST"
test -s "$BUILD_PROVENANCE"
/usr/bin/python3 -I -B \
    "$PROJECT_DIR/security/generate_build_provenance.py" \
    --verify "$BUILD_PROVENANCE"
/usr/bin/python3 -I -B -c '
import json
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
if path.stat().st_size > 32 * 1024 * 1024:
    raise SystemExit("runtime manifest exceeds 32 MiB")
value = json.loads(path.read_bytes())
if value.get("schemaVersion") != "corelm-python-runtime-manifest-v1":
    raise SystemExit("unexpected runtime manifest schema")
' "$RUNTIME_MANIFEST"

identifier=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$PLIST")
if [ "$identifier" != "com.corelm.benchmark" ]; then
    printf 'unexpected bundle identifier: %s\n' "$identifier" >&2
    exit 1
fi

if /usr/libexec/PlistBuddy -c 'Print :LSEnvironment' "$PLIST" >/dev/null 2>&1; then
    printf 'release bundle must not inject executables through LSEnvironment\n' >&2
    exit 1
fi

if [ -e "$APP_PATH/Contents/Resources/BenchmarkCore" ]; then
    printf 'release bundle must not contain the synthetic BenchmarkCore\n' >&2
    exit 1
fi

resource_file_count=$(find "$APP_PATH/Contents/Resources" -type f -print \
    | wc -l | tr -d '[:space:]')
if [ "$resource_file_count" -ne 7 ]; then
    printf 'release bundle must contain exactly seven declared resources\n' >&2
    exit 1
fi

if LC_ALL=C grep -R -a -E -i \
    'BenchmarkCore|corelm_benchmark|synthetic' \
    "$APP_PATH/Contents/Resources/RealLLM" >/dev/null 2>&1
then
    printf 'release worker contains a forbidden development-only reference\n' >&2
    exit 1
fi

for relative in \
    RealLLM/__init__.py \
    RealLLM/app_proof_core.py \
    RealLLM/app_proof_runner.py \
    RealLLM/codecs.py \
    RealLLM/voidtoken_v5.py
do
    source_path="$PROJECT_DIR/$relative"
    bundled_path="$APP_PATH/Contents/Resources/$relative"
    if [ ! -f "$bundled_path" ]; then
        printf 'missing bundled source: %s\n' "$relative" >&2
        exit 1
    fi
    cmp "$source_path" "$bundled_path"
done
/usr/bin/python3 -I -B \
    "$PROJECT_DIR/security/generate_app_proof_core.py" \
    --verify "$APP_PATH/Contents/Resources/RealLLM/app_proof_core.py"

for forbidden_runner in \
    RealLLM/benchmark_real_llm.py \
    RealLLM/develop_voidtoken_v5.py
do
    if [ -e "$APP_PATH/Contents/Resources/$forbidden_runner" ]; then
        printf 'release bundle contains development engine: %s\n' \
            "$forbidden_runner" >&2
        exit 1
    fi
done

if find "$APP_PATH" -type l -print | grep -q .; then
    printf 'unexpected symbolic link in application bundle\n' >&2
    exit 1
fi

if find "$APP_PATH" -perm -0002 -print | grep -q .; then
    printf 'world-writable path in application bundle\n' >&2
    exit 1
fi

signature=$(codesign --display --verbose=4 "$APP_PATH" 2>&1)
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
printf '%s\n' "$signature" | grep -q '^Identifier=com\.corelm\.benchmark$'
printf '%s\n' "$signature" | grep -Eq '^CodeDirectory .*flags=.*\(.*runtime.*\)'

if [ "${REQUIRE_DEVELOPER_ID:-0}" = "1" ]; then
    if printf '%s\n' "$signature" | grep -q '^Signature=adhoc$'; then
        printf '%s\n' \
            'Developer ID signature required, but bundle is ad-hoc signed.' >&2
        exit 1
    fi
    printf '%s\n' "$signature" \
        | grep -q '^Authority=Developer ID Application: '
    if printf '%s\n' "$signature" | grep -q '^TeamIdentifier=not set$'; then
        printf '%s\n' \
            'Developer ID build has no Apple TeamIdentifier.' >&2
        exit 1
    fi
fi
file "$EXECUTABLE"

if printf '%s\n' "$signature" | grep -q '^Signature=adhoc$'; then
    signing='ad-hoc (local/CI only)'
else
    signing='Developer ID'
fi
printf '%s\n' \
    "APP BUNDLE PASS: resources, source/build provenance, Python-runtime manifest, structure, identifier, hardened runtime, and $signing signature are consistent."
