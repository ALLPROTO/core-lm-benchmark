#!/usr/bin/env python3
"""Canonical, evidence-derived reports for one completed macOS proof.

The two public verifier entrypoints call this module only after their own
verification succeeds.  Report fields are recomputed from the retained result,
receipt, build provenance, and primary evidence; no metric or source identity
is accepted from an operator-provided declaration.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import uuid
from pathlib import Path
from typing import Any

from RealLLM.pinned_assets import PINNED_RELEASE_ASSETS


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
REPORT_DIRECTORY_NAME = "proof-reports"
STRUCTURAL_REPORT_NAME = "structural-verifier.json"
REPLAY_REPORT_NAME = "fresh-model-replay.json"
TERMINAL_LOG_NAME = "terminal.log"
MODEL_REPOSITORY = PINNED_RELEASE_ASSETS["model"]["repository"]
MODEL_REVISION = PINNED_RELEASE_ASSETS["model"]["revision"]
WORKLOAD_CLASSIFICATION = "AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION"
RECORDED_RESULT_ROLE = "PUBLIC_VALIDATION_REGRESSION"
REPLAY_INTEGRITY_VERDICT = "AUTHOR_RECORDED_HEAVY_REPLAY_INTEGRITY_PASS"
REPLAY_EXECUTION_SCOPE = (
    "AUTHOR_RECORDED_NOT_INDEPENDENTLY_REEXECUTED_BY_RELEASE_VERIFIER"
)
MAX_JSON_BYTES = 16 * 1024 * 1024
EXPECTED_REPLAY_DECISIONS = 1_024
EXPECTED_LOSS_ABSOLUTE_TOLERANCE = 2e-5
EXPECTED_LOSS_RELATIVE_TOLERANCE = 2e-6
REPLAY_SUMMARY_KEYS = {
    "decisions",
    "lossAbsoluteTolerance",
    "lossRelativeTolerance",
    "maximumBaselineLossDifference",
    "maximumCandidateLossDifference",
}
REPLAY_EVIDENCE_KEYS = {
    "maximumAllowedBaselineDifference",
    "maximumAllowedCandidateDifference",
    "perDecisionEvidenceSHA256",
    "primaryManifestSHA256",
    "tokenMetricsSHA256",
}


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON value is forbidden: {value}")


def _without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _regular_file(path: Path, maximum_bytes: int = MAX_JSON_BYTES) -> os.stat_result:
    status = path.lstat()
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_nlink != 1
        or status.st_size <= 0
        or status.st_size > maximum_bytes
    ):
        raise ValueError(f"unsafe or unbounded proof file: {path.name}")
    return status


def read_json_object(path: Path, *, canonical: bool = False) -> dict[str, Any]:
    status = _regular_file(path)
    raw = path.read_bytes()
    if len(raw) != status.st_size or raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"unstable or BOM-prefixed JSON: {path.name}")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path.name}")
    if canonical and raw != canonical_json_bytes(value):
        raise ValueError(f"report is not canonical JSON: {path.name}")
    return value


def sha256_file(path: Path) -> str:
    _regular_file(path)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validated_run_directory(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("proof run directory must be absolute and not symlinked")
    run = path.resolve(strict=True)
    if run != path:
        raise ValueError("proof run directory must be a canonical path")
    status = run.stat()
    if (
        not stat.S_ISDIR(status.st_mode)
        or status.st_uid != os.getuid()
        or status.st_mode & 0o022
    ):
        raise ValueError("proof run directory is not private and owner-controlled")
    try:
        parsed = uuid.UUID(run.name)
    except ValueError as error:
        raise ValueError("proof run directory name is not a canonical UUID") from error
    if str(parsed) != run.name:
        raise ValueError("proof run UUID is not lowercase canonical text")
    return run


def _exact_object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} fields are not exact")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{label} is not lowercase SHA-256")
    return value


def derive_binding(run_directory: Path) -> dict[str, Any]:
    """Re-verify and derive every common report field from retained bytes."""

    # Imported lazily so lightweight report-schema tests do not import the
    # numerical verifier graph until an actual retained run is inspected.
    from security.generate_build_provenance import (
        canonical_json_bytes as canonical_build_bytes,
        validate_build_manifest,
    )
    from security.verify_app_run_evidence import _verify_result_and_receipt

    run = validated_run_directory(run_directory)
    result_path = run / "validation-064-071.json"
    receipt_path = run / "app-run-receipt.json"
    receipt = read_json_object(receipt_path)
    challenge = _digest(receipt.get("challengeNonce"), "proof challenge")
    result = _verify_result_and_receipt(
        result_path,
        receipt_path,
        None,
        portable_macos_environment=True,
        expected_challenge_nonce=challenge,
        require_metric_pass=False,
    )
    if receipt.get("schemaVersion") != "corelm-macos-app-real-llm-run-v5":
        raise ValueError("proof report requires the current v5 app receipt")
    result_receipt = _exact_object(
        receipt.get("result"),
        {
            "compressionRatioVsBF16",
            "deltaNLLNatPerToken",
            "metricVerdict",
            "path",
            "resultFileSHA256",
            "resultRole",
            "resultSHA256",
            "swiftStructuralVerification",
            "top1Agreement",
        },
        "proof result receipt",
    )
    aggregates = result.get("aggregates")
    if not isinstance(aggregates, list) or len(aggregates) != 1:
        raise ValueError("proof result has no unique aggregate")
    passed = aggregates[0].get("pass")
    if not isinstance(passed, bool):
        raise ValueError("proof metric outcome is not Boolean")
    metric_verdict = "PASS" if passed else "FAIL"
    if (
        result_receipt["metricVerdict"] != metric_verdict
        or result_receipt["resultRole"] != RECORDED_RESULT_ROLE
        or result_receipt["swiftStructuralVerification"] != "PASS"
        or receipt.get("error") is not None
    ):
        raise ValueError("proof receipt does not preserve the verified metric outcome")
    build = _exact_object(
        receipt.get("buildProvenance"),
        {"document", "path", "sha256"},
        "build provenance receipt",
    )
    document = build["document"]
    validate_build_manifest(document)
    canonical_build = canonical_build_bytes(document)
    if (
        build["path"] != "Resources/build-provenance.json"
        or hashlib.sha256(canonical_build).hexdigest()
        != _digest(build["sha256"], "build provenance")
    ):
        raise ValueError("proof build provenance binding is inconsistent")
    source = document["source"]
    if (
        source.get("mode") != "git"
        or source.get("dirty") is not False
        or not isinstance(source.get("commit"), str)
        or GIT_OBJECT_RE.fullmatch(source["commit"]) is None
        or not isinstance(source.get("tree"), str)
        or GIT_OBJECT_RE.fullmatch(source["tree"]) is None
    ):
        raise ValueError("proof source is not one clean Git commit/tree")
    application = receipt.get("application")
    if not isinstance(application, dict):
        raise ValueError("proof receipt has no application identity")
    _digest(application.get("executableSHA256"), "application executable")
    return {
        "schema_version": 1,
        "verdict": "PASS",
        "metric_verdict": metric_verdict,
        "source": {"commit": source["commit"], "tree": source["tree"]},
        "receipt_sha256": sha256_file(receipt_path),
        "result_sha256": sha256_file(result_path),
        "workload_classification": WORKLOAD_CLASSIFICATION,
        "synthetic_data": False,
    }


def _replay_integrity(run_directory: Path) -> dict[str, Any]:
    """Recompute the retained per-decision binding and tolerance envelope.

    This does not execute Qwen.  It first runs the independent raw-evidence
    verifier, then binds the author-recorded heavy replay to the exact retained
    primary manifest and token metrics.  The two recorded maximum differences
    may therefore be checked for mathematical compatibility with the verifier,
    but are not represented as a second independent model execution.
    """

    from security.verify_primary_evidence import verify_primary_evidence

    run = validated_run_directory(run_directory)
    verified = verify_primary_evidence(run)
    if verified.get("predictionTokens") != EXPECTED_REPLAY_DECISIONS:
        raise ValueError("retained evidence does not contain 1,024 decisions")
    result = read_json_object(run / "validation-064-071.json")
    descriptor = _exact_object(
        result.get("primaryEvidence"),
        {
            "schemaVersion",
            "path",
            "manifestSHA256",
            "manifestBytes",
            "containerCount",
            "containerBytes",
            "blocks",
            "predictionTokens",
        },
        "primary evidence descriptor",
    )
    manifest_path = run / "primary-evidence" / "manifest.json"
    manifest_digest = sha256_file(manifest_path)
    if descriptor.get("path") != "primary-evidence/manifest.json" or (
        descriptor.get("manifestSHA256") != manifest_digest
    ):
        raise ValueError("retained primary manifest binding is inconsistent")
    manifest = read_json_object(manifest_path)
    token_reference = _exact_object(
        manifest.get("tokenMetrics"),
        {"path", "bytes", "sha256", "blocks", "predictionTokens"},
        "token metrics reference",
    )
    if token_reference.get("path") != "primary-evidence/token-metrics.json":
        raise ValueError("retained token metrics path is not canonical")
    token_path = run / "primary-evidence" / "token-metrics.json"
    token_raw = token_path.read_bytes()
    token_digest = hashlib.sha256(token_raw).hexdigest()
    if (
        token_reference.get("sha256") != token_digest
        or token_reference.get("bytes") != len(token_raw)
        or token_reference.get("predictionTokens") != EXPECTED_REPLAY_DECISIONS
    ):
        raise ValueError("retained token metrics binding is inconsistent")
    token_document = read_json_object(token_path)
    blocks = token_document.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("retained token metrics have no block list")
    decisions: list[dict[str, Any]] = []
    maximum_baseline_envelope = 0.0
    maximum_candidate_envelope = 0.0
    relative_scale = 1.0 - EXPECTED_LOSS_RELATIVE_TOLERANCE
    for block in blocks:
        if not isinstance(block, dict) or type(block.get("blockIndex")) is not int:
            raise ValueError("retained token block identity is malformed")
        rows = block.get("tokens")
        if not isinstance(rows, list):
            raise ValueError("retained token block has no decisions")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("retained token decision is malformed")
            baseline = row.get("baselineLossNat")
            candidate = row.get("candidateLossNat")
            if (
                isinstance(baseline, bool)
                or not isinstance(baseline, (int, float))
                or not math.isfinite(float(baseline))
                or isinstance(candidate, bool)
                or not isinstance(candidate, (int, float))
                or not math.isfinite(float(candidate))
            ):
                raise ValueError("retained token losses are not finite")
            decisions.append(
                {
                    "blockIndex": block["blockIndex"],
                    "offset": row.get("offset"),
                    "targetTokenId": row.get("targetTokenId"),
                    "baselineLossNat": baseline,
                    "candidateLossNat": candidate,
                    "baselineTop1TokenId": row.get("baselineTop1TokenId"),
                    "candidateTop1TokenId": row.get("candidateTop1TokenId"),
                    "top1Agrees": row.get("top1Agrees"),
                }
            )
            maximum_baseline_envelope = max(
                maximum_baseline_envelope,
                EXPECTED_LOSS_ABSOLUTE_TOLERANCE,
                EXPECTED_LOSS_RELATIVE_TOLERANCE
                * abs(float(baseline))
                / relative_scale,
            )
            maximum_candidate_envelope = max(
                maximum_candidate_envelope,
                EXPECTED_LOSS_ABSOLUTE_TOLERANCE,
                EXPECTED_LOSS_RELATIVE_TOLERANCE
                * abs(float(candidate))
                / relative_scale,
            )
    if len(decisions) != EXPECTED_REPLAY_DECISIONS:
        raise ValueError("retained per-decision evidence count is not 1,024")
    return {
        "primaryManifestSHA256": manifest_digest,
        "tokenMetricsSHA256": token_digest,
        "perDecisionEvidenceSHA256": hashlib.sha256(
            canonical_json_bytes(decisions)
        ).hexdigest(),
        "maximumAllowedBaselineDifference": maximum_baseline_envelope,
        "maximumAllowedCandidateDifference": maximum_candidate_envelope,
    }


def _validated_replay_summary(
    value: Any, integrity: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("recorded heavy replay summary is not an object")
    if set(value) == REPLAY_SUMMARY_KEYS | REPLAY_EVIDENCE_KEYS:
        recorded = {key: value[key] for key in REPLAY_SUMMARY_KEYS}
        for key in REPLAY_EVIDENCE_KEYS:
            if value[key] != integrity[key]:
                raise ValueError(f"recorded replay {key} differs from retained evidence")
    else:
        recorded = _exact_object(
            value, REPLAY_SUMMARY_KEYS, "recorded heavy replay summary"
        )
    summary = dict(recorded)
    if summary["decisions"] != EXPECTED_REPLAY_DECISIONS:
        raise ValueError("recorded heavy replay did not retain exactly 1,024 decisions")
    for key, maximum_key in (
        ("maximumBaselineLossDifference", "maximumAllowedBaselineDifference"),
        ("maximumCandidateLossDifference", "maximumAllowedCandidateDifference"),
    ):
        observed = summary[key]
        if (
            isinstance(observed, bool)
            or not isinstance(observed, (int, float))
            or not math.isfinite(float(observed))
            or observed < 0
        ):
            raise ValueError(f"recorded heavy replay {key} is invalid")
        if float(observed) > float(integrity[maximum_key]):
            raise ValueError(f"recorded heavy replay {key} exceeds its tolerance envelope")
    if (
        summary["lossAbsoluteTolerance"] != EXPECTED_LOSS_ABSOLUTE_TOLERANCE
        or summary["lossRelativeTolerance"] != EXPECTED_LOSS_RELATIVE_TOLERANCE
    ):
        raise ValueError("recorded heavy replay tolerances differ from the verifier")
    return {**summary, **integrity}


def expected_report(
    run_directory: Path,
    kind: str,
    *,
    replay_summary: Any = None,
) -> dict[str, Any]:
    binding = derive_binding(run_directory)
    if kind == "structural_verifier":
        return {**binding, "report_kind": kind}
    if kind == "fresh_model_replay":
        if replay_summary is None:
            raise ValueError("recorded heavy replay report requires the verifier summary")
        integrity = _replay_integrity(run_directory)
        return {
            **binding,
            "verdict": REPLAY_INTEGRITY_VERDICT,
            "report_kind": kind,
            "execution_scope": REPLAY_EXECUTION_SCOPE,
            "model": {
                "repository": MODEL_REPOSITORY,
                "revision": MODEL_REVISION,
            },
            "replay": _validated_replay_summary(replay_summary, integrity),
        }
    raise ValueError(f"unsupported proof report kind: {kind}")


def _validated_report_target(path: Path, run_directory: Path) -> Path:
    run = validated_run_directory(run_directory)
    parent = path.parent
    expected_parent = run / REPORT_DIRECTORY_NAME
    if not path.is_absolute() or parent != expected_parent:
        raise ValueError("proof report target is outside the exact report directory")
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("proof report directory is missing or symlinked")
    status = parent.stat()
    if status.st_uid != os.getuid() or stat.S_IMODE(status.st_mode) != 0o700:
        raise ValueError("proof report directory must be owner-only mode 0700")
    if path.exists() or path.is_symlink():
        raise ValueError("proof report target already exists")
    return path


def write_report(
    path: Path,
    run_directory: Path,
    kind: str,
    *,
    replay_summary: Any = None,
) -> dict[str, Any]:
    expected_name = {
        "structural_verifier": STRUCTURAL_REPORT_NAME,
        "fresh_model_replay": REPLAY_REPORT_NAME,
    }.get(kind)
    if expected_name is None or path.name != expected_name:
        raise ValueError("proof report kind does not match its canonical filename")
    target = _validated_report_target(path, run_directory)
    report = expected_report(
        run_directory,
        kind,
        replay_summary=replay_summary,
    )
    payload = canonical_json_bytes(report)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("proof report write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if target.read_bytes() != payload:
        raise ValueError("proof report changed after exclusive creation")
    return report


def verify_report(path: Path, run_directory: Path, kind: str) -> dict[str, Any]:
    observed = read_json_object(path, canonical=True)
    replay_summary = observed.get("replay") if kind == "fresh_model_replay" else None
    expected = expected_report(
        run_directory,
        kind,
        replay_summary=replay_summary,
    )
    if observed != expected:
        raise ValueError(f"{kind} report differs from recomputed proof evidence")
    return observed


__all__ = [
    "MODEL_REPOSITORY",
    "MODEL_REVISION",
    "REPLAY_EXECUTION_SCOPE",
    "REPLAY_INTEGRITY_VERDICT",
    "REPLAY_REPORT_NAME",
    "REPORT_DIRECTORY_NAME",
    "STRUCTURAL_REPORT_NAME",
    "TERMINAL_LOG_NAME",
    "WORKLOAD_CLASSIFICATION",
    "canonical_json_bytes",
    "derive_binding",
    "expected_report",
    "read_json_object",
    "sha256_file",
    "validated_run_directory",
    "verify_report",
    "write_report",
]
