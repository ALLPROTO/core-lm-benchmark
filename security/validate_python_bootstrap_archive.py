#!/usr/bin/env python3
"""Validate the topology of the pinned owner-local Python tar archive."""

from __future__ import annotations

import argparse
import tarfile
from pathlib import Path, PurePosixPath


class ArchiveValidationError(ValueError):
    """Raised when an archive could escape or ambiguously overwrite its root."""


def _normalized_path(
    value: PurePosixPath,
    *,
    base: PurePosixPath = PurePosixPath(),
    description: str,
) -> PurePosixPath:
    if value.is_absolute():
        raise ArchiveValidationError(f"{description} is absolute: {value}")
    parts: list[str] = []
    for part in (*base.parts, *value.parts):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ArchiveValidationError(
                    f"{description} escapes the archive root: {value}"
                )
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        raise ArchiveValidationError(f"{description} is empty")
    return PurePosixPath(*parts)


def validate_archive(archive_path: Path) -> None:
    """Reject paths, links, duplicates, and special entries unsafe to extract."""

    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
    except (OSError, tarfile.TarError) as error:
        raise ArchiveValidationError(
            f"could not read Python archive: {error}"
        ) from error
    if not members:
        raise ArchiveValidationError("Python archive is empty")

    by_name: dict[PurePosixPath, tarfile.TarInfo] = {}
    for member in members:
        path = _normalized_path(
            PurePosixPath(member.name),
            description=f"archive path {member.name!r}",
        )
        if path.parts[0] != "python":
            raise ArchiveValidationError(
                f"unexpected archive root: {member.name}"
            )
        if path in by_name:
            raise ArchiveValidationError(
                f"duplicate archive entry: {member.name}"
            )
        if not (
            member.isdir()
            or member.isreg()
            or member.issym()
            or member.islnk()
        ):
            raise ArchiveValidationError(
                f"special archive entry is forbidden: {member.name}"
            )
        by_name[path] = member

    for path, member in by_name.items():
        if not (member.issym() or member.islnk()):
            continue
        target = PurePosixPath(member.linkname)
        # POSIX symlinks resolve from their containing directory. Tar hardlink
        # targets are names relative to the archive root.
        base = path.parent if member.issym() else PurePosixPath()
        try:
            normalized_target = _normalized_path(
                target,
                base=base,
                description=f"archive link target for {member.name!r}",
            )
        except ArchiveValidationError as error:
            raise ArchiveValidationError(
                f"archive link escapes Python root: {member.name}: {error}"
            ) from error
        if normalized_target.parts[0] != "python":
            raise ArchiveValidationError(
                f"archive link escapes Python root: {member.name}"
            )
        if member.islnk():
            hardlink_target = by_name.get(normalized_target)
            if hardlink_target is None or not hardlink_target.isreg():
                raise ArchiveValidationError(
                    "archive hardlink target is not a registered regular "
                    f"file: {member.name}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    arguments = parser.parse_args()
    try:
        validate_archive(arguments.archive)
    except ArchiveValidationError as error:
        parser.exit(1, f"PYTHON ARCHIVE VALIDATION FAIL: {error}\n")
    print("PYTHON ARCHIVE VALIDATION PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
