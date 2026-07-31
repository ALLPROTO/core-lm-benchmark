#!/usr/bin/env python3
"""Verify the published VoidToken v5 validation-only development artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RealLLM.benchmark_real_llm import (  # noqa: E402
    DATASET_REPOSITORY,
    DATASET_REVISION,
    MODEL_REPOSITORY,
    MODEL_REVISION,
    MODEL_WEIGHTS_SHA256,
    validate_v5_container_manifest,
)
from RealLLM.run_voidtoken_v5_frozen import (  # noqa: E402
    DEVELOPMENT_ARTIFACTS,
    DEVELOPMENT_MANIFEST,
    DEVELOPMENT_OBSERVATION,
    FROZEN_CONFIGURATION,
    FROZEN_CONFIGURATION_SHA256,
    SUITE_ID,
    validate_frozen_registration,
)


MANIFEST_PATH = PROJECT_ROOT / DEVELOPMENT_MANIFEST["path"]
FULL_DEVELOPMENT_GRID_SHA256 = (
    "ed69605b34db08566ea26680d51e29f7808bb0c207bc8efefd4fb62423c72c35"
)
CONFIGURATION_ID = FROZEN_CONFIGURATION_SHA256[:16]
DEVELOPMENT_THRESHOLDS = {
    "minimumCompressionRatioVsBF16": 2.0,
    "maximumDeltaNLLNatPerToken": 0.01,
    "minimumTop1Agreement": 0.99,
}
PROSPECTIVE_GATES = {
    "minimumCompressionRatioVsBF16": 2.0,
    "maximumDeltaNLLNatPerToken": 0.01,
    "maximumBlockwiseDeltaNLLUpperOneSided95": 0.01,
    "minimumTop1Agreement": 0.99,
    "minimumBlockwiseTop1LowerOneSided95": 0.99,
    "minimumWilsonLowerOneSided95": 0.99,
    "requireStructuralReplay": True,
}
STUDENT_T_ONE_SIDED_95_DF31 = 1.6955187825458675
WILSON_Z_ONE_SIDED_95 = 1.6448536269514715
EXPECTED_ENVIRONMENT = {
    "device": "mps",
    "hfHome": "/Users/ivan/.cache/corelm-huggingface",
    "machine": "arm64",
    "numpy": "2.5.1",
    "platform": "macOS-26.3-arm64-arm-64bit",
    "pyarrow": "23.0.1",
    "python": "3.12.13",
    "seed": 20260729,
    "torch": "2.13.0",
    "transformers": "5.14.1",
}
TOP_LEVEL_KEYS = {
    "aggregates",
    "baselines",
    "createdAt",
    "environment",
    "protocol",
    "records",
    "resultSHA256",
    "schemaVersion",
    "selected",
    "selectedTokenIdsSHA256",
    "selectionError",
    "status",
    "testDataOpened",
}
PROTOCOL_KEYS = {
    "datasetRepository",
    "datasetRevision",
    "evaluatedCandidateIndices",
    "evaluatedGrid",
    "fullDevelopmentGrid",
    "modelRepository",
    "modelRevision",
    "modelWeightsSHA256",
    "split",
    "thresholds",
    "validationBlocks",
    "validationStartBlock",
}
ENVIRONMENT_KEYS = {
    "device",
    "hfHome",
    "machine",
    "numpy",
    "platform",
    "pyarrow",
    "python",
    "seed",
    "torch",
    "transformers",
}
LEGACY_RECORD_KEYS = {
    "baselineNLLNatPerToken",
    "blockIndex",
    "cacheCandidateSumSquares",
    "cacheDifferenceSumSquares",
    "cacheDotProduct",
    "cacheMaximumAbsoluteError",
    "cacheReferenceSumSquares",
    "candidateNLLNatPerToken",
    "canonicalCacheBF16SHA256",
    "configurationId",
    "decodeNanoseconds",
    "deltaNLLNatPerToken",
    "denseBF16Bytes",
    "encodeNanoseconds",
    "encodedFileBytes",
    "meanKLDivergenceNat",
    "modelContinuationNanoseconds",
    "payloadBytes",
    "payloadSHA256",
    "perplexityRatio",
    "predictionTokens",
    "tokenIdsSHA256",
    "top1Agreement",
    "top1AgreementCount",
}
RECORD_KEYS = LEGACY_RECORD_KEYS | {
    "containerManifest",
    "containerManifestSHA256",
}
BASELINE_KEYS = {
    "baselineContinuationNanoseconds",
    "blockIndex",
    "canonicalBF16NLLNatPerToken",
    "canonicalCacheBF16SHA256",
    "denseBF16Bytes",
    "exactRebuildMaxAbsLogitDifference",
    "exactRebuildTop1Identical",
    "headDimension",
    "kvHeads",
    "layers",
    "layoutRebuildMaxAbsLogitDifference",
    "layoutRebuildTop1Identical",
    "nativeBF16DeltaNLLNatPerToken",
    "nativeBF16Top1Agreement",
    "originalContinuationNanoseconds",
    "originalFP32NLLNatPerToken",
    "originalRebuildContinuationNanoseconds",
    "predictionTokens",
    "tokenIdsSHA256",
    "trajectoryShapePerLayer",
}
AGGREGATE_KEYS = {
    "allPayloadDigestsUnique",
    "baselineNLLNatPerToken",
    "blocks",
    "cacheCosineSimilarity",
    "cacheMaximumAbsoluteError",
    "cacheNormalizedRMSE",
    "candidateNLLNatPerToken",
    "compressionRatioVsBF16",
    "configuration",
    "configurationId",
    "decodeNanoseconds",
    "deltaNLLNatPerToken",
    "denseBF16Bytes",
    "encodeNanoseconds",
    "encodedFileBytes",
    "gates",
    "meanKLDivergenceNat",
    "modelContinuationNanoseconds",
    "pass",
    "perplexityRatio",
    "predictionTokens",
    "top1Agreement",
}
MANIFEST_KEYS = {
    "artifacts",
    "candidateIndex",
    "combinedObservation",
    "configurationSHA256",
    "manifestSHA256",
    "schemaVersion",
    "status",
    "suiteId",
    "testDataOpened",
}


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key is forbidden: {key}")
        result[key] = value
    return result


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_json,
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    _require_finite_numbers(value, path.name)
    return value


def _require_finite_numbers(value: Any, label: str) -> None:
    if type(value) is float and not math.isfinite(value):
        raise ValueError(f"{label} contains a non-finite number")
    if isinstance(value, dict):
        for child in value.values():
            _require_finite_numbers(child, label)
    elif isinstance(value, list):
        for child in value:
            _require_finite_numbers(child, label)


def independent_canonical_json_bytes(value: Any) -> bytes:
    """Canonical JSON used only by this verifier, not the benchmark writer."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _close(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(
            float(left), float(right), rel_tol=1e-12, abs_tol=1e-12
        )
    return left == right


def _less_than_or_close(left: float, right: float) -> bool:
    tolerance = max(
        1e-12,
        1e-12 * max(abs(left), abs(right)),
    )
    return left <= right + tolerance


def _compare_mapping(
    observed: Any,
    expected: dict[str, Any],
    label: str,
) -> list[str]:
    if not isinstance(observed, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    if set(observed) != set(expected):
        errors.append(f"{label} fields are not exact")
    for key, value in expected.items():
        if key not in observed or not _close(observed[key], value):
            errors.append(f"{label}.{key} is inconsistent")
    return errors


def _is_lower_hex_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_digest_without(
    value: dict[str, Any], field: str
) -> str:
    digest_input = dict(value)
    digest_input.pop(field, None)
    return _sha256_bytes(independent_canonical_json_bytes(digest_input))


def _safe_artifact_path(relative: Any) -> Path:
    if (
        not isinstance(relative, str)
        or not relative
        or relative.startswith("/")
        or "\\" in relative
    ):
        raise ValueError("development artifact path is not a safe relative path")
    parts = Path(relative).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("development artifact path contains unsafe components")
    path = PROJECT_ROOT.joinpath(*parts)
    try:
        path.resolve(strict=True).relative_to(PROJECT_ROOT.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise ValueError(
            f"development artifact escapes or is missing: {relative}"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            f"development artifact must be a regular non-symlink file: {relative}"
        )
    return path


def _strict_real(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if type(value) not in {int, float} or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be a finite JSON number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"{label} is below its valid range")
    if maximum is not None and result > maximum:
        raise ValueError(f"{label} is above its valid range")
    return result


def _strict_int(
    value: Any,
    label: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be a JSON integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} is below its valid range")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} is above its valid range")
    return value


def _weighted_average(
    records: list[dict[str, Any]], key: str
) -> float:
    numerator = 0.0
    denominator = 0
    for index, record in enumerate(records):
        tokens = _strict_int(
            record.get("predictionTokens"),
            f"record {index} predictionTokens",
            minimum=1,
        )
        value = _strict_real(record.get(key), f"record {index} {key}")
        numerator += value * tokens
        denominator += tokens
    if denominator <= 0:
        raise ValueError("cannot aggregate zero prediction tokens")
    return numerator / denominator


def independent_aggregate_candidate_records(
    configuration: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Recompute an aggregate without calling the benchmark implementation."""
    if not isinstance(records, list) or not records:
        raise ValueError("candidate aggregation requires records")
    if any(not isinstance(record, dict) for record in records):
        raise ValueError("candidate records must be JSON objects")
    dense_bf16_bytes = sum(
        _strict_int(
            record.get("denseBF16Bytes"),
            f"record {index} denseBF16Bytes",
            minimum=1,
        )
        for index, record in enumerate(records)
    )
    encoded_bytes = sum(
        _strict_int(
            record.get("encodedFileBytes"),
            f"record {index} encodedFileBytes",
            minimum=1,
        )
        for index, record in enumerate(records)
    )
    tokens = sum(
        _strict_int(
            record.get("predictionTokens"),
            f"record {index} predictionTokens",
            minimum=1,
        )
        for index, record in enumerate(records)
    )
    agreements = sum(
        _strict_int(
            record.get("top1AgreementCount"),
            f"record {index} top1AgreementCount",
            minimum=0,
            maximum=_strict_int(
                record.get("predictionTokens"),
                f"record {index} predictionTokens",
                minimum=1,
            ),
        )
        for index, record in enumerate(records)
    )
    difference_sum_squares = sum(
        _strict_real(
            record.get("cacheDifferenceSumSquares"),
            f"record {index} cacheDifferenceSumSquares",
            minimum=0.0,
        )
        for index, record in enumerate(records)
    )
    reference_sum_squares = sum(
        _strict_real(
            record.get("cacheReferenceSumSquares"),
            f"record {index} cacheReferenceSumSquares",
            minimum=0.0,
        )
        for index, record in enumerate(records)
    )
    candidate_sum_squares = sum(
        _strict_real(
            record.get("cacheCandidateSumSquares"),
            f"record {index} cacheCandidateSumSquares",
            minimum=0.0,
        )
        for index, record in enumerate(records)
    )
    dot_product = sum(
        _strict_real(
            record.get("cacheDotProduct"),
            f"record {index} cacheDotProduct",
        )
        for index, record in enumerate(records)
    )
    baseline_nll = _weighted_average(records, "baselineNLLNatPerToken")
    candidate_nll = _weighted_average(records, "candidateNLLNatPerToken")
    mean_kl = _weighted_average(records, "meanKLDivergenceNat")
    if baseline_nll < 0.0 or candidate_nll < 0.0 or mean_kl < 0.0:
        raise ValueError("NLL and KL aggregates must be non-negative")
    delta_nll = candidate_nll - baseline_nll
    cache_cosine = dot_product / max(
        math.sqrt(reference_sum_squares * candidate_sum_squares),
        1e-30,
    )
    if not -1.0 <= cache_cosine <= 1.0:
        raise ValueError("aggregate cache cosine is outside [-1, 1]")
    result: dict[str, Any] = {
        "configuration": configuration,
        "configurationId": _sha256_bytes(
            independent_canonical_json_bytes(configuration)
        )[:16],
        "blocks": len(records),
        "predictionTokens": tokens,
        "denseBF16Bytes": dense_bf16_bytes,
        "encodedFileBytes": encoded_bytes,
        "compressionRatioVsBF16": dense_bf16_bytes / encoded_bytes,
        "baselineNLLNatPerToken": baseline_nll,
        "candidateNLLNatPerToken": candidate_nll,
        "deltaNLLNatPerToken": delta_nll,
        "perplexityRatio": math.exp(delta_nll),
        "top1Agreement": agreements / tokens,
        "meanKLDivergenceNat": mean_kl,
        "cacheNormalizedRMSE": math.sqrt(
            difference_sum_squares / max(reference_sum_squares, 1e-30)
        ),
        "cacheCosineSimilarity": cache_cosine,
        "cacheMaximumAbsoluteError": max(
            _strict_real(
                record.get("cacheMaximumAbsoluteError"),
                f"record {index} cacheMaximumAbsoluteError",
                minimum=0.0,
            )
            for index, record in enumerate(records)
        ),
        "encodeNanoseconds": sum(
            _strict_int(
                record.get("encodeNanoseconds"),
                f"record {index} encodeNanoseconds",
                minimum=0,
            )
            for index, record in enumerate(records)
        ),
        "decodeNanoseconds": sum(
            _strict_int(
                record.get("decodeNanoseconds"),
                f"record {index} decodeNanoseconds",
                minimum=0,
            )
            for index, record in enumerate(records)
        ),
        "modelContinuationNanoseconds": sum(
            _strict_int(
                record.get("modelContinuationNanoseconds"),
                f"record {index} modelContinuationNanoseconds",
                minimum=0,
            )
            for index, record in enumerate(records)
        ),
        "allPayloadDigestsUnique": len(
            {record.get("payloadSHA256") for record in records}
        )
        == len(records),
        "pass": False,
    }
    result["gates"] = {
        "compression": (
            result["compressionRatioVsBF16"]
            >= DEVELOPMENT_THRESHOLDS["minimumCompressionRatioVsBF16"]
        ),
        "deltaNLL": (
            result["deltaNLLNatPerToken"]
            <= DEVELOPMENT_THRESHOLDS["maximumDeltaNLLNatPerToken"]
        ),
        "top1Agreement": (
            result["top1Agreement"]
            >= DEVELOPMENT_THRESHOLDS["minimumTop1Agreement"]
        ),
    }
    result["pass"] = all(result["gates"].values())
    return result


def _independent_wilson_lower(successes: int, trials: int) -> float:
    if trials <= 0 or successes < 0 or successes > trials:
        raise ValueError("invalid Bernoulli counts")
    probability = successes / trials
    z = WILSON_Z_ONE_SIDED_95
    denominator = 1.0 + z * z / trials
    center = probability + z * z / (2.0 * trials)
    radius = z * math.sqrt(
        probability * (1.0 - probability) / trials
        + z * z / (4.0 * trials * trials)
    )
    return (center - radius) / denominator


def independent_confidence_and_verdict(
    records: list[dict[str, Any]],
    baselines: list[dict[str, Any]],
    aggregate: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, bool], bool]:
    """Recompute frozen confidence gates without calling the phase runner."""
    if len(records) != 32 or len(baselines) != 32:
        raise ValueError("a frozen phase requires 32 record pairs")
    if any(not isinstance(item, dict) for item in (*records, *baselines)):
        raise ValueError("frozen records and baselines must be objects")
    delta_values = [
        _strict_real(
            record.get("deltaNLLNatPerToken"),
            f"record {index} deltaNLLNatPerToken",
        )
        for index, record in enumerate(records)
    ]
    delta_mean = statistics.fmean(delta_values)
    delta_standard_deviation = statistics.stdev(delta_values)
    delta_upper = delta_mean + (
        STUDENT_T_ONE_SIDED_95_DF31
        * delta_standard_deviation
        / math.sqrt(32)
    )
    prediction_tokens = sum(
        _strict_int(
            record.get("predictionTokens"),
            f"record {index} predictionTokens",
            minimum=1,
        )
        for index, record in enumerate(records)
    )
    agreement_count = sum(
        _strict_int(
            record.get("top1AgreementCount"),
            f"record {index} top1AgreementCount",
            minimum=0,
            maximum=_strict_int(
                record.get("predictionTokens"),
                f"record {index} predictionTokens",
                minimum=1,
            ),
        )
        for index, record in enumerate(records)
    )
    block_top1_values = [
        _strict_int(
            record.get("top1AgreementCount"),
            f"record {index} top1AgreementCount",
            minimum=0,
        )
        / _strict_int(
            record.get("predictionTokens"),
            f"record {index} predictionTokens",
            minimum=1,
        )
        for index, record in enumerate(records)
    ]
    block_top1_mean = statistics.fmean(block_top1_values)
    block_top1_standard_deviation = statistics.stdev(block_top1_values)
    block_top1_lower = block_top1_mean - (
        STUDENT_T_ONE_SIDED_95_DF31
        * block_top1_standard_deviation
        / math.sqrt(32)
    )
    confidence = {
        "blockDeltaNLLMean": delta_mean,
        "blockDeltaNLLSampleStandardDeviation": delta_standard_deviation,
        "blockwiseDeltaNLLUpperOneSided95": delta_upper,
        "blockTop1Mean": block_top1_mean,
        "blockTop1SampleStandardDeviation": block_top1_standard_deviation,
        "blockwiseTop1LowerOneSided95": block_top1_lower,
        "predictionTokens": prediction_tokens,
        "top1AgreementCount": agreement_count,
        "wilsonLowerOneSided95": _independent_wilson_lower(
            agreement_count, prediction_tokens
        ),
    }
    structural_replay = all(
        baseline.get("exactRebuildMaxAbsLogitDifference") == 0.0
        and baseline.get("exactRebuildTop1Identical") is True
        and baseline.get("layoutRebuildMaxAbsLogitDifference") == 0.0
        and baseline.get("layoutRebuildTop1Identical") is True
        for baseline in baselines
    )
    gates = {
        "compressionRatioVsBF16": (
            _strict_real(
                aggregate.get("compressionRatioVsBF16"),
                "aggregate compressionRatioVsBF16",
                minimum=0.0,
            )
            >= PROSPECTIVE_GATES["minimumCompressionRatioVsBF16"]
        ),
        "deltaNLLNatPerToken": (
            _strict_real(
                aggregate.get("deltaNLLNatPerToken"),
                "aggregate deltaNLLNatPerToken",
            )
            <= PROSPECTIVE_GATES["maximumDeltaNLLNatPerToken"]
        ),
        "blockwiseDeltaNLLUpperOneSided95": (
            delta_upper
            <= PROSPECTIVE_GATES[
                "maximumBlockwiseDeltaNLLUpperOneSided95"
            ]
        ),
        "top1Agreement": (
            _strict_real(
                aggregate.get("top1Agreement"),
                "aggregate top1Agreement",
                minimum=0.0,
                maximum=1.0,
            )
            >= PROSPECTIVE_GATES["minimumTop1Agreement"]
        ),
        "blockwiseTop1LowerOneSided95": (
            block_top1_lower
            >= PROSPECTIVE_GATES["minimumBlockwiseTop1LowerOneSided95"]
        ),
        "wilsonLowerOneSided95": (
            confidence["wilsonLowerOneSided95"]
            >= PROSPECTIVE_GATES["minimumWilsonLowerOneSided95"]
        ),
        "structuralReplay": structural_replay,
    }
    return confidence, gates, all(gates.values())


def _verify_record_pair(
    record: Any,
    baseline: Any,
    block_index: int,
    *,
    require_container_manifest: bool,
) -> list[str]:
    label = f"block {block_index}"
    errors: list[str] = []
    expected_record_keys = (
        RECORD_KEYS if require_container_manifest else LEGACY_RECORD_KEYS
    )
    if not isinstance(record, dict) or set(record) != expected_record_keys:
        return [f"{label} candidate record fields are not exact"]
    if not isinstance(baseline, dict) or set(baseline) != BASELINE_KEYS:
        return [f"{label} baseline record fields are not exact"]
    if (
        type(record.get("blockIndex")) is not int
        or record.get("blockIndex") != block_index
    ):
        errors.append(f"{label} candidate index is inconsistent")
    if (
        type(baseline.get("blockIndex")) is not int
        or baseline.get("blockIndex") != block_index
    ):
        errors.append(f"{label} baseline index is inconsistent")
    if (
        record.get("configurationId") != CONFIGURATION_ID
        or type(record.get("predictionTokens")) is not int
        or record.get("predictionTokens") != 128
        or type(baseline.get("predictionTokens")) is not int
        or baseline.get("predictionTokens") != 128
        or type(record.get("denseBF16Bytes")) is not int
        or record.get("denseBF16Bytes") != 4_706_304
        or type(baseline.get("denseBF16Bytes")) is not int
        or baseline.get("denseBF16Bytes") != 4_706_304
    ):
        errors.append(f"{label} fixed shape/size fields are inconsistent")
    if (
        type(baseline.get("layers")) is not int
        or baseline.get("layers") != 24
        or type(baseline.get("kvHeads")) is not int
        or baseline.get("kvHeads") != 2
        or type(baseline.get("headDimension")) is not int
        or baseline.get("headDimension") != 64
        or baseline.get("trajectoryShapePerLayer") != [383, 256]
        or any(
            type(value) is not int
            for value in baseline.get("trajectoryShapePerLayer", [])
        )
    ):
        errors.append(f"{label} baseline trajectory shape is inconsistent")
    try:
        trajectory_shape = baseline["trajectoryShapePerLayer"]
        scalar_count = (
            _strict_int(baseline["layers"], f"{label} baseline layers", minimum=1)
            * _strict_int(
                trajectory_shape[0],
                f"{label} baseline trajectory rows",
                minimum=1,
            )
            * _strict_int(
                trajectory_shape[1],
                f"{label} baseline trajectory columns",
                minimum=1,
            )
        )
        expected_dense_bytes = scalar_count * 2
        if (
            baseline.get("denseBF16Bytes") != expected_dense_bytes
            or record.get("denseBF16Bytes") != expected_dense_bytes
        ):
            errors.append(f"{label} cache scalar count is inconsistent")
    except (IndexError, KeyError, TypeError, ValueError):
        scalar_count = 0
        errors.append(f"{label} cache scalar count is invalid")
    if (
        baseline.get("exactRebuildMaxAbsLogitDifference") != 0.0
        or baseline.get("exactRebuildTop1Identical") is not True
        or baseline.get("layoutRebuildMaxAbsLogitDifference") != 0.0
        or baseline.get("layoutRebuildTop1Identical") is not True
    ):
        errors.append(f"{label} structural replay is not exact")
    for field in (
        "tokenIdsSHA256",
        "canonicalCacheBF16SHA256",
        "payloadSHA256",
    ):
        if not _is_lower_hex_sha256(record.get(field)):
            errors.append(f"{label} {field} is not a lowercase SHA-256")
    for field in ("tokenIdsSHA256", "canonicalCacheBF16SHA256"):
        if not _is_lower_hex_sha256(baseline.get(field)):
            errors.append(
                f"{label} baseline {field} is not a lowercase SHA-256"
            )
    if record.get("tokenIdsSHA256") != baseline.get("tokenIdsSHA256"):
        errors.append(f"{label} candidate/baseline token digests differ")
    if record.get("canonicalCacheBF16SHA256") != baseline.get(
        "canonicalCacheBF16SHA256"
    ):
        errors.append(f"{label} candidate/baseline cache digests differ")
    agreement = record.get("top1AgreementCount")
    if (
        type(agreement) is not int
        or not 0 <= agreement <= 128
        or not _close(record.get("top1Agreement"), agreement / 128)
    ):
        errors.append(f"{label} top-1 fields are inconsistent")
    for field in (
        "payloadBytes",
        "encodedFileBytes",
        "encodeNanoseconds",
        "decodeNanoseconds",
        "modelContinuationNanoseconds",
    ):
        if type(record.get(field)) is not int or record[field] < 0:
            errors.append(f"{label} {field} is not a non-negative integer")
    record_real_ranges = {
        "baselineNLLNatPerToken": (0.0, None),
        "candidateNLLNatPerToken": (0.0, None),
        "deltaNLLNatPerToken": (None, None),
        "perplexityRatio": (0.0, None),
        "meanKLDivergenceNat": (0.0, None),
        "top1Agreement": (0.0, 1.0),
        "cacheCandidateSumSquares": (0.0, None),
        "cacheDifferenceSumSquares": (0.0, None),
        "cacheDotProduct": (None, None),
        "cacheMaximumAbsoluteError": (0.0, None),
        "cacheReferenceSumSquares": (0.0, None),
    }
    for field, (minimum, maximum) in record_real_ranges.items():
        try:
            _strict_real(
                record.get(field),
                f"{label} {field}",
                minimum=minimum,
                maximum=maximum,
            )
        except ValueError as error:
            errors.append(str(error))
    if (
        type(record.get("payloadBytes")) is int
        and type(record.get("encodedFileBytes")) is int
        and (
            record["payloadBytes"] <= 0
            or record["encodedFileBytes"]
            < record["payloadBytes"] + (24 * 8)
        )
    ):
        errors.append(f"{label} container byte accounting is inconsistent")
    if require_container_manifest:
        try:
            validate_v5_container_manifest(record, FROZEN_CONFIGURATION)
        except (IndexError, KeyError, TypeError, ValueError) as error:
            errors.append(
                f"{label} container manifest is inconsistent: {error}"
            )
    for field in (
        "baselineContinuationNanoseconds",
        "originalContinuationNanoseconds",
        "originalRebuildContinuationNanoseconds",
    ):
        if type(baseline.get(field)) is not int or baseline[field] < 0:
            errors.append(f"{label} {field} is not a non-negative integer")
    baseline_real_ranges = {
        "canonicalBF16NLLNatPerToken": (0.0, None),
        "originalFP32NLLNatPerToken": (0.0, None),
        "nativeBF16DeltaNLLNatPerToken": (None, None),
        "nativeBF16Top1Agreement": (0.0, 1.0),
        "exactRebuildMaxAbsLogitDifference": (0.0, None),
        "layoutRebuildMaxAbsLogitDifference": (0.0, None),
    }
    for field, (minimum, maximum) in baseline_real_ranges.items():
        try:
            _strict_real(
                baseline.get(field),
                f"{label} baseline {field}",
                minimum=minimum,
                maximum=maximum,
            )
        except ValueError as error:
            errors.append(str(error))
    try:
        native_agreement = _strict_real(
            baseline["nativeBF16Top1Agreement"],
            f"{label} baseline nativeBF16Top1Agreement",
            minimum=0.0,
            maximum=1.0,
        )
        native_agreement_count = native_agreement * 128.0
        if not _close(native_agreement_count, round(native_agreement_count)):
            errors.append(
                f"{label} native BF16 top-1 agreement is not k/128"
            )
    except (KeyError, TypeError, ValueError, OverflowError):
        errors.append(f"{label} native BF16 top-1 agreement is invalid")
    try:
        delta = _strict_real(
            record["candidateNLLNatPerToken"],
            f"{label} candidateNLLNatPerToken",
            minimum=0.0,
        ) - _strict_real(
            record["baselineNLLNatPerToken"],
            f"{label} baselineNLLNatPerToken",
            minimum=0.0,
        )
        if not _close(record.get("deltaNLLNatPerToken"), delta):
            errors.append(f"{label} delta NLL is inconsistent")
        if not _close(record.get("perplexityRatio"), math.exp(delta)):
            errors.append(f"{label} perplexity ratio is inconsistent")
        native_delta = _strict_real(
            baseline["canonicalBF16NLLNatPerToken"],
            f"{label} canonicalBF16NLLNatPerToken",
            minimum=0.0,
        ) - _strict_real(
            baseline["originalFP32NLLNatPerToken"],
            f"{label} originalFP32NLLNatPerToken",
            minimum=0.0,
        )
        if not _close(
            baseline.get("nativeBF16DeltaNLLNatPerToken"), native_delta
        ):
            errors.append(f"{label} native BF16 delta is inconsistent")
        if not _close(
            record.get("baselineNLLNatPerToken"),
            baseline.get("canonicalBF16NLLNatPerToken"),
        ):
            errors.append(f"{label} candidate/baseline NLL values differ")
    except (KeyError, TypeError, ValueError, OverflowError):
        errors.append(f"{label} NLL fields are invalid")
    try:
        reference_sum_squares = _strict_real(
            record["cacheReferenceSumSquares"],
            f"{label} cacheReferenceSumSquares",
            minimum=0.0,
        )
        candidate_sum_squares = _strict_real(
            record["cacheCandidateSumSquares"],
            f"{label} cacheCandidateSumSquares",
            minimum=0.0,
        )
        dot_product = _strict_real(
            record["cacheDotProduct"],
            f"{label} cacheDotProduct",
        )
        difference_sum_squares = _strict_real(
            record["cacheDifferenceSumSquares"],
            f"{label} cacheDifferenceSumSquares",
            minimum=0.0,
        )
        maximum_absolute_error = _strict_real(
            record["cacheMaximumAbsoluteError"],
            f"{label} cacheMaximumAbsoluteError",
            minimum=0.0,
        )
        cache_identity = (
            reference_sum_squares
            + candidate_sum_squares
            - (2.0 * dot_product)
        )
        if not math.isfinite(cache_identity) or not math.isclose(
            difference_sum_squares,
            cache_identity,
            rel_tol=1e-9,
            abs_tol=1e-6,
        ):
            errors.append(f"{label} cache accumulators are inconsistent")
        norm_product = math.sqrt(reference_sum_squares) * math.sqrt(
            candidate_sum_squares
        )
        if not _less_than_or_close(abs(dot_product), norm_product):
            errors.append(f"{label} cache Cauchy-Schwarz bound is violated")
        maximum_error_squared = maximum_absolute_error**2
        maximum_error_sum_bound = scalar_count * maximum_error_squared
        if (
            scalar_count <= 0
            or not math.isfinite(maximum_error_squared)
            or not math.isfinite(maximum_error_sum_bound)
            or not _less_than_or_close(
                maximum_error_squared,
                difference_sum_squares,
            )
            or not _less_than_or_close(
                difference_sum_squares,
                maximum_error_sum_bound,
            )
        ):
            errors.append(f"{label} cache maximum-error bounds are violated")
    except (KeyError, TypeError, ValueError, OverflowError):
        errors.append(f"{label} cache accumulators are invalid")
    return errors


def _verify_shard(
    shard: dict[str, Any],
    artifact: dict[str, Any],
    *,
    portable_macos_environment: bool = False,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    label = Path(artifact["path"]).name
    errors: list[str] = []
    expected_top_level_keys = set(TOP_LEVEL_KEYS)
    if shard.get("schemaVersion") == (
        "corelm-voidtoken-v5-validation-development-v3"
    ):
        expected_top_level_keys.add("primaryEvidence")
    if set(shard) != expected_top_level_keys:
        errors.append(f"{label} top-level fields are not exact")
    if shard.get("schemaVersion") not in {
        "corelm-voidtoken-v5-validation-development-v1",
        "corelm-voidtoken-v5-validation-development-v2",
        "corelm-voidtoken-v5-validation-development-v3",
    }:
        errors.append(f"{label} schema version is inconsistent")
    if shard.get("status") != "validation-only-development":
        errors.append(f"{label} status is inconsistent")
    if shard.get("testDataOpened") is not False:
        errors.append(f"{label} claims or permits test-data access")
    if shard.get("selectionError") is not None:
        errors.append(f"{label} recorded a configuration-selection error")
    if shard.get("selected") != FROZEN_CONFIGURATION:
        errors.append(f"{label} selected configuration is not frozen")
    if not _is_lower_hex_sha256(shard.get("selectedTokenIdsSHA256")):
        errors.append(f"{label} selected token digest is invalid")
    try:
        created_at = datetime.fromisoformat(str(shard["createdAt"]))
        if created_at.tzinfo is None:
            raise ValueError("timestamp has no timezone")
    except (KeyError, TypeError, ValueError):
        errors.append(f"{label} createdAt is invalid")

    protocol = shard.get("protocol")
    if not isinstance(protocol, dict) or set(protocol) != PROTOCOL_KEYS:
        errors.append(f"{label} protocol fields are not exact")
        protocol = {}
    expected_protocol = {
        "modelRepository": MODEL_REPOSITORY,
        "modelRevision": MODEL_REVISION,
        "modelWeightsSHA256": MODEL_WEIGHTS_SHA256,
        "datasetRepository": DATASET_REPOSITORY,
        "datasetRevision": DATASET_REVISION,
        "split": "validation",
        "validationStartBlock": artifact["startBlock"],
        "validationBlocks": artifact["blocks"],
        "thresholds": DEVELOPMENT_THRESHOLDS,
        "evaluatedCandidateIndices": [32],
        "evaluatedGrid": [FROZEN_CONFIGURATION],
    }
    for key, value in expected_protocol.items():
        if protocol.get(key) != value:
            errors.append(f"{label} protocol.{key} is inconsistent")
    full_grid = protocol.get("fullDevelopmentGrid")
    try:
        if (
            not isinstance(full_grid, list)
            or len(full_grid) <= 32
            or full_grid[32] != FROZEN_CONFIGURATION
            or _sha256_bytes(independent_canonical_json_bytes(full_grid))
            != FULL_DEVELOPMENT_GRID_SHA256
        ):
            errors.append(f"{label} full development grid is inconsistent")
    except (TypeError, ValueError):
        errors.append(f"{label} full development grid is not canonical JSON")

    environment = shard.get("environment")
    if not isinstance(environment, dict) or set(environment) != ENVIRONMENT_KEYS:
        errors.append(f"{label} environment fields are not exact")
    else:
        if portable_macos_environment:
            python_components = str(environment.get("python", "")).split(".")
            portable_environment = (
                environment.get("device") == "mps"
                and environment.get("hfHome") == "configured"
                and environment.get("machine") == "arm64"
                and environment.get("numpy") == EXPECTED_ENVIRONMENT["numpy"]
                and environment.get("pyarrow") == EXPECTED_ENVIRONMENT["pyarrow"]
                and environment.get("torch") == EXPECTED_ENVIRONMENT["torch"]
                and environment.get("transformers")
                == EXPECTED_ENVIRONMENT["transformers"]
                and environment.get("seed") == EXPECTED_ENVIRONMENT["seed"]
                and len(python_components) == 3
                and python_components[:2] == ["3", "12"]
                and python_components[2].isdigit()
                and str(environment.get("platform", "")).startswith("macOS-")
                and "arm64" in str(environment.get("platform", ""))
            )
            if not portable_environment:
                errors.append(
                    f"{label} portable macOS environment is inconsistent"
                )
        else:
            expected_environment = dict(EXPECTED_ENVIRONMENT)
            if shard.get("schemaVersion") in {
                "corelm-voidtoken-v5-validation-development-v2",
                "corelm-voidtoken-v5-validation-development-v3",
            }:
                expected_environment["hfHome"] = "configured"
            if environment != expected_environment:
                errors.append(
                    f"{label} development environment is inconsistent"
                )

    records = shard.get("records")
    baselines = shard.get("baselines")
    if not isinstance(records, list) or not isinstance(baselines, list):
        return errors + [f"{label} records/baselines are missing"], [], []
    expected_indices = list(
        range(
            artifact["startBlock"],
            artifact["startBlock"] + artifact["blocks"],
        )
    )
    if len(records) != 8 or len(baselines) != 8:
        errors.append(f"{label} must contain exactly eight record pairs")
    for relative_index, block_index in enumerate(expected_indices):
        if relative_index >= len(records) or relative_index >= len(baselines):
            break
        errors.extend(
            _verify_record_pair(
                records[relative_index],
                baselines[relative_index],
                block_index,
                require_container_manifest=(
                    shard.get("schemaVersion")
                    in {
                        "corelm-voidtoken-v5-validation-development-v2",
                        "corelm-voidtoken-v5-validation-development-v3",
                    }
                ),
            )
        )

    aggregates = shard.get("aggregates")
    if not isinstance(aggregates, list) or len(aggregates) != 1:
        errors.append(f"{label} must contain exactly one aggregate")
    else:
        observed = aggregates[0]
        if not isinstance(observed, dict) or set(observed) != AGGREGATE_KEYS:
            errors.append(f"{label} aggregate fields are not exact")
        try:
            recomputed = independent_aggregate_candidate_records(
                FROZEN_CONFIGURATION, records
            )
            errors.extend(
                _compare_mapping(observed, recomputed, f"{label} aggregate")
            )
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            errors.append(f"{label} aggregate cannot be recomputed: {error}")

    recorded_result_digest = shard.get("resultSHA256")
    try:
        recomputed_result_digest = _canonical_digest_without(
            shard, "resultSHA256"
        )
    except (TypeError, ValueError) as error:
        errors.append(f"{label} result cannot be canonicalized: {error}")
    else:
        if (
            recorded_result_digest != recomputed_result_digest
            or recorded_result_digest != artifact["resultSHA256"]
        ):
            errors.append(f"{label} result SHA-256 is inconsistent")
    return errors, records, baselines


def verify_development_evidence(
) -> tuple[list[str], dict[str, Any] | None]:
    errors: list[str] = []
    try:
        validate_frozen_registration()
    except ValueError as error:
        return [str(error)], None
    try:
        manifest = _load_json_object(MANIFEST_PATH)
    except ValueError as error:
        return [str(error)], None
    if set(manifest) != MANIFEST_KEYS:
        errors.append("development manifest fields are not exact")
    expected_manifest_fields = {
        "schemaVersion": "corelm-voidtoken-v5-development-manifest-v1",
        "suiteId": SUITE_ID,
        "status": "adaptive-development-not-prospective-evidence",
        "configurationSHA256": FROZEN_CONFIGURATION_SHA256,
        "candidateIndex": 32,
        "testDataOpened": False,
        "artifacts": DEVELOPMENT_ARTIFACTS,
    }
    for key, value in expected_manifest_fields.items():
        if manifest.get(key) != value:
            errors.append(f"development manifest {key} is inconsistent")
    if MANIFEST_PATH.stat().st_size != DEVELOPMENT_MANIFEST["sizeBytes"]:
        errors.append("development manifest byte size is inconsistent")
    if _sha256_file(MANIFEST_PATH) != DEVELOPMENT_MANIFEST["fileSHA256"]:
        errors.append("development manifest file SHA-256 is inconsistent")
    try:
        manifest_digest = _canonical_digest_without(
            manifest, "manifestSHA256"
        )
    except (TypeError, ValueError) as error:
        errors.append(f"development manifest is not canonicalizable: {error}")
    else:
        if (
            manifest.get("manifestSHA256") != manifest_digest
            or manifest_digest != DEVELOPMENT_MANIFEST["manifestSHA256"]
        ):
            errors.append("development manifest canonical SHA-256 is inconsistent")

    all_records: list[Any] = []
    all_baselines: list[Any] = []
    environments: list[Any] = []
    selected_token_digests: list[Any] = []
    for artifact in DEVELOPMENT_ARTIFACTS:
        try:
            path = _safe_artifact_path(artifact["path"])
        except ValueError as error:
            errors.append(str(error))
            continue
        if path.stat().st_size != artifact["sizeBytes"]:
            errors.append(f"{artifact['path']} byte size is inconsistent")
        if _sha256_file(path) != artifact["fileSHA256"]:
            errors.append(f"{artifact['path']} file SHA-256 is inconsistent")
        try:
            shard = _load_json_object(path)
        except ValueError as error:
            errors.append(str(error))
            continue
        shard_errors, records, baselines = _verify_shard(shard, artifact)
        errors.extend(shard_errors)
        all_records.extend(records)
        all_baselines.extend(baselines)
        environments.append(shard.get("environment"))
        selected_token_digests.append(shard.get("selectedTokenIdsSHA256"))

    records_are_objects = all(
        isinstance(record, dict) for record in all_records
    )
    baselines_are_objects = all(
        isinstance(baseline, dict) for baseline in all_baselines
    )
    if (
        len(all_records) != 32
        or not records_are_objects
        or [record.get("blockIndex") for record in all_records]
        != list(range(32))
    ):
        errors.append("development records do not cover blocks 0-31 exactly")
    if (
        len(all_baselines) != 32
        or not baselines_are_objects
        or [baseline.get("blockIndex") for baseline in all_baselines]
        != list(range(32))
    ):
        errors.append("development baselines do not cover blocks 0-31 exactly")
    if environments and any(
        environment != environments[0] for environment in environments[1:]
    ):
        errors.append("development shard environments are inconsistent")
    if (
        not all(
            isinstance(value, str) for value in selected_token_digests
        )
        or len(set(selected_token_digests)) != len(selected_token_digests)
    ):
        errors.append("development shard token-set digests are not unique")
    if records_are_objects:
        for field in (
            "tokenIdsSHA256",
            "canonicalCacheBF16SHA256",
            "payloadSHA256",
        ):
            values = [record.get(field) for record in all_records]
            if (
                not all(isinstance(value, str) for value in values)
                or len(set(values)) != len(values)
            ):
                errors.append(
                    f"development record {field} values are not unique"
                )

    combined: dict[str, Any] | None = None
    if (
        len(all_records) == 32
        and len(all_baselines) == 32
        and records_are_objects
        and baselines_are_objects
    ):
        try:
            aggregate = independent_aggregate_candidate_records(
                FROZEN_CONFIGURATION, all_records
            )
            confidence, gates, passed = independent_confidence_and_verdict(
                all_records, all_baselines, aggregate
            )
            combined = {
                "blocks": aggregate["blocks"],
                "predictionTokens": aggregate["predictionTokens"],
                "denseBF16Bytes": aggregate["denseBF16Bytes"],
                "encodedFileBytes": aggregate["encodedFileBytes"],
                "compressionRatioVsBF16": (
                    aggregate["compressionRatioVsBF16"]
                ),
                "deltaNLLNatPerToken": aggregate["deltaNLLNatPerToken"],
                "blockwiseDeltaNLLUpperOneSided95": (
                    confidence["blockwiseDeltaNLLUpperOneSided95"]
                ),
                "top1AgreementCount": confidence["top1AgreementCount"],
                "top1Agreement": aggregate["top1Agreement"],
                "blockwiseTop1LowerOneSided95": (
                    confidence["blockwiseTop1LowerOneSided95"]
                ),
                "wilsonLowerOneSided95": (
                    confidence["wilsonLowerOneSided95"]
                ),
                "meanKLDivergenceNat": aggregate["meanKLDivergenceNat"],
            }
            errors.extend(
                _compare_mapping(
                    manifest.get("combinedObservation"),
                    combined,
                    "development manifest combined observation",
                )
            )
            errors.extend(
                _compare_mapping(
                    DEVELOPMENT_OBSERVATION,
                    combined,
                    "registered development observation",
                )
            )
            if not passed or not all(gates.values()):
                errors.append(
                    "recomputed development observation misses a frozen gate"
                )
        except (
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
        ) as error:
            errors.append(f"combined development metrics cannot be recomputed: {error}")
    return errors, combined


def main() -> int:
    errors, combined = verify_development_evidence()
    if errors:
        print(
            "VOIDTOKEN V5 DEVELOPMENT VERIFICATION FAILED "
            f"({len(errors)} problem(s)):"
        )
        for error in errors:
            print(f"- {error}")
        return 1
    assert combined is not None
    print(
        "VOIDTOKEN V5 DEVELOPMENT ARTIFACTS VERIFIED: "
        f"{combined['blocks']} validation blocks, "
        f"{combined['compressionRatioVsBF16']:.6f}x, "
        f"delta NLL {combined['deltaNLLNatPerToken']:+.9f}, "
        f"top-1 {combined['top1Agreement']:.6%}. "
        "This is adaptive development evidence, not a prospective verdict."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
