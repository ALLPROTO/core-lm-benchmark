#!/usr/bin/env python3
"""Repeat the resolved window only as non-scientific regression evidence."""

from __future__ import annotations

import argparse
import os
import stat
import secrets
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
        raise RuntimeError("regression runner requires python -I -B")
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
            "remove local Python bytecode before regression replay: "
            + ", ".join(sorted(suspicious))
        )


_early_reject_local_bytecode()

from RealLLM.beacon_protocol import (  # noqa: E402
    ATTEMPT_PATH,
    OUTCOME_PATH,
    REGRESSION_DIRECTORY,
    RESOLUTION_PATH,
    SUITE_ID,
    artifact_digest_without_field,
    durable_exclusive_write,
    git_text,
    implementation_sha256,
    load_json_object,
    serialized_json_bytes,
    sha256_file,
    validate_registration_and_ledger,
    verify_resolution,
)


def _require_isolated_python() -> None:
    if not sys.flags.isolated or not sys.flags.dont_write_bytecode:
        raise ValueError("regression runner requires python -I -B")


def _configure_frozen_process_environment() -> None:
    from RealLLM.run_beacon_one_shot import _FROZEN_PROCESS_ENVIRONMENT

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
        raise ValueError("HF_HOME is not a private current-user cache")
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
            raise ValueError(f"process environment {name} differs from the freeze")
        os.environ[name] = expected


def _load_terminal_scientific_state() -> tuple[dict[str, Any], dict[str, Any]]:
    attempt = load_json_object(ATTEMPT_PATH, label="one-shot attempt")
    resolution = load_json_object(RESOLUTION_PATH, label="beacon resolution")
    outcome = load_json_object(OUTCOME_PATH, label="one-shot outcome")
    if attempt.get("suiteId") != SUITE_ID or resolution.get("suiteId") != SUITE_ID:
        raise ValueError("normative attempt or resolution has a different suite ID")
    if outcome.get("suiteId") != SUITE_ID:
        raise ValueError("normative outcome has a different suite ID")
    if outcome.get("verdict") not in {"PASS", "FAIL_GATES"}:
        raise ValueError(
            "regression is permitted only after a terminal scientific PASS or FAIL_GATES"
        )
    if outcome.get("scientificResult") is None:
        raise ValueError("normative scientific outcome has no result")
    expected_digest = artifact_digest_without_field(outcome, "outcomeSHA256")
    if outcome.get("outcomeSHA256") != expected_digest:
        raise ValueError("normative outcome digest is inconsistent")
    if outcome.get("attemptSHA256") != attempt.get("attemptSHA256"):
        raise ValueError("normative outcome references another attempt")
    if outcome.get("resolutionSHA256") != resolution.get("resolutionSHA256"):
        raise ValueError("normative outcome references another resolution")
    errors = verify_resolution(resolution)
    if errors:
        raise ValueError("normative resolution is invalid: " + "; ".join(errors))
    return resolution, outcome


def run_regression(*, local_files_only: bool) -> tuple[Path, dict[str, Any]]:
    _require_isolated_python()
    if local_files_only is not True:
        raise ValueError("regression replay requires --local-files-only")
    _configure_frozen_process_environment()
    from RealLLM.run_beacon_one_shot import (
        _acquire_proof_lock,
        _release_proof_lock,
        _require_mac_resource_headroom,
    )

    _require_mac_resource_headroom()
    proof_lock = _acquire_proof_lock()
    try:
        return _run_regression_locked(local_files_only=local_files_only)
    finally:
        _release_proof_lock(proof_lock)


def _run_regression_locked(
    *, local_files_only: bool
) -> tuple[Path, dict[str, Any]]:
    validate_registration_and_ledger()
    resolution, outcome = _load_terminal_scientific_state()
    head = git_text("rev-parse", "HEAD")
    implementation_digest = implementation_sha256()
    selected = resolution["selection"]["selectedWindow"]

    from RealLLM.beacon_evaluation import prepare_runtime, run_selected_window

    runtime = prepare_runtime()
    scientific_result = run_selected_window(
        int(selected["startBlock"]),
        local_files_only=local_files_only,
        runtime=runtime,
        retain_primary_evidence=False,
    )
    created = datetime.now(timezone.utc).replace(microsecond=0)
    challenge = secrets.token_hex(16)
    regression: dict[str, Any] = {
        "schemaVersion": "corelm-beacon-regression-v1",
        "suiteId": SUITE_ID,
        "evidenceClass": "regression-only",
        "countsTowardScientificVerdict": False,
        "createdAt": created.isoformat().replace("+00:00", "Z"),
        "challenge": challenge,
        "gitCommitAtExecution": head,
        "implementationSHA256": implementation_digest,
        "normativeAttemptSHA256": load_json_object(
            ATTEMPT_PATH, label="one-shot attempt"
        )["attemptSHA256"],
        "normativeAttemptArtifactSHA256": sha256_file(ATTEMPT_PATH),
        "normativeResolutionSHA256": resolution["resolutionSHA256"],
        "normativeResolutionArtifactSHA256": sha256_file(RESOLUTION_PATH),
        "normativeOutcomeSHA256": outcome["outcomeSHA256"],
        "normativeOutcomeArtifactSHA256": sha256_file(OUTCOME_PATH),
        "normativeVerdictUnchanged": outcome["verdict"],
        "selectedWindow": selected,
        "scientificResult": scientific_result,
    }
    regression["regressionSHA256"] = artifact_digest_without_field(
        regression, "regressionSHA256"
    )
    filename = (
        created.strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + challenge[:16]
        + ".json"
    )
    output = REGRESSION_DIRECTORY / filename
    durable_exclusive_write(output, serialized_json_bytes(regression))
    return output, regression


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-files-only", action="store_true")
    return parser.parse_args(arguments)


def main() -> int:
    arguments = parse_arguments()
    try:
        output, regression = run_regression(
            local_files_only=arguments.local_files_only
        )
    except Exception as error:
        print(f"BEACON REGRESSION FAILED: {error}", file=sys.stderr)
        return 1
    aggregate = regression["scientificResult"]["aggregate"]
    print(
        "REGRESSION ONLY (does not change the normative verdict): "
        f"{aggregate['compressionRatioVsBF16']:.6f}x, "
        f"delta NLL {aggregate['deltaNLLNatPerToken']:+.6f}."
    )
    print(f"Artifact: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
