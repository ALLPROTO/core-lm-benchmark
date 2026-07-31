#!/usr/bin/env python3
"""Require an exact installed-distribution closure from hash-locked files."""

from __future__ import annotations

import argparse
import importlib.metadata
import re
import sys
from pathlib import Path


LOCKED_REQUIREMENT = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9._+!-]*)"
    r"(?:\s|\\|$)"
)


def normalize_name(value: str) -> str:
    normalized = re.sub(r"[-_.]+", "-", value).lower()
    if not normalized or normalized.startswith("-") or normalized.endswith("-"):
        raise ValueError(f"invalid distribution name: {value!r}")
    return normalized


def locked_distributions(lock_files: list[Path]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for lock_file in lock_files:
        if lock_file.is_symlink() or not lock_file.is_file():
            raise ValueError(f"lock file is missing or unsafe: {lock_file}")
        for line_number, line in enumerate(
            lock_file.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line or line[0].isspace() or line.startswith("#"):
                continue
            match = LOCKED_REQUIREMENT.match(line)
            if match is None:
                raise ValueError(
                    f"unsupported lock entry at {lock_file}:{line_number}"
                )
            raw_name, version = match.groups()
            name = normalize_name(raw_name)
            previous = expected.setdefault(name, version)
            if previous != version:
                raise ValueError(
                    f"conflicting locked versions for {name}: "
                    f"{previous} and {version}"
                )
    if not expected:
        raise ValueError("the supplied lock files contain no distributions")
    return expected


def installed_distributions() -> dict[str, str]:
    installed: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        raw_name = distribution.metadata.get("Name")
        if not isinstance(raw_name, str) or not raw_name:
            raise ValueError("installed distribution has no valid Name metadata")
        name = normalize_name(raw_name)
        version = distribution.version
        if not isinstance(version, str) or not version:
            raise ValueError(f"installed distribution {name} has no version")
        if name in installed:
            raise ValueError(f"installed distribution is duplicated: {name}")
        installed[name] = version
    return installed


def verify_environment(runtime: Path, lock_files: list[Path]) -> None:
    expected_runtime = runtime.resolve(strict=True)
    actual_runtime = Path(sys.prefix).resolve(strict=True)
    base_runtime = Path(sys.base_prefix).resolve(strict=True)
    if expected_runtime != actual_runtime:
        raise ValueError(
            f"Python prefix {actual_runtime} does not match {expected_runtime}"
        )
    if base_runtime == actual_runtime:
        raise ValueError("a dedicated virtual environment is required")

    expected = locked_distributions(lock_files)
    installed = installed_distributions()
    missing = sorted(set(expected) - set(installed))
    extra = sorted(set(installed) - set(expected))
    changed = sorted(
        name
        for name in expected.keys() & installed.keys()
        if expected[name] != installed[name]
    )
    if missing or extra or changed:
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("extra=" + ",".join(extra))
        if changed:
            details.append(
                "versions="
                + ",".join(
                    f"{name}:{installed[name]}!={expected[name]}"
                    for name in changed
                )
            )
        raise ValueError(
            "installed distributions differ from the exact lock closure: "
            + "; ".join(details)
        )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--lock", action="append", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        verify_environment(arguments.runtime, arguments.lock)
    except (OSError, ValueError) as error:
        print(f"LOCKED ENVIRONMENT FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "LOCKED ENVIRONMENT PASS: installed distributions exactly match "
        "the supplied hash-locked closure."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
