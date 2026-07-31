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
MANIFEST_KEYS = {
    "entries",
    "fileCount",
    "pythonDeclaredPath",
    "pythonExecutableSHA256",
    "pythonResolvedPath",
    "pythonVersion",
    "roots",
    "schemaVersion",
    "symlinkCount",
    "totalBytes",
}


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
        mode = stat.S_IMODE(status.st_mode)
        raise ValueError(
            f"{label} is unsafe: {resolved} has mode {mode:04o} "
            f"and owner uid {status.st_uid}; use an owner-controlled "
            "Python installation with no group/world write bits"
        )
    return resolved


def _loadable_symlink(relative: str) -> bool:
    return (
        relative.startswith("bin/")
        or (
            relative.startswith("lib/")
            and not relative.startswith("lib/pkgconfig/")
        )
    )


def _require_symlink_within_roots(
    path: Path,
    relative: str,
    roots: tuple[Path, ...],
) -> None:
    if not _loadable_symlink(relative):
        return
    resolved = path.resolve(strict=True)
    canonical_roots = tuple(root.resolve(strict=True) for root in roots)
    if not any(
        resolved == root or root in resolved.parents
        for root in canonical_roots
    ):
        raise ValueError(
            f"loadable runtime symlink escapes the manifested roots: {path}"
        )
    if "__pycache__" in resolved.parts:
        raise ValueError(
            f"loadable runtime symlink targets excluded bytecode: {path}"
        )
    status = resolved.lstat()
    if not (stat.S_ISREG(status.st_mode) or stat.S_ISDIR(status.st_mode)):
        raise ValueError(
            f"loadable runtime symlink has an unsupported target: {path}"
        )


def scan_root(
    root: Path,
    root_index: int,
    roots: tuple[Path, ...],
) -> tuple[list[dict[str, Any]], int]:
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
            mode = stat.S_IMODE(directory_status.st_mode)
            raise ValueError(
                f"unsafe runtime directory: {directory} has mode "
                f"{mode:04o} and owner uid {directory_status.st_uid}"
            )
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
                    mode = stat.S_IMODE(status.st_mode)
                    raise ValueError(
                        f"unsafe runtime file: {path} has mode {mode:04o} "
                        f"and owner uid {status.st_uid}"
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
                _require_symlink_within_roots(path, relative, roots)
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
    if Path(details["executable"]).resolve(strict=True) != resolved_python:
        raise ValueError(
            "Python probe executable differs from the declared executable"
        )
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
    runtime_roots = (base_prefix, virtual_environment)
    for root_index, root in enumerate(runtime_roots):
        scanned, root_bytes = scan_root(root, root_index, runtime_roots)
        entries.extend(scanned)
        total_bytes += root_bytes
    entries.sort(key=lambda entry: (entry["root"], entry["path"]))
    if len(entries) > MAXIMUM_FILES:
        raise ValueError("combined Python runtime exceeds the file-count limit")
    if total_bytes > MAXIMUM_TOTAL_BYTES:
        raise ValueError("combined Python runtime exceeds the byte limit")

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


def validate_manifest_files(manifest: dict[str, Any]) -> None:
    """Re-hash a recorded runtime without executing its Python binary."""

    if set(manifest) != MANIFEST_KEYS:
        raise ValueError("Python runtime manifest fields are not exact")
    if manifest["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError("Python runtime manifest schema is unsupported")
    roots_value = manifest["roots"]
    if (
        not isinstance(roots_value, list)
        or len(roots_value) != 2
    ):
        raise ValueError("Python runtime manifest roots are malformed")
    for root, role in zip(
        roots_value,
        ("base-prefix", "virtual-environment"),
        strict=True,
    ):
        if (
            not isinstance(root, dict)
            or set(root) != {"path", "role"}
            or not isinstance(root.get("path"), str)
            or root.get("role") != role
        ):
            raise ValueError("Python runtime manifest roots are malformed")
    roots = [
        safe_runtime_root(root["path"], label=root["role"])
        for root in roots_value
    ]
    if [str(root) for root in roots] != [
        root["path"] for root in roots_value
    ]:
        raise ValueError("Python runtime manifest roots are not canonical")
    if (
        roots[0] == roots[1]
        or roots[0] in roots[1].parents
        or roots[1] in roots[0].parents
    ):
        raise ValueError("Python runtime manifest roots overlap")

    declared_value = manifest["pythonDeclaredPath"]
    resolved_value = manifest["pythonResolvedPath"]
    if (
        not isinstance(declared_value, str)
        or not isinstance(resolved_value, str)
        or os.path.abspath(declared_value) != declared_value
        or os.path.abspath(resolved_value) != resolved_value
    ):
        raise ValueError("Python runtime manifest executable paths are unsafe")
    declared = Path(declared_value)
    declared_status = declared.lstat()
    if not (
        stat.S_ISREG(declared_status.st_mode)
        or stat.S_ISLNK(declared_status.st_mode)
    ):
        raise ValueError("declared Python executable is not a file or symlink")
    resolved = declared.resolve(strict=True)
    if str(resolved) != resolved_value:
        raise ValueError("Python executable resolution differs from manifest")
    if declared.parent.parent.resolve(strict=True) != roots[1]:
        raise ValueError("declared Python is outside the virtual environment")

    entries: list[dict[str, Any]] = []
    total_bytes = 0
    runtime_roots = tuple(roots)
    for root_index, root in enumerate(roots):
        scanned, root_bytes = scan_root(root, root_index, runtime_roots)
        entries.extend(scanned)
        total_bytes += root_bytes
    entries.sort(key=lambda entry: (entry["root"], entry["path"]))
    if len(entries) > MAXIMUM_FILES:
        raise ValueError("combined Python runtime exceeds the file-count limit")
    if total_bytes > MAXIMUM_TOTAL_BYTES:
        raise ValueError("combined Python runtime exceeds the byte limit")
    if manifest["entries"] != entries:
        raise ValueError("Python runtime files differ from the signed manifest")

    file_count = sum(entry["kind"] == "file" for entry in entries)
    symlink_count = sum(entry["kind"] == "symlink" for entry in entries)
    if (
        type(manifest["fileCount"]) is not int
        or manifest["fileCount"] != file_count
        or type(manifest["symlinkCount"]) is not int
        or manifest["symlinkCount"] != symlink_count
        or type(manifest["totalBytes"]) is not int
        or manifest["totalBytes"] != total_bytes
    ):
        raise ValueError("Python runtime manifest totals are inconsistent")
    resolved_entry = next(
        (
            entry
            for entry in entries
            if entry["kind"] == "file"
            and Path(roots[entry["root"]], entry["path"]) == resolved
        ),
        None,
    )
    if (
        resolved_entry is None
        or manifest["pythonExecutableSHA256"] != resolved_entry["sha256"]
    ):
        raise ValueError("Python executable digest differs from the manifest")
    version = manifest["pythonVersion"]
    components = version.split(".") if isinstance(version, str) else []
    if (
        len(components) != 3
        or components[:2] != ["3", "12"]
        or not components[2].isdigit()
    ):
        raise ValueError("Python runtime version is unsupported")


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
