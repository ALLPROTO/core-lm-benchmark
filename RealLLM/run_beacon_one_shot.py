#!/usr/bin/env python3
"""Execute the separately registered beacon-selected held-out run once."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.dont_write_bytecode = True


def _early_reject_local_bytecode() -> None:
    if not sys.flags.isolated or not sys.flags.dont_write_bytecode:
        raise RuntimeError("beacon runner requires python -I -B")
    suspicious: set[str] = set()
    for root in (
        PROJECT_ROOT,
        PROJECT_ROOT / "RealLLM",
        PROJECT_ROOT / "BenchmarkCore",
        PROJECT_ROOT / "security",
    ):
        if root == PROJECT_ROOT:
            candidates = list(root.glob("*.py[co]")) + list(root.glob("__pycache__"))
        else:
            candidates = list(root.rglob("*.py[co]")) + list(root.rglob("__pycache__"))
        suspicious.update(
            path.relative_to(PROJECT_ROOT).as_posix() for path in candidates
        )
    if suspicious:
        raise RuntimeError(
            "remove local Python bytecode before beacon execution: "
            + ", ".join(sorted(suspicious))
        )


_early_reject_local_bytecode()

from RealLLM.beacon_protocol import (  # noqa: E402
    ATTEMPT_PATH,
    FREEZE_TAG,
    LEDGER_PATH,
    OUTCOME_PATH,
    PULSE_URL,
    REGISTRATION_PATH,
    RESOLUTION_PATH,
    SUITE_ID,
    TARGET_TIMESTAMP,
    artifact_digest_without_field,
    build_resolution,
    canonical_json_bytes,
    durable_exclusive_write,
    fetch_nist_pulse,
    git_text,
    implementation_sha256,
    load_json_object,
    load_registration,
    registration_artifact_sha256,
    registration_canonical_sha256,
    require_clean_head,
    require_public_freeze,
    serialized_json_bytes,
    sha256_bytes,
    sha256_file,
    validate_registration_and_ledger,
    verify_resolution,
)


_PYTHON_INJECTION_VARIABLES = (
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
)
_FROZEN_PROCESS_ENVIRONMENT = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "TOKENIZERS_PARALLELISM": "false",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "HF_HUB_DISABLE_PROGRESS_BARS": "1",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    "PYTORCH_MPS_HIGH_WATERMARK_RATIO": "0.85",
    "PYTORCH_MPS_LOW_WATERMARK_RATIO": "0.75",
    "PYTORCH_MPS_FAST_MATH": "0",
    "PYTORCH_ENABLE_MPS_FALLBACK": "0",
    "PYTORCH_MPS_PREFER_METAL": "0",
    "OMP_NUM_THREADS": "2",
    "OPENBLAS_NUM_THREADS": "2",
    "MKL_NUM_THREADS": "2",
    "VECLIB_MAXIMUM_THREADS": "2",
    "NUMEXPR_NUM_THREADS": "2",
}
_MINIMUM_PHYSICAL_MEMORY_BYTES = 8 * 1024 * 1024 * 1024
_MINIMUM_FREE_MEMORY_PERCENT = 15
_PROOF_LOCK_PARENT = Path.home() / ".cache" / "corelm-proof-runtimes"
_PROOF_LOCK_PATH = _PROOF_LOCK_PARENT / ".proof-run.lock"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_seconds() -> str:
    return _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_z(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("registered timestamp must end in Z")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _path_present(path: Path) -> bool:
    return os.path.lexists(path)


def _require_isolated_python() -> None:
    problems: list[str] = []
    if not sys.flags.isolated:
        problems.append("Python isolated mode is disabled")
    if not sys.flags.dont_write_bytecode:
        problems.append("Python bytecode writes are enabled")
    for name in _PYTHON_INJECTION_VARIABLES:
        if os.environ.get(name):
            problems.append(f"Python injection environment is set: {name}")
    suspicious: set[str] = set()
    for root in (
        PROJECT_ROOT,
        PROJECT_ROOT / "RealLLM",
        PROJECT_ROOT / "BenchmarkCore",
        PROJECT_ROOT / "security",
    ):
        if root == PROJECT_ROOT:
            candidates = list(root.glob("*.py[co]")) + list(root.glob("__pycache__"))
        else:
            candidates = list(root.rglob("*.py[co]")) + list(root.rglob("__pycache__"))
        suspicious.update(
            path.relative_to(PROJECT_ROOT).as_posix() for path in candidates
        )
    if suspicious:
        problems.append("local Python bytecode/cache exists: " + ", ".join(sorted(suspicious)))
    if problems:
        raise ValueError("; ".join(problems))


def _configure_frozen_process_environment() -> None:
    raw_cache = os.environ.get("HF_HOME")
    if not raw_cache:
        raise ValueError("HF_HOME must name the pre-verified private asset cache")
    cache = Path(raw_cache)
    if not cache.is_absolute() or cache.is_symlink() or not cache.is_dir():
        raise ValueError("HF_HOME must be an existing absolute non-symlink directory")
    resolved = cache.resolve(strict=True)
    status = resolved.stat()
    if (
        not stat.S_ISDIR(status.st_mode)
        or status.st_uid != os.getuid()
        or status.st_mode & 0o022
    ):
        raise ValueError(
            "HF_HOME must be owned by the current user and not group/world writable"
        )
    os.environ["HF_HOME"] = str(resolved)
    allowed_mps_variables = {
        name for name in _FROZEN_PROCESS_ENVIRONMENT if name.startswith("PYTORCH_MPS_")
    }
    unexpected_mps_variables = sorted(
        name
        for name in os.environ
        if name.startswith("PYTORCH_MPS_") and name not in allowed_mps_variables
    )
    if unexpected_mps_variables:
        raise ValueError(
            "unregistered MPS environment variables are set: "
            + ", ".join(unexpected_mps_variables)
        )
    for name, expected in _FROZEN_PROCESS_ENVIRONMENT.items():
        observed = os.environ.get(name)
        if observed is not None and observed != expected:
            raise ValueError(
                f"process environment {name}={observed!r} differs from "
                f"the frozen value {expected!r}"
            )
        os.environ[name] = expected


def _require_mac_resource_headroom() -> None:
    try:
        physical = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "hw.memsize"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
        )
        physical_bytes = int(physical.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise ValueError(f"cannot verify physical memory: {error}") from error
    if physical_bytes < _MINIMUM_PHYSICAL_MEMORY_BYTES:
        raise ValueError("beacon run requires at least 8 GiB unified memory")
    try:
        pressure = subprocess.run(
            ["/usr/bin/memory_pressure", "-Q"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"cannot verify macOS memory pressure: {error}") from error
    prefix = "System-wide memory free percentage:"
    matches = [
        line[len(prefix) :].strip().removesuffix("%")
        for line in pressure.stdout.splitlines()
        if line.startswith(prefix)
    ]
    if len(matches) != 1 or not matches[0].isdigit():
        raise ValueError("macOS memory-pressure output has an unexpected format")
    if int(matches[0]) < _MINIMUM_FREE_MEMORY_PERCENT:
        raise ValueError(
            f"only {matches[0]}% system memory is free; "
            f"{_MINIMUM_FREE_MEMORY_PERCENT}% is required"
        )


def _acquire_proof_lock() -> Path:
    _PROOF_LOCK_PARENT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if _PROOF_LOCK_PARENT.is_symlink() or not _PROOF_LOCK_PARENT.is_dir():
        raise ValueError("proof lock parent must be a real directory")
    status = _PROOF_LOCK_PARENT.stat()
    if status.st_uid != os.getuid() or status.st_mode & 0o022:
        raise ValueError("proof lock parent is not private to the current user")
    try:
        completed = subprocess.run(
            [
                "/usr/bin/shlock",
                "-p",
                str(os.getpid()),
                "-f",
                str(_PROOF_LOCK_PATH),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"cannot acquire the shared proof lock: {error}") from error
    if completed.returncode != 0:
        raise ValueError("another Core LM proof or beacon run is already active")
    if _PROOF_LOCK_PATH.is_symlink() or not _PROOF_LOCK_PATH.is_file():
        raise ValueError("proof lock was not created as a regular file")
    return _PROOF_LOCK_PATH


def _release_proof_lock(path: Path) -> None:
    if path != _PROOF_LOCK_PATH or path.is_symlink() or not path.is_file():
        return
    try:
        owner_pid = path.read_text(encoding="ascii").strip()
    except OSError:
        return
    if owner_pid == str(os.getpid()):
        path.unlink()


def _require_time_window(registration: dict[str, Any]) -> None:
    now = _utc_now()
    target = _parse_z(TARGET_TIMESTAMP)
    deadline = _parse_z(str(registration.get("execution", {}).get("deadline", "")))
    if now < target:
        raise ValueError(
            "future beacon pulse is not available yet; refusing to create the attempt marker"
        )
    if now > deadline:
        raise ValueError(
            "registered execution deadline passed; this suite must not be revived"
        )


def _require_artifacts_absent() -> None:
    present = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in (ATTEMPT_PATH, RESOLUTION_PATH, OUTCOME_PATH)
        if _path_present(path)
    ]
    primary = PROJECT_ROOT / "real-llm-beacon-results" / "primary-evidence"
    if _path_present(primary):
        present.append(primary.relative_to(PROJECT_ROOT).as_posix())
    if present:
        raise ValueError(
            "one-shot suite is already consumed or contaminated: " + ", ".join(present)
        )


def _require_only_result_artifacts(head: str) -> None:
    observed_head = git_text("rev-parse", "HEAD")
    if observed_head != head:
        raise RuntimeError("HEAD changed during one-shot execution")
    status = git_text(
        "status", "--porcelain=v1", "--untracked-files=all", "--ignored=no"
    )
    unexpected = [
        line
        for line in status.splitlines()
        if not (
            line.startswith("?? ")
            and line[3:].startswith("real-llm-beacon-results/")
        )
    ]
    if unexpected:
        raise RuntimeError(
            "worktree changed outside the one-shot result directory: "
            + ", ".join(unexpected)
        )


def _create_attempt(
    *, head: str, freeze: dict[str, Any], implementation_digest: str
) -> dict[str, Any]:
    marker: dict[str, Any] = {
        "schemaVersion": "corelm-beacon-attempt-v1",
        "suiteId": SUITE_ID,
        "status": "attempt-started-beacon-and-data-not-yet-resolved",
        "startedAt": _utc_seconds(),
        "gitCommitAtExecution": head,
        "gitTagAtExecution": FREEZE_TAG,
        "protocolCommit": freeze["protocolCommit"],
        "publicFreezeRelease": freeze["publicReleaseVerification"],
        "registrationArtifactSHA256": registration_artifact_sha256(),
        "registrationCanonicalSHA256": registration_canonical_sha256(),
        "windowLedgerSHA256": sha256_file(LEDGER_PATH),
        "implementationSHA256": implementation_digest,
        "beaconTargetTimestamp": TARGET_TIMESTAMP,
        "beaconEndpoint": PULSE_URL,
        "beaconWillBeFetchedAfterMarker": True,
        "testSplitWillBeResolvedAfterBeacon": True,
        "rerunPermitted": False,
    }
    marker["attemptSHA256"] = artifact_digest_without_field(
        marker, "attemptSHA256"
    )
    durable_exclusive_write(ATTEMPT_PATH, serialized_json_bytes(marker))
    observed = load_json_object(ATTEMPT_PATH, label="one-shot attempt")
    if observed != marker:
        raise RuntimeError("attempt marker changed during durable creation")
    return marker


def _assert_normative_state(
    *,
    head: str,
    implementation_digest: str,
    attempt: dict[str, Any],
    resolution: dict[str, Any] | None,
) -> None:
    _require_only_result_artifacts(head)
    if registration_artifact_sha256() != attempt["registrationArtifactSHA256"]:
        raise RuntimeError("registration changed after attempt creation")
    if registration_canonical_sha256() != attempt["registrationCanonicalSHA256"]:
        raise RuntimeError("canonical registration changed after attempt creation")
    if sha256_file(LEDGER_PATH) != attempt["windowLedgerSHA256"]:
        raise RuntimeError("window ledger changed after attempt creation")
    if implementation_sha256() != implementation_digest:
        raise RuntimeError("normative implementation changed during execution")
    observed_attempt = load_json_object(ATTEMPT_PATH, label="one-shot attempt")
    if observed_attempt != attempt:
        raise RuntimeError("attempt marker changed during execution")
    if resolution is not None:
        observed_resolution = load_json_object(
            RESOLUTION_PATH, label="beacon resolution"
        )
        if observed_resolution != resolution:
            raise RuntimeError("beacon resolution changed during execution")
        errors = verify_resolution(resolution)
        if errors:
            raise RuntimeError("beacon resolution failed re-verification: " + "; ".join(errors))
    if _path_present(OUTCOME_PATH):
        raise RuntimeError("one-shot outcome appeared before exclusive write")


def _write_execution_failure(
    *,
    error: BaseException,
    attempt: dict[str, Any],
    resolution: dict[str, Any] | None,
) -> None:
    if _path_present(OUTCOME_PATH):
        return
    outcome: dict[str, Any] = {
        "schemaVersion": "corelm-beacon-outcome-v1",
        "suiteId": SUITE_ID,
        "evidenceClass": "post-freeze-beacon-selected-heldout-window",
        "countsTowardScientificVerdict": True,
        "verdict": "FAIL_EXECUTION",
        "status": "terminal-execution-failure",
        "finishedAt": _utc_seconds(),
        "attemptSHA256": attempt.get("attemptSHA256"),
        "attemptArtifactSHA256": sha256_file(ATTEMPT_PATH),
        "resolutionSHA256": (
            resolution.get("resolutionSHA256") if resolution else None
        ),
        "resolutionArtifactSHA256": (
            sha256_file(RESOLUTION_PATH) if resolution and RESOLUTION_PATH.is_file() else None
        ),
        "error": {
            "type": type(error).__name__,
            "message": str(error)[:2000],
        },
        "scientificResult": None,
    }
    outcome["outcomeSHA256"] = artifact_digest_without_field(
        outcome, "outcomeSHA256"
    )
    durable_exclusive_write(OUTCOME_PATH, serialized_json_bytes(outcome))


def run_one_shot(*, local_files_only: bool) -> dict[str, Any]:
    _require_isolated_python()
    if local_files_only is not True:
        raise ValueError("the normative one-shot requires --local-files-only")
    _configure_frozen_process_environment()
    _require_mac_resource_headroom()
    proof_lock = _acquire_proof_lock()
    try:
        return _run_one_shot_locked(local_files_only=local_files_only)
    finally:
        _release_proof_lock(proof_lock)


def _run_one_shot_locked(*, local_files_only: bool) -> dict[str, Any]:
    registration, _ = validate_registration_and_ledger()
    _require_time_window(registration)
    _require_artifacts_absent()
    head = require_clean_head()
    freeze = require_public_freeze(head)
    implementation_digest = implementation_sha256()

    # Imports, exact version checks, and MPS availability are preflight. Model
    # files, corpus files, beacon output, and the selected window remain unopened.
    from RealLLM.beacon_evaluation import prepare_runtime, run_selected_window

    runtime = prepare_runtime()
    attempt = _create_attempt(
        head=head,
        freeze=freeze,
        implementation_digest=implementation_digest,
    )
    resolution: dict[str, Any] | None = None
    try:
        pulse, certificate = fetch_nist_pulse()
        resolution = build_resolution(
            pulse=pulse,
            certificate_pem=certificate,
            attempt=attempt,
        )
        resolution_errors = verify_resolution(resolution)
        if resolution_errors:
            raise RuntimeError(
                "new beacon resolution failed verification: "
                + "; ".join(resolution_errors)
            )
        durable_exclusive_write(
            RESOLUTION_PATH, serialized_json_bytes(resolution)
        )
        _assert_normative_state(
            head=head,
            implementation_digest=implementation_digest,
            attempt=attempt,
            resolution=resolution,
        )
        selected = resolution["selection"]["selectedWindow"]
        scientific_result = run_selected_window(
            int(selected["startBlock"]),
            local_files_only=local_files_only,
            runtime=runtime,
            retain_primary_evidence=True,
        )
        from RealLLM.verify_beacon_evidence import verify_scientific_result

        scientific_errors = verify_scientific_result(
            scientific_result, resolution
        )
        if scientific_errors:
            raise RuntimeError(
                "computed scientific result failed frozen verification: "
                + "; ".join(scientific_errors)
            )
        _assert_normative_state(
            head=head,
            implementation_digest=implementation_digest,
            attempt=attempt,
            resolution=resolution,
        )
        deadline = _parse_z(str(registration["execution"]["deadline"]))
        if _utc_now() > deadline:
            raise RuntimeError(
                "execution deadline passed before the terminal scientific outcome"
            )
        passed = scientific_result.get("pass") is True
        outcome: dict[str, Any] = {
            "schemaVersion": "corelm-beacon-outcome-v1",
            "suiteId": SUITE_ID,
            "evidenceClass": "post-freeze-beacon-selected-heldout-window",
            "countsTowardScientificVerdict": True,
            "verdict": "PASS" if passed else "FAIL_GATES",
            "status": "terminal-scientific-result",
            "finishedAt": _utc_seconds(),
            "gitCommitAtExecution": head,
            "protocolCommit": freeze["protocolCommit"],
            "registrationArtifactSHA256": registration_artifact_sha256(),
            "implementationSHA256": implementation_digest,
            "attemptSHA256": attempt["attemptSHA256"],
            "attemptArtifactSHA256": sha256_file(ATTEMPT_PATH),
            "resolutionSHA256": resolution["resolutionSHA256"],
            "resolutionArtifactSHA256": sha256_file(RESOLUTION_PATH),
            "scientificResult": scientific_result,
        }
        outcome["outcomeSHA256"] = artifact_digest_without_field(
            outcome, "outcomeSHA256"
        )
        durable_exclusive_write(OUTCOME_PATH, serialized_json_bytes(outcome))
        return outcome
    except BaseException as error:
        try:
            _write_execution_failure(
                error=error,
                attempt=attempt,
                resolution=resolution,
            )
        except BaseException as write_error:
            raise RuntimeError(
                "attempt is CONSUMED_INCOMPLETE and terminal failure could not "
                f"be written: original={error}; write={write_error}"
            ) from error
        raise RuntimeError(
            "one-shot attempt is consumed with FAIL_EXECUTION: " + str(error)
        ) from error


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="use only already verified Hugging Face cache files",
    )
    return parser.parse_args(arguments)


def main() -> int:
    arguments = parse_arguments()
    try:
        outcome = run_one_shot(local_files_only=arguments.local_files_only)
    except Exception as error:
        print(f"BEACON ONE-SHOT FAILED: {error}", file=sys.stderr)
        return 1
    result = outcome["scientificResult"]
    aggregate = result["aggregate"]
    confidence = result["confidence"]
    print(
        f"{outcome['verdict']}: {aggregate['compressionRatioVsBF16']:.6f}x, "
        f"delta NLL {aggregate['deltaNLLNatPerToken']:+.6f}, "
        f"upper95 {confidence['blockwiseDeltaNLLUpperOneSided95']:+.6f}, "
        f"top-1 {aggregate['top1Agreement']:.6%}."
    )
    print(f"Outcome SHA-256: {outcome['outcomeSHA256']}")
    return 0 if outcome["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
