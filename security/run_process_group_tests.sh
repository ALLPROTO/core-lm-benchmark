#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
TEST_TMP=$(/usr/bin/mktemp -d /tmp/corelm-process-group-test.XXXXXX)
SUPERVISED_GROUPS="$TEST_TMP/supervised-groups"
READY_FILE="$TEST_TMP/ready"
TERM_MARKER="$TEST_TMP/term-observed"
RESULTS_ROOT="$TEST_TMP/results"
MARKER="$TEST_TMP/proof-start"
PROOF_GROUP_TERM_GRACE_SECONDS=1
LEADER_PID=
CAPTURED_GROUP=

. "$PROJECT_DIR/security/proof_process_groups.sh"

/bin/mkdir -m 700 "$RESULTS_ROOT"
/usr/bin/touch "$MARKER"

cleanup() {
    if [ -n "$CAPTURED_GROUP" ] \
        && proof_group_is_safe "$CAPTURED_GROUP"; then
        /bin/kill -KILL -- "-$CAPTURED_GROUP" 2>/dev/null || :
    fi
    if [ -n "$LEADER_PID" ]; then
        /bin/kill -KILL "$LEADER_PID" 2>/dev/null || :
        wait "$LEADER_PID" 2>/dev/null || :
    fi
    /bin/rm -rf -- "$TEST_TMP"
}
trap cleanup EXIT HUP INT TERM

/usr/bin/python3 -c '
import os
import signal
import sys
import time

os.setpgid(0, 0)
child = os.fork()
if child == 0:
    def observe_term(_signum, _frame):
        with open(sys.argv[2], "w", encoding="ascii") as marker:
            marker.write("SIGTERM ignored\n")
            marker.flush()
            os.fsync(marker.fileno())

    signal.signal(signal.SIGTERM, observe_term)
    with open(sys.argv[1], "w", encoding="ascii") as ready:
        ready.write(str(os.getpid()) + "\n")
        ready.flush()
        os.fsync(ready.fileno())
    while True:
        time.sleep(1)

while True:
    time.sleep(1)
' "$READY_FILE" "$TERM_MARKER" >/dev/null 2>&1 &
LEADER_PID=$!

attempt=0
while [ ! -s "$READY_FILE" ]; do
    /bin/kill -0 "$LEADER_PID" 2>/dev/null || {
        printf '%s\n' 'PROCESS GROUP TEST FAIL: fixture leader exited early.' >&2
        exit 1
    }
    attempt=$((attempt + 1))
    [ "$attempt" -lt 100 ] || {
        printf '%s\n' 'PROCESS GROUP TEST FAIL: fixture did not become ready.' >&2
        exit 1
    }
    /bin/sleep 0.05
done

observed_group=$(
    /bin/ps -o pgid= -p "$LEADER_PID" 2>/dev/null \
        | /usr/bin/tr -d '[:space:]'
)
[ "$observed_group" = "$LEADER_PID" ] || {
    printf '%s\n' 'PROCESS GROUP TEST FAIL: fixture has no independent group.' >&2
    exit 1
}
CAPTURED_GROUP=$observed_group
printf '%s\n' "$observed_group" >"$SUPERVISED_GROUPS"

terminate_recorded_groups

if wait "$LEADER_PID"; then
    leader_status=0
else
    leader_status=$?
fi
LEADER_PID=
[ "$leader_status" -eq 143 ] || {
    printf 'PROCESS GROUP TEST FAIL: leader status %s, expected SIGTERM.\n' \
        "$leader_status" >&2
    exit 1
}
[ -s "$TERM_MARKER" ] || {
    printf '%s\n' \
        'PROCESS GROUP TEST FAIL: child did not survive and observe SIGTERM.' >&2
    exit 1
}

attempt=0
while proof_group_exists "$observed_group"; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 100 ] || {
        printf '%s\n' \
            'PROCESS GROUP TEST FAIL: SIGTERM-ignoring child survived SIGKILL.' \
            >&2
        exit 1
    }
    /bin/sleep 0.05
done
CAPTURED_GROUP=

/bin/sleep 0.05
published_run="$RESULTS_ROOT/published-run"
/bin/mkdir -m 700 "$published_run"
published_group_file="$published_run/.worker-process-group"
published_ready="$TEST_TMP/published-ready"
published_term_marker="$TEST_TMP/published-term-observed"
: >"$SUPERVISED_GROUPS"

/usr/bin/python3 -c '
import os
import signal
import sys
import time

os.setpgid(0, 0)
group = os.getpid()
descriptor = os.open(
    sys.argv[1],
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
    0o600,
)
try:
    os.write(descriptor, (str(group) + "\n").encode("ascii"))
    os.fsync(descriptor)
finally:
    os.close(descriptor)

child = os.fork()
if child == 0:
    def observe_term(_signum, _frame):
        with open(sys.argv[3], "w", encoding="ascii") as marker:
            marker.write("SIGTERM ignored\n")
            marker.flush()
            os.fsync(marker.fileno())

    signal.signal(signal.SIGTERM, observe_term)
    with open(sys.argv[2], "w", encoding="ascii") as ready:
        ready.write(str(os.getpid()) + "\n")
        ready.flush()
        os.fsync(ready.fileno())
    while True:
        time.sleep(1)

while not os.path.exists(sys.argv[2]):
    time.sleep(0.01)
' "$published_group_file" "$published_ready" \
    "$published_term_marker" >/dev/null 2>&1 &
LEADER_PID=$!
CAPTURED_GROUP=$LEADER_PID

if wait "$LEADER_PID"; then
    leader_status=0
else
    leader_status=$?
fi
LEADER_PID=
[ "$leader_status" -eq 0 ] || {
    printf 'PROCESS GROUP TEST FAIL: pre-scan leader status %s.\n' \
        "$leader_status" >&2
    exit 1
}
proof_group_exists "$CAPTURED_GROUP" || {
    printf '%s\n' \
        'PROCESS GROUP TEST FAIL: pre-scan orphan group is not alive.' >&2
    exit 1
}

record_published_worker_groups
recorded_group=$(/usr/bin/sed -n '1p' "$SUPERVISED_GROUPS")
[ "$recorded_group" = "$CAPTURED_GROUP" ] || {
    printf '%s\n' \
        'PROCESS GROUP TEST FAIL: private marker did not recover orphan PGID.' \
        >&2
    exit 1
}
terminate_recorded_groups
[ -s "$published_term_marker" ] || {
    printf '%s\n' \
        'PROCESS GROUP TEST FAIL: recovered orphan did not observe SIGTERM.' \
        >&2
    exit 1
}

attempt=0
while proof_group_exists "$CAPTURED_GROUP"; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 100 ] || {
        printf '%s\n' \
            'PROCESS GROUP TEST FAIL: recovered orphan survived SIGKILL.' >&2
        exit 1
    }
    /bin/sleep 0.05
done
CAPTURED_GROUP=

printf '%s\n' \
    'PROCESS GROUP TEST PASS: captured and published orphan PGIDs were killed.'
