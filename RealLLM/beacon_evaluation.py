#!/usr/bin/env python3
"""Frozen real-model evaluation used by one-shot and regression runners."""

from __future__ import annotations

import json
import math
import os
import platform
import statistics
import subprocess
import zlib
from pathlib import Path
from typing import Any

import numpy as np

from RealLLM.beacon_protocol import PROJECT_ROOT, load_registration, sha256_file
from RealLLM.benchmark_real_llm import (
    BLOCK_TOKENS,
    DATASET_FILES,
    DATASET_REPOSITORY,
    DATASET_REVISION,
    MODEL_ASSET_FILES,
    MODEL_REPOSITORY,
    MODEL_REVISION,
    MODEL_WEIGHTS_BYTES,
    MODEL_WEIGHTS_SHA256,
    PREDICTIONS_PER_BLOCK,
    PREFILL_TOKENS,
    PrimaryEvidenceWriter,
    _aggregate_phase,
    _evaluate_block,
    _resolve_device,
    _token_blocks,
    canonical_json_bytes,
    sha256_bytes,
    validate_v5_container_manifest,
)


FROZEN_EVALUATION = {
    "attentionImplementation": "eager",
    "blockTokens": 512,
    "cacheCanonicalization": "FP32-to-BF16-to-FP32",
    "candidateConfigurationId": "4c7be8c836aa7257",
    "candidateConfigurationSHA256": (
        "4c7be8c836aa725722b51f66dce78af7a5094e887432e622b5322f7ca2cf0af8"
    ),
    "candidateDevelopmentGridIndex": 32,
    "compressionByteAccounting": "complete-container-bytes",
    "layers": 24,
    "predictionMode": "teacher-forced",
    "predictionsPerBlock": 128,
    "prefillTokens": 383,
    "trajectoryShapePerLayer": [383, 256],
    "windowBlocks": 32,
}
FROZEN_RUNTIME = {
    "huggingfaceHub": "1.25.1",
    "numpy": "2.5.1",
    "pyarrow": "23.0.1",
    "python": "3.12.13",
    "safetensors": "0.8.0",
    "tokenizers": "0.22.2",
    "torch": "2.13.0",
    "transformers": "5.14.1",
    "zlibCompileVersion": "1.2.12",
    "zlibRuntimeVersion": "1.2.12",
}
WILSON_Z_ONE_SIDED_95 = 1.6448536269514715
STUDENT_T_ONE_SIDED_95_DF31 = 1.6955187825458675


def _require_memory_headroom(minimum_percent: int) -> None:
    try:
        completed = subprocess.run(
            ["/usr/bin/memory_pressure", "-Q"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"cannot monitor macOS memory pressure: {error}") from error
    prefix = "System-wide memory free percentage:"
    matches = [
        line[len(prefix) :].strip().removesuffix("%")
        for line in completed.stdout.splitlines()
        if line.startswith(prefix)
    ]
    if len(matches) != 1 or not matches[0].isdigit():
        raise RuntimeError("macOS memory-pressure output has an unexpected format")
    if int(matches[0]) < minimum_percent:
        raise RuntimeError(
            f"system memory fell to {matches[0]}% free; "
            f"the frozen minimum is {minimum_percent}%"
        )


def _resolve_model_and_test(local_files_only: bool) -> tuple[Path, Path]:
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
            raise RuntimeError(f"pinned model asset digest mismatch: {filename}")
    test_specification = DATASET_FILES["test"]
    test_path = Path(
        hf_hub_download(
            DATASET_REPOSITORY,
            repo_type="dataset",
            revision=DATASET_REVISION,
            filename=test_specification["path"],
            local_files_only=local_files_only,
            token=False,
        )
    )
    if test_path.stat().st_size != test_specification["bytes"]:
        raise RuntimeError("pinned test dataset size mismatch")
    if sha256_file(test_path) != test_specification["sha256"]:
        raise RuntimeError("pinned test dataset digest mismatch")
    return model_path, test_path


def _load_runtime_dependencies() -> tuple[Any, ...]:
    import huggingface_hub
    import pyarrow
    import safetensors
    import tokenizers
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    return (
        pyarrow,
        huggingface_hub,
        safetensors,
        tokenizers,
        torch,
        transformers,
        AutoModelForCausalLM,
        AutoTokenizer,
    )


def validate_runtime_versions(
    torch_module: Any,
    transformers_module: Any,
    pyarrow_module: Any,
    huggingface_hub_module: Any,
    tokenizers_module: Any,
    safetensors_module: Any,
) -> None:
    registered_runtime = load_registration().get("runtime", {}).get("versions")
    if registered_runtime != FROZEN_RUNTIME:
        raise ValueError(
            "registered runtime versions differ from the frozen evaluator"
        )
    observed = {
        "huggingfaceHub": huggingface_hub_module.__version__,
        "numpy": np.__version__,
        "pyarrow": pyarrow_module.__version__,
        "python": platform.python_version(),
        "safetensors": safetensors_module.__version__,
        "tokenizers": tokenizers_module.__version__,
        "torch": torch_module.__version__,
        "transformers": transformers_module.__version__,
        "zlibCompileVersion": zlib.ZLIB_VERSION,
        "zlibRuntimeVersion": zlib.ZLIB_RUNTIME_VERSION,
    }
    if observed != registered_runtime:
        raise ValueError(
            "runtime differs from the frozen registration: "
            + json.dumps(observed, sort_keys=True)
        )


def prepare_runtime() -> dict[str, Any]:
    (
        pyarrow,
        huggingface_hub,
        safetensors,
        tokenizers,
        torch,
        transformers,
        AutoModelForCausalLM,
        AutoTokenizer,
    ) = _load_runtime_dependencies()
    validate_runtime_versions(
        torch,
        transformers,
        pyarrow,
        huggingface_hub,
        tokenizers,
        safetensors,
    )
    device = _resolve_device("mps", torch)
    if device != "mps":
        raise RuntimeError("beacon experiment requires Apple MPS")
    return {
        "pyarrow": pyarrow,
        "huggingface_hub": huggingface_hub,
        "safetensors": safetensors,
        "tokenizers": tokenizers,
        "torch": torch,
        "transformers": transformers,
        "AutoModelForCausalLM": AutoModelForCausalLM,
        "AutoTokenizer": AutoTokenizer,
        "device": device,
    }


def _wilson_lower(successes: int, trials: int) -> float:
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


def _structural_replay_passed(baselines: list[dict[str, Any]]) -> bool:
    return bool(baselines) and all(
        baseline.get("exactRebuildMaxAbsLogitDifference") == 0.0
        and baseline.get("exactRebuildTop1Identical") is True
        and baseline.get("layoutRebuildMaxAbsLogitDifference") == 0.0
        and baseline.get("layoutRebuildTop1Identical") is True
        for baseline in baselines
    )


def compute_confidence_and_verdict(
    records: list[dict[str, Any]],
    baselines: list[dict[str, Any]],
    aggregate: dict[str, Any],
    gates_definition: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, bool], bool]:
    if len(records) != 32 or len(baselines) != 32:
        raise ValueError("frozen held-out evaluation requires exactly 32 blocks")
    delta_values = [float(record["deltaNLLNatPerToken"]) for record in records]
    delta_mean = statistics.fmean(delta_values)
    delta_standard_deviation = statistics.stdev(delta_values)
    delta_upper = delta_mean + (
        STUDENT_T_ONE_SIDED_95_DF31
        * delta_standard_deviation
        / math.sqrt(len(delta_values))
    )
    prediction_tokens = sum(int(record["predictionTokens"]) for record in records)
    agreement_count = sum(int(record["top1AgreementCount"]) for record in records)
    block_top1_values = [
        int(record["top1AgreementCount"]) / int(record["predictionTokens"])
        for record in records
    ]
    block_top1_mean = statistics.fmean(block_top1_values)
    block_top1_standard_deviation = statistics.stdev(block_top1_values)
    block_top1_lower = block_top1_mean - (
        STUDENT_T_ONE_SIDED_95_DF31
        * block_top1_standard_deviation
        / math.sqrt(len(block_top1_values))
    )
    wilson_lower = _wilson_lower(agreement_count, prediction_tokens)
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
    gates = {
        "compressionRatioVsBF16": (
            float(aggregate["compressionRatioVsBF16"])
            >= gates_definition["minimumCompressionRatioVsBF16"]
        ),
        "deltaNLLNatPerToken": (
            float(aggregate["deltaNLLNatPerToken"])
            <= gates_definition["maximumDeltaNLLNatPerToken"]
        ),
        "blockwiseDeltaNLLUpperOneSided95": (
            delta_upper
            <= gates_definition["maximumBlockwiseDeltaNLLUpperOneSided95"]
        ),
        "top1Agreement": (
            float(aggregate["top1Agreement"])
            >= gates_definition["minimumTop1Agreement"]
        ),
        "blockwiseTop1LowerOneSided95": (
            block_top1_lower
            >= gates_definition["minimumBlockwiseTop1LowerOneSided95"]
        ),
        "wilsonLowerOneSided95": (
            wilson_lower >= gates_definition["minimumWilsonLowerOneSided95"]
        ),
        "structuralReplay": _structural_replay_passed(baselines),
    }
    return confidence, gates, all(gates.values())


def run_selected_window(
    start_block: int,
    *,
    local_files_only: bool,
    runtime: dict[str, Any] | None = None,
    retain_primary_evidence: bool = True,
) -> dict[str, Any]:
    registration = load_registration()
    configuration = registration["configuration"]
    gates_definition = registration["gates"]
    evaluation = registration.get("evaluation")
    if evaluation != FROZEN_EVALUATION:
        raise ValueError(
            "registered evaluation parameters differ from the frozen evaluator"
        )
    if registration.get("runtime", {}).get("versions") != FROZEN_RUNTIME:
        raise ValueError(
            "registered runtime versions differ from the frozen evaluator"
        )
    if (
        BLOCK_TOKENS != FROZEN_EVALUATION["blockTokens"]
        or PREFILL_TOKENS != FROZEN_EVALUATION["prefillTokens"]
        or PREDICTIONS_PER_BLOCK
        != FROZEN_EVALUATION["predictionsPerBlock"]
    ):
        raise RuntimeError("benchmark constants differ from frozen evaluation")
    configuration_sha256 = sha256_bytes(canonical_json_bytes(configuration))
    if (
        configuration_sha256
        != FROZEN_EVALUATION["candidateConfigurationSHA256"]
        or configuration_sha256[:16]
        != FROZEN_EVALUATION["candidateConfigurationId"]
    ):
        raise ValueError("candidate 32 identity differs from frozen evaluation")
    if type(start_block) is not int or start_block < 0:
        raise ValueError("selected start block must be a non-negative integer")
    runtime = runtime or prepare_runtime()
    torch = runtime["torch"]
    seed = int(registration["execution"]["seed"])
    torch.manual_seed(seed)
    np.random.seed(seed)
    if hasattr(torch, "use_deterministic_algorithms"):
        torch.use_deterministic_algorithms(True, warn_only=True)
    device = runtime["device"]
    model_path, test_path = _resolve_model_and_test(local_files_only)
    verified_snapshot = model_path.parent
    tokenizer = runtime["AutoTokenizer"].from_pretrained(
        verified_snapshot,
        local_files_only=True,
        trust_remote_code=False,
    )
    model = runtime["AutoModelForCausalLM"].from_pretrained(
        verified_snapshot,
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.float32,
        attn_implementation="eager",
    ).to(device)
    model.eval()
    if model.config._attn_implementation != "eager":
        raise RuntimeError("model did not retain eager attention")
    if str(next(model.parameters()).dtype) != "torch.float32":
        raise RuntimeError("model dtype differs from frozen float32")

    tokenization = registration["corpus"]["tokenization"]
    window_blocks = int(evaluation["windowBlocks"])
    blocks, token_digest = _token_blocks(
        tokenizer,
        test_path,
        window_blocks,
        start_block=start_block,
        expected_token_count=tokenization["tokenCount"],
        expected_full_blocks=tokenization["fullBlocks"],
        expected_remainder_tokens=tokenization["remainderTokens"],
        expected_all_token_ids_sha256=tokenization["allTokenIdsSHA256"],
    )
    primary_writer: PrimaryEvidenceWriter | None = None
    if retain_primary_evidence:
        primary_directory = PROJECT_ROOT / registration["execution"][
            "primaryEvidenceDirectory"
        ]
        primary_writer = PrimaryEvidenceWriter(
            primary_directory,
            result_filename="outcome.json",
        )
    baselines: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    grid = (configuration,)
    minimum_free_memory = int(
        registration["runtime"]["resourcePolicy"]["minimumFreeMemoryPercent"]
    )
    for relative_index, block in enumerate(blocks):
        _require_memory_headroom(minimum_free_memory)
        source_index = start_block + relative_index
        print(
            f"beacon held-out block {relative_index + 1}/{window_blocks} "
            f"(test source {source_index})",
            flush=True,
        )
        baseline, candidates = _evaluate_block(
            block,
            source_index,
            grid,
            model=model,
            device=device,
            torch_module=torch,
            primary_evidence_writer=primary_writer,
        )
        baselines.append(baseline)
        records.extend(candidates)
        if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
            torch.mps.empty_cache()
        _require_memory_headroom(minimum_free_memory)
    aggregate = _aggregate_phase(grid, records)[0]
    confidence, gates, passed = compute_confidence_and_verdict(
        records,
        baselines,
        aggregate,
        gates_definition,
    )
    for record in records:
        validate_v5_container_manifest(record, configuration)
    primary_evidence = primary_writer.finalize() if primary_writer else None
    return {
        "source": {
            "split": "test",
            "startBlock": start_block,
            "blocks": window_blocks,
            "endBlockExclusive": start_block + window_blocks,
            "selectedTokenIdsSHA256": token_digest,
        },
        "configuration": configuration,
        "configurationSHA256": configuration_sha256,
        "gatesDefinition": gates_definition,
        "environment": {
            "attentionImplementation": model.config._attn_implementation,
            "device": device,
            "hfHome": "configured" if os.environ.get("HF_HOME") else None,
            "huggingfaceHub": runtime["huggingface_hub"].__version__,
            "machine": platform.machine(),
            "modelDtype": str(next(model.parameters()).dtype),
            "numpy": np.__version__,
            "platform": platform.platform(),
            "pyarrow": runtime["pyarrow"].__version__,
            "python": platform.python_version(),
            "safetensors": runtime["safetensors"].__version__,
            "seed": seed,
            "tokenizers": runtime["tokenizers"].__version__,
            "torch": torch.__version__,
            "transformers": runtime["transformers"].__version__,
            "zlibCompileVersion": zlib.ZLIB_VERSION,
            "zlibRuntimeVersion": zlib.ZLIB_RUNTIME_VERSION,
        },
        "baselines": baselines,
        "records": records,
        "aggregate": aggregate,
        "confidence": confidence,
        "gates": gates,
        "pass": passed,
        "primaryEvidence": primary_evidence,
    }
