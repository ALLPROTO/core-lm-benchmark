#!/usr/bin/env python3
"""Validate private Linux runtime, cache, and evidence destinations."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


EXPECTED_PYTHON_VERSION = "3.12.13"
RUNTIME_MARKER_NAME = ".corelm-linux-runtime-v1"
RUNTIME_MARKER_BYTES = b"corelm-linux-runtime-v1\n"


def _safe_directory(path: Path, *, current_owner: bool) -> None:
    status = path.lstat()
    allowed_owners = {os.getuid()} if current_owner else {0, os.getuid()}
    if (
        not stat.S_ISDIR(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_uid not in allowed_owners
        or status.st_mode & 0o022
    ):
        raise ValueError(f"unsafe directory: {path}")


def _safe_regular_file(path: Path, *, current_owner: bool) -> None:
    status = path.lstat()
    allowed_owners = {os.getuid()} if current_owner else {0, os.getuid()}
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_uid not in allowed_owners
        or status.st_mode & 0o022
    ):
        raise ValueError(f"unsafe regular file: {path}")


def _safe_existing_chain(path: Path) -> None:
    current = path
    while not os.path.lexists(current):
        parent = current.parent
        if parent == current:
            raise ValueError(f"path has no existing ancestor: {path}")
        current = parent
    anchor = current
    while True:
        status = current.lstat()
        root_owned_sticky_ancestor = (
            current != anchor
            and stat.S_ISDIR(status.st_mode)
            and not stat.S_ISLNK(status.st_mode)
            and status.st_uid == 0
            and bool(status.st_mode & stat.S_ISVTX)
        )
        if not root_owned_sticky_ancestor:
            _safe_directory(current, current_owner=False)
        if current == Path("/"):
            return
        current = current.parent


def canonical_target(raw_path: str, project_path: str, *, label: str) -> Path:
    if not raw_path or any(
        ord(character) < 32 or ord(character) == 127
        for character in raw_path
    ):
        raise ValueError(f"{label} path is empty or contains a control character")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        raise ValueError(f"{label} path must be absolute")
    resolved = candidate.resolve(strict=False)
    if raw_path != str(resolved):
        raise ValueError(
            f"{label} path must be canonical and contain no symlink or '..' aliases"
        )

    home = Path.home().resolve(strict=True)
    project = Path(project_path).resolve(strict=True)
    dangerous = {Path("/"), home, home / ".cache", project}
    if (
        resolved in dangerous
        or resolved in project.parents
        or project in resolved.parents
    ):
        raise ValueError(f"refusing unsafe {label} target: {resolved}")
    _safe_existing_chain(resolved)
    return resolved


def _overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def require_disjoint_paths(paths: dict[str, Path]) -> None:
    entries = list(paths.items())
    for index, (first_label, first) in enumerate(entries):
        for second_label, second in entries[index + 1 :]:
            if _overlap(first, second):
                raise ValueError(
                    f"{first_label} and {second_label} paths overlap: "
                    f"{first} and {second}"
                )


def _disk_anchor(path: Path) -> Path:
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            raise ValueError(f"cannot find a disk anchor for {path}")
        current = parent
    if current.is_symlink() or not current.is_dir():
        raise ValueError(f"disk anchor is not a safe directory: {current}")
    return current


def verify_target_disk_space(
    paths: dict[str, Path], *, minimum_free_kib: int
) -> list[dict[str, Any]]:
    if minimum_free_kib < 1:
        raise ValueError("minimum free disk space must be positive")
    required_bytes = minimum_free_kib * 1024
    volumes: dict[int, dict[str, Any]] = {}
    for label, path in paths.items():
        anchor = _disk_anchor(path)
        device = anchor.stat().st_dev
        entry = volumes.setdefault(
            device,
            {"anchor": anchor, "labels": [], "freeBytes": 0},
        )
        entry["labels"].append(label)

    results: list[dict[str, Any]] = []
    for device, entry in sorted(volumes.items()):
        usage = shutil.disk_usage(entry["anchor"])
        if usage.free < required_bytes:
            labels = ", ".join(sorted(entry["labels"]))
            raise ValueError(
                f"at least {minimum_free_kib} KiB free disk space is required "
                f"for {labels} on {entry['anchor']}"
            )
        results.append(
            {
                "device": device,
                "anchor": str(entry["anchor"]),
                "labels": sorted(entry["labels"]),
                "freeBytes": usage.free,
            }
        )
    return results


def validate_targets(
    *,
    project: str,
    runtime: str,
    cache: str,
    run: str,
    minimum_free_kib: int,
) -> tuple[dict[str, Path], list[dict[str, Any]]]:
    paths = {
        "runtime": canonical_target(runtime, project, label="runtime"),
        "cache": canonical_target(cache, project, label="cache"),
        "run": canonical_target(run, project, label="run"),
    }
    require_disjoint_paths(paths)
    volumes = verify_target_disk_space(
        paths, minimum_free_kib=minimum_free_kib
    )
    return paths, volumes


def _runtime_python_observation(python: Path) -> dict[str, Any]:
    program = """
import json
import pathlib
import platform
import sys
print(json.dumps({
    "basePrefix": str(pathlib.Path(sys.base_prefix).resolve(strict=True)),
    "executable": str(pathlib.Path(sys.executable).resolve(strict=True)),
    "prefix": str(pathlib.Path(sys.prefix).resolve(strict=True)),
    "version": platform.python_version(),
}, sort_keys=True))
"""
    completed = subprocess.run(
        [str(python), "-I", "-B", "-c", program],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
        env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
    )
    if completed.returncode:
        detail = completed.stderr.strip()[:1000]
        raise ValueError(f"runtime Python inspection failed: {detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("runtime Python returned invalid inspection data") from error
    if not isinstance(value, dict):
        raise ValueError("runtime Python inspection is not an object")
    return value


def validate_runtime_observation(
    observation: dict[str, Any],
    *,
    runtime: Path,
    resolved_python: Path,
    expected_version: str = EXPECTED_PYTHON_VERSION,
) -> Path:
    expected = {"basePrefix", "executable", "prefix", "version"}
    if set(observation) != expected or any(
        not isinstance(value, str) or not value
        for value in observation.values()
    ):
        raise ValueError("runtime Python inspection has unexpected fields")
    if observation["version"] != expected_version:
        raise ValueError(
            f"runtime Python {expected_version} is required; "
            f"found {observation['version']}"
        )
    if Path(observation["prefix"]) != runtime:
        raise ValueError(
            f"runtime Python prefix {observation['prefix']} does not match {runtime}"
        )
    if Path(observation["executable"]) != resolved_python:
        raise ValueError("runtime Python executable changed during inspection")
    base_prefix = Path(observation["basePrefix"])
    if base_prefix == runtime:
        raise ValueError("a dedicated virtual environment is required")
    _safe_existing_chain(base_prefix)
    _safe_directory(base_prefix, current_owner=False)
    return base_prefix


def validate_existing_runtime(
    runtime: Path, *, expected_version: str = EXPECTED_PYTHON_VERSION
) -> dict[str, Any]:
    if runtime.resolve(strict=True) != runtime:
        raise ValueError("runtime path is not canonical")
    _safe_existing_chain(runtime)
    _safe_directory(runtime, current_owner=True)
    if stat.S_IMODE(runtime.stat().st_mode) != 0o700:
        raise ValueError("runtime directory mode must be exactly 0700")

    marker = runtime / RUNTIME_MARKER_NAME
    _safe_regular_file(marker, current_owner=True)
    if stat.S_IMODE(marker.stat().st_mode) != 0o600:
        raise ValueError("runtime marker mode must be exactly 0600")
    if marker.read_bytes() != RUNTIME_MARKER_BYTES:
        raise ValueError("runtime ownership marker is invalid")

    configuration = runtime / "pyvenv.cfg"
    _safe_regular_file(configuration, current_owner=True)
    bin_directory = runtime / "bin"
    _safe_directory(bin_directory, current_owner=True)
    python = bin_directory / "python"
    declared_status = python.lstat()
    if not (
        stat.S_ISREG(declared_status.st_mode)
        or stat.S_ISLNK(declared_status.st_mode)
    ):
        raise ValueError("runtime Python is not a file or symlink")
    if declared_status.st_uid != os.getuid():
        raise ValueError("runtime Python entry has an unexpected owner")
    resolved_python = python.resolve(strict=True)
    _safe_regular_file(resolved_python, current_owner=False)
    _safe_existing_chain(resolved_python.parent)

    observation = _runtime_python_observation(python)
    base_prefix = validate_runtime_observation(
        observation,
        runtime=runtime,
        resolved_python=resolved_python,
        expected_version=expected_version,
    )
    return {
        "runtime": str(runtime),
        "python": str(resolved_python),
        "basePrefix": str(base_prefix),
        "version": observation["version"],
    }


def initialize_runtime_marker(runtime: Path) -> None:
    resolved = runtime.resolve(strict=True)
    if resolved != runtime:
        raise ValueError("runtime path is not canonical")
    _safe_existing_chain(runtime)
    _safe_directory(runtime, current_owner=True)
    os.chmod(runtime, 0o700, follow_symlinks=False)
    marker = runtime / RUNTIME_MARKER_NAME
    descriptor = os.open(
        marker,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        os.write(descriptor, RUNTIME_MARKER_BYTES)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_runtime(staging: Path, destination: Path) -> None:
    staging = staging.resolve(strict=True)
    destination = destination.resolve(strict=False)
    if staging.parent != destination.parent:
        raise ValueError("staging and destination must share one parent")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"runtime destination appeared: {destination}")
    _safe_directory(staging.parent, current_owner=True)
    _safe_directory(staging, current_owner=True)
    os.rename(staging, destination)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    paths = subparsers.add_parser("validate-paths")
    paths.add_argument("--project", required=True)
    paths.add_argument("--runtime", required=True)
    paths.add_argument("--cache", required=True)
    paths.add_argument("--run", required=True)
    paths.add_argument("--minimum-free-kib", required=True, type=int)

    validate = subparsers.add_parser("validate-runtime")
    validate.add_argument("--runtime", required=True, type=Path)

    initialize = subparsers.add_parser("initialize-runtime")
    initialize.add_argument("--runtime", required=True, type=Path)

    publish = subparsers.add_parser("publish-runtime")
    publish.add_argument("--staging", required=True, type=Path)
    publish.add_argument("--destination", required=True, type=Path)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    parsed = _parser().parse_args(arguments)
    try:
        if parsed.command == "validate-paths":
            paths, volumes = validate_targets(
                project=parsed.project,
                runtime=parsed.runtime,
                cache=parsed.cache,
                run=parsed.run,
                minimum_free_kib=parsed.minimum_free_kib,
            )
            result = {
                "paths": {key: str(value) for key, value in paths.items()},
                "volumes": volumes,
            }
        elif parsed.command == "validate-runtime":
            result = validate_existing_runtime(parsed.runtime)
        elif parsed.command == "initialize-runtime":
            initialize_runtime_marker(parsed.runtime)
            result = {"runtime": str(parsed.runtime), "marker": "created"}
        elif parsed.command == "publish-runtime":
            publish_runtime(parsed.staging, parsed.destination)
            result = {"runtime": str(parsed.destination), "published": True}
        else:  # pragma: no cover - argparse enforces the command set.
            raise AssertionError("unreachable command")
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"LINUX RUNTIME SAFETY FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
