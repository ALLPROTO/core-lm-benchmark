#!/usr/bin/env python3
"""Run the repository-recorded exploratory real-LLM KV-cache pilot.

Heavy dependencies are imported only by ``main``/``run_registered_pilot`` so
the codec and protocol helpers remain testable in the lightweight core CI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_CORE = PROJECT_ROOT / "BenchmarkCore"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RealLLM.codecs import PackedGroupQuantBackend  # noqa: E402
from RealLLM.voidtoken_v5 import VoidTokenV5Backend  # noqa: E402


SCHEMA_VERSION = "corelm-real-llm-kv-pilot-v1"
IMPLEMENTATION_VERSION = "0.4.0-pilot"
MODEL_REPOSITORY = "Qwen/Qwen2.5-0.5B"
MODEL_REVISION = "060db6499f32faf8b98477b0a26969ef7d8b9987"
MODEL_WEIGHTS_SHA256 = (
    "88c142557820ccad55bb59756bfcfcf891de9cc6202816bd346445188a0ed342"
)
MODEL_WEIGHTS_BYTES = 988_097_824
MODEL_ASSET_FILES = {
    "config.json": {
        "bytes": 681,
        "sha256": (
            "479dcf0c5286339e41ad3992cd08ae88a467c4187587936248e2b7c96283484b"
        ),
    },
    "generation_config.json": {
        "bytes": 138,
        "sha256": (
            "8c970692323e3ea0e9b8b0a4dca79388d31226e41f83c9fd6014804280ebf6e8"
        ),
    },
    "merges.txt": {
        "bytes": 1_671_839,
        "sha256": (
            "599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3"
        ),
    },
    "tokenizer.json": {
        "bytes": 7_031_645,
        "sha256": (
            "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539"
        ),
    },
    "tokenizer_config.json": {
        "bytes": 7_228,
        "sha256": (
            "c91efca15ceff6e9ee9424db58a6f59cd41294e550a86cbd07e3c1fb500b34f9"
        ),
    },
    "vocab.json": {
        "bytes": 2_776_833,
        "sha256": (
            "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910"
        ),
    },
}
DATASET_REPOSITORY = "Salesforce/wikitext"
DATASET_REVISION = "b08601e04326c79dfdd32d625aee71d232d685c3"
DATASET_CONFIGURATION = "wikitext-2-raw-v1"
DATASET_FILES = {
    "validation": {
        "path": "wikitext-2-raw-v1/validation-00000-of-00001.parquet",
        "sha256": "204929b7ff9d6184953f867dedb860e40aa69c078fc1e54b3baaa8fb28511c4c",
        "bytes": 657_209,
    },
    "test": {
        "path": "wikitext-2-raw-v1/test-00000-of-00001.parquet",
        "sha256": "5f1bea067869d04849c0f975a2b29c4ff47d867f484f5010ea5e861eab246d91",
        "bytes": 732_610,
    },
}

BLOCK_TOKENS = 512
PREFILL_TOKENS = 383
PREDICTIONS_PER_BLOCK = BLOCK_TOKENS - PREFILL_TOKENS - 1
VALIDATION_BLOCKS = 4
TEST_BLOCKS = 8
REGISTERED_TEST_START_BLOCK = 8
V5_PROTECTED_TEST_START_BLOCK = 384
V5_PROTECTED_TEST_END_BLOCK = 448

THRESHOLDS = {
    "minimumCompressionRatioVsBF16": 2.0,
    "maximumDeltaNLLNatPerToken": 0.01,
    "minimumTop1Agreement": 0.99,
}


def _legacy_voidtoken_types() -> tuple[type[Any], type[Any]]:
    """Resolve the source-only legacy codec only when it is selected.

    The final macOS app packages only the real-LLM v5 path.  Keeping this
    import lazy lets that package load and run without shipping the source-only
    ``BenchmarkCore`` workbench, while source checkouts retain the historical
    v3/v4 comparison backend byte-for-byte.
    """
    module_path = BENCHMARK_CORE / "corelm_benchmark.py"
    if not module_path.is_file():
        raise RuntimeError(
            "legacy VoidToken backend is unavailable because the source-only "
            "BenchmarkCore workbench is not packaged"
        )
    benchmark_core = str(BENCHMARK_CORE)
    if benchmark_core not in sys.path:
        sys.path.insert(0, benchmark_core)
    try:
        from corelm_benchmark import (  # type: ignore[import-not-found]
            EncodedRepresentation,
            VoidTokenBackend,
        )
    except ImportError as error:
        raise RuntimeError(
            "legacy VoidToken backend could not be loaded from BenchmarkCore"
        ) from error
    return EncodedRepresentation, VoidTokenBackend

VOIDTOKEN_GRID = (
    {"backend": "voidtoken", "topK": 32, "qmax": 127, "keyframeInterval": 32},
    {"backend": "voidtoken", "topK": 32, "qmax": 127, "keyframeInterval": 64},
    {"backend": "voidtoken", "topK": 48, "qmax": 127, "keyframeInterval": 64},
    {"backend": "voidtoken", "topK": 64, "qmax": 127, "keyframeInterval": 64},
    {"backend": "voidtoken", "topK": 64, "qmax": 127, "keyframeInterval": 128},
)

LAYER_SENSITIVITY_ORDER = (
    8,
    0,
    1,
    4,
    16,
    9,
    2,
    20,
    11,
    21,
    3,
    14,
    22,
    13,
    17,
    12,
    19,
    10,
    15,
    23,
    5,
    7,
    6,
    18,
)


def _mixed_precision_configuration(
    eight_bit_layers: int, low_bits: int
) -> dict[str, Any]:
    selected = set(LAYER_SENSITIVITY_ORDER[:eight_bit_layers])
    return {
        "backend": "group-quant",
        "bitsByLayer": [
            8 if layer_index in selected else low_bits
            for layer_index in range(24)
        ],
        "groupSize": 16,
        "scaleCompression": "zlib-9",
        "schedule": (
            f"validation-kl-top-{eight_bit_layers}-8bit-rest-{low_bits}bit"
        ),
    }


GROUP_QUANT_GRID = tuple(
    {
        "backend": "group-quant",
        "bits": bits,
        "groupSize": group_size,
        "scaleCompression": scale_compression,
    }
    for bits, group_size, scale_compression in (
        (4, 16, "none"),
        (4, 32, "none"),
        (5, 16, "none"),
        (5, 32, "none"),
        (6, 16, "none"),
        (6, 32, "none"),
        (7, 16, "zlib-9"),
        (7, 32, "none"),
        (7, 64, "none"),
    )
) + (
    _mixed_precision_configuration(16, 5),
    _mixed_precision_configuration(17, 5),
)


@dataclass(frozen=True)
class RuntimeOptions:
    device: str = "auto"
    validation_blocks: int = VALIDATION_BLOCKS
    test_blocks: int = TEST_BLOCKS
    test_start_block: int = REGISTERED_TEST_START_BLOCK
    local_files_only: bool = False
    seed: int = 20260729

    def validate(self) -> None:
        if self.device not in {"auto", "cpu", "mps", "cuda"}:
            raise ValueError("device must be auto, cpu, mps, or cuda")
        if self.validation_blocks < 1:
            raise ValueError("validation_blocks must be at least one")
        if self.test_blocks < 1:
            raise ValueError("test_blocks must be at least one")
        if self.test_start_block < 0:
            raise ValueError("test_start_block must be non-negative")
        test_end_block = self.test_start_block + self.test_blocks
        if (
            self.test_start_block < V5_PROTECTED_TEST_END_BLOCK
            and test_end_block > V5_PROTECTED_TEST_START_BLOCK
        ):
            raise ValueError(
                "test range overlaps the prospectively frozen VoidToken v5 "
                "holdout/reserve"
            )


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _exclusive_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)


def configuration_id(configuration: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(configuration))[:16]


def validate_registered_protocol() -> None:
    if BLOCK_TOKENS <= PREFILL_TOKENS + 1:
        raise ValueError("block must leave at least one continuation prediction")
    if PREDICTIONS_PER_BLOCK != 128:
        raise ValueError("registered protocol must produce 128 predictions")
    identifiers = [
        configuration_id(configuration)
        for configuration in (*VOIDTOKEN_GRID, *GROUP_QUANT_GRID)
    ]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("candidate grid contains duplicate configurations")
    for configuration in VOIDTOKEN_GRID:
        if configuration["qmax"] != 127:
            raise ValueError("registered VoidToken grid must use int8 tokens")
    for configuration in GROUP_QUANT_GRID:
        bits = configuration.get("bits")
        bits_by_layer = configuration.get("bitsByLayer")
        if (bits is None) == (bits_by_layer is None):
            raise ValueError(
                "group-quant must declare either bits or bitsByLayer"
            )
        if bits is not None and bits not in {4, 5, 6, 7, 8}:
            raise ValueError("unsupported registered group-quant bit width")
        if bits_by_layer is not None and (
            not isinstance(bits_by_layer, list)
            or len(bits_by_layer) != 24
            or any(item not in {5, 8} for item in bits_by_layer)
        ):
            raise ValueError("invalid registered per-layer bit schedule")
        if 256 % configuration["groupSize"]:
            raise ValueError("group size must divide the Qwen KV width")
        if configuration["scaleCompression"] not in {"none", "zlib-9"}:
            raise ValueError("unsupported registered scale compression")


def _weighted_average(records: Iterable[dict[str, Any]], key: str) -> float:
    numerator = 0.0
    denominator = 0
    for record in records:
        tokens = int(record["predictionTokens"])
        value = float(record[key])
        if tokens <= 0 or not math.isfinite(value):
            raise ValueError(f"invalid {key} aggregation input")
        numerator += value * tokens
        denominator += tokens
    if denominator == 0 or not math.isfinite(numerator):
        raise ValueError("cannot aggregate zero prediction tokens")
    return numerator / denominator


def _finite_sum(records: Iterable[dict[str, Any]], key: str) -> float:
    result = sum(float(record[key]) for record in records)
    if not math.isfinite(result):
        raise ValueError(f"non-finite aggregate for {key}")
    return result


def _finite_exp(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    try:
        result = math.exp(value)
    except OverflowError as error:
        raise ValueError(f"{label} is outside the supported range") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} produced a non-finite exponential")
    return result


def aggregate_candidate_records(
    configuration: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    if not records:
        raise ValueError("candidate aggregation requires at least one record")
    dense_bf16_bytes = sum(int(record["denseBF16Bytes"]) for record in records)
    encoded_bytes = sum(int(record["encodedFileBytes"]) for record in records)
    tokens = sum(int(record["predictionTokens"]) for record in records)
    agreements = sum(int(record["top1AgreementCount"]) for record in records)
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
    normalized_rmse = math.sqrt(
        difference_sum_squares / max(reference_sum_squares, 1e-30)
    )
    cosine = dot_product / max(
        math.sqrt(reference_sum_squares * candidate_sum_squares), 1e-30
    )
    baseline_nll = _weighted_average(records, "baselineNLLNatPerToken")
    candidate_nll = _weighted_average(records, "candidateNLLNatPerToken")
    result = {
        "configuration": configuration,
        "configurationId": configuration_id(configuration),
        "blocks": len(records),
        "predictionTokens": tokens,
        "denseBF16Bytes": dense_bf16_bytes,
        "encodedFileBytes": encoded_bytes,
        "compressionRatioVsBF16": dense_bf16_bytes / max(encoded_bytes, 1),
        "baselineNLLNatPerToken": baseline_nll,
        "candidateNLLNatPerToken": candidate_nll,
        "deltaNLLNatPerToken": candidate_nll - baseline_nll,
        "perplexityRatio": _finite_exp(
            candidate_nll - baseline_nll, "aggregate delta NLL"
        ),
        "top1Agreement": agreements / max(tokens, 1),
        "meanKLDivergenceNat": _weighted_average(
            records, "meanKLDivergenceNat"
        ),
        "cacheNormalizedRMSE": normalized_rmse,
        "cacheCosineSimilarity": cosine,
        "cacheMaximumAbsoluteError": max(
            float(record["cacheMaximumAbsoluteError"]) for record in records
        ),
        "encodeNanoseconds": sum(
            int(record["encodeNanoseconds"]) for record in records
        ),
        "decodeNanoseconds": sum(
            int(record["decodeNanoseconds"]) for record in records
        ),
        "modelContinuationNanoseconds": sum(
            int(record["modelContinuationNanoseconds"]) for record in records
        ),
        "allPayloadDigestsUnique": len(
            {record["payloadSHA256"] for record in records}
        )
        == len(records),
        "pass": False,
    }
    result["gates"] = {
        "compression": (
            result["compressionRatioVsBF16"]
            >= THRESHOLDS["minimumCompressionRatioVsBF16"]
        ),
        "deltaNLL": (
            result["deltaNLLNatPerToken"]
            <= THRESHOLDS["maximumDeltaNLLNatPerToken"]
        ),
        "top1Agreement": (
            result["top1Agreement"] >= THRESHOLDS["minimumTop1Agreement"]
        ),
    }
    result["pass"] = all(result["gates"].values())
    return result


def select_validation_configuration(
    aggregates: list[dict[str, Any]], backend: str
) -> dict[str, Any]:
    eligible = [
        aggregate
        for aggregate in aggregates
        if aggregate["configuration"]["backend"] == backend
        and aggregate["compressionRatioVsBF16"]
        >= THRESHOLDS["minimumCompressionRatioVsBF16"]
    ]
    if not eligible:
        raise ValueError(
            f"no {backend} validation candidate reaches the compression gate"
        )
    validation_passes = [aggregate for aggregate in eligible if aggregate["pass"]]
    pool = validation_passes or eligible
    # Selection sees validation only. Prefer configurations that meet every
    # validation gate. If a family has none (a useful negative result), retain
    # its lowest-KL >=2x candidate so test still quantifies that family.
    return min(
        pool,
        key=lambda aggregate: (
            aggregate["meanKLDivergenceNat"],
            -aggregate["top1Agreement"],
            aggregate["encodedFileBytes"],
            aggregate["configurationId"],
        ),
    )


def _cache_error_accumulators(
    reference_layers: list[np.ndarray],
    candidate_layers: list[np.ndarray],
) -> dict[str, float]:
    if len(reference_layers) != len(candidate_layers):
        raise ValueError("cache layer count mismatch")
    difference_sum_squares = 0.0
    reference_sum_squares = 0.0
    candidate_sum_squares = 0.0
    dot_product = 0.0
    maximum_absolute_error = 0.0
    for reference, candidate in zip(reference_layers, candidate_layers):
        if reference.shape != candidate.shape:
            raise ValueError("cache layer shape mismatch")
        reference64 = np.asarray(reference, dtype=np.float64)
        candidate64 = np.asarray(candidate, dtype=np.float64)
        difference = candidate64 - reference64
        difference_sum_squares += float(np.sum(difference * difference))
        reference_sum_squares += float(np.sum(reference64 * reference64))
        candidate_sum_squares += float(np.sum(candidate64 * candidate64))
        dot_product += float(np.sum(reference64 * candidate64))
        maximum_absolute_error = max(
            maximum_absolute_error, float(np.max(np.abs(difference)))
        )
    return {
        "cacheDifferenceSumSquares": difference_sum_squares,
        "cacheReferenceSumSquares": reference_sum_squares,
        "cacheCandidateSumSquares": candidate_sum_squares,
        "cacheDotProduct": dot_product,
        "cacheMaximumAbsoluteError": maximum_absolute_error,
    }


def _mean_kl_divergence(reference_logits: Any, candidate_logits: Any) -> float:
    """Compute KL(reference || candidate) in bounded CPU chunks."""
    import torch
    import torch.nn.functional as functional

    total = 0.0
    rows = int(reference_logits.shape[0] * reference_logits.shape[1])
    reference = reference_logits.reshape(rows, -1)
    candidate = candidate_logits.reshape(rows, -1)
    for start in range(0, rows, 8):
        stop = min(rows, start + 8)
        reference_log_probabilities = functional.log_softmax(
            reference[start:stop].float(), dim=-1
        )
        candidate_log_probabilities = functional.log_softmax(
            candidate[start:stop].float(), dim=-1
        )
        divergence = (
            reference_log_probabilities.exp()
            * (reference_log_probabilities - candidate_log_probabilities)
        ).sum(dim=-1)
        total += float(divergence.sum().item())
    return total / max(rows, 1)


def _nll(logits: Any, targets: Any) -> float:
    import torch.nn.functional as functional

    return float(
        functional.cross_entropy(
            logits.reshape(-1, logits.shape[-1]).float(),
            targets.reshape(-1),
            reduction="mean",
        ).item()
    )


def _resolve_device(requested: str, torch_module: Any) -> str:
    if requested != "auto":
        if requested == "mps" and not torch_module.backends.mps.is_available():
            raise RuntimeError("MPS was requested but is unavailable")
        if requested == "cuda" and not torch_module.cuda.is_available():
            raise RuntimeError("CUDA was requested but is unavailable")
        return requested
    if torch_module.backends.mps.is_available():
        return "mps"
    if torch_module.cuda.is_available():
        return "cuda"
    return "cpu"


def _download_and_verify_inputs(local_files_only: bool) -> dict[str, Path]:
    from huggingface_hub import hf_hub_download

    paths: dict[str, Path] = {}
    model_path = Path(
        hf_hub_download(
            MODEL_REPOSITORY,
            revision=MODEL_REVISION,
            filename="model.safetensors",
            local_files_only=local_files_only,
        )
    )
    if model_path.stat().st_size != MODEL_WEIGHTS_BYTES:
        raise RuntimeError("pinned model weight size mismatch")
    if sha256_file(model_path) != MODEL_WEIGHTS_SHA256:
        raise RuntimeError("pinned model weight digest mismatch")
    paths["modelWeights"] = model_path
    paths["modelSnapshot"] = model_path.parent
    for filename, asset in MODEL_ASSET_FILES.items():
        asset_path = Path(
            hf_hub_download(
                MODEL_REPOSITORY,
                revision=MODEL_REVISION,
                filename=filename,
                local_files_only=local_files_only,
            )
        )
        if asset_path.stat().st_size != asset["bytes"]:
            raise RuntimeError(f"pinned model asset size mismatch: {filename}")
        if sha256_file(asset_path) != asset["sha256"]:
            raise RuntimeError(
                f"pinned model asset digest mismatch: {filename}"
            )
    for split, specification in DATASET_FILES.items():
        path = Path(
            hf_hub_download(
                DATASET_REPOSITORY,
                repo_type="dataset",
                revision=DATASET_REVISION,
                filename=specification["path"],
                local_files_only=local_files_only,
            )
        )
        if path.stat().st_size != specification["bytes"]:
            raise RuntimeError(f"pinned {split} dataset size mismatch")
        if sha256_file(path) != specification["sha256"]:
            raise RuntimeError(f"pinned {split} dataset digest mismatch")
        paths[split] = path
    return paths


def _token_blocks(
    tokenizer: Any, parquet_path: Path, count: int, *, start_block: int = 0
) -> tuple[list[list[int]], str]:
    import pyarrow.parquet as parquet

    rows = parquet.read_table(parquet_path, columns=["text"]).column("text")
    corpus = "\n\n".join(rows.to_pylist())
    previous_maximum = tokenizer.model_max_length
    tokenizer.model_max_length = sys.maxsize
    try:
        token_ids = tokenizer(
            corpus,
            add_special_tokens=False,
            return_attention_mask=False,
            return_token_type_ids=False,
        )["input_ids"]
    finally:
        tokenizer.model_max_length = previous_maximum
    required = (start_block + count) * BLOCK_TOKENS
    if len(token_ids) < required:
        raise RuntimeError(
            f"dataset split has {len(token_ids)} tokens; {required} required"
        )
    start_token = start_block * BLOCK_TOKENS
    selected = token_ids[start_token:required]
    blocks = [
        selected[offset : offset + BLOCK_TOKENS]
        for offset in range(0, len(selected), BLOCK_TOKENS)
    ]
    digest_values = np.asarray(selected, dtype="<u4")
    return blocks, sha256_bytes(digest_values.tobytes())


def _extract_cache_layers(
    dynamic_cache: Any, torch_module: Any
) -> tuple[list[np.ndarray], list[np.ndarray], list[bytes], int, int]:
    original_layers: list[np.ndarray] = []
    canonical_layers: list[np.ndarray] = []
    canonical_bf16_bytes: list[bytes] = []
    heads = 0
    head_dimension = 0
    if len(dynamic_cache.layers) != 24:
        raise RuntimeError(
            f"expected 24 Qwen cache layers, got {len(dynamic_cache.layers)}"
        )
    for layer in dynamic_cache.layers:
        keys = layer.keys.detach().float().cpu()
        values = layer.values.detach().float().cpu()
        if tuple(keys.shape) != (1, 2, PREFILL_TOKENS, 64):
            raise RuntimeError(
                f"unexpected Qwen key-cache shape {tuple(keys.shape)}"
            )
        if values.shape != keys.shape:
            raise RuntimeError("unexpected Qwen DynamicCache tensor shape")
        if not torch_module.isfinite(keys).all() or not torch_module.isfinite(
            values
        ).all():
            raise RuntimeError("Qwen DynamicCache contains non-finite values")
        heads = int(keys.shape[1])
        tokens = int(keys.shape[2])
        head_dimension = int(keys.shape[3])
        key_trajectory = (
            keys[0]
            .permute(1, 0, 2)
            .contiguous()
            .reshape(tokens, heads * head_dimension)
        )
        value_trajectory = (
            values[0]
            .permute(1, 0, 2)
            .contiguous()
            .reshape(tokens, heads * head_dimension)
        )
        joined = torch_module.cat((key_trajectory, value_trajectory), dim=1)
        original_layers.append(
            np.ascontiguousarray(joined.numpy(), dtype=np.float32)
        )
        canonical_bf16 = joined.to(torch_module.bfloat16).contiguous()
        canonical_bf16_bytes.append(
            canonical_bf16.view(torch_module.uint16)
            .numpy()
            .astype("<u2", copy=False)
            .tobytes()
        )
        canonical_layers.append(
            np.ascontiguousarray(canonical_bf16.float().numpy(), dtype=np.float32)
        )
    return (
        original_layers,
        canonical_layers,
        canonical_bf16_bytes,
        heads,
        head_dimension,
    )


def _dynamic_cache_from_layers(
    layers: list[np.ndarray],
    *,
    model: Any,
    device: str,
    heads: int,
    head_dimension: int,
    torch_module: Any,
) -> Any:
    from transformers import DynamicCache

    if len(layers) != 24:
        raise RuntimeError(f"decoded cache has {len(layers)} layers, expected 24")
    cache = DynamicCache(config=model.config)
    key_width = heads * head_dimension
    for layer_index, trajectory in enumerate(layers):
        tokens, width = trajectory.shape
        if tokens != PREFILL_TOKENS:
            raise RuntimeError(
                f"decoded cache has {tokens} tokens, expected {PREFILL_TOKENS}"
            )
        if width != key_width * 2:
            raise RuntimeError("decoded cache trajectory has unexpected width")
        keys = (
            torch_module.from_numpy(
                np.ascontiguousarray(trajectory[:, :key_width])
            )
            .reshape(tokens, heads, head_dimension)
            .permute(1, 0, 2)
            .unsqueeze(0)
            .to(device)
        )
        values = (
            torch_module.from_numpy(
                np.ascontiguousarray(trajectory[:, key_width:])
            )
            .reshape(tokens, heads, head_dimension)
            .permute(1, 0, 2)
            .unsqueeze(0)
            .to(device)
        )
        cache.update(keys, values, layer_index)
    if int(cache.get_seq_length()) != PREFILL_TOKENS:
        raise RuntimeError("rebuilt DynamicCache length mismatch")
    return cache


def _continuation_logits_from_cache(
    model: Any,
    continuation_input_ids: Any,
    cache: Any,
    *,
    device: str,
    torch_module: Any,
) -> tuple[Any, int]:
    cached_tokens = int(cache.get_seq_length())
    continuation_tokens = int(continuation_input_ids.shape[1])
    cache_position = torch_module.arange(
        cached_tokens,
        cached_tokens + continuation_tokens,
        dtype=torch_module.long,
        device=device,
    )
    attention_mask = torch_module.ones(
        (1, cached_tokens + continuation_tokens),
        dtype=torch_module.long,
        device=device,
    )
    started = time.perf_counter_ns()
    with torch_module.inference_mode():
        logits = model(
            continuation_input_ids,
            past_key_values=cache,
            attention_mask=attention_mask,
            cache_position=cache_position,
            position_ids=cache_position.unsqueeze(0),
            use_cache=False,
            return_dict=True,
        ).logits.float().cpu()
    return logits, time.perf_counter_ns() - started


def _continuation_logits(
    model: Any,
    continuation_input_ids: Any,
    cache_layers: list[np.ndarray],
    *,
    device: str,
    heads: int,
    head_dimension: int,
    torch_module: Any,
) -> tuple[Any, int]:
    cache = _dynamic_cache_from_layers(
        cache_layers,
        model=model,
        device=device,
        heads=heads,
        head_dimension=head_dimension,
        torch_module=torch_module,
    )
    return _continuation_logits_from_cache(
        model,
        continuation_input_ids,
        cache,
        device=device,
        torch_module=torch_module,
    )


def _encode_layers(
    layers: list[np.ndarray], configuration: dict[str, Any]
) -> tuple[list[np.ndarray], dict[str, Any]]:
    reconstructed: list[np.ndarray] = []
    digest = hashlib.sha256()
    container_manifest: list[dict[str, Any]] = []
    encoded_file_bytes = 0
    payload_bytes = 0
    encode_nanoseconds = 0
    decode_nanoseconds = 0
    for layer_index, layer in enumerate(layers):
        if configuration["backend"] == "voidtoken":
            _, voidtoken_backend = _legacy_voidtoken_types()
            representation = voidtoken_backend.encode(
                layer,
                top_k=int(configuration["topK"]),
                qmax=int(configuration["qmax"]),
                keyframe_interval=int(configuration["keyframeInterval"]),
            )
        elif configuration["backend"] == "voidtoken-v5":
            bits_by_layer = configuration.get("bitsByLayer")
            bits_by_kv_by_layer = configuration.get("bitsByKVByLayer")
            if bits_by_layer is not None and bits_by_kv_by_layer is not None:
                raise ValueError(
                    "voidtoken-v5 cannot combine layer and KV bit schedules"
                )
            if bits_by_kv_by_layer is not None:
                bits = None
                bits_by_column_group = [
                    int(value)
                    for value in bits_by_kv_by_layer[layer_index]
                ]
            else:
                bits = (
                    int(bits_by_layer[layer_index])
                    if bits_by_layer is not None
                    else int(configuration["bits"])
                )
                bits_by_column_group = None
            representation = VoidTokenV5Backend.encode(
                layer,
                bits=bits,
                bits_by_column_group=bits_by_column_group,
                group_size=int(configuration["groupSize"]),
                transform_block_size=int(
                    configuration["transformBlockSize"]
                ),
                layer_index=layer_index,
                scale_compression=str(configuration["scaleCompression"]),
                code_compression=str(configuration["codeCompression"]),
                sign_mode=str(configuration.get("signMode", "shake256")),
            )
        elif configuration["backend"] == "group-quant":
            bits_by_layer = configuration.get("bitsByLayer")
            bits = (
                int(bits_by_layer[layer_index])
                if bits_by_layer is not None
                else int(configuration["bits"])
            )
            representation = PackedGroupQuantBackend.encode(
                layer,
                bits=bits,
                group_size=int(configuration["groupSize"]),
                scale_compression=str(configuration["scaleCompression"]),
            )
        else:
            raise ValueError(f"unknown backend {configuration['backend']!r}")
        container = representation.to_bytes()
        if configuration["backend"] == "voidtoken":
            encoded_representation, _ = _legacy_voidtoken_types()
            parsed = encoded_representation.from_bytes(container)
        elif configuration["backend"] == "voidtoken-v5":
            parsed = VoidTokenV5Backend.from_bytes(container)
        else:
            parsed = PackedGroupQuantBackend.from_bytes(container)
        if parsed.to_bytes() != container:
            raise RuntimeError("codec parser did not preserve canonical bytes")
        if parsed.payload != representation.payload:
            raise RuntimeError("codec parser changed the encoded payload")
        digest.update(layer_index.to_bytes(4, "little"))
        digest.update(len(container).to_bytes(8, "little"))
        digest.update(container)
        reconstructed.append(
            np.ascontiguousarray(parsed.reconstructed, dtype=np.float32)
        )
        encoded_file_bytes += len(container)
        payload_bytes += int(representation.payload_bytes)
        encode_nanoseconds += int(representation.encode_nanoseconds)
        decode_nanoseconds += int(representation.decode_nanoseconds)
        if configuration["backend"] == "voidtoken-v5":
            container_manifest.append(
                {
                    "layerIndex": layer_index,
                    "metadata": representation.metadata,
                    "payloadBytes": int(representation.payload_bytes),
                    "containerBytes": len(container),
                    "containerSHA256": sha256_bytes(container),
                }
            )
    encoding = {
        "encodedFileBytes": encoded_file_bytes,
        "payloadBytes": payload_bytes,
        "payloadSHA256": digest.hexdigest(),
        "encodeNanoseconds": encode_nanoseconds,
        "decodeNanoseconds": decode_nanoseconds,
    }
    if configuration["backend"] == "voidtoken-v5":
        encoding["containerManifest"] = container_manifest
        encoding["containerManifestSHA256"] = sha256_bytes(
            canonical_json_bytes(container_manifest)
        )
    return reconstructed, encoding


_V5_CONTAINER_MANIFEST_ENTRY_KEYS = {
    "layerIndex",
    "metadata",
    "payloadBytes",
    "containerBytes",
    "containerSHA256",
}


def _zlib_compress_bound(source_bytes: int) -> int:
    """Return zlib's documented conservative deflate upper bound."""
    if type(source_bytes) is not int or source_bytes < 0:
        raise ValueError("zlib source length must be a non-negative integer")
    return (
        source_bytes
        + (source_bytes >> 12)
        + (source_bytes >> 14)
        + (source_bytes >> 25)
        + 13
    )


def validate_v5_container_manifest(
    record: dict[str, Any],
    configuration: dict[str, Any],
    *,
    expected_layers: int = 24,
    expected_shape: tuple[int, int] = (PREFILL_TOKENS, 256),
) -> None:
    """Independently reconstruct every v5 container's byte accounting.

    Payload bytes are intentionally not embedded in an evidence JSON document.
    Their per-layer SHA-256 commitments remain in the exact codec metadata, and
    each full-container commitment is recorded separately.  Container length is
    nevertheless exactly reconstructible as the fixed eight-byte header,
    canonical metadata JSON, and the declared payload length.
    """
    if not isinstance(record, dict):
        raise ValueError("candidate record must be an object")
    manifest = record.get("containerManifest")
    if (
        not isinstance(manifest, list)
        or len(manifest) != expected_layers
    ):
        raise ValueError(
            f"containerManifest must contain exactly {expected_layers} layers"
        )
    if sha256_bytes(canonical_json_bytes(manifest)) != record.get(
        "containerManifestSHA256"
    ):
        raise ValueError("containerManifestSHA256 is inconsistent")

    total_payload_bytes = 0
    total_container_bytes = 0
    container_digests: set[str] = set()
    for expected_layer_index, entry in enumerate(manifest):
        if (
            not isinstance(entry, dict)
            or set(entry) != _V5_CONTAINER_MANIFEST_ENTRY_KEYS
        ):
            raise ValueError(
                f"layer {expected_layer_index} manifest fields are not exact"
            )
        if entry.get("layerIndex") != expected_layer_index:
            raise ValueError("containerManifest layer order is not canonical")
        metadata = entry.get("metadata")
        try:
            VoidTokenV5Backend.validate_metadata_layout(metadata)
        except ValueError as error:
            raise ValueError(
                f"layer {expected_layer_index} metadata is invalid: {error}"
            ) from error
        if metadata.get("layerIndex") != expected_layer_index:
            raise ValueError(
                f"layer {expected_layer_index} metadata index is inconsistent"
            )
        if metadata.get("shape") != list(expected_shape):
            raise ValueError(
                f"layer {expected_layer_index} cache shape is inconsistent"
            )
        expected_bits_by_kv = configuration.get("bitsByKVByLayer")
        expected_bits_by_layer = configuration.get("bitsByLayer")
        if expected_bits_by_kv is not None:
            if (
                metadata.get("bitsByColumnGroup")
                != expected_bits_by_kv[expected_layer_index]
                or "bits" in metadata
            ):
                raise ValueError(
                    f"layer {expected_layer_index} bit layout is inconsistent"
                )
        else:
            expected_bits = (
                expected_bits_by_layer[expected_layer_index]
                if expected_bits_by_layer is not None
                else configuration.get("bits")
            )
            if metadata.get("bits") != expected_bits:
                raise ValueError(
                    f"layer {expected_layer_index} bit width is inconsistent"
                )
        expected_metadata_fields = {
            "groupSize": configuration.get("groupSize"),
            "transformBlockSize": configuration.get("transformBlockSize"),
            "scaleCompression": configuration.get("scaleCompression"),
            "codeCompression": configuration.get("codeCompression"),
            "signMode": configuration.get("signMode", "shake256"),
        }
        for name, expected in expected_metadata_fields.items():
            if metadata.get(name) != expected:
                raise ValueError(
                    f"layer {expected_layer_index} {name} is inconsistent"
                )

        payload_bytes = entry.get("payloadBytes")
        container_bytes = entry.get("containerBytes")
        container_sha256 = entry.get("containerSHA256")
        if (
            type(payload_bytes) is not int
            or payload_bytes <= 0
            or payload_bytes != metadata.get("payloadBytes")
        ):
            raise ValueError(
                f"layer {expected_layer_index} payload bytes are inconsistent"
            )
        expected_container_bytes = (
            8 + len(canonical_json_bytes(metadata)) + payload_bytes
        )
        if (
            type(container_bytes) is not int
            or container_bytes != expected_container_bytes
        ):
            raise ValueError(
                f"layer {expected_layer_index} container bytes are inconsistent"
            )
        if (
            not isinstance(container_sha256, str)
            or len(container_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in container_sha256
            )
        ):
            raise ValueError(
                f"layer {expected_layer_index} container SHA-256 is invalid"
            )
        if container_sha256 in container_digests:
            raise ValueError("container SHA-256 commitments are not unique")
        container_digests.add(container_sha256)

        if metadata["scaleCompression"] == "zlib-9" and (
            metadata["storedScaleBytes"]
            > _zlib_compress_bound(metadata["scaleBytes"])
        ):
            raise ValueError(
                f"layer {expected_layer_index} scale stream is impossible"
            )
        if metadata["codeCompression"] == "zlib-9" and (
            metadata["storedCodeBytes"]
            > _zlib_compress_bound(metadata["packedBytes"])
        ):
            raise ValueError(
                f"layer {expected_layer_index} code stream is impossible"
            )
        total_payload_bytes += payload_bytes
        total_container_bytes += container_bytes

    if total_payload_bytes != record.get("payloadBytes"):
        raise ValueError("record payloadBytes does not equal its 24-layer sum")
    if total_container_bytes != record.get("encodedFileBytes"):
        raise ValueError(
            "record encodedFileBytes does not equal its 24-layer sum"
        )


def _evaluate_candidate(
    configuration: dict[str, Any],
    canonical_layers: list[np.ndarray],
    baseline_logits: Any,
    targets_cpu: Any,
    *,
    model: Any,
    continuation_input_ids: Any,
    device: str,
    heads: int,
    head_dimension: int,
    torch_module: Any,
    block_index: int,
    token_digest: str,
    cache_digest: str,
) -> dict[str, Any]:
    reconstructed, encoding = _encode_layers(canonical_layers, configuration)
    candidate_logits, continuation_nanoseconds = _continuation_logits(
        model,
        continuation_input_ids,
        reconstructed,
        device=device,
        heads=heads,
        head_dimension=head_dimension,
        torch_module=torch_module,
    )
    baseline_nll = _nll(baseline_logits, targets_cpu)
    candidate_nll = _nll(candidate_logits, targets_cpu)
    baseline_top1 = baseline_logits.argmax(dim=-1)
    candidate_top1 = candidate_logits.argmax(dim=-1)
    agreement_count = int((baseline_top1 == candidate_top1).sum().item())
    cache_errors = _cache_error_accumulators(canonical_layers, reconstructed)
    dense_bf16_bytes = sum(layer.size * 2 for layer in canonical_layers)
    return {
        "blockIndex": block_index,
        "tokenIdsSHA256": token_digest,
        "canonicalCacheBF16SHA256": cache_digest,
        "configurationId": configuration_id(configuration),
        "predictionTokens": int(targets_cpu.numel()),
        "denseBF16Bytes": dense_bf16_bytes,
        **encoding,
        **cache_errors,
        "baselineNLLNatPerToken": baseline_nll,
        "candidateNLLNatPerToken": candidate_nll,
        "deltaNLLNatPerToken": candidate_nll - baseline_nll,
        "perplexityRatio": math.exp(candidate_nll - baseline_nll),
        "top1AgreementCount": agreement_count,
        "top1Agreement": agreement_count / max(int(targets_cpu.numel()), 1),
        "meanKLDivergenceNat": _mean_kl_divergence(
            baseline_logits, candidate_logits
        ),
        "modelContinuationNanoseconds": continuation_nanoseconds,
    }


def _evaluate_block(
    token_ids: list[int],
    block_index: int,
    configurations: tuple[dict[str, Any], ...],
    *,
    model: Any,
    device: str,
    torch_module: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ids_cpu = torch_module.tensor(token_ids, dtype=torch_module.long).unsqueeze(0)
    ids = ids_cpu.to(device)
    prefix_ids = ids[:, :PREFILL_TOKENS]
    continuation_input_ids = ids[:, PREFILL_TOKENS:-1]
    targets_cpu = ids_cpu[:, PREFILL_TOKENS + 1 :]
    with torch_module.inference_mode():
        prefill = model(
            prefix_ids,
            use_cache=True,
            return_dict=True,
        )
    (
        original_layers,
        canonical_layers,
        canonical_bf16_bytes,
        heads,
        head_dimension,
    ) = _extract_cache_layers(prefill.past_key_values, torch_module)
    direct_logits, direct_runtime = _continuation_logits_from_cache(
        model,
        continuation_input_ids,
        prefill.past_key_values,
        device=device,
        torch_module=torch_module,
    )
    del prefill
    original_logits, original_rebuild_runtime = _continuation_logits(
        model,
        continuation_input_ids,
        original_layers,
        device=device,
        heads=heads,
        head_dimension=head_dimension,
        torch_module=torch_module,
    )
    layout_rebuild_difference = float(
        (direct_logits - original_logits).abs().max().item()
    )
    layout_rebuild_top1_identical = bool(
        torch_module.equal(
            direct_logits.argmax(dim=-1), original_logits.argmax(dim=-1)
        )
    )
    if layout_rebuild_difference != 0.0 or not layout_rebuild_top1_identical:
        raise RuntimeError(
            "flatten/rebuild layout changed direct FP32 cache continuation"
        )
    baseline_logits, baseline_runtime = _continuation_logits(
        model,
        continuation_input_ids,
        canonical_layers,
        device=device,
        heads=heads,
        head_dimension=head_dimension,
        torch_module=torch_module,
    )
    exact_replay_logits, _ = _continuation_logits(
        model,
        continuation_input_ids,
        [layer.copy() for layer in canonical_layers],
        device=device,
        heads=heads,
        head_dimension=head_dimension,
        torch_module=torch_module,
    )
    exact_difference = float(
        (baseline_logits - exact_replay_logits).abs().max().item()
    )
    token_digest = sha256_bytes(
        np.asarray(token_ids, dtype="<u4").tobytes()
    )
    cache_hasher = hashlib.sha256()
    for layer_index, raw in enumerate(canonical_bf16_bytes):
        cache_hasher.update(layer_index.to_bytes(4, "little"))
        cache_hasher.update(len(raw).to_bytes(8, "little"))
        cache_hasher.update(raw)
    cache_digest = cache_hasher.hexdigest()
    native_bf16_agreement_count = int(
        (
            direct_logits.argmax(dim=-1)
            == baseline_logits.argmax(dim=-1)
        )
        .sum()
        .item()
    )
    prediction_tokens = int(targets_cpu.numel())
    native_bf16_baseline = {
        "blockIndex": block_index,
        "tokenIdsSHA256": token_digest,
        "canonicalCacheBF16SHA256": cache_digest,
        "layers": len(canonical_layers),
        "kvHeads": heads,
        "headDimension": head_dimension,
        "trajectoryShapePerLayer": list(canonical_layers[0].shape),
        "predictionTokens": prediction_tokens,
        "denseBF16Bytes": sum(layer.size * 2 for layer in canonical_layers),
        "originalFP32NLLNatPerToken": _nll(direct_logits, targets_cpu),
        "canonicalBF16NLLNatPerToken": _nll(baseline_logits, targets_cpu),
        "nativeBF16DeltaNLLNatPerToken": (
            _nll(baseline_logits, targets_cpu)
            - _nll(direct_logits, targets_cpu)
        ),
        "nativeBF16Top1Agreement": (
            native_bf16_agreement_count / prediction_tokens
        ),
        "exactRebuildMaxAbsLogitDifference": exact_difference,
        "exactRebuildTop1Identical": bool(
            torch_module.equal(
                baseline_logits.argmax(dim=-1),
                exact_replay_logits.argmax(dim=-1),
            )
        ),
        "layoutRebuildMaxAbsLogitDifference": layout_rebuild_difference,
        "layoutRebuildTop1Identical": layout_rebuild_top1_identical,
        "originalContinuationNanoseconds": direct_runtime,
        "originalRebuildContinuationNanoseconds": original_rebuild_runtime,
        "baselineContinuationNanoseconds": baseline_runtime,
    }
    candidate_records = [
        _evaluate_candidate(
            configuration,
            canonical_layers,
            baseline_logits,
            targets_cpu,
            model=model,
            continuation_input_ids=continuation_input_ids,
            device=device,
            heads=heads,
            head_dimension=head_dimension,
            torch_module=torch_module,
            block_index=block_index,
            token_digest=token_digest,
            cache_digest=cache_digest,
        )
        for configuration in configurations
    ]
    return native_bf16_baseline, candidate_records


def _aggregate_phase(
    configurations: tuple[dict[str, Any], ...],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    aggregates: list[dict[str, Any]] = []
    for configuration in configurations:
        identifier = configuration_id(configuration)
        matching = [
            record
            for record in records
            if record["configurationId"] == identifier
        ]
        aggregates.append(aggregate_candidate_records(configuration, matching))
    return aggregates


def run_registered_pilot(
    output_path: Path, options: RuntimeOptions
) -> dict[str, Any]:
    options.validate()
    validate_registered_protocol()

    import pyarrow
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(options.seed)
    np.random.seed(options.seed)
    if hasattr(torch, "use_deterministic_algorithms"):
        torch.use_deterministic_algorithms(True, warn_only=True)
    device = _resolve_device(options.device, torch)
    input_paths = _download_and_verify_inputs(options.local_files_only)

    tokenizer = AutoTokenizer.from_pretrained(
        input_paths["modelSnapshot"],
        local_files_only=True,
        trust_remote_code=False,
    )
    model = AutoModelForCausalLM.from_pretrained(
        input_paths["modelSnapshot"],
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.float32,
        attn_implementation="eager",
    ).to(device)
    model.eval()

    validation_blocks, validation_tokens_digest = _token_blocks(
        tokenizer, input_paths["validation"], options.validation_blocks
    )
    test_blocks, test_tokens_digest = _token_blocks(
        tokenizer,
        input_paths["test"],
        options.test_blocks,
        start_block=options.test_start_block,
    )
    candidate_grid = (*VOIDTOKEN_GRID, *GROUP_QUANT_GRID)

    validation_baselines: list[dict[str, Any]] = []
    validation_records: list[dict[str, Any]] = []
    for block_index, block in enumerate(validation_blocks):
        print(
            f"validation block {block_index + 1}/{len(validation_blocks)}",
            flush=True,
        )
        baseline, records = _evaluate_block(
            block,
            block_index,
            candidate_grid,
            model=model,
            device=device,
            torch_module=torch,
        )
        validation_baselines.append(baseline)
        validation_records.extend(records)
    validation_aggregates = _aggregate_phase(
        candidate_grid, validation_records
    )
    selected_voidtoken = select_validation_configuration(
        validation_aggregates, "voidtoken"
    )
    selected_group_quant = select_validation_configuration(
        validation_aggregates, "group-quant"
    )
    selected_configurations = (
        selected_voidtoken["configuration"],
        selected_group_quant["configuration"],
    )

    test_baselines: list[dict[str, Any]] = []
    test_records: list[dict[str, Any]] = []
    for relative_index, block in enumerate(test_blocks):
        block_index = options.test_start_block + relative_index
        print(
            f"test block {relative_index + 1}/{len(test_blocks)} "
            f"(source block {block_index})",
            flush=True,
        )
        baseline, records = _evaluate_block(
            block,
            block_index,
            selected_configurations,
            model=model,
            device=device,
            torch_module=torch,
        )
        test_baselines.append(baseline)
        test_records.extend(records)
    test_aggregates = _aggregate_phase(
        selected_configurations, test_records
    )

    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "implementationVersion": IMPLEMENTATION_VERSION,
        "evidenceClass": "registered-real-llm-pilot",
        "createdAt": created_at,
        "registrationDisclosure": {
            "externallyTimestampedBeforeTest": False,
            "status": "exploratory-pilot",
            "statement": (
                "Validation and test were separated and the selected "
                "configuration was held fixed for test, but no independent "
                "external timestamp existed before the first test execution."
            ),
        },
        "claimBoundary": (
            "Qwen2.5-0.5B KV-cache replay on pinned WikiText-2 blocks; "
            "separate from the 115 synthetic Core LM runs"
        ),
        "protocol": {
            "model": {
                "repository": MODEL_REPOSITORY,
                "revision": MODEL_REVISION,
                "weightsSHA256": MODEL_WEIGHTS_SHA256,
                "weightsBytes": MODEL_WEIGHTS_BYTES,
                "license": "Apache-2.0",
            },
            "dataset": {
                "repository": DATASET_REPOSITORY,
                "revision": DATASET_REVISION,
                "configuration": DATASET_CONFIGURATION,
                "files": DATASET_FILES,
                "join": "text rows joined with two LF characters",
                "tokenization": "add_special_tokens=false",
                "selection": (
                    "validation starts at block 0; registered test starts at "
                    "the declared testStartBlock; all blocks are non-overlapping"
                ),
            },
            "tensorTap": {
                "name": "per-layer-key-value-cache",
                "sourceShape": "[1, 2, 383, 64] for K and V",
                "codecShape": "[383, 256] per layer",
                "canonicalInput": "round-to-BF16 then exact conversion to float32",
                "layersEncodedSeparately": True,
                "behavioralReplay": "decoded DynamicCache drives 128 next-token predictions",
            },
            "blockTokens": BLOCK_TOKENS,
            "prefillTokens": PREFILL_TOKENS,
            "predictionsPerBlock": PREDICTIONS_PER_BLOCK,
            "validationBlocks": options.validation_blocks,
            "testBlocks": options.test_blocks,
            "testStartBlock": options.test_start_block,
            "thresholds": THRESHOLDS,
            "selectionRule": (
                "Within each backend family, retain validation configurations "
                "with compression >=2x and prefer those passing every "
                "validation gate; if none pass, keep the family as a negative "
                "control. Minimize mean KL, with higher top-1 agreement, fewer "
                "bytes, and configuration ID as tie breakers. Test is run once."
            ),
            "validationGrid": list(candidate_grid),
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
            "attentionImplementation": model.config._attn_implementation,
            "modelDtype": str(next(model.parameters()).dtype),
            "seed": options.seed,
            "hfHome": (
                "configured" if os.environ.get("HF_HOME") else None
            ),
        },
        "validation": {
            "selectedTokenIdsSHA256": validation_tokens_digest,
            "baselines": validation_baselines,
            "records": validation_records,
            "aggregates": validation_aggregates,
            "selected": {
                "voidtoken": selected_voidtoken["configuration"],
                "groupQuant": selected_group_quant["configuration"],
            },
        },
        "test": {
            "selectedTokenIdsSHA256": test_tokens_digest,
            "baselines": test_baselines,
            "records": test_records,
            "aggregates": test_aggregates,
            "allPassed": all(aggregate["pass"] for aggregate in test_aggregates),
        },
    }
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
        "Real Qwen KV-cache pilot complete.",
        f"Result SHA-256: {result['resultSHA256']}",
    ]
    for aggregate in result["test"]["aggregates"]:
        configuration = aggregate["configuration"]
        lines.append(
            f"- {configuration['backend']} {configuration}: "
            f"{aggregate['compressionRatioVsBF16']:.3f}x BF16, "
            f"delta NLL {aggregate['deltaNLLNatPerToken']:+.6f}, "
            f"top-1 {aggregate['top1Agreement']:.4f}, "
            f"verdict {'PASS' if aggregate['pass'] else 'FAIL'}"
        )
    return "\n".join(lines)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "real-llm-results" / "aggregate.json",
    )
    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "mps", "cuda"),
        default="auto",
    )
    parser.add_argument(
        "--validation-blocks", type=int, default=VALIDATION_BLOCKS
    )
    parser.add_argument("--test-blocks", type=int, default=TEST_BLOCKS)
    parser.add_argument(
        "--test-start-block", type=int, default=REGISTERED_TEST_START_BLOCK
    )
    parser.add_argument("--local-files-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        result = run_registered_pilot(
            arguments.output,
            RuntimeOptions(
                device=arguments.device,
                validation_blocks=arguments.validation_blocks,
                test_blocks=arguments.test_blocks,
                test_start_block=arguments.test_start_block,
                local_files_only=arguments.local_files_only,
            ),
        )
    except Exception as error:  # report one clear CLI failure
        print(f"REAL-LLM BENCHMARK FAILED: {error}", file=sys.stderr)
        return 1
    print(_summary(result))
    return 0 if result["test"]["allPassed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
