#!/usr/bin/env python3
"""Hermetic pre-pulse rehearsal of the frozen beacon protocol primitives.

This is deliberately not a mode of the one-shot runner.  It has no network,
model, corpus, subprocess, or normative-result capability.  Every write is
confined to a private temporary directory and deleted before exit.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RealLLM import beacon_protocol as protocol  # noqa: E402


REHEARSAL_SCHEMA = "corelm-beacon-rehearsal-v1"
REHEARSAL_CUTOFF = datetime(2026, 8, 2, 17, 0, tzinfo=timezone.utc)
RESULT_DIRECTORY = PROJECT_ROOT / "real-llm-beacon-results"
PROOF_LOCK = Path.home() / ".cache" / "corelm-proof-runtimes" / ".proof-run.lock"
NORMATIVE_ARTIFACTS = (
    RESULT_DIRECTORY / "attempt.json",
    RESULT_DIRECTORY / "resolution.json",
    RESULT_DIRECTORY / "outcome.json",
    RESULT_DIRECTORY / "primary-evidence",
)
FIXTURE_PULSE = (
    PROJECT_ROOT
    / "Tests"
    / "fixtures"
    / "nist-beacon-chain-2-pulse-1884240.json"
)
FIXTURE_CERTIFICATE = (
    PROJECT_ROOT
    / "Tests"
    / "fixtures"
    / "nist-beacon-certificate-528943a5.pem"
)
FIXTURE_TIMESTAMP = "2026-07-31T23:20:00.000Z"
SYNTHETIC_SELECTION_DIGEST = (
    "779cdecfa37dc06ee8117c11d19358a8eeb4c40adc9e0beba21ac70f284578b8"
    "dde2fa3aee06a651cd63b1ab3f7593bb6039269b62228c0959e0f204d2d2ed40"
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _path_present(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_path(path: Path) -> Any:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return {"kind": "absent"}
    mode = stat.S_IMODE(status.st_mode)
    if stat.S_ISLNK(status.st_mode):
        return {"kind": "symlink", "mode": mode, "target": os.readlink(path)}
    if stat.S_ISREG(status.st_mode):
        return {
            "kind": "file",
            "mode": mode,
            "bytes": status.st_size,
            "sha256": _sha256_file(path),
        }
    if stat.S_ISDIR(status.st_mode):
        return {
            "kind": "directory",
            "mode": mode,
            "entries": {
                child.name: _snapshot_path(child)
                for child in sorted(path.iterdir(), key=lambda item: item.name)
            },
        }
    return {"kind": "other", "mode": mode, "type": status.st_mode}


def _frozen_snapshot() -> tuple[tuple[str, int, str], ...]:
    freeze = protocol.load_json_object(
        protocol.FREEZE_PATH, label="beacon freeze manifest"
    )
    entries = freeze.get("normativeFiles")
    if not isinstance(entries, list) or len(entries) != 26:
        raise ValueError("freeze manifest must contain exactly 26 normative files")
    observed: list[tuple[str, int, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("freeze manifest entry is not an object")
        relative = entry.get("path")
        expected_bytes = entry.get("bytes")
        expected_sha256 = entry.get("sha256")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or type(expected_bytes) is not int
            or not isinstance(expected_sha256, str)
        ):
            raise ValueError("freeze manifest contains an unsafe entry")
        path = PROJECT_ROOT / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"frozen path is missing or unsafe: {relative}")
        actual_bytes = path.stat().st_size
        actual_sha256 = _sha256_file(path)
        if actual_bytes != expected_bytes or actual_sha256 != expected_sha256:
            raise ValueError(f"frozen path differs from its manifest: {relative}")
        observed.append((relative, actual_bytes, actual_sha256))
    if protocol.implementation_sha256() != freeze.get("implementationSHA256"):
        raise ValueError("frozen implementation aggregate differs")
    return tuple(observed)


def _inside(path_value: object, allowed_root: Path) -> bool:
    if isinstance(path_value, int):
        return True
    try:
        candidate = Path(os.fsdecode(path_value)).resolve(strict=False)
    except (OSError, TypeError, ValueError):
        return False
    return candidate == allowed_root or allowed_root in candidate.parents


def _install_audit_guard(allowed_root: Path) -> None:
    allowed_root = allowed_root.resolve(strict=True)
    write_flags = (
        os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    )
    path_mutations = {
        "os.chmod",
        "os.chown",
        "os.link",
        "os.mkdir",
        "os.mknod",
        "os.remove",
        "os.removexattr",
        "os.rename",
        "os.rmdir",
        "os.setxattr",
        "os.symlink",
        "os.truncate",
        "os.utime",
        "shutil.copyfile",
        "shutil.copymode",
        "shutil.copystat",
        "shutil.move",
        "shutil.rmtree",
    }
    two_path_mutations = {
        "os.link",
        "os.rename",
        "os.symlink",
        "shutil.copyfile",
        "shutil.copymode",
        "shutil.copystat",
        "shutil.move",
    }

    def guard(event: str, arguments: tuple[Any, ...]) -> None:
        if event == "open":
            path_value = arguments[0] if arguments else None
            mode = arguments[1] if len(arguments) > 1 else None
            flags = arguments[2] if len(arguments) > 2 else 0
            writable_mode = isinstance(mode, str) and any(
                marker in mode for marker in ("w", "a", "x", "+")
            )
            writable_flags = isinstance(flags, int) and bool(flags & write_flags)
            if (writable_mode or writable_flags) and not _inside(
                path_value, allowed_root
            ):
                raise PermissionError("rehearsal write escaped its private temp root")
        elif event in path_mutations:
            paths = (
                arguments[:2]
                if event in two_path_mutations
                else arguments[:1]
            )
            if any(not _inside(path_value, allowed_root) for path_value in paths):
                raise PermissionError(
                    "rehearsal mutation escaped its private temp root"
                )
        elif (
            event.startswith("socket.")
            or event == "subprocess.Popen"
            or event == "os.system"
            or event.startswith("os.exec")
            or event.startswith("os.spawn")
            or event.startswith("os.posix_spawn")
            or event == "pty.spawn"
        ):
            raise PermissionError(
                "network and child processes are forbidden in rehearsal"
            )

    sys.addaudithook(guard)


def _remove_temp_tree(root: Path) -> None:
    if not _path_present(root):
        return
    if root.is_symlink() or not root.is_dir():
        root.unlink()
        return
    for child in list(root.iterdir()):
        if child.is_symlink() or not child.is_dir():
            child.unlink()
        else:
            _remove_temp_tree(child)
    root.rmdir()


def _validated_temp_parent() -> Path:
    project = PROJECT_ROOT.resolve(strict=True)
    parent = Path(tempfile.gettempdir()).resolve(strict=True)
    if parent == project or project in parent.parents:
        raise ValueError("protocol rehearsal TMPDIR resolves inside the repository")
    return parent


def _synthetic_protocol_checks(temp_root: Path) -> None:
    protocol.validate_registration_and_ledger()
    pulse_envelope = protocol.load_json_object(
        FIXTURE_PULSE, label="historical NIST fixture"
    )
    if set(pulse_envelope) != {"pulse"} or not isinstance(
        pulse_envelope["pulse"], dict
    ):
        raise ValueError("historical NIST fixture envelope is invalid")
    pulse = pulse_envelope["pulse"]
    verification = protocol.verify_nist_pulse(
        pulse,
        FIXTURE_CERTIFICATE.read_bytes(),
        expected_timestamp=FIXTURE_TIMESTAMP,
    )
    if not (
        verification.get("signatureVerified") is True
        and verification.get("outputValueVerified") is True
    ):
        raise ValueError("historical NIST fixture did not verify")

    synthetic_registration = {
        "selection": {
            "candidateCount": 7,
            "domainSeparatorHex": b"CoreLM/beacon-rehearsal/v1\0".hex(),
        }
    }
    registration_bytes = protocol.canonical_json_bytes(synthetic_registration)
    dummy_windows = [
        {"id": f"synthetic-{index}", "synthetic": True}
        for index in range(7)
    ]
    selection = protocol.select_window(
        registration_bytes,
        str(verification["outputValue"]),
        dummy_windows,
    )
    if (
        selection.get("candidateIndex") != 3
        or selection.get("counter") != 0
        or selection.get("seedDigestSHA512") != SYNTHETIC_SELECTION_DIGEST
        or selection.get("selectedWindow") != dummy_windows[3]
    ):
        raise ValueError("synthetic selection known answer differs")

    state_directory = temp_root / "states"
    base = {
        "schemaVersion": REHEARSAL_SCHEMA,
        "evidenceClass": "synthetic-rehearsal",
        "countsTowardScientificVerdict": False,
        "scientificEvidence": False,
        "targetBeaconFetched": False,
        "testDatasetOpened": False,
        "resultDirectoryWritten": False,
    }
    paths: list[Path] = []
    for sequence, stage in enumerate(("started", "resolved", "terminal"), start=1):
        state = dict(base, sequence=sequence, syntheticStage=stage)
        path = state_directory / f"stage-{sequence}.json"
        content = protocol.serialized_json_bytes(state)
        protocol.durable_exclusive_write(path, content)
        if path.read_bytes() != content or stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise ValueError("temporary durable state did not round-trip exactly")
        paths.append(path)
    try:
        protocol.durable_exclusive_write(paths[0], b"replacement forbidden\n")
    except ValueError:
        pass
    else:
        raise ValueError("exclusive state write unexpectedly allowed replacement")


def run_rehearsal() -> None:
    if not sys.flags.isolated or not sys.flags.dont_write_bytecode:
        raise ValueError("rehearsal requires Python -I -B")
    if _utc_now() >= REHEARSAL_CUTOFF:
        raise ValueError("pre-pulse rehearsal cutoff has passed")
    present = [path.name for path in NORMATIVE_ARTIFACTS if _path_present(path)]
    if present:
        raise ValueError("normative beacon artifacts already exist")
    if _path_present(PROOF_LOCK):
        raise ValueError("a Core LM proof lock is already present")

    temp_parent = _validated_temp_parent()
    frozen_before = _frozen_snapshot()
    results_before = _snapshot_path(RESULT_DIRECTORY)
    proof_lock_before = _snapshot_path(PROOF_LOCK)
    created_root = Path(
        tempfile.mkdtemp(
            prefix="corelm-beacon-rehearsal-",
            dir=temp_parent,
        )
    )
    try:
        temp_root = created_root.resolve(strict=True)
        if PROJECT_ROOT == temp_root or PROJECT_ROOT in temp_root.parents:
            raise ValueError(
                "rehearsal temp root must be outside the repository"
            )
        temp_root.chmod(0o700)
        (temp_root / "states").mkdir(mode=0o700)
        _install_audit_guard(temp_root)
        _synthetic_protocol_checks(temp_root)
        if _frozen_snapshot() != frozen_before:
            raise RuntimeError("frozen files changed during rehearsal")
        if _snapshot_path(RESULT_DIRECTORY) != results_before:
            raise RuntimeError("normative result tree changed during rehearsal")
        if _snapshot_path(PROOF_LOCK) != proof_lock_before:
            raise RuntimeError("proof lock changed during rehearsal")
    finally:
        _remove_temp_tree(created_root)
    if _path_present(created_root):
        raise RuntimeError("rehearsal temporary directory survived cleanup")
    if _snapshot_path(RESULT_DIRECTORY) != results_before:
        raise RuntimeError("normative result tree changed after cleanup")


def main() -> int:
    if len(sys.argv) != 1:
        print(
            "SYNTHETIC REHEARSAL FAIL: command-line overrides are forbidden",
            file=sys.stderr,
        )
        return 2
    try:
        run_rehearsal()
    except Exception as error:
        print(f"SYNTHETIC REHEARSAL FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "SYNTHETIC REHEARSAL PASS: frozen hashes, historical beacon "
        "cryptography, dummy selection, and temp-only state transitions verified; "
        "the scientific attempt is untouched."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
