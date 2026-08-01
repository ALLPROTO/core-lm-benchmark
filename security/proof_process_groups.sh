#!/bin/sh

# Source-only process-group supervision primitives.  PGIDs are captured either
# from a live descendant leader or from the runner's fresh owner-private marker;
# escalation intentionally uses that captured value after the leader exits.

proof_group_is_safe() {
    proof_candidate_group=${1:-}
    case "$proof_candidate_group" in
        ''|*[!0-9]*) return 1 ;;
    esac
    [ "$proof_candidate_group" -gt 1 ] || return 1
    proof_own_group=$(
        /bin/ps -o pgid= -p "$$" 2>/dev/null \
            | /usr/bin/tr -d '[:space:]'
    )
    case "$proof_own_group" in
        ''|*[!0-9]*) return 1 ;;
    esac
    [ "$proof_candidate_group" != "$proof_own_group" ]
}

proof_group_exists() {
    proof_group_is_safe "$1" || return 1
    /bin/kill -0 -- "-$1" 2>/dev/null
}

record_published_worker_groups() {
    [ -d "$RESULTS_ROOT" ] || return 0
    proof_current_uid=$(/usr/bin/id -u)
    for proof_group_candidate in "$RESULTS_ROOT"/*; do
        [ -d "$proof_group_candidate" ] || continue
        [ ! -L "$proof_group_candidate" ] || continue
        [ "$proof_group_candidate" -nt "$MARKER" ] || continue
        proof_candidate_owner=$(
            /usr/bin/stat -f '%u' "$proof_group_candidate" 2>/dev/null
        ) || continue
        proof_candidate_mode=$(
            /usr/bin/stat -f '%Lp' "$proof_group_candidate" 2>/dev/null
        ) || continue
        [ "$proof_candidate_owner" = "$proof_current_uid" ] || continue
        [ "$proof_candidate_mode" = 700 ] || continue

        proof_group_file="$proof_group_candidate/.worker-process-group"
        [ -f "$proof_group_file" ] || continue
        [ ! -L "$proof_group_file" ] || continue
        [ "$proof_group_file" -nt "$MARKER" ] || continue
        proof_group_file_owner=$(
            /usr/bin/stat -f '%u' "$proof_group_file" 2>/dev/null
        ) || continue
        proof_group_file_mode=$(
            /usr/bin/stat -f '%Lp' "$proof_group_file" 2>/dev/null
        ) || continue
        proof_group_file_bytes=$(
            /usr/bin/stat -f '%z' "$proof_group_file" 2>/dev/null
        ) || continue
        [ "$proof_group_file_owner" = "$proof_current_uid" ] || continue
        [ "$proof_group_file_mode" = 600 ] || continue
        case "$proof_group_file_bytes" in
            ''|*[!0-9]*) continue ;;
        esac
        [ "$proof_group_file_bytes" -gt 1 ] || continue
        [ "$proof_group_file_bytes" -le 32 ] || continue

        proof_published_group=$(/bin/cat "$proof_group_file")
        case "$proof_published_group" in
            ''|*[!0-9]*) continue ;;
        esac
        proof_group_is_safe "$proof_published_group" || continue
        # The runner created this marker O_EXCL inside its fresh 0700 run
        # directory.  The leader may already have exited, so group existence
        # -- not a second lookup of the leader PID -- is the final invariant.
        proof_group_exists "$proof_published_group" || continue
        printf '%s\n' "$proof_published_group" >>"$SUPERVISED_GROUPS"
    done
}

proof_signal_recorded_groups() {
    proof_signal_name=$1
    [ -s "$SUPERVISED_GROUPS" ] || return 0
    for proof_recorded_group in $(
        /usr/bin/sort -u "$SUPERVISED_GROUPS"
    ); do
        proof_group_is_safe "$proof_recorded_group" || continue
        proof_group_exists "$proof_recorded_group" || continue
        /bin/kill "-$proof_signal_name" -- \
            "-$proof_recorded_group" 2>/dev/null || :
    done
}

force_kill_recorded_groups() {
    proof_signal_recorded_groups KILL
}

terminate_recorded_groups() {
    record_published_worker_groups
    [ -s "$SUPERVISED_GROUPS" ] || return 0
    proof_signal_recorded_groups TERM
    /bin/sleep "${PROOF_GROUP_TERM_GRACE_SECONDS:-1}"
    force_kill_recorded_groups
}
