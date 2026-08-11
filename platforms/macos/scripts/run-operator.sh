#!/bin/sh
set -eu

umask 077

PROJECT_DIR=$(CDPATH= cd -- "$(/usr/bin/dirname -- "$0")/../../.." && pwd -P)
OPERATOR_PACKAGE="$PROJECT_DIR/platforms/macos/Operator"
SCRATCH_DIRECTORY=
CONTROL_DIRECTORY=
GROUP_FILE=
SELF_PROCESS_GROUP=

fail() {
    printf 'CORE LM OPERATOR FAIL: %s\n' "$*" >&2
    exit 1
}

terminate_active_group() {
    [ -n "$CONTROL_DIRECTORY" ] && [ -d "$CONTROL_DIRECTORY" ] \
        && [ ! -L "$CONTROL_DIRECTORY" ] || return 0
    # Freezing the directory closes the crash race: an unpublished helper
    # marker can no longer be renamed into place, so that helper exits before
    # it is allowed to spawn the canonical command.
    /bin/chmod 500 "$CONTROL_DIRECTORY" 2>/dev/null || return 0
    [ -n "$GROUP_FILE" ] && [ -f "$GROUP_FILE" ] \
        && [ ! -L "$GROUP_FILE" ] || return 0
    marker_owner=$(/usr/bin/stat -f '%u' "$GROUP_FILE" 2>/dev/null) || return 0
    marker_mode=$(/usr/bin/stat -f '%Lp' "$GROUP_FILE" 2>/dev/null) || return 0
    marker_lines=$(/usr/bin/wc -l <"$GROUP_FILE" | /usr/bin/tr -d '[:space:]')
    marker_bytes=$(/usr/bin/wc -c <"$GROUP_FILE" | /usr/bin/tr -d '[:space:]')
    [ "$marker_owner" -eq "$(/usr/bin/id -u)" ] \
        && [ "$marker_mode" = 600 ] \
        && [ "$marker_lines" = 1 ] \
        && [ "$marker_bytes" -ge 2 ] \
        && [ "$marker_bytes" -le 16 ] || return
    group_id=$(/bin/cat "$GROUP_FILE")
    case "$group_id" in
        ''|*[!0-9]*) return 0 ;;
    esac
    [ "$group_id" -gt 1 ] \
        && [ -n "$SELF_PROCESS_GROUP" ] \
        && [ "$group_id" != "$SELF_PROCESS_GROUP" ] || return 0
    /bin/kill -TERM -- "-$group_id" 2>/dev/null || :
    # run-proof reserves up to four seconds for its own separately supervised
    # worker-group cleanup, so the outer contour gives it six before KILL.
    for cleanup_second in 1 2 3 4 5 6; do
        /bin/kill -0 -- "-$group_id" 2>/dev/null || return 0
        /bin/sleep 1
    done
    /bin/kill -KILL -- "-$group_id" 2>/dev/null || :
    return 0
}

cleanup() {
    terminate_active_group
    if [ -n "$CONTROL_DIRECTORY" ] && [ -d "$CONTROL_DIRECTORY" ]; then
        /bin/chmod 700 "$CONTROL_DIRECTORY" 2>/dev/null || :
    fi
    if [ -n "$SCRATCH_DIRECTORY" ] && [ -d "$SCRATCH_DIRECTORY" ]; then
        /bin/rm -rf -- "$SCRATCH_DIRECTORY"
    fi
    return 0
}

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

[ "$#" -eq 0 ] || {
    printf '%s\n' './corelm macos operator accepts no arguments' >&2
    exit 2
}
[ "$(/usr/bin/uname -s)" = Darwin ] \
    || fail 'the Operator Control Center requires macOS'
[ -x /usr/bin/xcrun ] && [ -f /usr/bin/xcrun ] \
    && [ ! -L /usr/bin/xcrun ] \
    || fail 'fixed /usr/bin/xcrun is unavailable'
SELF_PROCESS_GROUP=$(
    /bin/ps -o pgid= -p $$ | /usr/bin/tr -d '[:space:]'
) || fail 'could not capture launcher process group'
case "$SELF_PROCESS_GROUP" in
    ''|*[!0-9]*) fail 'launcher process group is invalid' ;;
esac

case "${HOME:-}" in
    /*) ;;
    *) fail 'HOME must be an absolute path' ;;
esac
OPERATOR_HOME=$(CDPATH= cd -- "$HOME" && pwd -P) \
    || fail 'HOME is unavailable'
[ "$OPERATOR_HOME" = "$HOME" ] || fail 'HOME must be canonical'
home_owner=$(/usr/bin/stat -f '%u' "$OPERATOR_HOME") \
    || fail 'could not inspect HOME'
home_mode=$(/usr/bin/stat -f '%Lp' "$OPERATOR_HOME") \
    || fail 'could not inspect HOME permissions'
[ "$home_owner" -eq "$(/usr/bin/id -u)" ] \
    || fail 'HOME is not owned by the current user'
case "$home_mode" in
    *[2367][0-7]|*[0-7][2367]) fail 'HOME is group- or world-writable' ;;
esac

case "$PROJECT_DIR/" in
    "$OPERATOR_HOME/"*) ;;
    *) fail 'operator checkout must be below the current user HOME' ;;
esac

OPERATOR_CACHE_PARENT="$OPERATOR_HOME/Library/Caches"
[ -d "$OPERATOR_CACHE_PARENT" ] && [ ! -L "$OPERATOR_CACHE_PARENT" ] \
    || fail 'owner cache parent is unavailable'
cache_parent_owner=$(/usr/bin/stat -f '%u' "$OPERATOR_CACHE_PARENT") \
    || fail 'could not inspect owner cache parent'
cache_parent_mode=$(/usr/bin/stat -f '%Lp' "$OPERATOR_CACHE_PARENT") \
    || fail 'could not inspect owner cache parent permissions'
[ "$cache_parent_owner" -eq "$(/usr/bin/id -u)" ] \
    || fail 'owner cache parent has an unexpected owner'
case "$cache_parent_mode" in
    *[2367][0-7]|*[0-7][2367]) \
        fail 'owner cache parent is group- or world-writable' ;;
esac

OPERATOR_CACHE_ROOT="$OPERATOR_CACHE_PARENT/CoreLMOperator"
if [ ! -e "$OPERATOR_CACHE_ROOT" ]; then
    /bin/mkdir -m 700 "$OPERATOR_CACHE_ROOT"
fi
[ -d "$OPERATOR_CACHE_ROOT" ] && [ ! -L "$OPERATOR_CACHE_ROOT" ] \
    || fail 'operator cache root is not a regular directory'
cache_owner=$(/usr/bin/stat -f '%u' "$OPERATOR_CACHE_ROOT") \
    || fail 'could not inspect operator cache root'
cache_mode=$(/usr/bin/stat -f '%Lp' "$OPERATOR_CACHE_ROOT") \
    || fail 'could not inspect operator cache root permissions'
[ "$cache_owner" -eq "$(/usr/bin/id -u)" ] && [ "$cache_mode" = 700 ] \
    || fail 'operator cache root must be owner-only'

case "$OPERATOR_CACHE_ROOT/" in
    "$PROJECT_DIR/"|"$PROJECT_DIR/"*) \
        fail 'operator build scratch must be outside the source checkout' ;;
esac
SCRATCH_DIRECTORY=$(
    /usr/bin/mktemp -d "$OPERATOR_CACHE_ROOT/session.XXXXXX"
) || fail 'could not create operator scratch directory'
SCRATCH_DIRECTORY=$(CDPATH= cd -- "$SCRATCH_DIRECTORY" && pwd -P)
/bin/chmod 700 "$SCRATCH_DIRECTORY"
scratch_owner=$(/usr/bin/stat -f '%u' "$SCRATCH_DIRECTORY") \
    || fail 'could not inspect operator scratch directory'
scratch_mode=$(/usr/bin/stat -f '%Lp' "$SCRATCH_DIRECTORY") \
    || fail 'could not inspect operator scratch permissions'
[ "$scratch_owner" -eq "$(/usr/bin/id -u)" ] \
    && [ "$scratch_mode" = 700 ] \
    || fail 'operator scratch directory must be owner-only'
OPERATOR_COMMAND_TMP="$SCRATCH_DIRECTORY/tmp"
/bin/mkdir -m 700 "$OPERATOR_COMMAND_TMP"
CONTROL_DIRECTORY="$SCRATCH_DIRECTORY/control"
/bin/mkdir -m 700 "$CONTROL_DIRECTORY"
GROUP_FILE="$CONTROL_DIRECTORY/active-command-pgid"

[ -f "$OPERATOR_PACKAGE/Package.swift" ] \
    && [ ! -L "$OPERATOR_PACKAGE/Package.swift" ] \
    || fail 'nested Operator package is unavailable'

/usr/bin/env -i \
    HOME="$OPERATOR_HOME" \
    TMPDIR="$OPERATOR_COMMAND_TMP" \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    LANG=C \
    LC_ALL=C \
    /usr/bin/xcrun --sdk macosx swift build \
        --package-path "$OPERATOR_PACKAGE" \
        --scratch-path "$SCRATCH_DIRECTORY/swift-build" \
        --jobs 1

OPERATOR_BIN_PATH=$(
    /usr/bin/env -i \
        HOME="$OPERATOR_HOME" \
        TMPDIR="$OPERATOR_COMMAND_TMP" \
        PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        LANG=C \
        LC_ALL=C \
        /usr/bin/xcrun --sdk macosx swift build \
            --package-path "$OPERATOR_PACKAGE" \
            --scratch-path "$SCRATCH_DIRECTORY/swift-build" \
            --show-bin-path
) || fail 'could not resolve Operator build products'
case "$OPERATOR_BIN_PATH/" in
    "$SCRATCH_DIRECTORY/swift-build/"*) ;;
    *) fail 'Operator product path escaped external scratch' ;;
esac
[ -d "$OPERATOR_BIN_PATH" ] && [ ! -L "$OPERATOR_BIN_PATH" ] \
    || fail 'Operator product directory is invalid'
OPERATOR_APP="$OPERATOR_BIN_PATH/CoreLMOperator"
COMMAND_LAUNCHER="$OPERATOR_BIN_PATH/CoreLMOperatorCommandLauncher"
for executable in "$OPERATOR_APP" "$COMMAND_LAUNCHER"; do
    [ -f "$executable" ] && [ ! -L "$executable" ] && [ -x "$executable" ] \
        || fail 'Operator build product is not a regular executable'
    product_owner=$(/usr/bin/stat -f '%u' "$executable") \
        || fail 'could not inspect Operator build product owner'
    product_mode=$(/usr/bin/stat -f '%Lp' "$executable") \
        || fail 'could not inspect Operator build product permissions'
    [ "$product_owner" -eq "$(/usr/bin/id -u)" ] \
        || fail 'Operator build product owner is invalid'
    case "$product_mode" in
        *[2367][0-7]|*[0-7][2367]) \
            fail 'Operator build product is group- or world-writable' ;;
    esac
done

/usr/bin/env -i \
    HOME="$OPERATOR_HOME" \
    TMPDIR="$OPERATOR_COMMAND_TMP" \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    LANG=C \
    LC_ALL=C \
    "$OPERATOR_APP" \
        --project-root "$PROJECT_DIR" \
        --command-launcher "$COMMAND_LAUNCHER" \
        --group-file "$GROUP_FILE"
