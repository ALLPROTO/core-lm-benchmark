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


def _close(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(
            float(left), float(right), rel_tol=1e-12, abs_tol=1e-12
        )
    return left == right


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
        recomputed_validation.append(
            aggregate_candidate_records(configuration, matching)
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
        recomputed_test.append(
            aggregate_candidate_records(configuration, matching)
        )
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
        with arguments.evidence.open(encoding="utf-8") as handle:
            result = json.load(handle)
        if not isinstance(result, dict):
            raise ValueError("top-level JSON value must be an object")
        errors = verify_result(result)
    except (OSError, ValueError, json.JSONDecodeError) as error:
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
        "REAL-LLM EVIDENCE VERIFIED: pins, split selection, aggregates, "
        "verdicts, exact cache rebuild, and result digest are consistent."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
