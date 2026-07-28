#!/usr/bin/env python3
"""Run the required Core LM scenario matrix and save aggregate evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from corelm_benchmark import (
    ExperimentConfiguration,
    aggregate_suite,
    run_benchmark,
    save_result,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Run the full evidence matrix")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "benchmark-results",
    )
    arguments = parser.parse_args()

    scenarios = ["zero", "gaussian_bounded", "uniform_bounded", "impulse", "repeating_structured"]
    configurations = []
    if arguments.full:
        canonical_top_k = {32: 4, 96: 8, 256: 16}
        # Main matrix: every scenario, three dimensions and five seeds.
        for dimension in (32, 96, 256):
            for seed in (7, 17, 42, 101, 997):
                for scenario in scenarios:
                    configurations.append(
                        (dimension, 200, seed, scenario, canonical_top_k[dimension], 127)
                    )
        # Long-run coverage for every scenario and dimension.
        for dimension in (32, 96, 256):
            for scenario in scenarios:
                configurations.append(
                    (dimension, 5000, 42, scenario, canonical_top_k[dimension], 127)
                )
        # Dedicated top-k / quantization sweep.
        for top_k in (4, 8, 16):
            for qmax in (127, 32767):
                for seed in (7, 17, 42, 101, 997):
                    configurations.append((96, 200, seed, "gaussian_bounded", top_k, qmax))
    else:
        configurations = [(32, 200, 7, scenario, 4, 127) for scenario in scenarios]

    results = []
    seen = set()
    for dimension, step_count, seed, scenario, top_k, qmax in configurations:
        key = (dimension, step_count, seed, scenario, top_k, qmax)
        if key in seen:
            continue
        seen.add(key)
        config = ExperimentConfiguration(
            dimension=dimension,
            steps=step_count,
            seed=seed,
            input_scenario=scenario,
            pca_components=min(8, dimension, step_count + 1),
            top_k=top_k,
            qmax=qmax,
        )
        result = run_benchmark(config)
        save_result(result, arguments.output)
        results.append(result)
        print(result["runId"], result["verdict"])

    aggregate = aggregate_suite(results)
    aggregate_path = arguments.output / "aggregate.json"
    aggregate_path.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n")
    print(json.dumps(aggregate, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
