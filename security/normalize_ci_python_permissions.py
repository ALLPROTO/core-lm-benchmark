#!/usr/bin/env python3
"""Narrowly normalize the pinned setup-python trust boundary on Linux CI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any


EXPECTED_VERSION = "3.12.13"
EXPECTED_ARCHITECTURE = "x64"
EXPECTED_EXECUTABLE_NAME = "python3.12"
MAX_EXECUTABLE_BYTES = 128 * 1024 * 1024


class NormalizationError(ValueError):
    """The hosted interpreter does not match the narrow CI trust boundary."""


def _canonical_directory(path: Path, *, label: str) -> os.stat_result:
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise NormalizationError(f"{label} must be an existing canonical path")
    status = path.lstat()
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        raise NormalizationError(f"{label} must be a real directory")
    if status.st_uid not in {0, os.getuid()}:
        raise NormalizationError(f"{label} has an unexpected owner")
    return status


def _regular_file_sha256(path: Path, *, label: str) -> tuple[str, os.stat_result]:
    status = path.lstat()
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
        raise NormalizationError(f"{label} must be a regular non-symlink file")
    if status.st_uid not in {0, os.getuid()}:
        raise NormalizationError(f"{label} has an unexpected owner")
    if status.st_size < 1 or status.st_size > MAX_EXECUTABLE_BYTES:
        raise NormalizationError(f"{label} has an unsafe byte length")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != status.st_dev
            or opened.st_ino != status.st_ino
            or opened.st_size != status.st_size
        ):
            raise NormalizationError(f"{label} changed between stat and open")
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.lstat()
    if (
        after.st_dev != status.st_dev
        or after.st_ino != status.st_ino
        or after.st_size != status.st_size
    ):
        raise NormalizationError(f"{label} changed while hashing")
    return digest.hexdigest(), status


def _remove_other_write(path: Path, before: os.stat_result, *, label: str) -> int:
    if before.st_mode & 0o022:
        if before.st_uid != os.getuid():
            raise NormalizationError(
                f"{label} is writable by another principal and is not user-owned"
            )
        os.chmod(
            path,
            stat.S_IMODE(before.st_mode) & ~0o022,
            follow_symlinks=False,
        )
    after = path.lstat()
    if (
        after.st_dev != before.st_dev
        or after.st_ino != before.st_ino
        or after.st_uid != before.st_uid
        or after.st_mode & 0o022
    ):
        raise NormalizationError(f"{label} identity or permissions differ")
    return stat.S_IMODE(after.st_mode)


def normalize_permissions(
    *,
    runner_tool_cache: Path,
    python_location: Path,
    executable: Path,
) -> dict[str, Any]:
    """Normalize only the exact setup-python directory, bin dir, and executable."""

    _canonical_directory(runner_tool_cache, label="runner tool cache")
    python_root = runner_tool_cache / "Python"
    version_directory = python_root / EXPECTED_VERSION
    expected_location = version_directory / EXPECTED_ARCHITECTURE
    if python_location != expected_location:
        raise NormalizationError("pythonLocation differs from the pinned tool-cache path")
    python_root_status = _canonical_directory(
        python_root, label="Python tool-cache root"
    )
    version_status = _canonical_directory(
        version_directory, label="pinned Python version directory"
    )
    location_status = _canonical_directory(
        python_location, label="pinned Python location"
    )
    bin_directory = python_location / "bin"
    bin_status = _canonical_directory(bin_directory, label="pinned Python bin")
    resolved_executable = executable.resolve(strict=True)
    expected_executable = bin_directory / EXPECTED_EXECUTABLE_NAME
    if resolved_executable != expected_executable:
        raise NormalizationError("resolved Python executable differs from the pinned path")
    digest_before, executable_status = _regular_file_sha256(
        resolved_executable,
        label="pinned Python executable",
    )

    targets = (
        ("pythonRoot", python_root, python_root_status, "Python tool-cache root"),
        (
            "version",
            version_directory,
            version_status,
            "pinned Python version directory",
        ),
        ("location", python_location, location_status, "pinned Python location"),
        ("bin", bin_directory, bin_status, "pinned Python bin"),
        (
            "executable",
            resolved_executable,
            executable_status,
            "pinned Python executable",
        ),
    )
    modes = {
        key: _remove_other_write(path, before, label=label)
        for key, path, before, label in targets
    }
    for key, path, before, label in targets:
        after = path.lstat()
        if (
            after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
            or after.st_uid != before.st_uid
            or stat.S_IFMT(after.st_mode) != stat.S_IFMT(before.st_mode)
            or stat.S_IMODE(after.st_mode) != modes[key]
        ):
            raise NormalizationError(
                f"{label} changed after trust-boundary normalization"
            )
    digest_after, _ = _regular_file_sha256(
        resolved_executable,
        label="normalized Python executable",
    )
    if digest_after != digest_before:
        raise NormalizationError("Python executable bytes changed during normalization")
    return {
        "executable": str(resolved_executable),
        "modes": {key: f"{value:04o}" for key, value in modes.items()},
        "sha256": digest_after,
        "version": EXPECTED_VERSION,
    }


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-tool-cache", required=True, type=Path)
    parser.add_argument("--python-location", required=True, type=Path)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    parsed = parse_arguments(arguments)
    try:
        result = normalize_permissions(
            runner_tool_cache=parsed.runner_tool_cache,
            python_location=parsed.python_location,
            executable=Path(sys.executable),
        )
    except (OSError, ValueError) as error:
        print(f"CI PYTHON PERMISSION NORMALIZATION FAIL: {error}", file=sys.stderr)
        return 1
    print("CI PYTHON PERMISSION NORMALIZATION PASS")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
