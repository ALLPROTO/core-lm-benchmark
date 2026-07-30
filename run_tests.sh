#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}
TEST_ROOT=$SCRIPT_DIR

# Two unit tests deliberately exercise the registration-only state. Once
# immutable prospective artifacts exist, run the unit suite against a
# byte-identical fixture with only those phase artifacts omitted. The actual
# artifacts are verified separately by verify_voidtoken_v5_evidence.py.
if [ -f "$SCRIPT_DIR/real-llm-v5-results/selection.attempt.json" ] ||
   [ -f "$SCRIPT_DIR/real-llm-v5-results/selection.json" ] ||
   [ -f "$SCRIPT_DIR/real-llm-v5-results/holdout.attempt.json" ] ||
   [ -f "$SCRIPT_DIR/real-llm-v5-results/holdout.json" ]; then
    TEST_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/corelm-unit-fixture.XXXXXX")
    (
        cd "$SCRIPT_DIR"
        tar -cf - \
            --exclude='.git' \
            --exclude='.build' \
            --exclude='output' \
            --exclude='real-llm-v5-results/selection.attempt.json' \
            --exclude='real-llm-v5-results/selection.json' \
            --exclude='real-llm-v5-results/holdout.attempt.json' \
            --exclude='real-llm-v5-results/holdout.json' \
            .
    ) | tar -xf - -C "$TEST_ROOT"
fi

exec "$PYTHON_BIN" -m unittest discover -s "$TEST_ROOT/Tests" -p 'test_*.py' -v
