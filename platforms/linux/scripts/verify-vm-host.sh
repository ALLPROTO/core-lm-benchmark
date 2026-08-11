#!/bin/sh
set -eu

# GitHub-hosted Ubuntu labels are rolling images.  This gate proves that the
# job is running on the requested booted x86_64 Ubuntu VM rather than in a
# container; it intentionally does not claim a digest-hermetic base image.

fail() {
    printf 'LINUX VM HOST FAIL: %s\n' "$*" >&2
    exit 1
}

[ "$#" -eq 1 ] || fail "expected one Ubuntu version argument"
EXPECTED_VERSION=$1
case "$EXPECTED_VERSION" in
    22.04|24.04) ;;
    *) fail "supported Ubuntu VM versions are 22.04 and 24.04" ;;
esac

[ "$(/usr/bin/uname -s)" = Linux ] || fail "Linux is required"
[ "$(/usr/bin/uname -m)" = x86_64 ] \
    || fail "the registered Linux runtime and locks require x86_64"
[ -x /usr/bin/systemd-detect-virt ] \
    || fail "systemd-detect-virt is required"
[ -x /usr/bin/python3 ] || fail "Ubuntu system Python is required"

OS_RELEASE=$(/usr/bin/readlink -f -- /etc/os-release) \
    || fail "cannot resolve /etc/os-release"
case "$OS_RELEASE" in /*) ;; *) fail "os-release path is not absolute" ;; esac
[ -f "$OS_RELEASE" ] && [ ! -L "$OS_RELEASE" ] \
    || fail "resolved os-release is not a regular file"
OS_OWNER=$(/usr/bin/stat -c '%u' "$OS_RELEASE") \
    || fail "cannot inspect os-release owner"
OS_MODE=$(/usr/bin/stat -c '%a' "$OS_RELEASE") \
    || fail "cannot inspect os-release mode"
[ "$OS_OWNER" -eq 0 ] || fail "os-release is not root-owned"
case "$OS_MODE" in
    *[2367][0-7]|*[0-7][2367]) fail "os-release is group/world-writable" ;;
esac

VIRTUALIZATION=$(/usr/bin/systemd-detect-virt --vm 2>/dev/null) \
    || fail "host does not report a hardware VM"
case "$VIRTUALIZATION" in
    ''|none|docker|podman|lxc|lxc-libvirt|systemd-nspawn|container-other)
        fail "hardware VM identity is missing or container-like: $VIRTUALIZATION"
        ;;
esac
set +e
CONTAINER=$(/usr/bin/systemd-detect-virt --container 2>/dev/null)
CONTAINER_STATUS=$?
set -e
[ "$CONTAINER_STATUS" -eq 1 ] && [ "$CONTAINER" = none ] \
    || fail "container probe failed or detected a container: status=$CONTAINER_STATUS identity=$CONTAINER"

/usr/bin/python3 -I -B - \
    "$OS_RELEASE" "$EXPECTED_VERSION" "$VIRTUALIZATION" <<'PY'
import json
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
expected_version = sys.argv[2]
virtualization = sys.argv[3]
fields = {}
for raw_line in path.read_text(encoding="utf-8").splitlines():
    if not raw_line or raw_line.startswith("#"):
        continue
    if "=" not in raw_line:
        raise SystemExit("LINUX VM HOST FAIL: malformed os-release line")
    key, raw_value = raw_line.split("=", 1)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or key in fields:
        raise SystemExit("LINUX VM HOST FAIL: malformed os-release key")
    if raw_value.startswith('"'):
        if len(raw_value) < 2 or not raw_value.endswith('"'):
            raise SystemExit("LINUX VM HOST FAIL: malformed os-release quote")
        value = bytes(raw_value[1:-1], "utf-8").decode("unicode_escape")
    elif raw_value.startswith("'"):
        if len(raw_value) < 2 or not raw_value.endswith("'"):
            raise SystemExit("LINUX VM HOST FAIL: malformed os-release quote")
        value = raw_value[1:-1]
    else:
        value = raw_value
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise SystemExit("LINUX VM HOST FAIL: os-release contains a control character")
    fields[key] = value

if fields.get("ID") != "ubuntu":
    raise SystemExit("LINUX VM HOST FAIL: Ubuntu is required")
if fields.get("VERSION_ID") != expected_version:
    raise SystemExit(
        "LINUX VM HOST FAIL: expected Ubuntu "
        + expected_version
        + ", found "
        + repr(fields.get("VERSION_ID"))
    )
if not re.fullmatch(r"[a-z0-9_.-]{1,64}", virtualization):
    raise SystemExit("LINUX VM HOST FAIL: virtualization identity is malformed")

report = {
    "acceptedAsModelEvidence": False,
    "architecture": "x86_64",
    "classification": "BOOTED_VM_PORTABILITY_CHECK_NOT_HERMETIC_IMAGE",
    "container": False,
    "modelExecuted": False,
    "operatingSystem": "ubuntu",
    "operatingSystemVersion": expected_version,
    "schemaVersion": "corelm-linux-vm-host-v1",
    "virtualization": virtualization,
}
sys.stdout.buffer.write(
    json.dumps(
        report,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    + b"\n"
)
PY

printf 'LINUX VM HOST PASS: Ubuntu %s x86_64 on %s\n' \
    "$EXPECTED_VERSION" "$VIRTUALIZATION" >&2
