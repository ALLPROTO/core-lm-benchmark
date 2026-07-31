#!/usr/bin/env python3
"""Independently verify a fresh real-Qwen run from a locally built app."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from security.verify_app_run_evidence import verify_fresh_run  # noqa: E402


DEFAULT_RESULTS_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "CoreLMBenchmark"
    / "real-llm-results"
)
DEFAULT_APP = PROJECT_ROOT / "dist" / "CoreLMBenchmark.app"


def latest_complete_run(results_root: Path) -> Path:
    root = results_root.resolve()
    if results_root.is_symlink() or not root.is_dir():
        raise ValueError("application results directory is missing or unsafe")
    candidates: list[tuple[int, str, Path]] = []
    for candidate in root.iterdir():
        if candidate.is_symlink() or not candidate.is_dir():
            continue
        result = candidate / "validation-064-071.json"
        receipt = candidate / "app-run-receipt.json"
        if (
            result.is_symlink()
            or receipt.is_symlink()
            or not result.is_file()
            or not receipt.is_file()
        ):
            continue
        candidates.append(
            (receipt.stat().st_mtime_ns, candidate.name, candidate)
        )
    if not candidates:
        raise ValueError("no complete blocks 64–71 app run was found")
    return max(candidates)[2]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "recompute manifest-derived container accounting and scientific "
            "gates for a CoreLMBenchmark.app result, then bind its receipt "
            "to the local app"
        )
    )
    parser.add_argument(
        "--run-directory",
        type=Path,
        help=(
            "directory containing validation-064-071.json and "
            "app-run-receipt.json; defaults to the newest complete app run"
        ),
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=DEFAULT_RESULTS_ROOT,
        help="root used when --run-directory is omitted",
    )
    parser.add_argument(
        "--app",
        type=Path,
        default=DEFAULT_APP,
        help="the locally built app that produced the receipt",
    )
    parser.add_argument(
        "--challenge",
        help=(
            "64-character nonce supplied to the app by "
            "run_local_app_proof.sh; required for a freshness claim"
        ),
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        run_directory = (
            arguments.run_directory
            if arguments.run_directory is not None
            else latest_complete_run(arguments.results_root)
        )
        result = verify_fresh_run(
            run_directory,
            arguments.app,
            challenge_nonce=arguments.challenge,
        )
        aggregate = result["aggregates"][0]
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"LOCAL APP RUN FAIL: {error}", file=sys.stderr)
        return 1
    prefix = (
        "FRESH LOCAL APP PROOF PASS"
        if arguments.challenge is not None
        else "LOCAL APP RUN CONSISTENCY PASS"
    )
    print(
        f"{prefix}: "
        f"{aggregate['compressionRatioVsBF16']:.6f}x compression, "
        f"delta NLL {aggregate['deltaNLLNatPerToken']:+.8f}, "
        f"top-1 {aggregate['top1Agreement']:.4%}; "
        "all manifest-derived container totals, gates, receipt hashes, "
        "runtime identity, runner source, and app executable agree."
    )
    print(f"Verified run: {run_directory.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
