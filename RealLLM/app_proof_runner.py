#!/usr/bin/env python3
"""Run the single registered validation-only proof used by the macOS app."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTERED_CANDIDATE_INDEX = 32
SEED = 20260729


def establish_worker_process_group() -> int:
    """Become a group leader before importing the model or starting work."""

    identifier = os.getpid()
    if os.getpgrp() != identifier:
        os.setpgid(0, 0)
    if os.getpgrp() != identifier:
        raise RuntimeError("worker could not establish its process group")
    return identifier


def register_worker_process_group(identifier: int) -> Path | None:
    """Publish the group PID for the outer proof's crash-only cleanup."""

    raw_path = os.environ.get("CORELM_WORKER_GROUP_FILE")
    if raw_path is None:
        return None
    path = Path(raw_path)
    if not path.is_absolute() or path.name != ".worker-process-group":
        raise ValueError("worker group file has an invalid path")
    parent_status = path.parent.stat()
    if (
        not path.parent.is_dir()
        or path.parent.is_symlink()
        or parent_status.st_uid != os.getuid()
        or parent_status.st_mode & 0o022
    ):
        raise ValueError("worker group file parent is not private")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        payload = f"{identifier}\n".encode("ascii")
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("worker group registration write stalled")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def remove_worker_process_group_registration(
    path: Path | None, identifier: int | None
) -> None:
    if path is None or identifier is None:
        return
    try:
        if path.is_symlink() or path.read_text(encoding="ascii") != (
            f"{identifier}\n"
        ):
            return
        path.unlink()
    except FileNotFoundError:
        pass


def _load_core() -> Any:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from RealLLM import app_proof_core

    return app_proof_core


def _download_validation_only(
    core: Any, local_files_only: bool
) -> dict[str, Path]:
    """Resolve and verify model weights plus validation, never test parquet."""

    from huggingface_hub import hf_hub_download

    model_path = Path(
        hf_hub_download(
            core.MODEL_REPOSITORY,
            revision=core.MODEL_REVISION,
            filename="model.safetensors",
            local_files_only=local_files_only,
            token=False,
        )
    )
    if model_path.stat().st_size != core.MODEL_WEIGHTS_BYTES:
        raise RuntimeError("pinned model weight size mismatch")
    if core.sha256_file(model_path) != core.MODEL_WEIGHTS_SHA256:
        raise RuntimeError("pinned model weight digest mismatch")
    for filename, asset in core.MODEL_ASSET_FILES.items():
        asset_path = Path(
            hf_hub_download(
                core.MODEL_REPOSITORY,
                revision=core.MODEL_REVISION,
                filename=filename,
                local_files_only=local_files_only,
                token=False,
            )
        )
        if asset_path.stat().st_size != asset["bytes"]:
            raise RuntimeError(f"pinned model asset size mismatch: {filename}")
        if core.sha256_file(asset_path) != asset["sha256"]:
            raise RuntimeError(
                f"pinned model asset digest mismatch: {filename}"
            )

    specification = core.DATASET_FILES["validation"]
    validation_path = Path(
        hf_hub_download(
            core.DATASET_REPOSITORY,
            repo_type="dataset",
            revision=core.DATASET_REVISION,
            filename=specification["path"],
            local_files_only=local_files_only,
            token=False,
        )
    )
    if validation_path.stat().st_size != specification["bytes"]:
        raise RuntimeError("pinned validation dataset size mismatch")
    if core.sha256_file(validation_path) != specification["sha256"]:
        raise RuntimeError("pinned validation dataset digest mismatch")
    return {
        "modelSnapshot": model_path.parent,
        "modelWeights": model_path,
        "validation": validation_path,
    }


def run_app_proof(
    output_path: Path,
    *,
    device_requested: str,
    validation_start_block: int,
    validation_blocks: int,
    local_files_only: bool,
    primary_evidence_directory: Path,
) -> dict[str, Any]:
    core = _load_core()
    if device_requested != "mps":
        raise ValueError("the production app proof requires MPS")
    if validation_start_block < 64 or validation_start_block > 512:
        raise ValueError("validation start block is outside the app limits")
    if validation_blocks < 1 or validation_blocks > 32:
        raise ValueError("validation block count is outside the app limits")
    if not local_files_only:
        raise ValueError("the production app proof requires offline assets")
    if (
        primary_evidence_directory.parent.resolve()
        != output_path.parent.resolve()
        or primary_evidence_directory.name != "primary-evidence"
    ):
        raise ValueError("primary evidence must be beside the result file")
    primary_evidence_writer = core.PrimaryEvidenceWriter(
        primary_evidence_directory,
        result_filename=output_path.name,
    )

    import numpy as np
    import pyarrow
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(SEED)
    np.random.seed(SEED)
    if hasattr(torch, "use_deterministic_algorithms"):
        torch.use_deterministic_algorithms(True, warn_only=True)
    device = core._resolve_device(device_requested, torch)
    inputs = _download_validation_only(core, local_files_only)

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

    blocks, token_digest = core._token_blocks(
        tokenizer,
        inputs["validation"],
        validation_blocks,
        start_block=validation_start_block,
    )
    configuration = core.APP_CONFIGURATION
    candidate_grid = (configuration,)
    baselines: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for relative_index, block in enumerate(blocks):
        block_index = validation_start_block + relative_index
        print(
            f"validation block {relative_index + 1}/{len(blocks)} "
            f"(source block {block_index})",
            flush=True,
        )
        baseline, candidates = core._evaluate_block(
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

    aggregates = core._aggregate_phase(candidate_grid, records)
    selected: dict[str, Any] | None = configuration
    selection_error: str | None = None
    if (
        aggregates[0]["compressionRatioVsBF16"]
        < core.THRESHOLDS["minimumCompressionRatioVsBF16"]
    ):
        selected = None
        selection_error = "registered app candidate missed the compression gate"
    result: dict[str, Any] = {
        "schemaVersion": "corelm-voidtoken-v5-validation-development-v3",
        "status": "validation-only-development",
        "createdAt": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "testDataOpened": False,
        "protocol": {
            "modelRepository": core.MODEL_REPOSITORY,
            "modelRevision": core.MODEL_REVISION,
            "modelWeightsSHA256": core.MODEL_WEIGHTS_SHA256,
            "datasetRepository": core.DATASET_REPOSITORY,
            "datasetRevision": core.DATASET_REVISION,
            "split": "validation",
            "validationStartBlock": validation_start_block,
            "validationBlocks": validation_blocks,
            "thresholds": core.THRESHOLDS,
            "fullDevelopmentGrid": core.FULL_DEVELOPMENT_GRID,
            "evaluatedCandidateIndices": [REGISTERED_CANDIDATE_INDEX],
            "evaluatedGrid": [configuration],
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
            "hfHome": "configured" if os.environ.get("HF_HOME") else None,
            "seed": SEED,
        },
        "selectedTokenIdsSHA256": token_digest,
        "baselines": baselines,
        "records": records,
        "aggregates": aggregates,
        "selected": selected,
        "selectionError": selection_error,
    }
    result["primaryEvidence"] = primary_evidence_writer.finalize()
    result["resultSHA256"] = core.sha256_bytes(
        core.canonical_json_bytes(result)
    )
    core._exclusive_write_bytes(
        output_path,
        json.dumps(
            result,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n",
    )
    return result


def _summary(result: dict[str, Any]) -> str:
    aggregate = result["aggregates"][0]
    return "\n".join(
        (
            "Core LM app proof complete.",
            f"Result SHA-256: {result['resultSHA256']}",
            (
                "- schedule="
                f"{aggregate['configuration']['schedule']}: "
                f"{aggregate['compressionRatioVsBF16']:.3f}x, "
                f"delta NLL {aggregate['deltaNLLNatPerToken']:+.6f}, "
                f"top-1 {aggregate['top1Agreement']:.4f}, "
                f"{'PASS' if aggregate['pass'] else 'FAIL'}"
            ),
        )
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("mps",), required=True)
    parser.add_argument("--validation-start-block", type=int, required=True)
    parser.add_argument("--validation-blocks", type=int, required=True)
    parser.add_argument(
        "--candidate-index",
        type=int,
        choices=(REGISTERED_CANDIDATE_INDEX,),
        required=True,
    )
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument(
        "--primary-evidence-directory",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def main() -> int:
    group_identifier: int | None = None
    group_file: Path | None = None
    try:
        group_identifier = establish_worker_process_group()
        group_file = register_worker_process_group(group_identifier)
        arguments = parse_arguments()
        result = run_app_proof(
            arguments.output,
            device_requested=arguments.device,
            validation_start_block=arguments.validation_start_block,
            validation_blocks=arguments.validation_blocks,
            local_files_only=arguments.local_files_only,
            primary_evidence_directory=arguments.primary_evidence_directory,
        )
    except Exception as error:
        print(f"CORE LM APP PROOF FAILED: {error}", file=sys.stderr)
        return 1
    finally:
        remove_worker_process_group_registration(
            group_file, group_identifier
        )
    print(_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
