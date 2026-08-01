#!/bin/sh
set -eu

umask 077

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
RUNTIME="$HOME/.cache/corelm-app-runtime/bin/python"
CACHE="$HOME/.cache/corelm-model-assets"
REHEARSAL_TMP=${TMPDIR:-/tmp}

[ "$#" -eq 0 ] || {
    printf '%s\n' \
        'BEACON REHEARSAL FAIL: command-line overrides are forbidden.' >&2
    exit 2
}
[ -x "$RUNTIME" ] || {
    printf '%s\n' \
        'BEACON REHEARSAL FAIL: locked app runtime is missing.' >&2
    exit 1
}
[ -d "$CACHE" ] || {
    printf '%s\n' \
        'BEACON REHEARSAL FAIL: private model cache is missing.' >&2
    exit 1
}

/usr/bin/env -i \
    HOME="$HOME" \
    TMPDIR="$REHEARSAL_TMP" \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    LANG=C \
    LC_ALL=C \
    /usr/bin/python3 -I -B \
        "$PROJECT_DIR/security/rehearse_beacon_protocol.py"

/usr/bin/env -i \
    HOME="$HOME" \
    TMPDIR="$REHEARSAL_TMP" \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    LANG=C \
    LC_ALL=C \
    /usr/bin/python3 -I -B \
        "$PROJECT_DIR/security/supervise_beacon_model_rehearsal.py"

printf '%s\n' \
    'BEACON REHEARSAL PASS: hermetic protocol and model-only synthetic contours passed.'
