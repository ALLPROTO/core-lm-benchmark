#!/bin/sh
set -eu

umask 077

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APP_PATH="$PROJECT_DIR/dist/CoreLMBenchmark.app"
APP_EXECUTABLE="$APP_PATH/Contents/MacOS/CoreLMBenchmarkApp"
RESULTS_ROOT="$HOME/Library/Application Support/CoreLMBenchmark/real-llm-results"
RUNTIME_PARENT="$HOME/.cache/corelm-proof-runtimes"
PROOF_LOCK_FILE="$RUNTIME_PARENT/.proof-run.lock"
OFFLINE=${CORELM_OFFLINE:-0}
WHEELHOUSE=${CORELM_WHEELHOUSE:-}
PYPI_INDEX_URL=${CORELM_PYPI_INDEX_URL:-https://pypi.org/simple}
HF_ENDPOINT=${CORELM_HF_ENDPOINT:-https://huggingface.co}
PROOF_TIMEOUT_SECONDS=300
WATCHDOG_INTERVAL_SECONDS=2
MINIMUM_FREE_MEMORY_PERCENT=15
PROOF_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
RUNTIME_DIR="$RUNTIME_PARENT/$PROOF_ID"
MARKER=$(mktemp "${TMPDIR:-/tmp}/corelm-proof.XXXXXX")
VERIFY_CACHE=$(mktemp -d "${TMPDIR:-/tmp}/corelm-verify-pycache.XXXXXX")
PROOF_PROCESS_TMP=$(mktemp -d "${TMPDIR:-/tmp}/corelm-proof-process.XXXXXX")
TIMEOUT_REASON=$(mktemp "${TMPDIR:-/tmp}/corelm-timeout.XXXXXX")
MEMORY_REASON=$(mktemp "${TMPDIR:-/tmp}/corelm-memory.XXXXXX")
APP_PID=
TIMEOUT_WATCHDOG_PID=
MEMORY_WATCHDOG_PID=
LOCK_ACQUIRED=0
challenge=

run_clean() {
    /usr/bin/env -i \
        HOME="$HOME" \
        TMPDIR="$PROOF_PROCESS_TMP" \
        PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        LANG=C \
        LC_ALL=C \
        "$@"
}

fail() {
    printf 'END-TO-END PROOF FAIL: %s\n' "$*" >&2
    exit 1
}

memory_free_percent() {
    memory_report=$(/usr/bin/memory_pressure -Q 2>/dev/null || :)
    memory_percent=$(printf '%s\n' "$memory_report" | /usr/bin/awk '
        /System-wide memory free percentage:/ {
            gsub(/%/, "", $NF)
            print $NF
            exit
        }
    ')
    case "$memory_percent" in
        ''|*[!0-9]*) return 1 ;;
    esac
    printf '%s\n' "$memory_percent"
}

terminate_proof_tree() {
    proof_target_pid=$1
    case "$proof_target_pid" in
        ''|*[!0-9]*) return ;;
    esac

    proof_child_pids=$(
        /usr/bin/pgrep -P "$proof_target_pid" 2>/dev/null || :
    )
    for proof_child_pid in $proof_child_pids; do
        case "$proof_child_pid" in
            ''|*[!0-9]*) continue ;;
        esac
        /bin/kill -TERM -- "-$proof_child_pid" 2>/dev/null || :
        /bin/kill -TERM "$proof_child_pid" 2>/dev/null || :
    done

    if [ -n "$proof_child_pids" ]; then
        /bin/sleep 2
    fi
    for proof_child_pid in $proof_child_pids; do
        case "$proof_child_pid" in
            ''|*[!0-9]*) continue ;;
        esac
        /bin/kill -KILL -- "-$proof_child_pid" 2>/dev/null || :
        /bin/kill -KILL "$proof_child_pid" 2>/dev/null || :
    done
    if /bin/kill -0 "$proof_target_pid" 2>/dev/null; then
        /bin/kill -TERM "$proof_target_pid" 2>/dev/null || :
        /bin/sleep 1
        /bin/kill -KILL "$proof_target_pid" 2>/dev/null || :
    fi
}

timeout_watchdog() {
    trap - 0 1 2 15
    watchdog_elapsed=0
    while /bin/kill -0 "$APP_PID" 2>/dev/null; do
        if [ "$watchdog_elapsed" -ge "$PROOF_TIMEOUT_SECONDS" ]; then
            printf 'hard timeout after %s seconds\n' \
                "$PROOF_TIMEOUT_SECONDS" >"$TIMEOUT_REASON"
            terminate_proof_tree "$APP_PID"
            return
        fi
        /bin/sleep "$WATCHDOG_INTERVAL_SECONDS"
        watchdog_elapsed=$((watchdog_elapsed + WATCHDOG_INTERVAL_SECONDS))
    done
}

memory_watchdog() {
    trap - 0 1 2 15
    while /bin/kill -0 "$APP_PID" 2>/dev/null; do
        if ! watchdog_free_percent=$(memory_free_percent); then
            printf '%s\n' 'memory-pressure monitor became unavailable' \
                >"$MEMORY_REASON"
            terminate_proof_tree "$APP_PID"
            return
        fi
        if [ "$watchdog_free_percent" -lt "$MINIMUM_FREE_MEMORY_PERCENT" ]; then
            printf 'system free memory fell to %s%% (minimum %s%%)\n' \
                "$watchdog_free_percent" "$MINIMUM_FREE_MEMORY_PERCENT" \
                >"$MEMORY_REASON"
            terminate_proof_tree "$APP_PID"
            return
        fi
        /bin/sleep "$WATCHDOG_INTERVAL_SECONDS"
    done
}

cleanup() {
    for watchdog_pid in "$TIMEOUT_WATCHDOG_PID" "$MEMORY_WATCHDOG_PID"; do
        case "$watchdog_pid" in
            ''|*[!0-9]*) continue ;;
        esac
        /bin/kill -TERM "$watchdog_pid" 2>/dev/null || :
        wait "$watchdog_pid" 2>/dev/null || :
    done
    if [ -n "$APP_PID" ] && /bin/kill -0 "$APP_PID" 2>/dev/null; then
        terminate_proof_tree "$APP_PID"
    fi
    rm -f "$MARKER"
    rm -rf "$VERIFY_CACHE"
    rm -rf "$PROOF_PROCESS_TMP"
    rm -f "$TIMEOUT_REASON" "$MEMORY_REASON"
    if [ "$LOCK_ACQUIRED" = 1 ]; then
        rm -f "$PROOF_LOCK_FILE"
    fi
}
trap cleanup EXIT

case "$OFFLINE" in
    0|1) ;;
    *) fail "CORELM_OFFLINE must be 0 or 1" ;;
esac
[ -z "${CORELM_SWIFT_GATE_TEST_MODE:-}" ] \
    || fail "proof runs do not accept Swift gate test mode"
if [ "${CORELM_PROOF_CHALLENGE+x}" = x ]; then
    challenge=$(
        "$PROJECT_DIR/security/validate_proof_challenge.sh" \
            "$CORELM_PROOF_CHALLENGE"
    ) || fail \
        "CORELM_PROOF_CHALLENGE must be exactly 64 lowercase hex characters"
fi

if [ -n "${CORELM_REAL_LLM_VENV:-}" ]; then
    printf '%s\n' \
        'run_local_app_proof.sh requires a fresh runtime and does not accept' \
        'CORELM_REAL_LLM_VENV; use build_local_app.sh for an existing venv.' >&2
    exit 1
fi
mkdir -p "$RUNTIME_PARENT"
[ ! -L "$RUNTIME_PARENT" ] \
    || fail "proof runtime parent must not be a symlink"
runtime_parent_owner=$(/usr/bin/stat -f '%u' "$RUNTIME_PARENT" 2>/dev/null) \
    || fail "could not inspect proof runtime parent"
[ "$runtime_parent_owner" -eq "$(/usr/bin/id -u)" ] \
    || fail "proof runtime parent is not owned by the current user"
chmod 700 "$RUNTIME_PARENT"
/usr/bin/shlock -p "$$" -f "$PROOF_LOCK_FILE" \
    || fail "another local proof is already running"
LOCK_ACQUIRED=1

if [ "${CORELM_BOOTSTRAP_PYTHON+x}" = x ]; then
    bootstrap_path=$(run_clean \
        CORELM_BOOTSTRAP_PYTHON="$CORELM_BOOTSTRAP_PYTHON" \
        "$PROJECT_DIR/security/find_python312.sh") \
        || fail "explicit Python 3.12 bootstrap is invalid"
else
    bootstrap_path=$(run_clean \
        "$PROJECT_DIR/security/find_python312.sh") \
        || fail "Python 3.12 is missing; run ./bootstrap_python312_macos.sh"
fi

run_clean \
    CORELM_BOOTSTRAP_PYTHON="$bootstrap_path" \
    CORELM_REAL_LLM_VENV="$RUNTIME_DIR" \
    CORELM_SKIP_RUNTIME_INSTALL=0 \
    CORELM_SKIP_ASSET_PREPARATION=0 \
    CORELM_ASSETS_OFFLINE_ONLY="$OFFLINE" \
    CORELM_OFFLINE="$OFFLINE" \
    CORELM_WHEELHOUSE="$WHEELHOUSE" \
    CORELM_PYPI_INDEX_URL="$PYPI_INDEX_URL" \
    CORELM_HF_ENDPOINT="$HF_ENDPOINT" \
    CORELM_SKIP_MEMORY_CHECK=0 \
    CORELM_SKIP_MPS_CHECK=0 \
    CORELM_SKIP_SMOKE_TEST=0 \
    CORELM_REAL_LLM_PYTHON_SHA256= \
    CORELM_ALLOW_DIRTY_SOURCE=0 \
    CORELM_SOURCE_ARCHIVE_MANIFEST="${CORELM_SOURCE_ARCHIVE_MANIFEST:-}" \
    BUILD_CONFIG=release \
    "$PROJECT_DIR/build_local_app.sh"

[ -d "$APP_PATH/Contents" ] || {
    printf 'missing local application: %s\n' "$APP_PATH" >&2
    exit 1
}

run_clean PYTHON_BIN="$RUNTIME_DIR/bin/python" "$PROJECT_DIR/run_tests.sh"
run_clean "$PROJECT_DIR/security/run_swift_security_tests.sh"

[ -x "$APP_EXECUTABLE" ] || fail "missing app executable: $APP_EXECUTABLE"
[ -x /usr/bin/memory_pressure ] \
    || fail 'macOS memory-pressure monitor is unavailable'
if ! initial_free_percent=$(memory_free_percent); then
    fail 'could not read macOS memory pressure before launch'
fi
[ "$initial_free_percent" -ge "$MINIMUM_FREE_MEMORY_PERCENT" ] \
    || fail "only ${initial_free_percent}% system memory is free before launch"

touch "$MARKER"
if [ -z "$challenge" ]; then
    challenge=$(/usr/bin/openssl rand -hex 32)
fi
printf '%s\n' \
    'Launching the visible 8-block Qwen proof run.' \
    'The app exits automatically when the run finishes (up to 5 minutes).'
/usr/bin/nice -n 10 /usr/bin/env -i \
    HOME="$HOME" \
    TMPDIR="$PROOF_PROCESS_TMP" \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    LANG=C \
    LC_ALL=C \
    "$APP_EXECUTABLE" \
    --real-llm-smoke-run \
    --proof-challenge "$challenge" &
APP_PID=$!
timeout_watchdog &
TIMEOUT_WATCHDOG_PID=$!
memory_watchdog &
MEMORY_WATCHDOG_PID=$!

if wait "$APP_PID"; then
    app_status=0
else
    app_status=$?
fi
APP_PID=
for watchdog_pid in "$TIMEOUT_WATCHDOG_PID" "$MEMORY_WATCHDOG_PID"; do
    /bin/kill -TERM "$watchdog_pid" 2>/dev/null || :
    wait "$watchdog_pid" 2>/dev/null || :
done
TIMEOUT_WATCHDOG_PID=
MEMORY_WATCHDOG_PID=

if [ -s "$TIMEOUT_REASON" ]; then
    fail "$(/usr/bin/sed -n '1p' "$TIMEOUT_REASON")"
fi
if [ -s "$MEMORY_REASON" ]; then
    fail "$(/usr/bin/sed -n '1p' "$MEMORY_REASON")"
fi
[ "$app_status" -eq 0 ] \
    || fail "the app exited with status $app_status"

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

run_clean "$PROJECT_DIR/security/verify_app_bundle.sh" "$APP_PATH"
run_clean "$RUNTIME_DIR/bin/python" -I -B -X \
    "pycache_prefix=$VERIFY_CACHE" \
    "$PROJECT_DIR/security/verify_local_app_run.py" \
    --run-directory "$run_directory" \
    --app "$APP_PATH" \
    --challenge "$challenge"

printf '%s\n' \
    'Replaying all retained containers through pinned Qwen independently.'
: >"$TIMEOUT_REASON"
: >"$MEMORY_REASON"
/usr/bin/nice -n 10 /usr/bin/env -i \
    HOME="$HOME" \
    TMPDIR="$PROOF_PROCESS_TMP" \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    LANG=C \
    LC_ALL=C \
    "$RUNTIME_DIR/bin/python" -I -B -X \
    "pycache_prefix=$VERIFY_CACHE" \
    "$PROJECT_DIR/security/verify_primary_replay.py" \
    "$run_directory" \
    --hf-home "$HOME/.cache/corelm-model-assets" &
APP_PID=$!
timeout_watchdog &
TIMEOUT_WATCHDOG_PID=$!
memory_watchdog &
MEMORY_WATCHDOG_PID=$!

if wait "$APP_PID"; then
    replay_status=0
else
    replay_status=$?
fi
APP_PID=
for watchdog_pid in "$TIMEOUT_WATCHDOG_PID" "$MEMORY_WATCHDOG_PID"; do
    /bin/kill -TERM "$watchdog_pid" 2>/dev/null || :
    wait "$watchdog_pid" 2>/dev/null || :
done
TIMEOUT_WATCHDOG_PID=
MEMORY_WATCHDOG_PID=
if [ -s "$TIMEOUT_REASON" ]; then
    fail "heavy replay $(/usr/bin/sed -n '1p' "$TIMEOUT_REASON")"
fi
if [ -s "$MEMORY_REASON" ]; then
    fail "heavy replay $(/usr/bin/sed -n '1p' "$MEMORY_REASON")"
fi
[ "$replay_status" -eq 0 ] \
    || fail "the independent heavy replay exited with status $replay_status"

printf '%s\n' \
    'END-TO-END PROOF PASS: the locally built app ran pinned Qwen on MPS,' \
    'created fresh compressed KV containers, then a separate decoder rebuilt' \
    'both KV caches and reproduced all 1,024 Qwen decisions. Result, source,' \
    'receipt, runtime, and application integrity checks also passed.' \
    "Fresh proof runtime retained at: $RUNTIME_DIR"
