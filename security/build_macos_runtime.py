#!/usr/bin/env python3
"""Build a resumable, owner-local macOS runtime without changing completed ones."""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import json
import os
import secrets
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from security import manage_local_runtime as runtime  # noqa: E402


LOCK_PATHS = (
    ".github/locks/pip-maintained.txt",
    ".github/locks/real-llm-portable-py312.txt",
)


def _binding(target: Path, project: Path) -> dict:
    return {
        "schemaVersion": "corelm-macos-installing-v1",
        "destination": str(target),
        "lockfiles": {
            relative: hashlib.sha256((project / relative).read_bytes()).hexdigest()
            for relative in LOCK_PATHS
        },
    }


def _pending(target: Path, binding: dict) -> dict:
    runtime._safe_directory(target, current_owner=True)
    marker = target / runtime.INSTALLING_MARKER_NAME
    runtime._safe_regular_file(marker, current_owner=True)
    if marker.stat().st_size > 4096:
        raise ValueError("unfinished runtime marker is oversized")
    record = json.loads(marker.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or set(record) != set(binding) | {"nonce"}:
        raise ValueError("unfinished runtime marker has invalid fields")
    if any(record[key] != value for key, value in binding.items()):
        raise ValueError("unfinished runtime belongs to different inputs; use a fresh path")
    nonce = record["nonce"]
    if not isinstance(nonce, str) or len(nonce) != 64 or any(
        character not in "0123456789abcdef" for character in nonce
    ):
        raise ValueError("unfinished runtime marker has an invalid nonce")
    return record


@contextmanager
def _install_lock(target: Path):
    # Keep the lock inode: unlinking it would allow two independent locks.
    suffix = hashlib.sha256(os.fsencode(target)).hexdigest()[:24]
    path = target.parent / f".corelm-macos-install-{suffix}.lock"
    descriptor = os.open(
        path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600
    )
    try:
        status = os.fstat(descriptor)
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_mode & 0o077
            or status.st_nlink != 1
        ):
            raise ValueError("unsafe runtime installation lock")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("another process is installing this runtime") from error
        yield descriptor
    finally:
        os.close(descriptor)


def _rename_new(source: Path, destination: Path) -> None:
    """Atomically reserve a missing destination; never replace an empty directory."""
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        rename = library.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = rename(os.fsencode(source), os.fsencode(destination), 4)  # RENAME_EXCL
    elif sys.platform.startswith("linux"):
        rename = library.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    else:
        raise ValueError("atomic runtime reservation requires macOS or Linux")
    if result:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), str(destination))


def _reserve(target: Path, binding: dict) -> dict:
    staging = Path(tempfile.mkdtemp(prefix=".corelm-macos-reserve.", dir=target.parent))
    record = {**binding, "nonce": secrets.token_hex(32)}
    try:
        marker = staging / runtime.INSTALLING_MARKER_NAME
        with marker.open("x", encoding="utf-8") as handle:
            os.chmod(marker, 0o600)
            json.dump(record, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _rename_new(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return record


def _remove_pending(target: Path, binding: dict, *, nonce: str | None = None) -> None:
    record = _pending(target, binding)
    if nonce is not None and record["nonce"] != nonce:
        raise ValueError("unfinished runtime ownership changed; refusing cleanup")
    if not shutil.rmtree.avoids_symlink_attacks:
        raise ValueError("safe unfinished-runtime cleanup is unavailable")
    # Never follow installed symlinks, including the venv's base-Python links.
    for directory, names, files in os.walk(target, followlinks=False):
        for path in [Path(directory), *(Path(directory) / name for name in names + files)]:
            status = path.lstat()
            if status.st_uid != os.getuid() or not (
                stat.S_ISREG(status.st_mode)
                or stat.S_ISDIR(status.st_mode)
                or stat.S_ISLNK(status.st_mode)
            ):
                raise ValueError("unfinished runtime contains unexpected ownership or file types")
    shutil.rmtree(target)


def _run(
    python: Path, arguments: list[str], cache: Path, *, lock_fd: int | None = None
) -> None:
    command = [str(python), "-I", "-B", "-X", f"pycache_prefix={cache}", *arguments]
    process = subprocess.Popen(
        command,
        env={**os.environ, "PIP_CONFIG_FILE": os.devnull},
        # If this coordinator is killed while pip/venv is still running, its
        # child must retain the lock until it too finishes. A retry must not
        # erase an environment that an orphan installer is still writing.
        pass_fds=() if lock_fd is None else (lock_fd,),
        start_new_session=True,
    )
    try:
        status = process.wait()
    except BaseException:
        # Terminate this installer and its children before partial-tree cleanup.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise
    if status:
        raise subprocess.CalledProcessError(status, command)


def _verify(
    target: Path, project: Path, cache: Path,
    *, pip_only: bool = False, lock_fd: int | None = None,
) -> None:
    python = target / "bin/python"
    _run(python, ["-m", "pip", "check"], cache, lock_fd=lock_fd)
    arguments = [str(project / "security/verify_locked_environment.py"), "--runtime", str(target)]
    for relative in LOCK_PATHS[:1] if pip_only else LOCK_PATHS:
        arguments += ["--lock", str(project / relative)]
    _run(python, arguments, cache, lock_fd=lock_fd)


def build_runtime(
    raw_target: str,
    project: Path,
    cache: Path,
    *,
    index_url: str = "https://pypi.org/simple",
    wheelhouse: str = "",
    skip_install: bool = False,
) -> None:
    project = project.resolve(strict=True)
    target = runtime.canonical_target(raw_target, str(project))
    binding = _binding(target, project)
    if skip_install and not target.exists():
        raise ValueError("CORELM_SKIP_RUNTIME_INSTALL=1 requires an initialized runtime")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime._safe_existing_chain(target.parent)
    runtime._safe_directory(target.parent, current_owner=True)
    with _install_lock(target) as lock_fd:
        if target.exists():
            if os.path.lexists(target / runtime.INSTALLING_MARKER_NAME):
                if skip_install:
                    raise ValueError("runtime installation is unfinished; rerun without skip-install")
                _remove_pending(target, binding)
            else:
                runtime.validate_existing_runtime(target)
                try:
                    _verify(target, project, cache, lock_fd=lock_fd)
                except subprocess.CalledProcessError as error:
                    raise ValueError(
                        "existing runtime differs from maintained locks; use a fresh private path "
                        "and retain the old runtime for its apps and evidence"
                    ) from error
                return
        record = _reserve(target, binding)
        try:
            _run(Path(sys.executable), ["-m", "venv", str(target)], cache, lock_fd=lock_fd)
            runtime.initialize(str(target), str(project), allow_installing=True)
            python = target / "bin/python"
            common = [
                "-m", "pip", "install", "--isolated", "--no-input",
                "--disable-pip-version-check", "--no-cache-dir",
                "--only-binary=:all:", "--require-hashes",
            ]
            source = ["--no-index", "--find-links", wheelhouse] if wheelhouse else [
                "--index-url", "https://pypi.org/simple"
            ]
            _run(python, common + ["--no-deps"] + source + ["-r", str(project / LOCK_PATHS[0])], cache, lock_fd=lock_fd)
            # The bundled installer must never contact the configurable mirror.
            _verify(target, project, cache, pip_only=True, lock_fd=lock_fd)
            source = ["--no-index", "--find-links", wheelhouse] if wheelhouse else [
                "--index-url", index_url
            ]
            _run(python, common + source + ["-r", str(project / LOCK_PATHS[1])], cache, lock_fd=lock_fd)
            _verify(target, project, cache, lock_fd=lock_fd)
            runtime.validate_existing_runtime(target, allow_installing=True)
            if _pending(target, binding) != record:
                raise ValueError("unfinished runtime ownership changed")
            (target / runtime.INSTALLING_MARKER_NAME).unlink()
        except BaseException:
            # A hard kill leaves the bound marker for safe recovery on the next build.
            if target.exists() and os.path.lexists(target / runtime.INSTALLING_MARKER_NAME):
                _remove_pending(target, binding, nonce=record["nonce"])
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--pycache", required=True, type=Path)
    parser.add_argument("--index-url", default="https://pypi.org/simple")
    parser.add_argument("--wheelhouse", default="")
    parser.add_argument("--skip-install", action="store_true")
    arguments = parser.parse_args()
    os.umask(0o077)
    try:
        if sys.version_info[:3] != (3, 12, 13):
            raise ValueError("trusted bootstrap Python must be 3.12.13")
        build_runtime(
            arguments.runtime, arguments.project, arguments.pycache,
            index_url=arguments.index_url, wheelhouse=arguments.wheelhouse,
            skip_install=arguments.skip_install,
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"MACOS RUNTIME BUILD FAIL: {error}", file=sys.stderr)
        return 1
    print("MACOS RUNTIME READY: complete exact-lock environment; existing runtimes preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
