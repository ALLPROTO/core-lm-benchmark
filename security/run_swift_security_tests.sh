#!/bin/bash
set -euo pipefail

PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH
TEST_MODE=${CORELM_SWIFT_GATE_TEST_MODE:-0}
unset SWIFT_EXEC SDKROOT TOOLCHAINS DEVELOPER_DIR CC CXX CPP CFLAGS \
    CPPFLAGS CXXFLAGS LDFLAGS LD_LIBRARY_PATH DYLD_LIBRARY_PATH \
    DYLD_FRAMEWORK_PATH DYLD_INSERT_LIBRARIES SWIFTPM_CUSTOM_BIN_DIR \
    SWIFTPM_BUILD_DIR

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
case "$TEST_MODE" in
    0)
        SELECTED_DEVELOPER_DIR=$(/usr/bin/xcode-select -p)
        SWIFT_COMMAND=(/usr/bin/xcrun --sdk macosx swift)
        TEST_ENVIRONMENT=()
        ;;
    1)
        SELECTED_DEVELOPER_DIR=${CORELM_TEST_DEVELOPER_DIR:?}
        SWIFT_COMMAND=("${CORELM_TEST_SWIFT_LAUNCHER:?}")
        TEST_ENVIRONMENT=(
            "CORELM_SWIFT_ARGUMENTS_LOG=${CORELM_SWIFT_ARGUMENTS_LOG:?}"
            "CORELM_SWIFT_TEST_SUMMARY=${CORELM_SWIFT_TEST_SUMMARY:?}"
        )
        ;;
    *)
        printf '%s\n' 'CORELM_SWIFT_GATE_TEST_MODE must be 0 or 1.' >&2
        exit 1
        ;;
esac
TESTING_FRAMEWORKS="$SELECTED_DEVELOPER_DIR/Library/Developer/Frameworks"
SWIFT_TEST_TMP=$(/usr/bin/mktemp -d /tmp/corelm-swift-tests.XXXXXX)
OUTPUT_FILE="$SWIFT_TEST_TMP/output.txt"
SWIFT_TEST_FLAGS=(
    --enable-swift-testing
    --disable-xctest
)

cleanup() {
    /bin/rm -rf -- "$SWIFT_TEST_TMP"
}
trap cleanup EXIT HUP INT TERM

if [ -d "$TESTING_FRAMEWORKS/Testing.framework" ]; then
    SWIFT_TEST_FLAGS+=(
        -Xswiftc -F
        -Xswiftc "$TESTING_FRAMEWORKS"
    )
else
    printf 'Using toolchain-provided Swift Testing integration from: %s\n' \
        "$SELECTED_DEVELOPER_DIR"
fi

cd "$PROJECT_DIR"
if [ "$TEST_MODE" = 1 ]; then
    /usr/bin/env -i \
        HOME="$HOME" \
        TMPDIR="$SWIFT_TEST_TMP" \
        PATH="$PATH" \
        LANG=C \
        LC_ALL=C \
        "${TEST_ENVIRONMENT[@]}" \
        "${SWIFT_COMMAND[@]}" test \
        --scratch-path "$SWIFT_TEST_TMP/build" \
        "${SWIFT_TEST_FLAGS[@]}" \
        2>&1 | /usr/bin/tee "$OUTPUT_FILE"
else
    /usr/bin/env -i \
        HOME="$HOME" \
        TMPDIR="$SWIFT_TEST_TMP" \
        PATH="$PATH" \
        LANG=C \
        LC_ALL=C \
        "${SWIFT_COMMAND[@]}" test \
        --scratch-path "$SWIFT_TEST_TMP/build" \
        "${SWIFT_TEST_FLAGS[@]}" \
        2>&1 | /usr/bin/tee "$OUTPUT_FILE"
fi

if ! /usr/bin/grep -Eq \
    'Test run with [1-9][0-9]* tests?( in [1-9][0-9]* suites?)? passed' \
    "$OUTPUT_FILE"
then
    printf '%s\n' \
        'Swift security test gate failed: no non-empty passing test run.' >&2
    exit 1
fi

printf '%s\n' 'SWIFT SECURITY TESTS PASS: non-empty test execution confirmed.'
