#!/usr/bin/env python3
"""Verify the structure, pins, aggregation, and digest of real-LLM evidence."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RealLLM.benchmark_real_llm import (  # noqa: E402
    DATASET_FILES,
    DATASET_REPOSITORY,
    DATASET_REVISION,
    GROUP_QUANT_GRID,
    MODEL_REPOSITORY,
    MODEL_REVISION,
    MODEL_WEIGHTS_SHA256,
    REGISTERED_TEST_START_BLOCK,
    SCHEMA_VERSION,
    THRESHOLDS,
    VOIDTOKEN_GRID,
    aggregate_candidate_records,
    canonical_json_bytes,
    configuration_id,
    select_validation_configuration,
    sha256_bytes,
    validate_registered_protocol,
)


DEFAULT_EVIDENCE = PROJECT_ROOT / "real-llm-results" / "aggregate.json"
RESULT_SCHEMA = PROJECT_ROOT / "schemas" / "real-llm-result.schema.json"
REGISTRATION = PROJECT_ROOT / "RealLLM" / "registration.json"
MAX_EVIDENCE_BYTES = 16 * 1024 * 1024


def _close(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(
            float(left), float(right), rel_tol=1e-12, abs_tol=1e-12
        )
    return left == right


def _cache_close(left: Any, right: Any) -> bool:
    try:
        left_float = float(left)
        right_float = float(right)
    except (TypeError, ValueError, OverflowError):
        return False
    return (
        math.isfinite(left_float)
        and math.isfinite(right_float)
        and math.isclose(
            left_float, right_float, rel_tol=1e-10, abs_tol=1e-7
        )
    )


def _verify_phase_record_integrity(
    phase_name: str,
    phase: dict[str, Any],
    configurations: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    expected_indices: list[int],
) -> list[str]:
    """Validate record identity and arithmetic without claiming model replay."""

    errors: list[str] = []
    records = phase.get("records")
    baselines = phase.get("baselines")
    if not isinstance(records, list) or not isinstance(baselines, list):
        return [f"{phase_name} records/baselines must be arrays"]
    if any(not isinstance(item, dict) for item in (*records, *baselines)):
        return [f"{phase_name} records/baselines must contain objects"]
    if [item.get("blockIndex") for item in baselines] != expected_indices:
        errors.append(
            f"{phase_name} baselines do not cover the registered blocks exactly"
        )
    baseline_by_index = {
        baseline.get("blockIndex"): baseline for baseline in baselines
    }
    if len(baseline_by_index) != len(baselines):
        errors.append(f"{phase_name} contains duplicate baseline block indices")

    for baseline in baselines:
        block_index = baseline.get("blockIndex")
        try:
            native_delta = float(
                baseline["canonicalBF16NLLNatPerToken"]
            ) - float(baseline["originalFP32NLLNatPerToken"])
        except (KeyError, TypeError, ValueError, OverflowError):
            errors.append(
                f"{phase_name} baseline {block_index} has invalid NLL fields"
            )
        else:
            if not math.isfinite(native_delta) or not _close(
                baseline.get("nativeBF16DeltaNLLNatPerToken"),
                native_delta,
            ):
                errors.append(
                    f"{phase_name} baseline {block_index} native BF16 delta "
                    "is inconsistent"
                )

    for configuration in configurations:
        identifier = configuration_id(configuration)
        matching = [
            record
            for record in records
            if record.get("configurationId") == identifier
        ]
        if [record.get("blockIndex") for record in matching] != expected_indices:
            errors.append(
                f"{phase_name} {identifier} does not cover the registered "
                "blocks exactly"
            )
        payload_digests = [
            record.get("payloadSHA256") for record in matching
        ]
        if len(set(payload_digests)) != len(payload_digests):
            errors.append(
                f"{phase_name} {identifier} reuses a payload digest"
            )

    for record in records:
        block_index = record.get("blockIndex")
        baseline = baseline_by_index.get(block_index)
        if baseline is None:
            errors.append(
                f"{phase_name} record has no baseline for block {block_index}"
            )
            continue
        if record.get("tokenIdsSHA256") != baseline.get("tokenIdsSHA256"):
            errors.append(
                f"{phase_name} block {block_index} candidate/baseline token "
                "digests differ"
            )
        if record.get("canonicalCacheBF16SHA256") != baseline.get(
            "canonicalCacheBF16SHA256"
        ):
            errors.append(
                f"{phase_name} block {block_index} candidate/baseline cache "
                "digests differ"
            )
        if not _close(
            record.get("baselineNLLNatPerToken"),
            baseline.get("canonicalBF16NLLNatPerToken"),
        ):
            errors.append(
                f"{phase_name} block {block_index} candidate/baseline NLL "
                "values differ"
            )
        try:
            prediction_tokens = int(record["predictionTokens"])
            agreement_count = int(record["top1AgreementCount"])
            baseline_nll = float(record["baselineNLLNatPerToken"])
            candidate_nll = float(record["candidateNLLNatPerToken"])
            delta = candidate_nll - baseline_nll
            expected_ratio = math.exp(delta)
            cache_identity = (
                float(record["cacheReferenceSumSquares"])
                + float(record["cacheCandidateSumSquares"])
                - 2.0 * float(record["cacheDotProduct"])
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            errors.append(
                f"{phase_name} block {block_index} has invalid derived fields"
            )
            continue
        derived_values = (delta, expected_ratio, cache_identity)
        if any(not math.isfinite(value) for value in derived_values):
            errors.append(
                f"{phase_name} block {block_index} has non-finite derived fields"
            )
            continue
        if (
            prediction_tokens <= 0
            or not 0 <= agreement_count <= prediction_tokens
            or not _close(
                record.get("top1Agreement"),
                agreement_count / prediction_tokens,
            )
        ):
            errors.append(
                f"{phase_name} block {block_index} top-1 fields are inconsistent"
            )
        if not _close(record.get("deltaNLLNatPerToken"), delta):
            errors.append(
                f"{phase_name} block {block_index} delta NLL is inconsistent"
            )
        if not _close(record.get("perplexityRatio"), expected_ratio):
            errors.append(
                f"{phase_name} block {block_index} perplexity ratio is inconsistent"
            )
        if not _cache_close(
            record.get("cacheDifferenceSumSquares"), cache_identity
        ):
            errors.append(
                f"{phase_name} block {block_index} cache accumulators "
                "are inconsistent"
            )
        if (
            type(record.get("payloadBytes")) is not int
            or type(record.get("encodedFileBytes")) is not int
            or not 0 < record["payloadBytes"] <= record["encodedFileBytes"]
        ):
            errors.append(
                f"{phase_name} block {block_index} byte accounting is invalid"
            )
    return errors


def verify_result(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        validate_registered_protocol()
    except ValueError as error:
        errors.append(f"implementation protocol is invalid: {error}")
    try:
        import jsonschema

        with RESULT_SCHEMA.open(encoding="utf-8") as handle:
            schema = json.load(handle)
        validator = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
        for problem in sorted(
            validator.iter_errors(result),
            key=lambda error: tuple(str(item) for item in error.absolute_path),
        ):
            location = ".".join(str(item) for item in problem.absolute_path)
            errors.append(
                f"schema {location or '<root>'}: {problem.message}"
            )
    except (ImportError, OSError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"schema validation could not run: {error}")

    if result.get("schemaVersion") != SCHEMA_VERSION:
        errors.append("schemaVersion does not identify the registered KV pilot")
    disclosure = result.get("registrationDisclosure", {})
    if disclosure.get("externallyTimestampedBeforeTest") is not False:
        errors.append("pilot must disclose the absence of external preregistration")

    recorded_digest = result.get("resultSHA256")
    digest_input = dict(result)
    digest_input.pop("resultSHA256", None)
    expected_digest = sha256_bytes(canonical_json_bytes(digest_input))
    if recorded_digest != expected_digest:
        errors.append("resultSHA256 does not cover the canonical result")

    protocol = result.get("protocol")
    if not isinstance(protocol, dict):
        return errors + ["protocol is missing or is not an object"]
    model = protocol.get("model", {})
    expected_model = {
        "repository": MODEL_REPOSITORY,
        "revision": MODEL_REVISION,
        "weightsSHA256": MODEL_WEIGHTS_SHA256,
    }
    for key, value in expected_model.items():
        if model.get(key) != value:
            errors.append(f"protocol.model.{key} does not match the pin")
    dataset = protocol.get("dataset", {})
    if dataset.get("repository") != DATASET_REPOSITORY:
        errors.append("protocol.dataset.repository does not match the pin")
    if dataset.get("revision") != DATASET_REVISION:
        errors.append("protocol.dataset.revision does not match the pin")
    if dataset.get("files") != DATASET_FILES:
        errors.append("protocol.dataset.files do not match the pinned digests")
    if protocol.get("thresholds") != THRESHOLDS:
        errors.append("protocol thresholds differ from registration")
    if protocol.get("prefillTokens") != 383:
        errors.append("protocol must prefill 383 tokens")
    if protocol.get("predictionsPerBlock") != 128:
        errors.append("protocol must score 128 predictions per block")
    if protocol.get("testStartBlock") != REGISTERED_TEST_START_BLOCK:
        errors.append(
            "protocol test split overlaps the engineering smoke-test reserve"
        )
    if protocol.get("validationBlocks") != 4:
        errors.append("registered validation must contain exactly four blocks")
    if protocol.get("testBlocks") != 8:
        errors.append("registered test must contain exactly eight blocks")

    validation = result.get("validation")
    test = result.get("test")
    if not isinstance(validation, dict) or not isinstance(test, dict):
        return errors + ["validation and test objects are required"]

    validation_records = validation.get("records")
    validation_aggregates = validation.get("aggregates")
    if not isinstance(validation_records, list) or not isinstance(
        validation_aggregates, list
    ):
        errors.append("validation records/aggregates must be arrays")
        return errors

    grid = protocol.get("validationGrid")
    if not isinstance(grid, list):
        errors.append("protocol.validationGrid must be an array")
        return errors
    if len({configuration_id(item) for item in grid}) != len(grid):
        errors.append("validation grid contains duplicate configurations")
    expected_grid = list((*VOIDTOKEN_GRID, *GROUP_QUANT_GRID))
    if grid != expected_grid:
        errors.append("result validation grid differs from implementation")
    errors.extend(
        _verify_phase_record_integrity(
            "validation",
            validation,
            grid,
            list(range(4)),
        )
    )
    try:
        with REGISTRATION.open(encoding="utf-8") as handle:
            registration = json.load(handle)
        registered_void = [
            {"backend": "voidtoken", **configuration}
            for configuration in registration["codecFamilies"]["voidToken"][
                "candidates"
            ]
        ]
        registered_group = [
            {"backend": "group-quant", **configuration}
            for configuration in registration["codecFamilies"][
                "packedGroupQuant"
            ]["candidates"]
        ]
        if registered_void != list(VOIDTOKEN_GRID):
            errors.append("registration VoidToken grid differs from code")
        if registered_group != list(GROUP_QUANT_GRID):
            errors.append("registration group-quant grid differs from code")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        errors.append(f"registration could not be verified: {error}")

    recomputed_validation: list[dict[str, Any]] = []
    for configuration in grid:
        identifier = configuration_id(configuration)
        matching = [
            record
            for record in validation_records
            if record.get("configurationId") == identifier
        ]
        expected_blocks = protocol.get("validationBlocks")
        if len(matching) != expected_blocks:
            errors.append(
                f"validation {identifier} has {len(matching)} records, "
                f"expected {expected_blocks}"
            )
            continue
        try:
            recomputed_validation.append(
                aggregate_candidate_records(configuration, matching)
            )
        except (
            KeyError,
            OverflowError,
            TypeError,
            ValueError,
        ) as error:
            errors.append(
                f"validation {identifier} cannot be aggregated: {error}"
            )
    if len(recomputed_validation) == len(validation_aggregates):
        for observed, recomputed in zip(
            validation_aggregates, recomputed_validation
        ):
            for key, value in recomputed.items():
                if key not in observed or not _close(observed[key], value):
                    errors.append(
                        f"validation aggregate {recomputed['configurationId']} "
                        f"field {key} is inconsistent"
                    )
    else:
        errors.append("validation aggregate count differs from the grid")

    try:
        selected_voidtoken = select_validation_configuration(
            recomputed_validation, "voidtoken"
        )["configuration"]
        selected_group_quant = select_validation_configuration(
            recomputed_validation, "group-quant"
        )["configuration"]
    except ValueError as error:
        errors.append(str(error))
        return errors
    selected = validation.get("selected", {})
    if selected.get("voidtoken") != selected_voidtoken:
        errors.append("registered VoidToken selection is not validation-derived")
    if selected.get("groupQuant") != selected_group_quant:
        errors.append(
            "registered group-quant selection is not validation-derived"
        )

    test_records = test.get("records")
    test_aggregates = test.get("aggregates")
    if not isinstance(test_records, list) or not isinstance(test_aggregates, list):
        errors.append("test records/aggregates must be arrays")
        return errors
    selected_configurations = (selected_voidtoken, selected_group_quant)
    errors.extend(
        _verify_phase_record_integrity(
            "test",
            test,
            selected_configurations,
            list(
                range(
                    REGISTERED_TEST_START_BLOCK,
                    REGISTERED_TEST_START_BLOCK + 8,
                )
            ),
        )
    )
    recomputed_test: list[dict[str, Any]] = []
    for configuration in selected_configurations:
        identifier = configuration_id(configuration)
        matching = [
            record
            for record in test_records
            if record.get("configurationId") == identifier
        ]
        expected_blocks = protocol.get("testBlocks")
        if len(matching) != expected_blocks:
            errors.append(
                f"test {identifier} has {len(matching)} records, "
                f"expected {expected_blocks}"
            )
            continue
        try:
            recomputed_test.append(
                aggregate_candidate_records(configuration, matching)
            )
        except (
            KeyError,
            OverflowError,
            TypeError,
            ValueError,
        ) as error:
            errors.append(f"test {identifier} cannot be aggregated: {error}")
    if len(recomputed_test) != len(test_aggregates):
        errors.append("test aggregate count differs from selected families")
    else:
        for observed, recomputed in zip(test_aggregates, recomputed_test):
            for key, value in recomputed.items():
                if key not in observed or not _close(observed[key], value):
                    errors.append(
                        f"test aggregate {recomputed['configurationId']} "
                        f"field {key} is inconsistent"
                    )
    if test.get("allPassed") != all(
        aggregate["pass"] for aggregate in recomputed_test
    ):
        errors.append("test.allPassed is inconsistent with family verdicts")

    for phase_name, phase in (("validation", validation), ("test", test)):
        baselines = phase.get("baselines")
        if not isinstance(baselines, list):
            errors.append(f"{phase_name}.baselines must be an array")
            continue
        for baseline in baselines:
            if baseline.get("exactRebuildMaxAbsLogitDifference") != 0.0:
                errors.append(
                    f"{phase_name} block {baseline.get('blockIndex')} "
                    "did not reproduce the canonical cache exactly"
                )
            if baseline.get("exactRebuildTop1Identical") is not True:
                errors.append(
                    f"{phase_name} block {baseline.get('blockIndex')} "
                    "changed top-1 under exact cache rebuild"
                )
            if baseline.get("layoutRebuildMaxAbsLogitDifference") != 0.0:
                errors.append(
                    f"{phase_name} block {baseline.get('blockIndex')} "
                    "changed logits under direct-cache layout rebuild"
                )
            if baseline.get("layoutRebuildTop1Identical") is not True:
                errors.append(
                    f"{phase_name} block {baseline.get('blockIndex')} "
                    "changed top-1 under direct-cache layout rebuild"
                )
    return errors


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="?", type=Path, default=DEFAULT_EVIDENCE)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        if arguments.evidence.stat().st_size > MAX_EVIDENCE_BYTES:
            raise ValueError("evidence exceeds the verifier resource limit")
        with arguments.evidence.open(encoding="utf-8") as handle:
            result = json.load(handle)
        if not isinstance(result, dict):
            raise ValueError("top-level JSON value must be an object")
        errors = verify_result(result)
    except (
        KeyError,
        OSError,
        OverflowError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"REAL-LLM EVIDENCE VERIFICATION FAILED: {error}")
        return 1
    if errors:
        print(
            f"REAL-LLM EVIDENCE VERIFICATION FAILED ({len(errors)} problem(s)):"
        )
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "REAL-LLM EVIDENCE STRUCTURAL CONSISTENCY VERIFIED: pins, exact block "
        "coverage, cross-record identities, aggregates, verdicts, and result "
        "digest are internally consistent. This verifier does not rerun model "
        "inference and does not authenticate who produced the measurements."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
