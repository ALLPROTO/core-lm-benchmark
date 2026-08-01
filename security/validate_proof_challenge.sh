#!/bin/sh
set -eu

[ "$#" -eq 1 ] || exit 1
challenge=$1
case "$challenge" in
    *[!0-9a-f]*) exit 1 ;;
esac
[ "${#challenge}" -eq 64 ] || exit 1
printf '%s\n' "$challenge"
