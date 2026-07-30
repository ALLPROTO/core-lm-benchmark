#!/usr/bin/env python3
"""Generate a deterministic integrity manifest for an external Python runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "corelm-python-runtime-manifest-v1"
MAXIMUM_FILES = 100_000
MAXIMUM_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_regular_file(path: Path, expected: os.stat_result) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"runtime entry is not a regular file: {path}")
        if (
            opened.st_dev != expected.st_dev
            or opened.st_ino != expected.st_ino
            or opened.st_size != expected.st_size
        ):
            raise ValueError(f"runtime entry changed before hashing: {path}")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, READ_CHUNK_BYTES):
            digest.update(chunk)
        finished = os.fstat(descriptor)
        if (
            finished.st_dev != opened.st_dev
            or finished.st_ino != opened.st_ino
            or finished.st_size != opened.st_size
            or finished.st_mtime_ns != opened.st_mtime_ns
            or finished.st_ctime_ns != opened.st_ctime_ns
        ):
            raise ValueError(f"runtime entry changed while hashing: {path}")
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def inspect_python(python: Path) -> dict[str, str]:
    probe = (
        "import json,sys;"
        "print(json.dumps({"
        "'executable':sys.executable,"
        "'prefix':sys.prefix,"
        "'basePrefix':sys.base_prefix,"
        "'version':'.'.join(map(str,sys.version_info[:3]))"
        "},sort_keys=True))"
    )
    completed = subprocess.run(
        [str(python), "-I", "-B", "-c", probe],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(Path.home()),
        },
    )
    value = json.loads(completed.stdout)
    if (
        not isinstance(value, dict)
        or any(not isinstance(value.get(key), str) for key in (
            "executable",
            "prefix",
            "basePrefix",
            "version",
        ))
    ):
        raise ValueError("Python runtime probe returned an invalid result")
    return value


def safe_runtime_root(path: str, *, label: str) -> Path:
    root = Path(path)
    if not root.is_absolute():
        raise ValueError(f"{label} is not absolute")
    resolved = root.resolve(strict=True)
    if resolved in {Path("/"), Path.home().resolve()}:
        raise ValueError(f"refusing unsafe {label}: {resolved}")
    status = resolved.stat()
    if not stat.S_ISDIR(status.st_mode):
        raise ValueError(f"{label} is not a directory")
    if status.st_mode & 0o022 or status.st_uid not in {0, os.getuid()}:
        raise ValueError(f"{label} is group- or world-writable")
    return resolved


def scan_root(root: Path, root_index: int) -> tuple[list[dict[str, Any]], int]:
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        directory_status = directory.lstat()
        if (
            not stat.S_ISDIR(directory_status.st_mode)
            or directory_status.st_mode & 0o022
            or directory_status.st_uid not in {0, os.getuid()}
        ):
            raise ValueError(f"unsafe runtime directory: {directory}")
        with os.scandir(directory) as iterator:
            children = sorted(iterator, key=lambda item: item.name)
        for child in children:
            path = Path(child.path)
            relative = path.relative_to(root).as_posix()
            status = path.lstat()
            if stat.S_ISDIR(status.st_mode):
                if child.name == "__pycache__":
                    continue
                pending.append(path)
                continue
            if stat.S_ISREG(status.st_mode):
                if (
                    status.st_mode & 0o022
                    or status.st_uid not in {0, os.getuid()}
                ):
                    raise ValueError(
                        f"runtime file is group- or world-writable: {path}"
                    )
                total_bytes += status.st_size
                if total_bytes > MAXIMUM_TOTAL_BYTES:
                    raise ValueError("Python runtime exceeds the byte limit")
                entries.append(
                    {
                        "kind": "file",
                        "path": relative,
                        "root": root_index,
                        "sha256": sha256_regular_file(path, status),
                        "size": status.st_size,
                    }
                )
            elif stat.S_ISLNK(status.st_mode):
                entries.append(
                    {
                        "kind": "symlink",
                        "path": relative,
                        "root": root_index,
                        "target": os.readlink(path),
                    }
                )
            else:
                raise ValueError(f"unsupported runtime entry type: {path}")
            if len(entries) > MAXIMUM_FILES:
                raise ValueError("Python runtime exceeds the file-count limit")
    entries.sort(key=lambda entry: (entry["root"], entry["path"]))
    return entries, total_bytes


def build_manifest(python: Path) -> dict[str, Any]:
    declared = python.absolute()
    declared_status = declared.lstat()
    if not (
        stat.S_ISREG(declared_status.st_mode)
        or stat.S_ISLNK(declared_status.st_mode)
    ):
        raise ValueError("declared Python executable is not a file or symlink")
    resolved_python = declared.resolve(strict=True)
    details = inspect_python(declared)
    virtual_environment = safe_runtime_root(
        details["prefix"], label="virtual-environment prefix"
    )
    base_prefix = safe_runtime_root(
        details["basePrefix"], label="base Python prefix"
    )
    expected_venv = declared.parent.parent.resolve(strict=True)
    if virtual_environment != expected_venv:
        raise ValueError(
            "Python prefix does not match the declared virtual environment"
        )
    if base_prefix == virtual_environment:
        raise ValueError("a dedicated virtual environment is required")
    if (
        base_prefix in virtual_environment.parents
        or virtual_environment in base_prefix.parents
    ):
        raise ValueError("runtime roots must not overlap")

    roots = [
        {"path": str(base_prefix), "role": "base-prefix"},
        {"path": str(virtual_environment), "role": "virtual-environment"},
    ]
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for root_index, root in enumerate((base_prefix, virtual_environment)):
        scanned, root_bytes = scan_root(root, root_index)
        entries.extend(scanned)
        total_bytes += root_bytes
    entries.sort(key=lambda entry: (entry["root"], entry["path"]))

    resolved_entry = next(
        (
            entry
            for entry in entries
            if entry["kind"] == "file"
            and Path(roots[entry["root"]]["path"], entry["path"])
            == resolved_python
        ),
        None,
    )
    if resolved_entry is None:
        raise ValueError("resolved Python executable is outside runtime roots")

    return {
        "entries": entries,
        "fileCount": sum(entry["kind"] == "file" for entry in entries),
        "pythonDeclaredPath": str(declared),
        "pythonExecutableSHA256": resolved_entry["sha256"],
        "pythonResolvedPath": str(resolved_python),
        "pythonVersion": details["version"],
        "roots": roots,
        "schemaVersion": SCHEMA_VERSION,
        "symlinkCount": sum(entry["kind"] == "symlink" for entry in entries),
        "totalBytes": total_bytes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-python-sha256")
    arguments = parser.parse_args()

    manifest = build_manifest(arguments.python)
    expected_digest = arguments.expected_python_sha256
    if (
        expected_digest is not None
        and manifest["pythonExecutableSHA256"] != expected_digest
    ):
        raise ValueError("Python executable does not match the pinned digest")
    payload = canonical_json_bytes(manifest) + b"\n"
    descriptor = os.open(
        arguments.output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
        0o644,
    )
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    print(
        f"manifested {manifest['fileCount']} files, "
        f"{manifest['symlinkCount']} symlinks, "
        f"{manifest['totalBytes']} bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
