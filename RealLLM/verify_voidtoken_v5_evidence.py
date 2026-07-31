#!/usr/bin/env python3
"""Verify frozen VoidToken v5 registration and any recorded phase artifacts."""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RealLLM.run_voidtoken_v5_frozen import (  # noqa: E402
    HOLDOUT_ATTEMPT_PATH,
    HOLDOUT_PATH,
    FROZEN_CONFIGURATION,
    LEGACY_PHASE_SCHEMA_VERSION,
    PRETEST_TAG,
    REGISTERED_LEGACY_PHASE_RESULTS,
    SELECTION_ATTEMPT_PATH,
    SELECTION_PATH,
    SELECTION_PROTOCOL_TAG,
    _load_json_object,
    _path_present,
    _run_git_process,
    implementation_sha256,
    implementation_sha256_at_commit,
    registration_sha256,
    registration_sha256_at_commit,
    validate_frozen_registration,
    verify_attempt_artifact_self_consistency,
    verify_attempt_document,
    verify_phase_artifact_self_consistency,
    verify_phase_result,
)
from RealLLM.benchmark_real_llm import sha256_file  # noqa: E402
from RealLLM.verify_voidtoken_v5_development import (  # noqa: E402
    _verify_record_pair,
    independent_aggregate_candidate_records,
    independent_canonical_json_bytes,
    independent_confidence_and_verdict,
)


def _load_object(path: Path) -> dict[str, Any]:
    return _load_json_object(path)


def _git_show(tag: str, path: Path) -> bytes:
    relative = path.relative_to(PROJECT_ROOT).as_posix()
    completed = _run_git_process(["show", f"{tag}:{relative}"])
    if completed.returncode:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"cannot read {relative} from {tag}: {message}")
    return completed.stdout


def _verify_artifact_matches_head(path: Path, label: str) -> list[str]:
    """Bind a published artifact to the checked-out Git commit."""

    try:
        committed = _git_show("HEAD", path)
        observed = path.read_bytes()
    except (OSError, ValueError) as error:
        return [f"cannot bind {label} to Git HEAD: {error}"]
    if committed != observed:
        return [f"{label} bytes differ from Git HEAD"]
    return []


def _tag_commit(tag: str) -> str:
    completed = _run_git_process(
        ["rev-parse", f"refs/tags/{tag}^{{commit}}"], text=True
    )
    if completed.returncode:
        raise ValueError(f"cannot resolve local provenance tag {tag}")
    return completed.stdout.strip()


def _git_metadata_ancestor() -> Path | None:
    for directory in (PROJECT_ROOT, *PROJECT_ROOT.parents):
        candidate = directory / ".git"
        try:
            candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ValueError(
                f"cannot inspect possible Git metadata at {candidate}: {error}"
            ) from error
        return candidate
    return None


def detect_verification_mode(
    *, require_git_provenance: bool = False
) -> str:
    """Return `git` or `artifact` without silently downgrading a worktree."""
    metadata = _git_metadata_ancestor()
    git_environment = any(
        os.environ.get(name) for name in ("GIT_DIR", "GIT_WORK_TREE")
    )
    if metadata is None and not git_environment:
        if require_git_provenance:
            raise ValueError(
                "Git provenance was required, but this source tree has no "
                "Git metadata; verify a full clone with tags"
            )
        return "artifact"
    try:
        completed = _run_git_process(
            ["rev-parse", "--show-toplevel"], text=True
        )
    except ValueError as error:
        raise ValueError(
            "Git metadata or Git environment was detected, but Git "
            f"provenance cannot be inspected: {error}"
        ) from error
    if completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(
            "Git metadata or Git environment was detected, but the worktree "
            f"is invalid or inaccessible: {message}"
        )
    try:
        top_level = Path(completed.stdout.strip()).resolve(strict=True)
        project_root = PROJECT_ROOT.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"cannot resolve the Git worktree root: {error}") from error
    if top_level != project_root:
        raise ValueError(
            "the artifact is nested inside a different Git worktree; move the "
            "extracted archive outside that worktree for artifact-only "
            "verification"
        )
    return "git"


def _head_commit() -> str:
    completed = _run_git_process(["rev-parse", "HEAD"], text=True)
    if completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"cannot resolve Git HEAD: {message}")
    commit = completed.stdout.strip()
    if (
        len(commit) != 40
        or any(character not in "0123456789abcdef" for character in commit)
    ):
        raise ValueError("Git HEAD is not a full SHA-1 commit")
    return commit


def _verify_current_head_integrity(
    registration_digest: str,
    implementation_digest: str,
) -> list[str]:
    errors: list[str] = []
    try:
        head = _head_commit()
        committed_registration = registration_sha256_at_commit(head)
        committed_implementation = implementation_sha256_at_commit(head)
    except ValueError as error:
        return [f"cannot bind current sources to Git HEAD: {error}"]
    if committed_registration != registration_digest:
        errors.append("current registration bytes differ from Git HEAD")
    if committed_implementation != implementation_digest:
        errors.append("current normative implementation differs from Git HEAD")
    return errors


def _close(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(
            float(left), float(right), rel_tol=1e-12, abs_tol=1e-12
        )
    return left == right


def _independent_digest_errors(
    value: dict[str, Any],
    digest_field: str,
    label: str,
) -> list[str]:
    digest_input = dict(value)
    recorded_digest = digest_input.pop(digest_field, None)
    try:
        recomputed_digest = hashlib.sha256(
            independent_canonical_json_bytes(digest_input)
        ).hexdigest()
    except (TypeError, ValueError) as error:
        return [f"independent {label} canonicalization failed: {error}"]
    if recorded_digest != recomputed_digest:
        return [f"independent {label} SHA-256 is inconsistent"]
    return []


def _independent_phase_metric_errors(
    result: dict[str, Any],
    expected_phase: str,
) -> list[str]:
    """Second arithmetic/digest implementation, separate from the runner."""
    records = result.get("records")
    baselines = result.get("baselines")
    observed_aggregate = result.get("aggregate")
    observed_confidence = result.get("confidence")
    if (
        not isinstance(records, list)
        or not isinstance(baselines, list)
        or not isinstance(observed_aggregate, dict)
        or not isinstance(observed_confidence, dict)
        or any(not isinstance(record, dict) for record in records)
        or any(not isinstance(baseline, dict) for baseline in baselines)
    ):
        return [
            "independent recomputation requires object records, baselines, "
            "aggregate, and confidence"
        ]
    errors: list[str] = []
    expected_start = 32 if expected_phase == "selection" else 384
    if len(records) != 32 or len(baselines) != 32:
        errors.append("independent phase requires exactly 32 record pairs")
    else:
        for relative_index, (record, baseline) in enumerate(
            zip(records, baselines)
        ):
            errors.extend(
                _verify_record_pair(
                    record,
                    baseline,
                    expected_start + relative_index,
                    require_container_manifest=(
                        result.get("schemaVersion")
                        != LEGACY_PHASE_SCHEMA_VERSION
                    ),
                )
            )
    try:
        aggregate = independent_aggregate_candidate_records(
            FROZEN_CONFIGURATION, records
        )
        confidence, gates, passed = independent_confidence_and_verdict(
            records, baselines, aggregate
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as error:
        return [f"independent metric recomputation failed: {error}"]
    for key, value in aggregate.items():
        if key not in observed_aggregate or not _close(
            observed_aggregate[key], value
        ):
            errors.append(
                f"independent aggregate field {key} is inconsistent"
            )
    for key, value in confidence.items():
        if key not in observed_confidence or not _close(
            observed_confidence[key], value
        ):
            errors.append(
                f"independent confidence field {key} is inconsistent"
            )
    if result.get("gates") != gates:
        errors.append("independent frozen gates are inconsistent")
    if result.get("pass") is not passed:
        errors.append("independent frozen verdict is inconsistent")
    errors.extend(
        _independent_digest_errors(result, "resultSHA256", "result")
    )
    return errors


def _registered_legacy_artifact_errors(
    path: Path,
    result: dict[str, Any],
    phase: str,
) -> list[str]:
    """Permit only the byte-identical published v1 historical artifact."""
    if result.get("schemaVersion") != LEGACY_PHASE_SCHEMA_VERSION:
        return []
    registered = REGISTERED_LEGACY_PHASE_RESULTS[phase]
    try:
        observed = sha256_file(path)
    except OSError as error:
        return [f"cannot hash legacy {phase} artifact: {error}"]
    if observed != registered["artifactSHA256"]:
        return [
            f"legacy {phase} artifact SHA-256 differs from the immutable "
            "registered historical artifact"
        ]
    return []


def _legacy_accounting_limitation(
    *results: dict[str, Any],
) -> str:
    if any(
        result.get("schemaVersion") == LEGACY_PHASE_SCHEMA_VERSION
        for result in results
    ):
        return (
            " LEGACY_ACCOUNTING_LIMITATION: v1 complete-container byte "
            "totals and compression gates are runner-recorded and protected "
            "by immutable artifact/result/Git digests, but cannot be "
            "independently reconstructed per layer because v1 did not record "
            "container manifests"
        )
    return ""


def _verify_standalone_attempt(
    path: Path,
    phase: str,
    *,
    git_provenance: bool,
) -> tuple[list[str], dict[str, Any] | None]:
    try:
        attempt = _load_object(path)
    except ValueError as error:
        return [str(error)], None
    attempt_verifier = (
        verify_attempt_document
        if git_provenance
        else verify_attempt_artifact_self_consistency
    )
    errors = attempt_verifier(attempt, phase)
    errors.extend(
        _independent_digest_errors(
            attempt, "attemptSHA256", f"{phase} attempt"
        )
    )
    freeze = attempt.get("executionFreeze", {})
    expected_tag = (
        SELECTION_PROTOCOL_TAG if phase == "selection" else PRETEST_TAG
    )
    commit_key = (
        "freezeGitCommit" if phase == "selection" else "pretestGitCommit"
    )
    if git_provenance:
        try:
            if _tag_commit(expected_tag) != freeze.get(commit_key):
                errors.append(
                    f"{phase} attempt commit differs from local provenance tag"
                )
        except ValueError as error:
            errors.append(str(error))
    return errors, attempt


def verify_available_evidence(
    *, git_provenance: bool = True
) -> tuple[list[str], str]:
    errors: list[str] = []
    try:
        validate_frozen_registration()
        registration_digest = registration_sha256()
        implementation_digest = implementation_sha256()
    except ValueError as error:
        return [str(error)], "invalid registration"
    if git_provenance:
        errors.extend(
            _verify_current_head_integrity(
                registration_digest, implementation_digest
            )
        )

    if not _path_present(SELECTION_PATH):
        if _path_present(SELECTION_ATTEMPT_PATH):
            attempt_errors, _ = _verify_standalone_attempt(
                SELECTION_ATTEMPT_PATH,
                "selection",
                git_provenance=git_provenance,
            )
            errors.extend(attempt_errors)
            if _path_present(HOLDOUT_PATH):
                errors.append("holdout exists without a selection result")
            if _path_present(HOLDOUT_ATTEMPT_PATH):
                errors.append("holdout attempt exists without a selection result")
            return errors, (
                "selection attempt is CONSUMED_INCOMPLETE; rerun is forbidden"
            )
        if _path_present(HOLDOUT_PATH):
            errors.append("holdout exists without a selection artifact")
        if _path_present(HOLDOUT_ATTEMPT_PATH):
            errors.append("holdout attempt exists without a selection result")
        return errors, (
            "registration-only freeze "
            f"{registration_digest}; implementation {implementation_digest}; "
            "no selection artifact recorded"
        )

    try:
        selection = _load_object(SELECTION_PATH)
    except ValueError as error:
        return errors + [str(error)], "invalid selection"
    errors.extend(
        _registered_legacy_artifact_errors(
            SELECTION_PATH, selection, "selection"
        )
    )
    phase_verifier = (
        verify_phase_result
        if git_provenance
        else verify_phase_artifact_self_consistency
    )
    errors.extend(phase_verifier(selection, "selection"))
    errors.extend(
        _independent_phase_metric_errors(selection, "selection")
    )
    if git_provenance:
        errors.extend(
            _verify_artifact_matches_head(
                SELECTION_PATH, "selection artifact"
            )
        )
        errors.extend(
            _verify_artifact_matches_head(
                SELECTION_ATTEMPT_PATH, "selection attempt"
            )
        )
    if selection.get("pretestFreeze") is not None:
        errors.append("selection must precede the public pretest freeze")
    selection_passed = selection.get("pass") is True
    try:
        selection_attempt = _load_object(SELECTION_ATTEMPT_PATH)
        errors.extend(
            _independent_digest_errors(
                selection_attempt,
                "attemptSHA256",
                "selection attempt",
            )
        )
        selection_freeze = selection_attempt.get("executionFreeze", {})
        if selection_freeze.get("freezeGitTag") != SELECTION_PROTOCOL_TAG:
            errors.append("selection attempt references a different protocol tag")
        if git_provenance:
            if _tag_commit(SELECTION_PROTOCOL_TAG) != selection.get(
                "gitCommitAtExecution"
            ):
                errors.append(
                    "selection execution commit differs from its protocol tag"
                )
    except ValueError as error:
        errors.append(str(error))

    if not _path_present(HOLDOUT_PATH):
        if _path_present(HOLDOUT_ATTEMPT_PATH):
            if not selection_passed:
                errors.append(
                    "holdout attempt exists after a failed selection"
                )
            attempt_errors, _ = _verify_standalone_attempt(
                HOLDOUT_ATTEMPT_PATH,
                "holdout",
                git_provenance=git_provenance,
            )
            errors.extend(attempt_errors)
            return errors, (
                "selection verified; holdout attempt is "
                "CONSUMED_INCOMPLETE; rerun is forbidden"
                + _legacy_accounting_limitation(selection)
            )
        return errors, (
            "selection verified; "
            f"verdict={'PASS' if selection_passed else 'FAIL'}; "
            + (
                "prospective holdout is not yet recorded"
                if selection_passed
                else "holdout is permanently forbidden"
            )
            + _legacy_accounting_limitation(selection)
        )

    if not selection_passed:
        errors.append("holdout exists after a failed selection")
    try:
        holdout = _load_object(HOLDOUT_PATH)
    except ValueError as error:
        return errors + [str(error)], "invalid holdout"
    errors.extend(
        _registered_legacy_artifact_errors(
            HOLDOUT_PATH, holdout, "holdout"
        )
    )
    errors.extend(phase_verifier(holdout, "holdout"))
    errors.extend(_independent_phase_metric_errors(holdout, "holdout"))
    if git_provenance:
        errors.extend(
            _verify_artifact_matches_head(HOLDOUT_PATH, "holdout artifact")
        )
        errors.extend(
            _verify_artifact_matches_head(
                HOLDOUT_ATTEMPT_PATH, "holdout attempt"
            )
        )
    try:
        holdout_attempt = _load_object(HOLDOUT_ATTEMPT_PATH)
    except ValueError as error:
        errors.append(str(error))
    else:
        errors.extend(
            _independent_digest_errors(
                holdout_attempt,
                "attemptSHA256",
                "holdout attempt",
            )
        )
    freeze = holdout.get("pretestFreeze")
    if not isinstance(freeze, dict):
        errors.append("holdout has no pretest freeze record")
    else:
        if freeze.get("pretestGitTag") != PRETEST_TAG:
            errors.append("holdout pretest tag is inconsistent")
        if freeze.get("selectionResultSHA256") != selection.get(
            "resultSHA256"
        ):
            errors.append("holdout references a different selection result")
        try:
            selection_file_digest = sha256_file(SELECTION_PATH)
        except OSError as error:
            errors.append(f"cannot hash selection artifact: {error}")
        else:
            if (
                freeze.get("selectionArtifactSHA256")
                != selection_file_digest
            ):
                errors.append(
                    "holdout selection-file digest is inconsistent"
                )
        try:
            selection_attempt_digest = sha256_file(
                SELECTION_ATTEMPT_PATH
            )
        except OSError as error:
            errors.append(f"cannot hash selection attempt: {error}")
        else:
            if (
                freeze.get("selectionAttemptArtifactSHA256")
                != selection_attempt_digest
            ):
                errors.append(
                    "holdout selection-attempt digest is inconsistent"
                )
        if git_provenance:
            try:
                if _tag_commit(PRETEST_TAG) != holdout.get(
                    "gitCommitAtExecution"
                ):
                    errors.append(
                        "holdout execution commit differs from local pretest tag"
                    )
                if _git_show(PRETEST_TAG, SELECTION_PATH) != (
                    SELECTION_PATH.read_bytes()
                ):
                    errors.append(
                        "pretest tag contains a different selection artifact"
                    )
                if _git_show(PRETEST_TAG, SELECTION_ATTEMPT_PATH) != (
                    SELECTION_ATTEMPT_PATH.read_bytes()
                ):
                    errors.append(
                        "pretest tag contains a different selection attempt"
                    )
            except (OSError, ValueError) as error:
                errors.append(str(error))
    return errors, (
        "selection and prospective holdout verified; "
        f"holdout verdict={'PASS' if holdout.get('pass') else 'FAIL'}"
        + _legacy_accounting_limitation(selection, holdout)
    )


def parse_arguments(
    arguments: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-git-provenance",
        action="store_true",
        help=(
            "Fail unless running in the repository root with Git metadata; "
            "CI and public-clone verification should use this"
        ),
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_arguments(arguments)
    try:
        mode = detect_verification_mode(
            require_git_provenance=options.require_git_provenance
        )
    except ValueError as error:
        print(f"VOIDTOKEN V5 VERIFICATION MODE ERROR: {error}")
        return 1
    git_provenance = mode == "git"
    errors, status = verify_available_evidence(
        git_provenance=git_provenance
    )
    if errors:
        print(
            f"VOIDTOKEN V5 EVIDENCE VERIFICATION FAILED "
            f"[{mode}] ({len(errors)} problem(s)):"
        )
        for error in errors:
            print(f"- {error}")
        return 1
    if git_provenance:
        if status.startswith("registration-only freeze"):
            print(
                "VOIDTOKEN V5 GIT HEAD SOURCE INTEGRITY VERIFIED "
                "(NO PHASE PROVENANCE YET): "
                f"{status}."
            )
        else:
            print(
                "VOIDTOKEN V5 SOURCE + TRACKED-ARTIFACT CONSISTENCY PASSED: "
                f"{status}. Recorded inference was not independently rerun; "
                "Git and SHA-256 consistency do not authenticate the runtime "
                "producer."
            )
    else:
        print(
            "VOIDTOKEN V5 ARTIFACT SELF-CONSISTENCY VERIFIED: "
            f"{status}. Git commits, tags, and public timestamps were not "
            "available and were not verified."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
