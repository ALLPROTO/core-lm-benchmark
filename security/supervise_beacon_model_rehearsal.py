#!/usr/bin/env python3
"""Bound the model rehearsal and clean only its proven-owned stale lock."""

from __future__ import annotations

import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path.home() / ".cache" / "corelm-app-runtime" / "bin" / "python"
MODEL_CACHE = Path.home() / ".cache" / "corelm-model-assets"
MODEL_REHEARSAL = PROJECT_ROOT / "security" / "rehearse_beacon_model.py"
PROOF_LOCK = (
    Path.home() / ".cache" / "corelm-proof-runtimes" / ".proof-run.lock"
)
TIMEOUT_SECONDS = 300
MEMORY_POLL_SECONDS = 2.0
MINIMUM_FREE_MEMORY_PERCENT = 15
LOW_MEMORY_SAMPLES_TO_ABORT = 2
MAXIMUM_PROCESS_ID = (1 << 31) - 1
_STOP_SIGNAL: int | None = None


def _request_stop(signum: int, _frame: object) -> None:
    global _STOP_SIGNAL
    _STOP_SIGNAL = signum


def _stop_message() -> str | None:
    if _STOP_SIGNAL is None:
        return None
    try:
        name = signal.Signals(_STOP_SIGNAL).name
    except ValueError:
        name = str(_STOP_SIGNAL)
    return f"supervisor received {name}"


def _memory_free_percent() -> int:
    completed = subprocess.run(
        ["/usr/bin/memory_pressure", "-Q"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
    )
    if completed.returncode != 0:
        raise RuntimeError("cannot monitor macOS memory pressure")
    prefix = "System-wide memory free percentage:"
    matches = [
        line[len(prefix) :].strip().removesuffix("%")
        for line in completed.stdout.splitlines()
        if line.startswith(prefix)
    ]
    if len(matches) != 1 or not matches[0].isdigit():
        raise RuntimeError("macOS memory-pressure output is unexpected")
    return int(matches[0])


def _safe_lock_owner() -> int | None:
    try:
        status = PROOF_LOCK.lstat()
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(status.st_mode)
        or status.st_uid != os.getuid()
        or status.st_mode & 0o022
        or status.st_size > 32
    ):
        return None
    try:
        raw = PROOF_LOCK.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    if not raw.isdigit():
        return None
    owner = int(raw)
    return owner if 1 < owner <= MAXIMUM_PROCESS_ID else None


def _observe_owned_lock(group: int) -> int | None:
    owner = _safe_lock_owner()
    if owner is None:
        return None
    try:
        owner_group = os.getpgid(owner)
    except (OSError, OverflowError):
        return None
    return owner if owner_group == group else None


def _process_exists(process_id: int) -> bool:
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except (OSError, OverflowError):
        return True
    return True


def _cleanup_owned_lock(owner: int | None) -> bool:
    if owner is None or _safe_lock_owner() != owner:
        return False
    if _process_exists(owner):
        return False
    try:
        PROOF_LOCK.unlink()
    except FileNotFoundError:
        return True
    return not os.path.lexists(PROOF_LOCK)


def _group_exists(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_group(process: subprocess.Popen[bytes]) -> bool:
    group = process.pid
    if not _group_exists(group):
        if process.poll() is None:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                return False
        return True
    try:
        os.killpg(group, signal.SIGTERM)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + 5
    while _group_exists(group) and time.monotonic() < deadline:
        process.poll()
        time.sleep(0.1)
    if _group_exists(group):
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 10
    while _group_exists(group) and time.monotonic() < deadline:
        process.poll()
        time.sleep(0.1)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        return False
    return not _group_exists(group)


def _remove_private_temp(root: Path) -> bool:
    try:
        status = root.lstat()
    except FileNotFoundError:
        return True
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        try:
            root.unlink()
        except OSError:
            return False
        return False
    try:
        shutil.rmtree(root)
    except OSError:
        return False
    return not os.path.lexists(root)


def _validated_temp_parent() -> Path:
    project = PROJECT_ROOT.resolve(strict=True)
    parent = Path(tempfile.gettempdir()).resolve(strict=True)
    if parent == project or project in parent.parents:
        raise RuntimeError("supervisor TMPDIR resolves inside the repository")
    return parent


def run_supervised() -> int:
    if not RUNTIME.is_file() or not os.access(RUNTIME, os.X_OK):
        raise RuntimeError("locked app runtime is missing")
    if MODEL_CACHE.is_symlink() or not MODEL_CACHE.is_dir():
        raise RuntimeError("private model cache is missing or unsafe")
    project = PROJECT_ROOT.resolve(strict=True)
    temp_parent = _validated_temp_parent()
    created_root = Path(
        tempfile.mkdtemp(
            prefix="corelm-beacon-model-supervisor-",
            dir=temp_parent,
        )
    )
    process: subprocess.Popen[bytes] | None = None
    owned_lock: int | None = None
    supervisor_failure: str | None = None
    cleanup_failure: str | None = None
    try:
        temporary = created_root.resolve(strict=True)
        if temporary == project or project in temporary.parents:
            raise RuntimeError(
                "supervisor temp root resolves inside the repository"
            )
        temporary.chmod(0o700)
        environment = {
            "HOME": str(Path.home()),
            "HF_HOME": str(MODEL_CACHE),
            "TMPDIR": str(temporary),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
        }
        stop = _stop_message()
        if stop is not None:
            raise RuntimeError(stop)
        process = subprocess.Popen(
            [
                "/usr/bin/caffeinate",
                "-dimsu",
                str(RUNTIME),
                "-I",
                "-B",
                str(MODEL_REHEARSAL),
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            start_new_session=True,
        )
        deadline = time.monotonic() + TIMEOUT_SECONDS
        low_memory_samples = 0
        while process.poll() is None:
            stop = _stop_message()
            if stop is not None:
                supervisor_failure = stop
                break
            observed = _observe_owned_lock(process.pid)
            if observed is not None:
                owned_lock = observed
            if time.monotonic() >= deadline:
                supervisor_failure = (
                    f"model rehearsal exceeded {TIMEOUT_SECONDS} seconds"
                )
                break
            try:
                free = _memory_free_percent()
            except Exception as error:
                supervisor_failure = str(error)
                break
            if free < MINIMUM_FREE_MEMORY_PERCENT:
                low_memory_samples += 1
            else:
                low_memory_samples = 0
            if low_memory_samples >= LOW_MEMORY_SAMPLES_TO_ABORT:
                supervisor_failure = (
                    "model rehearsal crossed the sustained 15% free-memory "
                    "stop threshold"
                )
                break
            time.sleep(MEMORY_POLL_SECONDS)
        if supervisor_failure is None:
            supervisor_failure = _stop_message()
        if supervisor_failure is not None:
            if owned_lock is None:
                owned_lock = _observe_owned_lock(process.pid)
            if not _terminate_group(process):
                raise RuntimeError(
                    supervisor_failure + "; process group survived termination"
                )
        try:
            return_code = process.wait(timeout=1)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                "model rehearsal leader survived termination"
            ) from error
        if supervisor_failure is not None:
            raise RuntimeError(supervisor_failure)
        return return_code
    finally:
        if process is not None and (
            process.poll() is None or _group_exists(process.pid)
        ):
            if owned_lock is None:
                owned_lock = _observe_owned_lock(process.pid)
            if not _terminate_group(process):
                cleanup_failure = "model rehearsal process group survived cleanup"
        remaining_lock = _safe_lock_owner()
        if owned_lock is not None and remaining_lock == owned_lock:
            if not _cleanup_owned_lock(owned_lock):
                cleanup_failure = (
                    "owned proof lock could not be removed safely"
                )
        elif os.path.lexists(PROOF_LOCK):
            cleanup_failure = (
                "an unproven or unsafe proof lock remains; it was not removed"
            )
        group_alive = process is not None and _group_exists(process.pid)
        if not group_alive and not _remove_private_temp(created_root):
            cleanup_failure = cleanup_failure or (
                "private supervisor temp root was unsafe"
            )
        if cleanup_failure is not None:
            raise RuntimeError(cleanup_failure)


def main() -> int:
    if len(sys.argv) != 1:
        print(
            "MODEL REHEARSAL SUPERVISOR FAIL: command-line overrides are "
            "forbidden",
            file=sys.stderr,
        )
        return 2
    global _STOP_SIGNAL
    _STOP_SIGNAL = None
    handled_signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous = {
        signum: signal.getsignal(signum) for signum in handled_signals
    }
    for signum in handled_signals:
        signal.signal(signum, _request_stop)
    try:
        try:
            return run_supervised()
        except Exception as error:
            print(
                f"MODEL REHEARSAL SUPERVISOR FAIL: {error}",
                file=sys.stderr,
            )
            return 1
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
