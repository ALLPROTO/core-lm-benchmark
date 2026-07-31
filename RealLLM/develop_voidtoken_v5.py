#!/usr/bin/env python3
"""Tune VoidToken v5 on the validation split without opening test data."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RealLLM.benchmark_real_llm import (  # noqa: E402
    DATASET_FILES,
    DATASET_REPOSITORY,
    DATASET_REVISION,
    LAYER_SENSITIVITY_ORDER,
    MODEL_ASSET_FILES,
    MODEL_REPOSITORY,
    MODEL_REVISION,
    MODEL_WEIGHTS_BYTES,
    MODEL_WEIGHTS_SHA256,
    PrimaryEvidenceWriter,
    THRESHOLDS,
    _aggregate_phase,
    _evaluate_block,
    _exclusive_write_bytes,
    _resolve_device,
    _token_blocks,
    canonical_json_bytes,
    select_validation_configuration,
    sha256_bytes,
    sha256_file,
)


UNIFORM_DEVELOPMENT_GRID = tuple(
    {
        "backend": "voidtoken-v5",
        "bits": bits,
        "groupSize": group_size,
        "transformBlockSize": group_size,
        "scaleCompression": "zlib-9",
        "codeCompression": "zlib-9",
        "signMode": "shake256",
    }
    for bits in (6, 7, 8)
    for group_size in (16, 32, 64)
)


def _mixed_precision_configuration(eight_bit_layers: int) -> dict[str, Any]:
    selected = set(LAYER_SENSITIVITY_ORDER[:eight_bit_layers])
    return {
        "backend": "voidtoken-v5",
        "bitsByLayer": [
            8 if layer_index in selected else 5
            for layer_index in range(24)
        ],
        "groupSize": 16,
        "transformBlockSize": 16,
        "scaleCompression": "zlib-9",
        "codeCompression": "zlib-9",
        "signMode": "shake256",
        "schedule": (
            f"validation-kl-top-{eight_bit_layers}-8bit-rest-5bit"
        ),
    }


MIXED_DEVELOPMENT_GRID = tuple(
    _mixed_precision_configuration(eight_bit_layers)
    for eight_bit_layers in (16, 17, 18, 20, 22, 24)
)

UNSIGNED_UNIFORM_DEVELOPMENT_GRID = tuple(
    {
        "backend": "voidtoken-v5",
        "bits": 8,
        "groupSize": group_size,
        "transformBlockSize": group_size,
        "scaleCompression": "zlib-9",
        "codeCompression": "zlib-9",
        "signMode": "none",
    }
    for group_size in (16, 32, 64)
)


def _unsigned_mixed_precision_configuration(
    eight_bit_layers: int,
) -> dict[str, Any]:
    configuration = _mixed_precision_configuration(eight_bit_layers)
    configuration["signMode"] = "none"
    configuration["schedule"] += "-unsigned"
    return configuration


UNSIGNED_MIXED_DEVELOPMENT_GRID = tuple(
    _unsigned_mixed_precision_configuration(eight_bit_layers)
    for eight_bit_layers in (16, 17, 18)
)

WIDE_SCALE_DEVELOPMENT_GRID = (
    {
        "backend": "voidtoken-v5",
        "bits": 8,
        "groupSize": 128,
        "transformBlockSize": transform_block_size,
        "scaleCompression": "zlib-9",
        "codeCompression": "zlib-9",
        "signMode": "none",
    }
    for transform_block_size in (64, 128)
)

WIDE_TRANSFORM_DEVELOPMENT_GRID = tuple(
    {
        "backend": "voidtoken-v5",
        "bits": 8,
        "groupSize": group_size,
        "transformBlockSize": transform_block_size,
        "scaleCompression": "zlib-9",
        "codeCompression": "zlib-9",
        "signMode": "none",
    }
    for group_size, transform_block_size in (
        (64, 128),
        (64, 256),
        (128, 256),
    )
)

HIGH_PRECISION_DEVELOPMENT_GRID = tuple(
    {
        "backend": "voidtoken-v5",
        "bits": bits,
        "groupSize": 128,
        "transformBlockSize": 128,
        "scaleCompression": "zlib-9",
        "codeCompression": "zlib-9",
        "signMode": "none",
    }
    for bits in (9, 10)
)

KV_SENSITIVITY_ORDER = (
    16,
    21,
    0,
    22,
    20,
    1,
    9,
    23,
    3,
    14,
    13,
    11,
    2,
    4,
    17,
    12,
    19,
    10,
    15,
    8,
    5,
    7,
    6,
    18,
)


def _nine_bit_upgrade_configuration(
    order: tuple[int, ...], upgraded_layers: int, label: str
) -> dict[str, Any]:
    selected = set(order[:upgraded_layers])
    return {
        "backend": "voidtoken-v5",
        "bitsByLayer": [
            9 if layer_index in selected else 8
            for layer_index in range(24)
        ],
        "groupSize": 128,
        "transformBlockSize": 128,
        "scaleCompression": "zlib-9",
        "codeCompression": "zlib-9",
        "signMode": "none",
        "schedule": f"{label}-top-{upgraded_layers}-9bit-rest-8bit",
    }


NINE_BIT_UPGRADE_GRID = tuple(
    _nine_bit_upgrade_configuration(order, upgraded_layers, label)
    for order, label in (
        (LAYER_SENSITIVITY_ORDER, "group-kl"),
        (KV_SENSITIVITY_ORDER, "kv-forensics"),
    )
    for upgraded_layers in (4, 5)
)


MINIMAL_NINE_BIT_UPGRADE_GRID = tuple(
    _nine_bit_upgrade_configuration(
        LAYER_SENSITIVITY_ORDER,
        upgraded_layers,
        "group-kl",
    )
    for upgraded_layers in (2, 3)
)


def _value_upgrade_configuration(upgraded_layers: int) -> dict[str, Any]:
    selected = set(LAYER_SENSITIVITY_ORDER[:upgraded_layers])
    return {
        "backend": "voidtoken-v5",
        "bitsByKVByLayer": [
            [8, 9 if layer_index in selected else 8]
            for layer_index in range(24)
        ],
        "groupSize": 128,
        "transformBlockSize": 128,
        "scaleCompression": "zlib-9",
        "codeCompression": "zlib-9",
        "signMode": "none",
        "schedule": (
            f"group-kl-value-top-{upgraded_layers}-9bit-rest-8bit"
        ),
    }


VALUE_UPGRADE_GRID = tuple(
    _value_upgrade_configuration(upgraded_layers)
    for upgraded_layers in (4, 6, 8)
)


CONCENTRATED_PRECISION_GRID = (
    {
        "backend": "voidtoken-v5",
        "bitsByLayer": [
            10 if layer_index == LAYER_SENSITIVITY_ORDER[0]
            else 9 if layer_index == LAYER_SENSITIVITY_ORDER[1]
            else 8
            for layer_index in range(24)
        ],
        "groupSize": 128,
        "transformBlockSize": 128,
        "scaleCompression": "zlib-9",
        "codeCompression": "zlib-9",
        "signMode": "none",
        "schedule": "group-kl-top1-10bit-top2-9bit-rest-8bit",
    },
)


DEVELOPMENT_GRID = (
    UNIFORM_DEVELOPMENT_GRID
    + MIXED_DEVELOPMENT_GRID
    + UNSIGNED_UNIFORM_DEVELOPMENT_GRID
    + UNSIGNED_MIXED_DEVELOPMENT_GRID
    + tuple(WIDE_SCALE_DEVELOPMENT_GRID)
    + WIDE_TRANSFORM_DEVELOPMENT_GRID
    + HIGH_PRECISION_DEVELOPMENT_GRID
    + NINE_BIT_UPGRADE_GRID
    + MINIMAL_NINE_BIT_UPGRADE_GRID
    + VALUE_UPGRADE_GRID
    + CONCENTRATED_PRECISION_GRID
)


def _download_validation_only(local_files_only: bool) -> dict[str, Path]:
    """Resolve and verify model weights plus validation, never test parquet."""

    from huggingface_hub import hf_hub_download

    model_path = Path(
        hf_hub_download(
            MODEL_REPOSITORY,
            revision=MODEL_REVISION,
            filename="model.safetensors",
            local_files_only=local_files_only,
            token=False,
        )
    )
    if model_path.stat().st_size != MODEL_WEIGHTS_BYTES:
        raise RuntimeError("pinned model weight size mismatch")
    if sha256_file(model_path) != MODEL_WEIGHTS_SHA256:
        raise RuntimeError("pinned model weight digest mismatch")
    for filename, asset in MODEL_ASSET_FILES.items():
        asset_path = Path(
            hf_hub_download(
                MODEL_REPOSITORY,
                revision=MODEL_REVISION,
                filename=filename,
                local_files_only=local_files_only,
                token=False,
            )
        )
        if asset_path.stat().st_size != asset["bytes"]:
            raise RuntimeError(f"pinned model asset size mismatch: {filename}")
        if sha256_file(asset_path) != asset["sha256"]:
            raise RuntimeError(
                f"pinned model asset digest mismatch: {filename}"
            )

    specification = DATASET_FILES["validation"]
    validation_path = Path(
        hf_hub_download(
            DATASET_REPOSITORY,
            repo_type="dataset",
            revision=DATASET_REVISION,
            filename=specification["path"],
            local_files_only=local_files_only,
            token=False,
        )
    )
    if validation_path.stat().st_size != specification["bytes"]:
        raise RuntimeError("pinned validation dataset size mismatch")
    if sha256_file(validation_path) != specification["sha256"]:
        raise RuntimeError("pinned validation dataset digest mismatch")
    return {
        "modelSnapshot": model_path.parent,
        "modelWeights": model_path,
        "validation": validation_path,
    }


def _validate_grid() -> None:
    identifiers = {
        sha256_bytes(canonical_json_bytes(configuration))
        for configuration in DEVELOPMENT_GRID
    }
    if len(identifiers) != len(DEVELOPMENT_GRID):
        raise ValueError("VoidToken v5 development grid contains duplicates")


def run_validation_development(
    output_path: Path,
    *,
    device_requested: str,
    validation_start_block: int,
    validation_blocks: int,
    candidate_indices: tuple[int, ...] | None,
    local_files_only: bool,
    seed: int = 20260729,
    primary_evidence_directory: Path | None = None,
) -> dict[str, Any]:
    if device_requested not in {"auto", "cpu", "mps", "cuda"}:
        raise ValueError("device must be auto, cpu, mps, or cuda")
    if validation_start_block < 0:
        raise ValueError("validation_start_block must be non-negative")
    if validation_blocks < 1:
        raise ValueError("validation_blocks must be positive")
    _validate_grid()
    if candidate_indices is None:
        candidate_grid = DEVELOPMENT_GRID
    else:
        if not candidate_indices:
            raise ValueError("candidate_indices must not be empty")
        if len(set(candidate_indices)) != len(candidate_indices):
            raise ValueError("candidate_indices contains duplicates")
        if any(
            index < 0 or index >= len(DEVELOPMENT_GRID)
            for index in candidate_indices
        ):
            raise ValueError("candidate index is outside the development grid")
        candidate_grid = tuple(
            DEVELOPMENT_GRID[index] for index in candidate_indices
        )
    primary_evidence_writer: PrimaryEvidenceWriter | None = None
    if primary_evidence_directory is not None:
        if len(candidate_grid) != 1:
            raise ValueError(
                "primary evidence requires exactly one candidate configuration"
            )
        if (
            primary_evidence_directory.parent.resolve()
            != output_path.parent.resolve()
            or primary_evidence_directory.name != "primary-evidence"
        ):
            raise ValueError(
                "primary evidence must be output beside the result file"
            )
        primary_evidence_writer = PrimaryEvidenceWriter(
            primary_evidence_directory,
            result_filename=output_path.name,
        )

    import pyarrow
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(seed)
    np.random.seed(seed)
    if hasattr(torch, "use_deterministic_algorithms"):
        torch.use_deterministic_algorithms(True, warn_only=True)
    device = _resolve_device(device_requested, torch)
    inputs = _download_validation_only(local_files_only)

    tokenizer = AutoTokenizer.from_pretrained(
        inputs["modelSnapshot"],
        local_files_only=True,
        trust_remote_code=False,
    )
    model = AutoModelForCausalLM.from_pretrained(
        inputs["modelSnapshot"],
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.float32,
        attn_implementation="eager",
    ).to(device)
    model.eval()

    blocks, token_digest = _token_blocks(
        tokenizer,
        inputs["validation"],
        validation_blocks,
        start_block=validation_start_block,
    )
    baselines: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for relative_index, block in enumerate(blocks):
        block_index = validation_start_block + relative_index
        print(
            f"validation block {relative_index + 1}/{len(blocks)} "
            f"(source block {block_index})",
            flush=True,
        )
        baseline, candidates = _evaluate_block(
            block,
            block_index,
            candidate_grid,
            model=model,
            device=device,
            torch_module=torch,
            primary_evidence_writer=primary_evidence_writer,
        )
        baselines.append(baseline)
        records.extend(candidates)

    aggregates = _aggregate_phase(candidate_grid, records)
    selection_error: str | None = None
    try:
        selected = select_validation_configuration(
            aggregates, "voidtoken-v5"
        )["configuration"]
    except ValueError as error:
        selected = None
        selection_error = str(error)
    result: dict[str, Any] = {
        "schemaVersion": (
            "corelm-voidtoken-v5-validation-development-v3"
            if primary_evidence_writer is not None
            else "corelm-voidtoken-v5-validation-development-v2"
        ),
        "status": "validation-only-development",
        "createdAt": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "testDataOpened": False,
        "protocol": {
            "modelRepository": MODEL_REPOSITORY,
            "modelRevision": MODEL_REVISION,
            "modelWeightsSHA256": MODEL_WEIGHTS_SHA256,
            "datasetRepository": DATASET_REPOSITORY,
            "datasetRevision": DATASET_REVISION,
            "split": "validation",
            "validationStartBlock": validation_start_block,
            "validationBlocks": validation_blocks,
            "thresholds": THRESHOLDS,
            "fullDevelopmentGrid": list(DEVELOPMENT_GRID),
            "evaluatedCandidateIndices": (
                list(candidate_indices)
                if candidate_indices is not None
                else list(range(len(DEVELOPMENT_GRID)))
            ),
            "evaluatedGrid": list(candidate_grid),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "device": device,
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "numpy": np.__version__,
            "pyarrow": pyarrow.__version__,
            "hfHome": (
                "configured" if os.environ.get("HF_HOME") else None
            ),
            "seed": seed,
        },
        "selectedTokenIdsSHA256": token_digest,
        "baselines": baselines,
        "records": records,
        "aggregates": aggregates,
        "selected": selected,
        "selectionError": selection_error,
    }
    if primary_evidence_writer is not None:
        result["primaryEvidence"] = primary_evidence_writer.finalize()
    result["resultSHA256"] = sha256_bytes(canonical_json_bytes(result))
    _exclusive_write_bytes(
        output_path,
        json.dumps(
            result,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    return result


def _summary(result: dict[str, Any]) -> str:
    lines = [
        "VoidToken v5 validation-only development complete.",
        f"Result SHA-256: {result['resultSHA256']}",
    ]
    ordered = sorted(
        result["aggregates"],
        key=lambda item: (
            not item["pass"],
            item["meanKLDivergenceNat"],
            -item["compressionRatioVsBF16"],
        ),
    )
    for aggregate in ordered:
        configuration = aggregate["configuration"]
        precision = (
            f"schedule={configuration['schedule']}"
            if "schedule" in configuration
            else f"bits={configuration['bits']}"
        )
        lines.append(
            f"- {precision} "
            f"group={configuration['groupSize']}: "
            f"{aggregate['compressionRatioVsBF16']:.3f}x, "
            f"delta NLL {aggregate['deltaNLLNatPerToken']:+.6f}, "
            f"top-1 {aggregate['top1Agreement']:.4f}, "
            f"KL {aggregate['meanKLDivergenceNat']:.6f}, "
            f"{'PASS' if aggregate['pass'] else 'FAIL'}"
        )
    return "\n".join(lines)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "tmp" / "voidtoken-v5-validation.json",
    )
    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "mps", "cuda"),
        default="auto",
    )
    parser.add_argument("--validation-start-block", type=int, default=0)
    parser.add_argument("--validation-blocks", type=int, default=4)
    parser.add_argument(
        "--candidate-index",
        type=int,
        action="append",
        dest="candidate_indices",
        help="evaluate only this grid index; repeat for a small batch",
    )
    parser.add_argument(
        "--list-candidates",
        action="store_true",
        help="print the indexed development grid and exit",
    )
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument(
        "--primary-evidence-directory",
        type=Path,
        help=(
            "retain raw containers and per-token metrics in this new "
            "primary-evidence directory beside --output"
        ),
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    if arguments.list_candidates:
        for index, configuration in enumerate(DEVELOPMENT_GRID):
            print(
                f"{index}: "
                + json.dumps(
                    configuration,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        return 0
    try:
        result = run_validation_development(
            arguments.output,
            device_requested=arguments.device,
            validation_start_block=arguments.validation_start_block,
            validation_blocks=arguments.validation_blocks,
            candidate_indices=(
                tuple(arguments.candidate_indices)
                if arguments.candidate_indices is not None
                else None
            ),
            local_files_only=arguments.local_files_only,
            primary_evidence_directory=arguments.primary_evidence_directory,
        )
    except Exception as error:
        print(f"VOIDTOKEN V5 DEVELOPMENT FAILED: {error}", file=sys.stderr)
        return 1
    print(_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
