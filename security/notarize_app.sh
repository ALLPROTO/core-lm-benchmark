#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
APP_PATH=${1:-"$PROJECT_DIR/dist/CoreLMBenchmark.app"}
NOTARY_KEYCHAIN_PROFILE=${NOTARY_KEYCHAIN_PROFILE:-}
ARCHIVE_PATH=${ARCHIVE_PATH:-"$PROJECT_DIR/dist/CoreLMBenchmark-notarization.zip"}

if [ -z "$NOTARY_KEYCHAIN_PROFILE" ]; then
    printf '%s\n' \
        'Set NOTARY_KEYCHAIN_PROFILE to an xcrun notarytool keychain profile.' >&2
    exit 1
fi

REQUIRE_DEVELOPER_ID=1 \
    "$PROJECT_DIR/security/verify_app_bundle.sh" "$APP_PATH"

ditto -c -k --keepParent "$APP_PATH" "$ARCHIVE_PATH"
xcrun notarytool submit "$ARCHIVE_PATH" \
    --keychain-profile "$NOTARY_KEYCHAIN_PROFILE" \
    --wait
xcrun stapler staple "$APP_PATH"
xcrun stapler validate "$APP_PATH"
spctl --assess --type execute --verbose=4 "$APP_PATH"

printf '%s\n' "NOTARIZATION PASS: $APP_PATH"
