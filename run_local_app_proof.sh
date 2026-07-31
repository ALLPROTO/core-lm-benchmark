#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APP_PATH="$PROJECT_DIR/dist/CoreLMBenchmark.app"
RESULTS_ROOT="$HOME/Library/Application Support/CoreLMBenchmark/real-llm-results"
RUNTIME_PARENT="$HOME/.cache/corelm-proof-runtimes"
PROOF_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
RUNTIME_DIR="$RUNTIME_PARENT/$PROOF_ID"
MARKER=$(mktemp "${TMPDIR:-/tmp}/corelm-proof.XXXXXX")
VERIFY_CACHE=$(mktemp -d "${TMPDIR:-/tmp}/corelm-verify-pycache.XXXXXX")

cleanup() {
    rm -f "$MARKER"
    rm -rf "$VERIFY_CACHE"
}
trap cleanup EXIT

if [ -n "${CORELM_REAL_LLM_VENV:-}" ]; then
    printf '%s\n' \
        'run_local_app_proof.sh requires a fresh runtime and does not accept' \
        'CORELM_REAL_LLM_VENV; use build_local_app.sh for an existing venv.' >&2
    exit 1
fi
mkdir -p "$RUNTIME_PARENT"
chmod 700 "$RUNTIME_PARENT"
export CORELM_REAL_LLM_VENV="$RUNTIME_DIR"
CORELM_SKIP_RUNTIME_INSTALL=0 \
CORELM_SKIP_ASSET_PREPARATION=0 \
CORELM_ASSETS_OFFLINE_ONLY=0 \
CORELM_SKIP_MPS_CHECK=0 \
CORELM_SKIP_SMOKE_TEST=0 \
CORELM_REAL_LLM_PYTHON_SHA256= \
BUILD_CONFIG=release \
    "$PROJECT_DIR/build_local_app.sh"

[ -d "$APP_PATH/Contents" ] || {
    printf 'missing local application: %s\n' "$APP_PATH" >&2
    exit 1
}

PYTHON_BIN="$RUNTIME_DIR/bin/python" "$PROJECT_DIR/run_tests.sh"
"$PROJECT_DIR/security/run_swift_security_tests.sh"

touch "$MARKER"
challenge=$(/usr/bin/openssl rand -hex 32)
printf '%s\n' \
    'Launching the visible 8-block Qwen proof run.' \
    'The app exits automatically when the run finishes (up to 10 minutes).'
open -W -n "$APP_PATH" --args \
    --real-llm-smoke-run \
    --proof-challenge "$challenge"

run_directory=
run_count=0
if [ -d "$RESULTS_ROOT" ]; then
    for candidate in "$RESULTS_ROOT"/*; do
        [ -d "$candidate" ] || continue
        [ ! -L "$candidate" ] || continue
        [ "$candidate" -nt "$MARKER" ] || continue
        [ -f "$candidate/validation-064-071.json" ] || continue
        [ -f "$candidate/app-run-receipt.json" ] || continue
        run_directory=$candidate
        run_count=$((run_count + 1))
    done
fi

[ "$run_count" -eq 1 ] || {
    printf 'expected one fresh complete app run, found %s\n' "$run_count" >&2
    exit 1
}

"$PROJECT_DIR/security/verify_app_bundle.sh" "$APP_PATH"
"$RUNTIME_DIR/bin/python" -I -B -X "pycache_prefix=$VERIFY_CACHE" \
    "$PROJECT_DIR/security/verify_local_app_run.py" \
    --run-directory "$run_directory" \
    --app "$APP_PATH" \
    --challenge "$challenge"

printf '%s\n' \
    'END-TO-END PROOF PASS: the locally built app ran pinned Qwen on MPS,' \
    'created fresh compressed KV containers, replayed them, and passed an' \
    'independent result/receipt/app integrity check.' \
    "Fresh proof runtime retained at: $RUNTIME_DIR"
