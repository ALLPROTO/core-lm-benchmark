#!/bin/bash
set -euo pipefail

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SELECTED_DEVELOPER_DIR=${DEVELOPER_DIR:-$(xcode-select -p)}
TESTING_FRAMEWORKS="$SELECTED_DEVELOPER_DIR/Library/Developer/Frameworks"
OUTPUT_FILE=$(mktemp "${TMPDIR:-/tmp}/corelm-swift-tests.XXXXXX")

cleanup() {
    rm -f -- "$OUTPUT_FILE"
}
trap cleanup EXIT HUP INT TERM

if [ ! -d "$TESTING_FRAMEWORKS" ]; then
    printf 'Swift Testing framework directory is missing: %s\n' \
        "$TESTING_FRAMEWORKS" >&2
    exit 1
fi

cd "$PROJECT_DIR"
DEVELOPER_DIR="$SELECTED_DEVELOPER_DIR" swift test \
    --enable-swift-testing \
    --disable-xctest \
    -Xswiftc -F \
    -Xswiftc "$TESTING_FRAMEWORKS" \
    2>&1 | tee "$OUTPUT_FILE"

if ! grep -Eq \
    'Test run with [1-9][0-9]* tests? in [1-9][0-9]* suites? passed' \
    "$OUTPUT_FILE"
then
    printf '%s\n' \
        'Swift security test gate failed: no non-empty passing test run.' >&2
    exit 1
fi

printf '%s\n' 'SWIFT SECURITY TESTS PASS: non-empty test execution confirmed.'
