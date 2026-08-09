#!/usr/bin/env python3
"""Fail-closed inspection of a Git checkout against its exact HEAD tree.

``git status`` alone is not an integrity boundary: index flags such as
skip-worktree and assume-unchanged can hide modified tracked bytes.  This
module independently compares the raw HEAD tree, the stage-zero index, every
index flag view, and every tracked filesystem object.  It deliberately does
not reject ignored build products; callers separately decide whether ignored
outputs are permitted.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Iterable, Sequence


GIT = Path("/usr/bin/git")
OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}\Z")
MAX_GIT_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_TRACKED_FILES = 100_000
MAX_TRACKED_FILE_BYTES = 256 * 1024 * 1024
MAX_TRACKED_TOTAL_BYTES = 4 * 1024 * 1024 * 1024


class StrictCheckoutError(ValueError):
    """A checkout cannot be bound safely to its exact HEAD tree."""


@dataclass(frozen=True)
class CheckoutIdentity:
    root: Path
    commit: str
    tree: str
    origin: str
    branch: str | None
    upstream: str | None
    dirty: bool


def _environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": "/nonexistent-corelm-strict-checkout",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    }


def _run_git(
    root: Path,
    arguments: Sequence[str],
    *,
    allowed: tuple[int, ...] = (0,),
) -> tuple[int, bytes]:
    if not GIT.is_file() or not os.access(GIT, os.X_OK):
        raise StrictCheckoutError("/usr/bin/git is required")
    try:
        completed = subprocess.run(
            (
                str(GIT),
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.quotepath=false",
                "-C",
                str(root),
                *arguments,
            ),
            env=_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise StrictCheckoutError("strict Git inspection could not execute") from error
    if completed.returncode not in allowed:
        raise StrictCheckoutError(
            f"strict Git inspection rejected {' '.join(arguments)}"
        )
    if len(completed.stdout) > MAX_GIT_OUTPUT_BYTES:
        raise StrictCheckoutError("strict Git inspection output is oversized")
    return completed.returncode, completed.stdout


def _git_text(
    root: Path,
    arguments: Sequence[str],
    *,
    allowed: tuple[int, ...] = (0,),
) -> tuple[int, str]:
    code, raw = _run_git(root, arguments, allowed=allowed)
    try:
        return code, raw.decode("utf-8", errors="strict").rstrip("\n")
    except UnicodeDecodeError as error:
        raise StrictCheckoutError("strict Git text output is not UTF-8") from error


def _safe_path(raw: bytes, label: str) -> str:
    try:
        value = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise StrictCheckoutError(f"{label} path is not UTF-8") from error
    parts = value.split("/")
    if (
        not value
        or value.startswith("/")
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        or any(part in {"", ".", ".."} for part in parts)
        or parts[0] == ".git"
    ):
        raise StrictCheckoutError(f"{label} path is unsafe")
    return value


def _records(raw: bytes, label: str) -> list[bytes]:
    if not raw or not raw.endswith(b"\0"):
        raise StrictCheckoutError(f"{label} is empty or not NUL-terminated")
    values = raw[:-1].split(b"\0")
    if any(not value for value in values):
        raise StrictCheckoutError(f"{label} contains an empty record")
    return values


def _head_tree(root: Path) -> dict[str, tuple[str, str]]:
    raw = _run_git(root, ("ls-tree", "-rz", "--full-tree", "HEAD"))[1]
    values = _records(raw, "HEAD tree listing")
    if len(values) > MAX_TRACKED_FILES:
        raise StrictCheckoutError("HEAD tree contains too many tracked files")
    tree: dict[str, tuple[str, str]] = {}
    for value in values:
        header, separator, raw_path = value.partition(b"\t")
        fields = header.split(b" ")
        if not separator or len(fields) != 3:
            raise StrictCheckoutError("HEAD tree record is malformed")
        try:
            mode, object_type, object_id = (
                field.decode("ascii", errors="strict") for field in fields
            )
        except UnicodeDecodeError as error:
            raise StrictCheckoutError("HEAD tree header is not ASCII") from error
        path = _safe_path(raw_path, "HEAD tree")
        if (
            object_type != "blob"
            or mode not in {"100644", "100755", "120000"}
            or OBJECT_ID_RE.fullmatch(object_id) is None
            or path in tree
        ):
            raise StrictCheckoutError(
                "HEAD tree contains an unsupported object, mode, or path"
            )
        tree[path] = (mode, object_id)
    return tree


def _index(root: Path) -> dict[str, tuple[str, str]]:
    raw = _run_git(root, ("ls-files", "-z", "--stage"))[1]
    values = _records(raw, "Git index listing")
    entries: dict[str, tuple[str, str]] = {}
    for value in values:
        header, separator, raw_path = value.partition(b"\t")
        fields = header.split(b" ")
        if not separator or len(fields) != 3:
            raise StrictCheckoutError("Git index record is malformed")
        try:
            mode, object_id, stage = (
                field.decode("ascii", errors="strict") for field in fields
            )
        except UnicodeDecodeError as error:
            raise StrictCheckoutError("Git index header is not ASCII") from error
        path = _safe_path(raw_path, "Git index")
        if (
            stage != "0"
            or mode not in {"100644", "100755", "120000"}
            or OBJECT_ID_RE.fullmatch(object_id) is None
            or path in entries
        ):
            raise StrictCheckoutError("Git index is conflicted or malformed")
        entries[path] = (mode, object_id)
    return entries


def _ordinary_index_flags(root: Path, expected: set[str]) -> bool:
    ordinary = True
    for option, label in (
        ("-t", "status"),
        ("-v", "assume-unchanged"),
        ("-f", "fsmonitor"),
    ):
        raw = _run_git(root, ("ls-files", "-z", option))[1]
        observed: list[str] = []
        for record in _records(raw, f"Git index {label} flags"):
            if not record.startswith(b"H "):
                ordinary = False
            if len(record) < 3:
                raise StrictCheckoutError(f"Git index {label} flag is malformed")
            observed.append(_safe_path(record[2:], f"Git index {label}"))
        if len(observed) != len(set(observed)) or set(observed) != expected:
            raise StrictCheckoutError(f"Git index {label} paths differ from HEAD")
    return ordinary


def _identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _git_blob_sha1(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw, usedforsecurity=False).hexdigest()


def _parents_are_real_directories(root: Path, relative: str) -> None:
    current = root
    for part in relative.split("/")[:-1]:
        current = current / part
        try:
            value = current.lstat()
        except OSError as error:
            raise StrictCheckoutError("tracked parent directory is unavailable") from error
        if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
            raise StrictCheckoutError("tracked parent is not a real directory")


def _regular_bytes(path: Path, before: os.stat_result) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise StrictCheckoutError("tracked file cannot be opened safely") from error
    try:
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before):
            raise StrictCheckoutError("tracked file changed before reading")
        if opened.st_size > MAX_TRACKED_FILE_BYTES:
            raise StrictCheckoutError("tracked file exceeds its byte bound")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise StrictCheckoutError("tracked file ended before its declared size")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise StrictCheckoutError("tracked file grew while reading")
        after = os.fstat(descriptor)
        if _identity(after) != _identity(opened):
            raise StrictCheckoutError("tracked file changed while reading")
        return b"".join(chunks), after
    finally:
        os.close(descriptor)


def _worktree_matches(
    root: Path, tree: dict[str, tuple[str, str]]
) -> tuple[bool, dict[str, tuple[int, ...]]]:
    matches = True
    seals: dict[str, tuple[int, ...]] = {}
    total = 0
    for relative, (mode, expected_object) in tree.items():
        _parents_are_real_directories(root, relative)
        path = root / relative
        try:
            before = path.lstat()
        except OSError as error:
            raise StrictCheckoutError(f"tracked path is unavailable: {relative}") from error
        if mode == "120000":
            if not stat.S_ISLNK(before.st_mode) or before.st_nlink != 1:
                matches = False
                seals[relative] = _identity(before)
                continue
            try:
                raw = os.fsencode(os.readlink(path))
                after = path.lstat()
            except OSError as error:
                raise StrictCheckoutError("tracked symlink cannot be read safely") from error
            if _identity(after) != _identity(before):
                raise StrictCheckoutError("tracked symlink changed while reading")
        else:
            expected_executable = mode == "100755"
            executable = bool(stat.S_IMODE(before.st_mode) & 0o111)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or executable != expected_executable
            ):
                matches = False
                seals[relative] = _identity(before)
                continue
            raw, after = _regular_bytes(path, before)
        total += len(raw)
        if total > MAX_TRACKED_TOTAL_BYTES:
            raise StrictCheckoutError("tracked checkout exceeds its total byte bound")
        if _git_blob_sha1(raw) != expected_object:
            matches = False
        seals[relative] = _identity(after)
    return matches, seals


def _verify_seals(root: Path, seals: dict[str, tuple[int, ...]]) -> None:
    for relative, expected in seals.items():
        try:
            observed = _identity((root / relative).lstat())
        except OSError as error:
            raise StrictCheckoutError("tracked path disappeared during verification") from error
        if observed != expected:
            raise StrictCheckoutError("tracked checkout changed during verification")


def _optional_ref(root: Path, arguments: Sequence[str]) -> str | None:
    code, value = _git_text(root, arguments, allowed=(0, 1, 128))
    return value if code == 0 else None


def _validate_sparse_and_rewrite_state(root: Path) -> None:
    if _run_git(root, ("for-each-ref", "--format=%(refname)", "refs/replace"))[1]:
        raise StrictCheckoutError("Git replacement refs are forbidden")
    common_raw = _git_text(root, ("rev-parse", "--git-common-dir"))[1]
    common = Path(common_raw)
    if not common.is_absolute():
        common = root / common
    try:
        common = common.resolve(strict=True)
    except OSError as error:
        raise StrictCheckoutError("Git common directory is unavailable") from error
    grafts = common / "info" / "grafts"
    try:
        grafts.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise StrictCheckoutError("Git graft state cannot be inspected") from error
    else:
        raise StrictCheckoutError("Git legacy grafts are forbidden")
    for key in ("core.sparseCheckout", "core.sparseCheckoutCone", "index.sparse"):
        code, value = _git_text(root, ("config", "--bool", key), allowed=(0, 1))
        if code == 0 and value != "false":
            raise StrictCheckoutError("sparse checkout and sparse index are forbidden")
    sparse_raw = _git_text(root, ("rev-parse", "--git-path", "info/sparse-checkout"))[1]
    sparse = Path(sparse_raw)
    if not sparse.is_absolute():
        sparse = root / sparse
    try:
        sparse.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise StrictCheckoutError("sparse checkout metadata cannot be inspected") from error
    else:
        raise StrictCheckoutError("sparse checkout metadata is forbidden")


def inspect_checkout(
    repository: Path,
    *,
    require_clean: bool,
    expected_commit: str | None = None,
    expected_tree: str | None = None,
    expected_origins: Iterable[str] | None = None,
    expected_branch: str | None = None,
    expected_upstream: str | None = None,
) -> CheckoutIdentity:
    """Inspect and independently bind a checkout to its raw HEAD tree.

    With ``require_clean=False``, ordinary source deviations are returned as
    ``dirty=True`` so development provenance can still be recorded.  Rewrite,
    sparse-checkout, malformed-index, path-race, and unsafe-filesystem states
    always fail closed.
    """

    try:
        supplied = repository.absolute()
        supplied_status = supplied.lstat()
        root = supplied.resolve(strict=True)
    except OSError as error:
        raise StrictCheckoutError("checkout root is unavailable") from error
    if (
        supplied != root
        or stat.S_ISLNK(supplied_status.st_mode)
        or not stat.S_ISDIR(supplied_status.st_mode)
    ):
        raise StrictCheckoutError("checkout root must be a canonical real directory")
    root_identity = _identity(root.lstat())
    if _git_text(root, ("rev-parse", "--is-inside-work-tree"))[1] != "true":
        raise StrictCheckoutError("checkout is not a Git worktree")
    observed_root = Path(
        _git_text(root, ("rev-parse", "--show-toplevel"))[1]
    ).resolve(strict=True)
    if observed_root != root:
        raise StrictCheckoutError("checkout path is not the Git worktree root")
    if _git_text(root, ("rev-parse", "--show-object-format"))[1] != "sha1":
        raise StrictCheckoutError("checkout does not use SHA-1 Git objects")
    _validate_sparse_and_rewrite_state(root)

    commit = _git_text(root, ("rev-parse", "--verify", "HEAD^{commit}"))[1]
    tree_id = _git_text(root, ("rev-parse", "--verify", "HEAD^{tree}"))[1]
    if OBJECT_ID_RE.fullmatch(commit) is None or OBJECT_ID_RE.fullmatch(tree_id) is None:
        raise StrictCheckoutError("checkout HEAD identity is malformed")
    if expected_commit is not None and commit != expected_commit:
        raise StrictCheckoutError("checkout commit differs from the expected commit")
    if expected_tree is not None and tree_id != expected_tree:
        raise StrictCheckoutError("checkout tree differs from the expected tree")

    fetch = _git_text(root, ("remote", "get-url", "--all", "origin"))[1].splitlines()
    push = _git_text(
        root, ("remote", "get-url", "--push", "--all", "origin")
    )[1].splitlines()
    if len(fetch) != 1 or not fetch[0] or len(push) != 1:
        raise StrictCheckoutError("origin must have one exact fetch and push URL")
    origin = fetch[0]
    allowed_origins = set(expected_origins) if expected_origins is not None else None
    if allowed_origins is not None and (origin not in allowed_origins or push != fetch):
        raise StrictCheckoutError("checkout origin is not the expected canonical remote")

    branch = _optional_ref(root, ("symbolic-ref", "--quiet", "--short", "HEAD"))
    upstream = _optional_ref(
        root,
        ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"),
    )
    if expected_branch is not None and branch != expected_branch:
        raise StrictCheckoutError("checkout branch is not the expected branch")
    if expected_upstream is not None and upstream != expected_upstream:
        raise StrictCheckoutError("checkout upstream is not the expected upstream")

    status = _run_git(
        root,
        (
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored=no",
            "--ignore-submodules=none",
        ),
    )[1]
    head_tree = _head_tree(root)
    index = _index(root)
    flags_ordinary = _ordinary_index_flags(root, set(head_tree))
    worktree_matches, seals = _worktree_matches(root, head_tree)
    dirty = bool(status) or index != head_tree or not flags_ordinary or not worktree_matches

    if _git_text(root, ("rev-parse", "--verify", "HEAD^{commit}"))[1] != commit:
        raise StrictCheckoutError("checkout commit changed during verification")
    if _git_text(root, ("rev-parse", "--verify", "HEAD^{tree}"))[1] != tree_id:
        raise StrictCheckoutError("checkout tree changed during verification")
    if _head_tree(root) != head_tree or _index(root) != index:
        raise StrictCheckoutError("checkout tree or index changed during verification")
    if _ordinary_index_flags(root, set(head_tree)) != flags_ordinary:
        raise StrictCheckoutError("checkout index flags changed during verification")
    _verify_seals(root, seals)
    final_status = _run_git(
        root,
        (
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored=no",
            "--ignore-submodules=none",
        ),
    )[1]
    if final_status != status:
        raise StrictCheckoutError("checkout status changed during verification")
    if _identity(root.lstat()) != root_identity:
        raise StrictCheckoutError("checkout root changed during verification")
    if require_clean and dirty:
        raise StrictCheckoutError("checkout does not exactly match its signed HEAD tree")
    return CheckoutIdentity(
        root=root,
        commit=commit,
        tree=tree_id,
        origin=origin,
        branch=branch,
        upstream=upstream,
        dirty=dirty,
    )


def verify_clean_checkout(
    repository: Path,
    *,
    expected_commit: str | None = None,
    expected_tree: str | None = None,
    expected_origins: Iterable[str] | None = None,
    expected_branch: str | None = None,
    expected_upstream: str | None = None,
) -> CheckoutIdentity:
    return inspect_checkout(
        repository,
        require_clean=True,
        expected_commit=expected_commit,
        expected_tree=expected_tree,
        expected_origins=expected_origins,
        expected_branch=expected_branch,
        expected_upstream=expected_upstream,
    )


__all__ = [
    "CheckoutIdentity",
    "StrictCheckoutError",
    "inspect_checkout",
    "verify_clean_checkout",
]
