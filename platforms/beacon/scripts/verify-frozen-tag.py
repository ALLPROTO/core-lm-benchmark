#!/usr/bin/env python3
"""Read-only verification of the published beacon tag and its frozen blobs."""

from __future__ import annotations

import hashlib
import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GIT = Path("/usr/bin/git")
FREEZE_TAG = "corelm-beacon-heldout-v1"
EXPECTED_TAG_COMMIT = "0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44"
EXPECTED_PROTOCOL_COMMIT = "b34bc4d06c00c86b99076b117049e2d590d73bcd"
FREEZE_PATH = "RealLLM/beacon_freeze.json"
REGISTRATION_PATH = "RealLLM/beacon_registration.json"
EXPECTED_FILE_COUNT = 26
MAX_GIT_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_GIT_ERROR_BYTES = 64 * 1024
GIT_TIMEOUT_SECONDS = 15


def _git(*arguments: str) -> bytes:
    environment = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "HOME": str(Path.home()),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }
    process = subprocess.Popen(
        [
            str(GIT),
            "--no-replace-objects",
            "-c",
            "core.hooksPath=/dev/null",
            *arguments,
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        process.wait()
        raise ValueError("failed to create bounded Git output pipes")

    streams = selectors.DefaultSelector()
    streams.register(process.stdout, selectors.EVENT_READ, "stdout")
    streams.register(process.stderr, selectors.EVENT_READ, "stderr")
    output = bytearray()
    error = bytearray()
    deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
    try:
        while streams.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("Git compatibility check timed out")
            for key, _ in streams.select(timeout=min(remaining, 0.25)):
                chunk = os.read(key.fd, 64 * 1024)
                if not chunk:
                    streams.unregister(key.fileobj)
                    continue
                target = output if key.data == "stdout" else error
                limit = (
                    MAX_GIT_OUTPUT_BYTES
                    if key.data == "stdout"
                    else MAX_GIT_ERROR_BYTES
                )
                if len(target) + len(chunk) > limit:
                    raise ValueError(f"Git {key.data} exceeds the verifier limit")
                target.extend(chunk)
        remaining = max(0.0, deadline - time.monotonic())
        process.wait(timeout=remaining)
    except Exception:
        process.kill()
        process.wait()
        raise
    finally:
        streams.close()
        process.stdout.close()
        process.stderr.close()

    if process.returncode:
        detail = error.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git {' '.join(arguments)} failed: {detail}")
    return bytes(output)


def _blob_at(commit: str, relative: str) -> bytes:
    object_name = f"{commit}:{relative}"
    if _git("cat-file", "-t", object_name).strip() != b"blob":
        raise ValueError(f"normative path is not a Git blob: {relative}")
    size_text = _git("cat-file", "-s", object_name).strip()
    if not size_text.isdigit():
        raise ValueError(f"Git returned an invalid blob size: {relative}")
    size = int(size_text)
    if size > MAX_GIT_OUTPUT_BYTES:
        raise ValueError(f"Git blob exceeds the verifier limit: {relative}")
    content = _git("cat-file", "blob", object_name)
    if len(content) != size:
        raise ValueError(f"Git blob size changed while reading: {relative}")
    return content


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON value is forbidden: {value}")


def _json_at(commit: str, relative: str) -> dict[str, Any]:
    value = json.loads(
        _blob_at(commit, relative),
        object_pairs_hook=_strict_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError(f"{relative} is not a JSON object")
    return value


def _safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("normative path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError(f"unsafe normative path: {value!r}")
    return value


def _implementation_digest(entries: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for relative, content in entries:
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "little"))
        digest.update(encoded)
        digest.update(len(content).to_bytes(8, "little"))
        digest.update(content)
    return digest.hexdigest()


def verify() -> None:
    if not GIT.is_file() or not os.access(GIT, os.X_OK):
        raise ValueError("the system Git executable is unavailable")
    repository = Path(
        _git("rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve(strict=True)
    if repository != PROJECT_ROOT:
        raise ValueError("compatibility verifier is not inside its repository")

    tag_type = _git("cat-file", "-t", f"refs/tags/{FREEZE_TAG}").strip()
    if tag_type != b"commit":
        raise ValueError("the freeze tag must remain a lightweight commit tag")
    tag_commit = _git(
        "rev-parse", f"refs/tags/{FREEZE_TAG}^{{commit}}"
    ).decode("ascii").strip()
    if tag_commit != EXPECTED_TAG_COMMIT:
        raise ValueError("the local freeze tag resolves to an unexpected commit")
    topology = _git(
        "rev-list", "--parents", "-n", "1", EXPECTED_TAG_COMMIT
    ).decode("ascii").split()
    if topology != [EXPECTED_TAG_COMMIT, EXPECTED_PROTOCOL_COMMIT]:
        raise ValueError("the published two-commit freeze topology changed")

    freeze = _json_at(EXPECTED_TAG_COMMIT, FREEZE_PATH)
    if freeze.get("protocolCommit") != EXPECTED_PROTOCOL_COMMIT:
        raise ValueError("freeze manifest names an unexpected protocol commit")
    files = freeze.get("normativeFiles")
    if not isinstance(files, list) or len(files) != EXPECTED_FILE_COUNT:
        raise ValueError("freeze manifest must contain exactly 26 files")

    registration = _json_at(EXPECTED_PROTOCOL_COMMIT, REGISTRATION_PATH)
    registered_paths = registration.get("protocolSourceFiles")
    if not isinstance(registered_paths, list):
        raise ValueError("registration has no protocol source manifest")

    seen: set[str] = set()
    implementation_entries: list[tuple[str, bytes]] = []
    manifest_paths: list[str] = []
    for item in files:
        if not isinstance(item, dict) or set(item) != {"bytes", "path", "sha256"}:
            raise ValueError("freeze file entry has unexpected fields")
        relative = _safe_relative_path(item["path"])
        if relative in seen:
            raise ValueError(f"duplicate normative path: {relative}")
        seen.add(relative)
        manifest_paths.append(relative)
        protocol_blob = _blob_at(EXPECTED_PROTOCOL_COMMIT, relative)
        tag_blob = _blob_at(EXPECTED_TAG_COMMIT, relative)
        if tag_blob != protocol_blob:
            raise ValueError(f"freeze commit changed normative blob: {relative}")
        if type(item["bytes"]) is not int or item["bytes"] != len(protocol_blob):
            raise ValueError(f"normative size differs: {relative}")
        expected_sha = item["sha256"]
        if (
            not isinstance(expected_sha, str)
            or len(expected_sha) != 64
            or any(character not in "0123456789abcdef" for character in expected_sha)
            or hashlib.sha256(protocol_blob).hexdigest() != expected_sha
        ):
            raise ValueError(f"normative SHA-256 differs: {relative}")
        implementation_entries.append((relative, protocol_blob))

    if manifest_paths != registered_paths:
        raise ValueError("freeze paths differ from the registered source order")
    if _implementation_digest(implementation_entries) != freeze.get(
        "implementationSHA256"
    ):
        raise ValueError("implementation digest differs from the freeze manifest")


def main() -> int:
    if len(sys.argv) != 1:
        print(
            "BEACON TAG COMPATIBILITY ERROR: this command accepts no arguments",
            file=sys.stderr,
        )
        return 2
    try:
        verify()
    except Exception as error:
        print(f"BEACON TAG COMPATIBILITY ERROR: {error}", file=sys.stderr)
        return 1
    print(
        "BEACON TAG COMPATIBILITY VERIFIED: exact tag, protocol parent, "
        "and 26 normative Git blobs."
    )
    print("NOT A SCIENTIFIC RESULT: no model, data, NIST, or result path was opened.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
