#!/usr/bin/env python3
"""Replay and verify the registered Core LM benchmark evidence."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

BENCHMARK_CORE_DIRECTORY = Path(__file__).resolve().parent
if str(BENCHMARK_CORE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_CORE_DIRECTORY))

from run_suite import execute_suite, suite_configurations


PROJECT_ROOT = BENCHMARK_CORE_DIRECTORY.parent
DEFAULT_REGISTERED_DIRECTORY = PROJECT_ROOT / "benchmark-results"
REGISTERED_RUN_COUNT = 115
# Core states and VoidToken bytes are protected by exact SHA-256 digests.
# These narrow tolerances cover only derived floating-point diagnostics,
# principally the LAPACK-backed PCA baseline across platforms.
FLOAT_RELATIVE_TOLERANCE = 1e-4
FLOAT_ABSOLUTE_TOLERANCE = 1e-5
MAX_REPORTED_MISMATCHES = 100
MAX_JSON_BYTES = 4 * 1024 * 1024
RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")

VOLATILE_RESULT_FIELDS = {"createdAt", "coreRuntimeNanoseconds"}
VOLATILE_METHOD_FIELDS = {
    "encodeNanoseconds",
    "decodeNanoseconds",
    "stepsPerSecond",
    "peakMemoryBytes",
}


def load_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"{path} exceeds the evidence resource limit")
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return value


def scientific_record(record: dict[str, Any]) -> dict[str, Any]:
    """Remove only fields that are expected to vary between executions."""
    projected = {
        key: value
        for key, value in record.items()
        if key not in VOLATILE_RESULT_FIELDS
    }
    environment = record.get("environment", {})
    projected["environment"] = {
        "implementationVersion": environment.get("implementationVersion")
    }
    projected["methods"] = [
        {
            key: value
            for key, value in method.items()
            if key not in VOLATILE_METHOD_FIELDS
        }
        for method in record.get("methods", [])
    ]
    return projected


def compare_values(
    expected: Any,
    observed: Any,
    path: str,
    differences: list[str],
    *,
    relative_tolerance: float,
    absolute_tolerance: float,
    allow_float_tolerance: bool = True,
) -> None:
    if len(differences) >= MAX_REPORTED_MISMATCHES:
        return

    if isinstance(expected, dict):
        if not isinstance(observed, dict):
            differences.append(
                f"{path}: expected object, observed {type(observed).__name__}"
            )
            return
        expected_keys = set(expected)
        observed_keys = set(observed)
        for key in sorted(expected_keys - observed_keys):
            differences.append(f"{path}.{key}: missing from replay")
        for key in sorted(observed_keys - expected_keys):
            differences.append(f"{path}.{key}: unexpected replay field")
        for key in sorted(expected_keys & observed_keys):
            compare_values(
                expected[key],
                observed[key],
                f"{path}.{key}",
                differences,
                relative_tolerance=relative_tolerance,
                absolute_tolerance=absolute_tolerance,
                allow_float_tolerance=(
                    allow_float_tolerance and key != "configuration"
                ),
            )
        return

    if isinstance(expected, list):
        if not isinstance(observed, list):
            differences.append(
                f"{path}: expected list, observed {type(observed).__name__}"
            )
            return
        if len(expected) != len(observed):
            differences.append(
                f"{path}: expected {len(expected)} entries, observed {len(observed)}"
            )
        for index, (expected_item, observed_item) in enumerate(zip(expected, observed)):
            compare_values(
                expected_item,
                observed_item,
                f"{path}[{index}]",
                differences,
                relative_tolerance=relative_tolerance,
                absolute_tolerance=absolute_tolerance,
                allow_float_tolerance=allow_float_tolerance,
            )
        return

    if isinstance(expected, float):
        if not isinstance(observed, (int, float)) or isinstance(observed, bool):
            differences.append(f"{path}: expected number, observed {observed!r}")
            return
        observed_float = float(observed)
        matches = (
            expected == observed_float
            if not allow_float_tolerance
            else math.isclose(
                expected,
                observed_float,
                rel_tol=relative_tolerance,
                abs_tol=absolute_tolerance,
            )
        )
        if not matches:
            differences.append(f"{path}: expected {expected!r}, observed {observed!r}")
        return

    if expected != observed:
        differences.append(f"{path}: expected {expected!r}, observed {observed!r}")


def verify_evidence(
    registered_directory: Path,
    *,
    relative_tolerance: float = FLOAT_RELATIVE_TOLERANCE,
    absolute_tolerance: float = FLOAT_ABSOLUTE_TOLERANCE,
) -> list[str]:
    if (
        not math.isfinite(relative_tolerance)
        or not 0.0 <= relative_tolerance <= 1e-2
        or not math.isfinite(absolute_tolerance)
        or not 0.0 <= absolute_tolerance <= 1e-3
    ):
        raise ValueError("evidence tolerances are outside the safe verifier range")
    registered_aggregate_path = registered_directory / "aggregate.json"
    registered_aggregate = load_json(registered_aggregate_path)
    configurations = suite_configurations(full=True)
    differences: list[str] = []

    expected_run_ids = registered_aggregate.get("runIds")
    if not isinstance(expected_run_ids, list):
        return ["aggregate.runIds: expected a list"]
    if any(
        not isinstance(run_id, str)
        or RUN_ID_PATTERN.fullmatch(run_id) is None
        for run_id in expected_run_ids
    ):
        return [
            "aggregate.runIds: every run ID must be exactly 16 lowercase "
            "hexadecimal characters"
        ]

    if len(configurations) != REGISTERED_RUN_COUNT:
        differences.append(
            "suite: expected "
            f"{REGISTERED_RUN_COUNT} configurations, observed {len(configurations)}"
        )
    if len(expected_run_ids) != REGISTERED_RUN_COUNT:
        differences.append(
            "aggregate.runIds: expected "
            f"{REGISTERED_RUN_COUNT} entries, observed {len(expected_run_ids)}"
        )
    if len(set(expected_run_ids)) != len(expected_run_ids):
        differences.append("aggregate.runIds: duplicate registered run ID")

    with tempfile.TemporaryDirectory(prefix="corelm-evidence-") as temporary:
        replay_directory = Path(temporary)
        print(
            f"Replaying {len(configurations)} configurations in a temporary directory..."
        )
        execute_suite(configurations, replay_directory, progress=True)
        replay_aggregate = load_json(replay_directory / "aggregate.json")
        replay_run_ids = replay_aggregate.get("runIds", [])

        compare_values(
            registered_aggregate,
            replay_aggregate,
            "aggregate",
            differences,
            relative_tolerance=relative_tolerance,
            absolute_tolerance=absolute_tolerance,
        )

        for index, (expected_run_id, replay_run_id) in enumerate(
            zip(expected_run_ids, replay_run_ids)
        ):
            registered_path = registered_directory / f"{expected_run_id}.json"
            replay_path = replay_directory / f"{replay_run_id}.json"
            if not registered_path.is_file():
                differences.append(
                    f"run[{index}]: missing registered record {registered_path.name}"
                )
                continue
            if not replay_path.is_file():
                differences.append(
                    f"run[{index}]: missing replay record {replay_path.name}"
                )
                continue
            registered_record = scientific_record(load_json(registered_path))
            replay_record = scientific_record(load_json(replay_path))
            compare_values(
                registered_record,
                replay_record,
                f"run[{index}]",
                differences,
                relative_tolerance=relative_tolerance,
                absolute_tolerance=absolute_tolerance,
            )

    return differences


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registered-directory",
        type=Path,
        default=DEFAULT_REGISTERED_DIRECTORY,
        help="Directory containing aggregate.json and registered run records",
    )
    parser.add_argument(
        "--relative-tolerance",
        type=float,
        default=FLOAT_RELATIVE_TOLERANCE,
        help="Relative tolerance for floating-point scientific values",
    )
    parser.add_argument(
        "--absolute-tolerance",
        type=float,
        default=FLOAT_ABSOLUTE_TOLERANCE,
        help="Absolute tolerance for floating-point scientific values",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        differences = verify_evidence(
            arguments.registered_directory,
            relative_tolerance=arguments.relative_tolerance,
            absolute_tolerance=arguments.absolute_tolerance,
        )
    except (
        AttributeError,
        KeyError,
        OSError,
        OverflowError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"EVIDENCE VERIFICATION FAILED: {error}")
        return 1

    if differences:
        print(f"EVIDENCE VERIFICATION FAILED ({len(differences)} mismatch(es)):")
        for difference in differences:
            print(f"- {difference}")
        if len(differences) == MAX_REPORTED_MISMATCHES:
            print(f"- output stopped after {MAX_REPORTED_MISMATCHES} mismatches")
        return 1

    print(
        "EVIDENCE VERIFIED: 115/115 registered runs match exact run IDs, input, "
        "Core-state, VoidToken payload, container and reconstruction digests, "
        "configurations, invariants and verdicts; scientific metrics, time "
        "series and aggregate match with floating-point "
        f"rtol={arguments.relative_tolerance:g}, "
        f"atol={arguments.absolute_tolerance:g}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
