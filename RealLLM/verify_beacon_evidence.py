#!/usr/bin/env python3
"""Verify beacon, selection, metrics, raw containers, and artifact bindings."""

from __future__ import annotations

import argparse
import base64
import hashlib
import math
import os
import stat
import statistics
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _require_isolated_verifier_imports() -> None:
    problems: list[str] = []
    if not sys.flags.isolated:
        problems.append("Python isolated mode is disabled")
    if not sys.flags.dont_write_bytecode:
        problems.append("Python bytecode writes are enabled")
    suspicious: set[str] = set()
    for root in (
        PROJECT_ROOT,
        PROJECT_ROOT / "RealLLM",
        PROJECT_ROOT / "BenchmarkCore",
        PROJECT_ROOT / "security",
    ):
        if root == PROJECT_ROOT:
            candidates = list(root.glob("*.py[co]")) + list(
                root.glob("__pycache__")
            )
        else:
            candidates = list(root.rglob("*.py[co]")) + list(
                root.rglob("__pycache__")
            )
        suspicious.update(
            path.relative_to(PROJECT_ROOT).as_posix() for path in candidates
        )
    if suspicious:
        problems.append(
            "local Python bytecode/cache exists: "
            + ", ".join(sorted(suspicious))
        )
    if problems:
        raise RuntimeError("; ".join(problems))


_require_isolated_verifier_imports()

from RealLLM.beacon_protocol import (  # noqa: E402
    ATTEMPT_PATH,
    FREEZE_PATH,
    FREEZE_TAG,
    LEDGER_PATH,
    OUTCOME_PATH,
    PULSE_URL,
    PUBLIC_RELEASE_API,
    PUBLIC_RELEASE_URL,
    RESOLUTION_PATH,
    RESULT_DIRECTORY,
    SUITE_ID,
    TARGET_TIMESTAMP,
    artifact_digest_without_field,
    canonical_json_bytes,
    git_text,
    implementation_sha256,
    load_registration,
    parse_json_bytes,
    registration_artifact_sha256,
    registration_canonical_sha256,
    require_public_freeze,
    sha256_bytes,
    sha256_file,
    validate_registration_and_ledger,
    verify_resolution,
)
from RealLLM.benchmark_real_llm import validate_v5_container_manifest  # noqa: E402
from security.verify_primary_evidence import (  # noqa: E402
    _parse_container as independently_parse_container,
)


_ATTEMPT_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "beacon-attempt.schema.json"
_RESOLUTION_SCHEMA_PATH = (
    PROJECT_ROOT / "schemas" / "beacon-resolution.schema.json"
)
_OUTCOME_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "beacon-outcome.schema.json"

_MAX_ATTEMPT_BYTES = 64 * 1024
_MAX_RESOLUTION_BYTES = 256 * 1024
_MAX_OUTCOME_BYTES = 64 * 1024 * 1024
_MAX_FREEZE_BYTES = 4 * 1024 * 1024
_MAX_SCHEMA_BYTES = 4 * 1024 * 1024
_MAX_PRIMARY_MANIFEST_BYTES = 4 * 1024 * 1024
_MAX_TOKEN_METRICS_BYTES = 32 * 1024 * 1024
_MAX_CERTIFICATE_BYTES = 64 * 1024
_MAX_CERTIFICATE_BASE64_CHARS = 87_384
_MAX_CONTAINER_BYTES = 8 * 1024 * 1024
_MAX_TOTAL_CONTAINER_BYTES = 512 * 1024 * 1024

_ATTEMPT_FIELDS = {
    "schemaVersion",
    "suiteId",
    "status",
    "startedAt",
    "gitCommitAtExecution",
    "gitTagAtExecution",
    "protocolCommit",
    "publicFreezeRelease",
    "registrationArtifactSHA256",
    "registrationCanonicalSHA256",
    "windowLedgerSHA256",
    "implementationSHA256",
    "beaconTargetTimestamp",
    "beaconEndpoint",
    "beaconWillBeFetchedAfterMarker",
    "testSplitWillBeResolvedAfterBeacon",
    "rerunPermitted",
    "attemptSHA256",
}
_RESOLUTION_FIELDS = {
    "schemaVersion",
    "suiteId",
    "status",
    "resolvedAt",
    "attemptSHA256",
    "registrationArtifactSHA256",
    "windowLedgerSHA256",
    "pulseEndpoint",
    "pulse",
    "certificatePEMBase64",
    "verification",
    "selection",
    "resolutionSHA256",
}
_SCIENTIFIC_OUTCOME_FIELDS = {
    "schemaVersion",
    "suiteId",
    "evidenceClass",
    "countsTowardScientificVerdict",
    "verdict",
    "status",
    "finishedAt",
    "gitCommitAtExecution",
    "protocolCommit",
    "registrationArtifactSHA256",
    "implementationSHA256",
    "attemptSHA256",
    "attemptArtifactSHA256",
    "resolutionSHA256",
    "resolutionArtifactSHA256",
    "scientificResult",
    "outcomeSHA256",
}
_FAILURE_OUTCOME_FIELDS = {
    "schemaVersion",
    "suiteId",
    "evidenceClass",
    "countsTowardScientificVerdict",
    "verdict",
    "status",
    "finishedAt",
    "attemptSHA256",
    "attemptArtifactSHA256",
    "resolutionSHA256",
    "resolutionArtifactSHA256",
    "error",
    "scientificResult",
    "outcomeSHA256",
}
_FREEZE_FIELDS = {
    "schemaVersion",
    "suiteId",
    "status",
    "preparedAt",
    "protocolCommit",
    "registrationArtifactSHA256",
    "registrationCanonicalSHA256",
    "windowLedgerSHA256",
    "implementationSHA256",
    "normativeFiles",
}


def _require_exact_fields(
    value: dict[str, Any], expected: set[str], *, label: str
) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise ValueError(
            f"{label} fields differ (missing={missing}, extra={extra})"
        )


def _bounded_file_bytes(path: Path, maximum: int, *, label: str) -> bytes:
    """Read a regular non-symlink file only after enforcing a byte cap."""

    if type(maximum) is not int or maximum < 1:
        raise ValueError("file byte cap must be a positive integer")
    try:
        before = path.lstat()
    except OSError as error:
        raise ValueError(f"cannot stat {label}: {error}") from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} is not a regular non-symlink file")
    if before.st_size < 1 or before.st_size > maximum:
        raise ValueError(
            f"{label} byte length {before.st_size} is outside 1..{maximum}"
        )
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
                or opened.st_size != before.st_size
            ):
                raise ValueError(f"{label} changed between stat and open")
            raw = handle.read(maximum + 1)
    except OSError as error:
        raise ValueError(f"cannot read {label}: {error}") from error
    if len(raw) != before.st_size or len(raw) > maximum:
        raise ValueError(f"{label} changed or exceeded its byte cap while read")
    return raw


def _load_bounded_json_object(
    path: Path, maximum: int, *, label: str
) -> dict[str, Any]:
    raw = _bounded_file_bytes(path, maximum, label=label)
    value = parse_json_bytes(raw, label=label)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _validate_schema(
    document: dict[str, Any], schema_path: Path, *, label: str
) -> None:
    schema = _load_bounded_json_object(
        schema_path, _MAX_SCHEMA_BYTES, label=f"{label} schema"
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise ValueError(f"{label} schema violation at {location}: {first.message}")


def _parse_utc(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must use canonical UTC Z form")
    normalized = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"{label} is not a valid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must use UTC")
    return parsed.astimezone(timezone.utc)


def _finite_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be a finite number")
    return converted


def _finite_sum(records: list[dict[str, Any]], key: str) -> float:
    total = 0.0
    for record in records:
        total += _finite_number(record.get(key), label=f"record {key}")
    if not math.isfinite(total):
        raise ValueError(f"record {key} sum is non-finite")
    return total


def _weighted_average(records: list[dict[str, Any]], key: str) -> float:
    numerator = 0.0
    denominator = 0
    for record in records:
        tokens = record.get("predictionTokens")
        if type(tokens) is not int or tokens <= 0:
            raise ValueError("record predictionTokens must be positive integers")
        value = _finite_number(record.get(key), label=f"record {key}")
        numerator += value * tokens
        denominator += tokens
    if denominator <= 0 or not math.isfinite(numerator):
        raise ValueError(f"cannot aggregate record {key}")
    return numerator / denominator


def _configuration_id(configuration: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(configuration))[:16]


def _aggregate_records(
    configuration: dict[str, Any],
    records: list[dict[str, Any]],
    gates_definition: dict[str, Any],
) -> dict[str, Any]:
    """Independently recompute the frozen producer aggregate."""

    if len(records) != 32 or any(not isinstance(record, dict) for record in records):
        raise ValueError("scientific aggregate requires exactly 32 record objects")
    identifier = _configuration_id(configuration)
    if any(record.get("configurationId") != identifier for record in records):
        raise ValueError("record configuration ID differs from frozen configuration")

    integer_sum_fields = (
        "denseBF16Bytes",
        "encodedFileBytes",
        "predictionTokens",
        "top1AgreementCount",
        "encodeNanoseconds",
        "decodeNanoseconds",
        "modelContinuationNanoseconds",
    )
    integer_sums: dict[str, int] = {}
    for key in integer_sum_fields:
        values = [record.get(key) for record in records]
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError(f"record {key} values must be non-negative integers")
        integer_sums[key] = sum(values)
    if integer_sums["encodedFileBytes"] <= 0:
        raise ValueError("aggregate encoded bytes must be positive")
    if integer_sums["predictionTokens"] <= 0:
        raise ValueError("aggregate prediction tokens must be positive")

    difference_sum_squares = _finite_sum(records, "cacheDifferenceSumSquares")
    reference_sum_squares = _finite_sum(records, "cacheReferenceSumSquares")
    candidate_sum_squares = _finite_sum(records, "cacheCandidateSumSquares")
    dot_product = _finite_sum(records, "cacheDotProduct")
    if min(
        difference_sum_squares,
        reference_sum_squares,
        candidate_sum_squares,
    ) < 0.0:
        raise ValueError("cache sum-of-squares aggregates must be non-negative")
    baseline_nll = _weighted_average(records, "baselineNLLNatPerToken")
    candidate_nll = _weighted_average(records, "candidateNLLNatPerToken")
    delta_nll = candidate_nll - baseline_nll
    try:
        perplexity_ratio = math.exp(delta_nll)
    except OverflowError as error:
        raise ValueError("aggregate delta NLL cannot be exponentiated") from error
    if not math.isfinite(perplexity_ratio):
        raise ValueError("aggregate perplexity ratio is non-finite")

    maximum_errors = [
        _finite_number(
            record.get("cacheMaximumAbsoluteError"),
            label="record cacheMaximumAbsoluteError",
        )
        for record in records
    ]
    if any(value < 0.0 for value in maximum_errors):
        raise ValueError("cache maximum absolute errors must be non-negative")
    payload_digests = [record.get("payloadSHA256") for record in records]
    if any(not isinstance(value, str) for value in payload_digests):
        raise ValueError("record payload digests must be strings")

    result: dict[str, Any] = {
        "configuration": configuration,
        "configurationId": identifier,
        "blocks": len(records),
        "predictionTokens": integer_sums["predictionTokens"],
        "denseBF16Bytes": integer_sums["denseBF16Bytes"],
        "encodedFileBytes": integer_sums["encodedFileBytes"],
        "compressionRatioVsBF16": integer_sums["denseBF16Bytes"]
        / integer_sums["encodedFileBytes"],
        "baselineNLLNatPerToken": baseline_nll,
        "candidateNLLNatPerToken": candidate_nll,
        "deltaNLLNatPerToken": delta_nll,
        "perplexityRatio": perplexity_ratio,
        "top1Agreement": integer_sums["top1AgreementCount"]
        / integer_sums["predictionTokens"],
        "meanKLDivergenceNat": _weighted_average(
            records, "meanKLDivergenceNat"
        ),
        "cacheNormalizedRMSE": math.sqrt(
            difference_sum_squares / max(reference_sum_squares, 1e-30)
        ),
        "cacheCosineSimilarity": dot_product
        / max(math.sqrt(reference_sum_squares * candidate_sum_squares), 1e-30),
        "cacheMaximumAbsoluteError": max(maximum_errors),
        "encodeNanoseconds": integer_sums["encodeNanoseconds"],
        "decodeNanoseconds": integer_sums["decodeNanoseconds"],
        "modelContinuationNanoseconds": integer_sums[
            "modelContinuationNanoseconds"
        ],
        "allPayloadDigestsUnique": len(set(payload_digests))
        == len(payload_digests),
        "pass": False,
    }
    result["gates"] = {
        "compression": result["compressionRatioVsBF16"]
        >= gates_definition["minimumCompressionRatioVsBF16"],
        "deltaNLL": result["deltaNLLNatPerToken"]
        <= gates_definition["maximumDeltaNLLNatPerToken"],
        "top1Agreement": result["top1Agreement"]
        >= gates_definition["minimumTop1Agreement"],
    }
    result["pass"] = all(result["gates"].values())
    return result


def _wilson_lower(successes: int, trials: int, z: float) -> float:
    if trials <= 0 or successes < 0 or successes > trials:
        raise ValueError("invalid Bernoulli counts")
    probability = successes / trials
    denominator = 1.0 + z * z / trials
    center = probability + z * z / (2.0 * trials)
    radius = z * math.sqrt(
        probability * (1.0 - probability) / trials
        + z * z / (4.0 * trials * trials)
    )
    return (center - radius) / denominator


def _confidence_and_verdict(
    records: list[dict[str, Any]],
    baselines: list[dict[str, Any]],
    aggregate: dict[str, Any],
    gates_definition: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, bool], bool]:
    """Independently recompute confidence bounds and the seven gates."""

    if (
        len(records) != 32
        or len(baselines) != 32
        or any(not isinstance(item, dict) for item in (*records, *baselines))
    ):
        raise ValueError("frozen held-out evaluation requires exactly 32 blocks")
    delta_values = [
        _finite_number(record.get("deltaNLLNatPerToken"), label="record delta NLL")
        for record in records
    ]
    delta_mean = statistics.fmean(delta_values)
    delta_standard_deviation = statistics.stdev(delta_values)
    student_t = _finite_number(
        gates_definition.get("studentTCriticalOneSided95Df31"),
        label="registered Student t critical value",
    )
    delta_upper = delta_mean + (
        student_t * delta_standard_deviation / math.sqrt(len(delta_values))
    )
    prediction_tokens = 0
    agreement_count = 0
    block_top1_values: list[float] = []
    for record in records:
        tokens = record.get("predictionTokens")
        agreements = record.get("top1AgreementCount")
        if (
            type(tokens) is not int
            or tokens <= 0
            or type(agreements) is not int
            or agreements < 0
            or agreements > tokens
        ):
            raise ValueError("invalid record prediction/agreement counts")
        prediction_tokens += tokens
        agreement_count += agreements
        block_top1_values.append(agreements / tokens)
    block_top1_mean = statistics.fmean(block_top1_values)
    block_top1_standard_deviation = statistics.stdev(block_top1_values)
    block_top1_lower = block_top1_mean - (
        student_t
        * block_top1_standard_deviation
        / math.sqrt(len(block_top1_values))
    )
    wilson_z = _finite_number(
        gates_definition.get("wilsonZOneSided95"),
        label="registered Wilson z value",
    )
    wilson_lower = _wilson_lower(agreement_count, prediction_tokens, wilson_z)
    confidence = {
        "blockDeltaNLLMean": delta_mean,
        "blockDeltaNLLSampleStandardDeviation": delta_standard_deviation,
        "blockwiseDeltaNLLUpperOneSided95": delta_upper,
        "blockTop1Mean": block_top1_mean,
        "blockTop1SampleStandardDeviation": block_top1_standard_deviation,
        "blockwiseTop1LowerOneSided95": block_top1_lower,
        "predictionTokens": prediction_tokens,
        "top1AgreementCount": agreement_count,
        "wilsonLowerOneSided95": wilson_lower,
    }
    structural_replay = bool(baselines) and all(
        baseline.get("exactRebuildMaxAbsLogitDifference") == 0.0
        and baseline.get("exactRebuildTop1Identical") is True
        and baseline.get("layoutRebuildMaxAbsLogitDifference") == 0.0
        and baseline.get("layoutRebuildTop1Identical") is True
        for baseline in baselines
    )
    gates = {
        "compressionRatioVsBF16": aggregate["compressionRatioVsBF16"]
        >= gates_definition["minimumCompressionRatioVsBF16"],
        "deltaNLLNatPerToken": aggregate["deltaNLLNatPerToken"]
        <= gates_definition["maximumDeltaNLLNatPerToken"],
        "blockwiseDeltaNLLUpperOneSided95": delta_upper
        <= gates_definition["maximumBlockwiseDeltaNLLUpperOneSided95"],
        "top1Agreement": aggregate["top1Agreement"]
        >= gates_definition["minimumTop1Agreement"],
        "blockwiseTop1LowerOneSided95": block_top1_lower
        >= gates_definition["minimumBlockwiseTop1LowerOneSided95"],
        "wilsonLowerOneSided95": wilson_lower
        >= gates_definition["minimumWilsonLowerOneSided95"],
        "structuralReplay": structural_replay,
    }
    return confidence, gates, all(gates.values())


def _close(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if not math.isfinite(float(left)) or not math.isfinite(float(right)):
            return False
        return math.isclose(
            float(left), float(right), rel_tol=1e-12, abs_tol=1e-12
        )
    return left == right


def _same_mapping(
    observed: dict[str, Any], expected: dict[str, Any], *, label: str
) -> None:
    if set(observed) != set(expected):
        raise ValueError(f"{label} fields differ")
    for key, value in expected.items():
        if not _close(observed[key], value):
            raise ValueError(f"{label} field {key} differs")


def _safe_relative_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("artifact path must be a non-empty string")
    candidate = root / relative
    if candidate.is_symlink():
        raise ValueError(f"artifact is symlinked: {relative}")
    resolved_root = root.resolve(strict=True)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"artifact is missing: {relative}") from error
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(f"artifact escapes result directory: {relative}") from error
    return resolved


def _ordered_mean(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot average an empty metric sequence")
    total = 0.0
    for value in values:
        if not math.isfinite(float(value)):
            raise ValueError("token metric contains a non-finite value")
        total += float(value)
    return total / len(values)


def verify_primary_evidence(scientific: dict[str, Any]) -> dict[str, Any]:
    configuration = scientific.get("configuration")
    if not isinstance(configuration, dict):
        raise ValueError("scientific result has no codec configuration")
    descriptor = scientific.get("primaryEvidence")
    if not isinstance(descriptor, dict):
        raise ValueError("scientific result has no primary-evidence descriptor")
    expected_descriptor_keys = {
        "schemaVersion",
        "path",
        "manifestSHA256",
        "manifestBytes",
        "containerCount",
        "containerBytes",
        "blocks",
        "predictionTokens",
    }
    if set(descriptor) != expected_descriptor_keys:
        raise ValueError("primary-evidence descriptor fields differ")
    if descriptor["schemaVersion"] != "corelm-real-llm-primary-evidence-v1":
        raise ValueError("primary-evidence schema version differs")
    manifest_bytes = descriptor.get("manifestBytes")
    if (
        type(manifest_bytes) is not int
        or manifest_bytes < 1
        or manifest_bytes > _MAX_PRIMARY_MANIFEST_BYTES
    ):
        raise ValueError("primary-evidence manifest byte count is outside its cap")
    manifest_path = _safe_relative_file(RESULT_DIRECTORY, descriptor["path"])
    manifest_raw = _bounded_file_bytes(
        manifest_path,
        _MAX_PRIMARY_MANIFEST_BYTES,
        label="primary-evidence manifest",
    )
    manifest_value = parse_json_bytes(
        manifest_raw, label="primary-evidence manifest"
    )
    if not isinstance(manifest_value, dict):
        raise ValueError("primary-evidence manifest must be an object")
    manifest = manifest_value
    if (
        descriptor["manifestSHA256"] != sha256_bytes(manifest_raw)
        or descriptor["manifestBytes"] != len(manifest_raw)
    ):
        raise ValueError("primary-evidence manifest binding differs")
    if set(manifest) != {
        "schemaVersion",
        "resultFile",
        "containers",
        "tokenMetrics",
    }:
        raise ValueError("primary-evidence manifest fields differ")
    if (
        manifest["schemaVersion"] != "corelm-real-llm-primary-evidence-v1"
        or manifest["resultFile"] != "outcome.json"
    ):
        raise ValueError("primary-evidence manifest identity differs")

    source = scientific.get("source")
    if not isinstance(source, dict):
        raise ValueError("scientific result has no source description")
    start = source.get("startBlock")
    blocks = source.get("blocks")
    if type(start) is not int or blocks != 32:
        raise ValueError("scientific source window is not 32 blocks")
    expected_blocks = list(range(start, start + 32))
    records = scientific.get("records")
    baselines = scientific.get("baselines")
    if not isinstance(records, list) or not isinstance(baselines, list):
        raise ValueError("scientific result records or baselines are missing")
    if [record.get("blockIndex") for record in records] != expected_blocks:
        raise ValueError("scientific record block order differs")
    if [baseline.get("blockIndex") for baseline in baselines] != expected_blocks:
        raise ValueError("scientific baseline block order differs")

    containers = manifest.get("containers")
    if not isinstance(containers, list) or len(containers) != 32 * 24:
        raise ValueError("primary evidence must contain exactly 768 containers")
    declared_total = descriptor.get("containerBytes")
    if (
        type(declared_total) is not int
        or declared_total < 1
        or declared_total > _MAX_TOTAL_CONTAINER_BYTES
    ):
        raise ValueError("primary-evidence container byte total is outside its cap")
    total_container_bytes = 0
    observed_paths: set[str] = set()
    for block_offset, block_index in enumerate(expected_blocks):
        record = records[block_offset]
        record_manifest = record.get("containerManifest")
        validate_v5_container_manifest(record, configuration)
        if not isinstance(record_manifest, list) or len(record_manifest) != 24:
            raise ValueError(f"block {block_index} has no 24-layer manifest")
        payload_hasher = hashlib.sha256()
        block_payload_bytes = 0
        block_container_bytes = 0
        for layer_index in range(24):
            position = block_offset * 24 + layer_index
            entry = containers[position]
            if not isinstance(entry, dict) or set(entry) != {
                "blockIndex",
                "layerIndex",
                "path",
                "bytes",
                "sha256",
            }:
                raise ValueError("primary container entry fields differ")
            expected_path = (
                "primary-evidence/containers/"
                f"block-{block_index:03d}/layer-{layer_index:02d}.vtl5"
            )
            if (
                entry["blockIndex"] != block_index
                or entry["layerIndex"] != layer_index
                or entry["path"] != expected_path
                or expected_path in observed_paths
            ):
                raise ValueError("primary container order or path differs")
            entry_bytes = entry.get("bytes")
            if (
                type(entry_bytes) is not int
                or entry_bytes < 1
                or entry_bytes > _MAX_CONTAINER_BYTES
            ):
                raise ValueError(f"raw container byte count is outside cap: {expected_path}")
            observed_paths.add(expected_path)
            path = _safe_relative_file(RESULT_DIRECTORY, expected_path)
            raw = _bounded_file_bytes(
                path, _MAX_CONTAINER_BYTES, label=f"raw container {expected_path}"
            )
            if entry["bytes"] != len(raw) or entry["sha256"] != sha256_bytes(raw):
                raise ValueError(f"raw container binding differs: {expected_path}")
            payload_bytes, _ = independently_parse_container(
                raw,
                block_index=block_index,
                layer_index=layer_index,
                expected_manifest=record_manifest[layer_index],
            )
            payload_hasher.update(layer_index.to_bytes(4, "little"))
            payload_hasher.update(len(raw).to_bytes(8, "little"))
            payload_hasher.update(raw)
            block_payload_bytes += payload_bytes
            block_container_bytes += len(raw)
            total_container_bytes += len(raw)
            if total_container_bytes > _MAX_TOTAL_CONTAINER_BYTES:
                raise ValueError("primary-evidence container bytes exceed total cap")
        if (
            record.get("payloadBytes") != block_payload_bytes
            or record.get("encodedFileBytes") != block_container_bytes
            or record.get("payloadSHA256") != payload_hasher.hexdigest()
        ):
            raise ValueError(f"block {block_index} raw byte accounting differs")

    token_reference = manifest.get("tokenMetrics")
    if not isinstance(token_reference, dict) or set(token_reference) != {
        "path",
        "bytes",
        "sha256",
        "blocks",
        "predictionTokens",
    }:
        raise ValueError("token-metrics reference fields differ")
    token_bytes = token_reference.get("bytes")
    if (
        type(token_bytes) is not int
        or token_bytes < 1
        or token_bytes > _MAX_TOKEN_METRICS_BYTES
    ):
        raise ValueError("token-metrics byte count is outside its cap")
    token_path = _safe_relative_file(RESULT_DIRECTORY, token_reference["path"])
    token_raw = _bounded_file_bytes(
        token_path, _MAX_TOKEN_METRICS_BYTES, label="token metrics"
    )
    token_value = parse_json_bytes(token_raw, label="token metrics")
    if not isinstance(token_value, dict):
        raise ValueError("token metrics must contain a JSON object")
    token_document = token_value
    if (
        token_reference["bytes"] != len(token_raw)
        or token_reference["sha256"] != sha256_bytes(token_raw)
        or token_reference["blocks"] != 32
        or token_reference["predictionTokens"] != 4096
    ):
        raise ValueError("token-metrics file binding differs")
    if set(token_document) != {"schemaVersion", "blocks"}:
        raise ValueError("token-metrics document fields differ")
    if token_document.get("schemaVersion") != "corelm-real-llm-token-metrics-v1":
        raise ValueError("token-metrics schema version differs")
    token_blocks = token_document["blocks"]
    if not isinstance(token_blocks, list) or [
        block.get("blockIndex") for block in token_blocks
    ] != expected_blocks:
        raise ValueError("token-metrics block order differs")
    selected_token_bytes = bytearray()
    for block_index, block, record in zip(expected_blocks, token_blocks, records):
        if not isinstance(block, dict) or set(block) != {
            "blockIndex",
            "tokenIds",
            "predictionTokens",
            "tokens",
        }:
            raise ValueError(f"block {block_index} token fields differ")
        token_ids = block["tokenIds"]
        token_rows = block["tokens"]
        if (
            not isinstance(token_ids, list)
            or len(token_ids) != 512
            or any(type(value) is not int or value < 0 or value > 0xFFFFFFFF for value in token_ids)
            or block["predictionTokens"] != 128
            or not isinstance(token_rows, list)
            or len(token_rows) != 128
        ):
            raise ValueError(f"block {block_index} token evidence dimensions differ")
        block_bytes = b"".join(struct.pack("<I", value) for value in token_ids)
        selected_token_bytes.extend(block_bytes)
        if record.get("tokenIdsSHA256") != sha256_bytes(block_bytes):
            raise ValueError(f"block {block_index} token digest differs")
        baseline = baselines[block_index - expected_blocks[0]]
        if (
            not isinstance(baseline, dict)
            or baseline.get("tokenIdsSHA256") != sha256_bytes(block_bytes)
        ):
            raise ValueError(f"block {block_index} baseline token digest differs")
        baseline_losses: list[float] = []
        candidate_losses: list[float] = []
        agreements = 0
        token_row_fields = {
            "offset",
            "targetTokenId",
            "baselineLossNat",
            "candidateLossNat",
            "baselineTop1TokenId",
            "candidateTop1TokenId",
            "top1Agrees",
        }
        for offset, row in enumerate(token_rows):
            if (
                not isinstance(row, dict)
                or set(row) != token_row_fields
                or row.get("offset") != offset
            ):
                raise ValueError(f"block {block_index} token row order differs")
            for name in (
                "targetTokenId",
                "baselineTop1TokenId",
                "candidateTop1TokenId",
            ):
                value = row.get(name)
                if type(value) is not int or value < 0 or value > 0xFFFFFFFF:
                    raise ValueError(
                        f"block {block_index} token row {name} is invalid"
                    )
            if row.get("targetTokenId") != token_ids[384 + offset]:
                raise ValueError(f"block {block_index} target token differs")
            agrees = row.get("baselineTop1TokenId") == row.get(
                "candidateTop1TokenId"
            )
            if type(row.get("top1Agrees")) is not bool or row.get(
                "top1Agrees"
            ) is not agrees:
                raise ValueError(f"block {block_index} agreement flag differs")
            baseline_loss = _finite_number(
                row.get("baselineLossNat"), label="baseline token loss"
            )
            candidate_loss = _finite_number(
                row.get("candidateLossNat"), label="candidate token loss"
            )
            if baseline_loss < 0.0 or candidate_loss < 0.0:
                raise ValueError(f"block {block_index} token loss is negative")
            baseline_losses.append(baseline_loss)
            candidate_losses.append(candidate_loss)
            agreements += int(agrees)
        baseline_mean = _ordered_mean(baseline_losses)
        candidate_mean = _ordered_mean(candidate_losses)
        if (
            not _close(record.get("baselineNLLNatPerToken"), baseline_mean)
            or not _close(record.get("candidateNLLNatPerToken"), candidate_mean)
            or not _close(
                record.get("deltaNLLNatPerToken"), candidate_mean - baseline_mean
            )
            or record.get("top1AgreementCount") != agreements
            or not _close(record.get("top1Agreement"), agreements / 128)
        ):
            raise ValueError(f"block {block_index} token metrics do not recompute")
    if source.get("selectedTokenIdsSHA256") != sha256_bytes(
        bytes(selected_token_bytes)
    ):
        raise ValueError("selected-window token digest differs")
    if (
        descriptor["containerCount"] != 768
        or descriptor["containerBytes"] != total_container_bytes
        or descriptor["blocks"] != 32
        or descriptor["predictionTokens"] != 4096
    ):
        raise ValueError("primary-evidence descriptor totals differ")
    return {
        "containers": 768,
        "containerBytes": total_container_bytes,
        "blocks": 32,
        "predictionTokens": 4096,
    }


def verify_scientific_result(
    scientific: dict[str, Any], resolution: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    try:
        registration = load_registration()
        selected = resolution["selection"]["selectedWindow"]
        source = scientific.get("source")
        if not isinstance(source, dict):
            raise ValueError("scientific result has no source")
        if (
            source.get("split") != "test"
            or source.get("startBlock") != selected.get("startBlock")
            or source.get("blocks") != 32
            or source.get("endBlockExclusive")
            != int(selected["startBlock"]) + 32
        ):
            raise ValueError("scientific result uses a different resolved window")
        configuration = scientific.get("configuration")
        if configuration != registration["configuration"]:
            raise ValueError("scientific configuration differs from registration")
        if scientific.get("configurationSHA256") != registration[
            "configurationSHA256"
        ]:
            raise ValueError("scientific configuration digest differs")
        if scientific.get("gatesDefinition") != registration["gates"]:
            raise ValueError("scientific gates differ from registration")
        records = scientific.get("records")
        baselines = scientific.get("baselines")
        if (
            not isinstance(records, list)
            or len(records) != 32
            or not isinstance(baselines, list)
            or len(baselines) != 32
        ):
            raise ValueError("scientific records or baselines are missing")
        recomputed_aggregate = _aggregate_records(
            configuration, records, registration["gates"]
        )
        observed_aggregate = scientific.get("aggregate")
        if not isinstance(observed_aggregate, dict):
            raise ValueError("scientific aggregate is missing")
        _same_mapping(observed_aggregate, recomputed_aggregate, label="aggregate")
        confidence, gates, passed = _confidence_and_verdict(
            records,
            baselines,
            recomputed_aggregate,
            registration["gates"],
        )
        observed_confidence = scientific.get("confidence")
        if not isinstance(observed_confidence, dict):
            raise ValueError("scientific confidence is missing")
        _same_mapping(observed_confidence, confidence, label="confidence")
        if scientific.get("gates") != gates or scientific.get("pass") is not passed:
            raise ValueError("scientific verdict does not recompute")
        verify_primary_evidence(scientific)
    except (KeyError, TypeError, ValueError) as error:
        errors.append(str(error))
    return errors


def _git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw,
        usedforsecurity=False,
    ).hexdigest()


def _verify_attempt_and_freeze(
    attempt: dict[str, Any],
    registration: dict[str, Any],
) -> datetime:
    _require_exact_fields(attempt, _ATTEMPT_FIELDS, label="attempt")
    _validate_schema(attempt, _ATTEMPT_SCHEMA_PATH, label="attempt")
    if (
        attempt.get("schemaVersion") != "corelm-beacon-attempt-v1"
        or attempt.get("suiteId") != SUITE_ID
        or attempt.get("status")
        != "attempt-started-beacon-and-data-not-yet-resolved"
    ):
        raise ValueError("attempt identity or status differs")
    if (
        attempt.get("beaconWillBeFetchedAfterMarker") is not True
        or attempt.get("testSplitWillBeResolvedAfterBeacon") is not True
        or attempt.get("rerunPermitted") is not False
    ):
        raise ValueError("attempt state policy differs")
    if attempt.get("attemptSHA256") != artifact_digest_without_field(
        attempt, "attemptSHA256"
    ):
        raise ValueError("attempt digest is inconsistent")
    if (
        attempt.get("gitTagAtExecution") != FREEZE_TAG
        or attempt.get("beaconTargetTimestamp") != TARGET_TIMESTAMP
        or attempt.get("beaconEndpoint") != PULSE_URL
    ):
        raise ValueError("attempt tag or beacon binding differs")

    freeze_raw = _bounded_file_bytes(
        FREEZE_PATH, _MAX_FREEZE_BYTES, label="beacon freeze manifest"
    )
    freeze_value = parse_json_bytes(freeze_raw, label="beacon freeze manifest")
    if not isinstance(freeze_value, dict):
        raise ValueError("beacon freeze manifest must be an object")
    freeze = freeze_value
    _require_exact_fields(freeze, _FREEZE_FIELDS, label="freeze manifest")
    if (
        freeze.get("schemaVersion") != "corelm-beacon-freeze-v1"
        or freeze.get("suiteId") != SUITE_ID
        or freeze.get("status") != "protocol-files-frozen-before-beacon"
    ):
        raise ValueError("freeze manifest identity or status differs")

    execution_commit = attempt.get("gitCommitAtExecution")
    if not isinstance(execution_commit, str):
        raise ValueError("attempt has no execution commit")
    tagged_blob = git_text(
        "rev-parse", f"{execution_commit}:RealLLM/beacon_freeze.json"
    )
    if tagged_blob != _git_blob_sha1(freeze_raw):
        raise ValueError("working freeze manifest differs from the tagged commit")
    verified_public_freeze = require_public_freeze(execution_commit)
    if not isinstance(verified_public_freeze, dict):
        raise ValueError("public freeze verification did not return an object")
    verified_manifest = dict(verified_public_freeze)
    release_verification = verified_manifest.pop(
        "publicReleaseVerification", None
    )
    if verified_manifest != freeze:
        raise ValueError("public tag freeze differs from the local freeze manifest")
    public_release = attempt.get("publicFreezeRelease")
    if (
        not isinstance(public_release, dict)
        or set(public_release) != {"apiURL", "htmlURL", "immutable", "publishedAt"}
        or public_release.get("apiURL") != PUBLIC_RELEASE_API
        or public_release.get("htmlURL") != PUBLIC_RELEASE_URL
        or public_release.get("immutable") is not True
        or public_release != release_verification
    ):
        raise ValueError("attempt public freeze release binding differs")

    expected_bindings = {
        "protocolCommit": freeze.get("protocolCommit"),
        "registrationArtifactSHA256": freeze.get(
            "registrationArtifactSHA256"
        ),
        "registrationCanonicalSHA256": freeze.get(
            "registrationCanonicalSHA256"
        ),
        "windowLedgerSHA256": freeze.get("windowLedgerSHA256"),
        "implementationSHA256": freeze.get("implementationSHA256"),
    }
    for field, expected in expected_bindings.items():
        if attempt.get(field) != expected:
            raise ValueError(f"attempt {field} differs from public freeze")
    if attempt.get("registrationArtifactSHA256") != registration_artifact_sha256():
        raise ValueError("attempt registration artifact digest differs")
    if attempt.get("registrationCanonicalSHA256") != registration_canonical_sha256():
        raise ValueError("attempt canonical registration digest differs")
    if attempt.get("windowLedgerSHA256") != sha256_file(LEDGER_PATH):
        raise ValueError("attempt window-ledger digest differs")
    if attempt.get("implementationSHA256") != implementation_sha256():
        raise ValueError("attempt implementation digest differs")
    if registration.get("suiteId") != SUITE_ID:
        raise ValueError("current registration suite differs")

    target_time = _parse_utc(TARGET_TIMESTAMP, label="target beacon time")
    prepared_time = _parse_utc(freeze.get("preparedAt"), label="freeze preparedAt")
    published_time = _parse_utc(
        public_release.get("publishedAt"), label="public freeze publishedAt"
    )
    started_time = _parse_utc(attempt.get("startedAt"), label="attempt startedAt")
    deadline_time = _parse_utc(
        registration.get("execution", {}).get("deadline"),
        label="registered execution deadline",
    )
    if not prepared_time < target_time:
        raise ValueError("freeze manifest was not prepared before beacon reveal")
    if not prepared_time <= published_time < target_time:
        raise ValueError("public freeze release was not published before beacon reveal")
    if not target_time <= started_time <= deadline_time:
        raise ValueError("attempt start is outside the registered execution window")
    return started_time


def _verify_nist_nested_fields(resolution: dict[str, Any]) -> None:
    pulse = resolution.get("pulse")
    if not isinstance(pulse, dict):
        raise ValueError("resolution has no NIST pulse")
    external = pulse.get("external")
    if not isinstance(external, dict) or set(external) != {
        "sourceId",
        "statusCode",
        "value",
    }:
        raise ValueError("NIST external-value fields differ")
    list_values = pulse.get("listValues")
    if not isinstance(list_values, list) or len(list_values) != 5:
        raise ValueError("NIST listValues count differs")
    chain_index = pulse.get("chainIndex")
    pulse_index = pulse.get("pulseIndex")
    if type(chain_index) is not int or type(pulse_index) is not int:
        raise ValueError("NIST pulse indices must be integers")
    uri_prefix = (
        f"https://beacon.nist.gov/beacon/2.0/chain/{chain_index}/pulse/"
    )
    observed_types: set[str] = set()
    for item in list_values:
        if not isinstance(item, dict) or set(item) != {"uri", "type", "value"}:
            raise ValueError("NIST list-value fields differ")
        kind = item.get("type")
        if not isinstance(kind, str) or kind in observed_types:
            raise ValueError("NIST list-value types are not unique")
        observed_types.add(kind)
        uri = item.get("uri")
        if not isinstance(uri, str) or not uri.startswith(uri_prefix):
            raise ValueError("NIST list-value URI uses a different chain")
        suffix = uri[len(uri_prefix) :]
        if (
            not suffix.isascii()
            or not suffix.isdecimal()
            or (len(suffix) > 1 and suffix.startswith("0"))
        ):
            raise ValueError("NIST list-value URI has a non-canonical pulse index")
        linked_index = int(suffix)
        if linked_index < 0 or linked_index >= pulse_index:
            raise ValueError("NIST list-value URI does not refer to an earlier pulse")
    if observed_types != {"previous", "hour", "day", "month", "year"}:
        raise ValueError("NIST list-value types differ")


def _verify_resolution_artifact(
    resolution: dict[str, Any],
    attempt: dict[str, Any],
    *,
    started_time: datetime,
    finished_time: datetime,
) -> datetime:
    _require_exact_fields(resolution, _RESOLUTION_FIELDS, label="resolution")
    _validate_schema(
        resolution, _RESOLUTION_SCHEMA_PATH, label="beacon resolution"
    )
    if (
        resolution.get("schemaVersion") != "corelm-beacon-resolution-v1"
        or resolution.get("suiteId") != SUITE_ID
        or resolution.get("status") != "beacon-resolved-before-model-data"
        or resolution.get("pulseEndpoint") != PULSE_URL
    ):
        raise ValueError("resolution identity or status differs")
    if resolution.get("attemptSHA256") != attempt.get("attemptSHA256"):
        raise ValueError("resolution references a different attempt")
    if (
        resolution.get("registrationArtifactSHA256")
        != attempt.get("registrationArtifactSHA256")
        or resolution.get("windowLedgerSHA256")
        != attempt.get("windowLedgerSHA256")
    ):
        raise ValueError("resolution registration or ledger binding differs")
    encoded_certificate = resolution.get("certificatePEMBase64")
    if (
        not isinstance(encoded_certificate, str)
        or len(encoded_certificate) > _MAX_CERTIFICATE_BASE64_CHARS
    ):
        raise ValueError("resolution certificate exceeds its encoded byte cap")
    try:
        certificate = base64.b64decode(encoded_certificate, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("resolution certificate is not valid base64") from error
    if len(certificate) < 1 or len(certificate) > _MAX_CERTIFICATE_BYTES:
        raise ValueError("resolution certificate exceeds its decoded byte cap")
    _verify_nist_nested_fields(resolution)
    resolution_errors = verify_resolution(resolution)
    if resolution_errors:
        raise ValueError(
            "beacon resolution is invalid: " + "; ".join(resolution_errors)
        )
    resolved_time = _parse_utc(
        resolution.get("resolvedAt"), label="resolution resolvedAt"
    )
    if not started_time <= resolved_time <= finished_time:
        raise ValueError("resolution timestamp is outside attempt/outcome order")
    return resolved_time


def verify_evidence() -> tuple[list[str], dict[str, Any] | None]:
    errors: list[str] = []
    outcome: dict[str, Any] | None = None
    try:
        registration, _ = validate_registration_and_ledger()
        attempt_raw = _bounded_file_bytes(
            ATTEMPT_PATH, _MAX_ATTEMPT_BYTES, label="one-shot attempt"
        )
        attempt_value = parse_json_bytes(attempt_raw, label="one-shot attempt")
        if not isinstance(attempt_value, dict):
            raise ValueError("one-shot attempt must contain a JSON object")
        attempt = attempt_value
        started_time = _verify_attempt_and_freeze(attempt, registration)

        outcome_raw = _bounded_file_bytes(
            OUTCOME_PATH, _MAX_OUTCOME_BYTES, label="one-shot outcome"
        )
        outcome_value = parse_json_bytes(outcome_raw, label="one-shot outcome")
        if not isinstance(outcome_value, dict):
            raise ValueError("one-shot outcome must contain a JSON object")
        outcome = outcome_value
        verdict = outcome.get("verdict")
        if verdict == "FAIL_EXECUTION":
            _require_exact_fields(
                outcome, _FAILURE_OUTCOME_FIELDS, label="FAIL_EXECUTION outcome"
            )
        elif verdict in {"PASS", "FAIL_GATES"}:
            _require_exact_fields(
                outcome, _SCIENTIFIC_OUTCOME_FIELDS, label="scientific outcome"
            )
        else:
            raise ValueError("outcome verdict is not terminal")
        _validate_schema(outcome, _OUTCOME_SCHEMA_PATH, label="outcome")
        if (
            outcome.get("schemaVersion") != "corelm-beacon-outcome-v1"
            or outcome.get("suiteId") != SUITE_ID
            or outcome.get("evidenceClass")
            != "post-freeze-beacon-selected-heldout-window"
            or outcome.get("countsTowardScientificVerdict") is not True
        ):
            raise ValueError("outcome identity or evidence class differs")
        if outcome.get("outcomeSHA256") != artifact_digest_without_field(
            outcome, "outcomeSHA256"
        ):
            raise ValueError("outcome digest is inconsistent")
        if outcome.get("attemptSHA256") != attempt.get("attemptSHA256"):
            raise ValueError("outcome references a different attempt")
        if outcome.get("attemptArtifactSHA256") != sha256_bytes(attempt_raw):
            raise ValueError("outcome attempt artifact binding differs")
        finished_time = _parse_utc(
            outcome.get("finishedAt"), label="outcome finishedAt"
        )
        if finished_time < started_time:
            raise ValueError("outcome predates the attempt marker")

        resolution_exists = os.path.lexists(RESOLUTION_PATH)
        if verdict == "FAIL_EXECUTION":
            if (
                outcome.get("status") != "terminal-execution-failure"
                or outcome.get("scientificResult") is not None
            ):
                raise ValueError("FAIL_EXECUTION status or scientific result differs")
            if resolution_exists:
                resolution_raw = _bounded_file_bytes(
                    RESOLUTION_PATH,
                    _MAX_RESOLUTION_BYTES,
                    label="beacon resolution",
                )
                resolution_value = parse_json_bytes(
                    resolution_raw, label="beacon resolution"
                )
                if not isinstance(resolution_value, dict):
                    raise ValueError("beacon resolution must contain a JSON object")
                resolution = resolution_value
                _verify_resolution_artifact(
                    resolution,
                    attempt,
                    started_time=started_time,
                    finished_time=finished_time,
                )
                if (
                    outcome.get("resolutionSHA256")
                    != resolution.get("resolutionSHA256")
                    or outcome.get("resolutionArtifactSHA256")
                    != sha256_bytes(resolution_raw)
                ):
                    raise ValueError(
                        "FAIL_EXECUTION references a different resolution"
                    )
            elif (
                outcome.get("resolutionSHA256") is not None
                or outcome.get("resolutionArtifactSHA256") is not None
            ):
                raise ValueError(
                    "FAIL_EXECUTION claims a resolution artifact that is absent"
                )
            return errors, outcome

        if outcome.get("status") != "terminal-scientific-result":
            raise ValueError("scientific outcome status differs")
        deadline_time = _parse_utc(
            registration.get("execution", {}).get("deadline"),
            label="registered execution deadline",
        )
        if finished_time > deadline_time:
            raise ValueError(
                "scientific outcome finished after the registered execution deadline"
            )
        if (
            outcome.get("registrationArtifactSHA256")
            != attempt.get("registrationArtifactSHA256")
            or outcome.get("implementationSHA256")
            != attempt.get("implementationSHA256")
            or outcome.get("protocolCommit") != attempt.get("protocolCommit")
            or outcome.get("gitCommitAtExecution")
            != attempt.get("gitCommitAtExecution")
        ):
            raise ValueError("scientific outcome freeze bindings differ")
        if not resolution_exists:
            raise ValueError("scientific outcome has no resolution artifact")
        resolution_raw = _bounded_file_bytes(
            RESOLUTION_PATH, _MAX_RESOLUTION_BYTES, label="beacon resolution"
        )
        resolution_value = parse_json_bytes(
            resolution_raw, label="beacon resolution"
        )
        if not isinstance(resolution_value, dict):
            raise ValueError("beacon resolution must contain a JSON object")
        resolution = resolution_value
        _verify_resolution_artifact(
            resolution,
            attempt,
            started_time=started_time,
            finished_time=finished_time,
        )
        if outcome.get("resolutionSHA256") != resolution.get("resolutionSHA256"):
            raise ValueError("outcome references a different resolution")
        if outcome.get("resolutionArtifactSHA256") != sha256_bytes(resolution_raw):
            raise ValueError("outcome resolution artifact binding differs")
        scientific = outcome.get("scientificResult")
        if not isinstance(scientific, dict):
            raise ValueError("terminal scientific outcome has no result")
        scientific_errors = verify_scientific_result(scientific, resolution)
        if scientific_errors:
            raise ValueError("; ".join(scientific_errors))
        expected_verdict = "PASS" if scientific.get("pass") is True else "FAIL_GATES"
        if verdict != expected_verdict:
            raise ValueError("terminal verdict differs from recomputed gates")
    except (OSError, TypeError, ValueError) as error:
        errors.append(str(error))
    return errors, outcome


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args(arguments)


def main() -> int:
    parse_arguments()
    errors, outcome = verify_evidence()
    if errors:
        print("BEACON EVIDENCE INVALID:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    assert outcome is not None
    print(f"BEACON EVIDENCE VERIFIED: {outcome['verdict']}")
    print(f"Outcome SHA-256: {outcome['outcomeSHA256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
