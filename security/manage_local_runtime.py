#!/usr/bin/env python3
"""Validate and initialize a dedicated local Core LM virtual environment."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path


MARKER_NAME = ".corelm-real-llm-runtime-v1"
MARKER_BYTES = b"corelm-real-llm-runtime-v1\n"


def _safe_directory(path: Path, *, current_owner: bool) -> None:
    status = path.lstat()
    allowed_owners = {os.getuid()} if current_owner else {0, os.getuid()}
    if (
        not stat.S_ISDIR(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_uid not in allowed_owners
        or status.st_mode & 0o022
    ):
        raise ValueError(f"unsafe directory in runtime path: {path}")


def _safe_existing_chain(path: Path) -> None:
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            raise ValueError("runtime path has no existing parent")
        current = parent
    while True:
        _safe_directory(current, current_owner=False)
        if current == Path("/"):
            break
        current = current.parent


def _safe_regular_file(path: Path, *, current_owner: bool) -> None:
    status = path.lstat()
    allowed_owners = {os.getuid()} if current_owner else {0, os.getuid()}
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_uid not in allowed_owners
        or status.st_mode & 0o022
    ):
        raise ValueError(f"unsafe runtime file: {path}")


def canonical_target(raw_path: str, project_path: str) -> Path:
    if any(ord(character) < 32 or ord(character) == 127 for character in raw_path):
        raise ValueError("runtime path contains a control character")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        raise ValueError("runtime path must be absolute")
    resolved = candidate.resolve(strict=False)
    if raw_path != str(resolved):
        raise ValueError(
            "runtime path must be canonical and contain no symlink or '..' aliases"
        )
    home = Path.home().resolve(strict=True)
    project = Path(project_path).resolve(strict=True)
    dangerous = {Path("/"), home, home / ".cache", project}
    if (
        resolved in dangerous
        or resolved in project.parents
        or project in resolved.parents
    ):
        raise ValueError(f"refusing unsafe runtime target: {resolved}")
    _safe_existing_chain(resolved)
    return resolved


def validate_existing_runtime(path: Path) -> None:
    _safe_directory(path, current_owner=True)
    marker = path / MARKER_NAME
    _safe_regular_file(marker, current_owner=True)
    if marker.read_bytes() != MARKER_BYTES:
        raise ValueError("runtime ownership marker is invalid")
    configuration = path / "pyvenv.cfg"
    _safe_regular_file(configuration, current_owner=True)
    bin_directory = path / "bin"
    _safe_directory(bin_directory, current_owner=True)
    python = bin_directory / "python"
    declared_status = python.lstat()
    if not (
        stat.S_ISREG(declared_status.st_mode)
        or stat.S_ISLNK(declared_status.st_mode)
    ):
        raise ValueError("runtime Python is not a file or symlink")
    resolved_python = python.resolve(strict=True)
    _safe_regular_file(resolved_python, current_owner=False)
    _safe_existing_chain(resolved_python.parent)


def preflight(raw_path: str, project_path: str) -> tuple[str, Path]:
    target = canonical_target(raw_path, project_path)
    if target.exists():
        validate_existing_runtime(target)
        return "existing", target
    return "new", target


def initialize(raw_path: str, project_path: str) -> Path:
    target = canonical_target(raw_path, project_path)
    if not target.is_dir():
        raise ValueError("new virtual environment was not created")
    _safe_directory(target, current_owner=True)
    _safe_regular_file(target / "pyvenv.cfg", current_owner=True)
    _safe_directory(target / "bin", current_owner=True)
    python = target / "bin" / "python"
    if not python.exists():
        raise ValueError("new virtual environment has no Python executable")
    marker = target / MARKER_NAME
    descriptor = os.open(
        marker,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        os.write(descriptor, MARKER_BYTES)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    validate_existing_runtime(target)
    return target


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--mode",
        choices=("preflight", "initialize"),
        required=True,
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        if arguments.mode == "preflight":
            state, _ = preflight(arguments.path, arguments.project)
            print(state)
        else:
            print(initialize(arguments.path, arguments.project))
    except (OSError, ValueError) as error:
        print(f"LOCAL RUNTIME FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
