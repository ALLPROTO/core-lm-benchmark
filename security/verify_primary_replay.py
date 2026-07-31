#!/usr/bin/env python3
"""Heavy clean-room replay of retained Core LM app primary evidence.

The implementation imports neither the benchmark writer nor either codec
module.  It independently resolves the pinned model/dataset, reconstructs the
registered token slice, decodes every retained VTL5 container, rebuilds both
baseline and candidate KV caches, and reruns all 1,024 model decisions.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import platform
import stat
import struct
import sys
import zlib
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from security.verify_primary_evidence import (  # noqa: E402
    verify_primary_evidence,
)


MODEL_REPOSITORY = "Qwen/Qwen2.5-0.5B"
MODEL_REVISION = "060db6499f32faf8b98477b0a26969ef7d8b9987"
MODEL_FILES = {
    "model.safetensors": (
        988_097_824,
        "88c142557820ccad55bb59756bfcfcf891de9cc6202816bd346445188a0ed342",
    ),
    "config.json": (
        681,
        "479dcf0c5286339e41ad3992cd08ae88a467c4187587936248e2b7c96283484b",
    ),
    "generation_config.json": (
        138,
        "8c970692323e3ea0e9b8b0a4dca79388d31226e41f83c9fd6014804280ebf6e8",
    ),
    "merges.txt": (
        1_671_839,
        "599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3",
    ),
    "tokenizer.json": (
        7_031_645,
        "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    ),
    "tokenizer_config.json": (
        7_228,
        "c91efca15ceff6e9ee9424db58a6f59cd41294e550a86cbd07e3c1fb500b34f9",
    ),
    "vocab.json": (
        2_776_833,
        "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910",
    ),
}
DATASET_REPOSITORY = "Salesforce/wikitext"
DATASET_REVISION = "b08601e04326c79dfdd32d625aee71d232d685c3"
VALIDATION_FILE = "wikitext-2-raw-v1/validation-00000-of-00001.parquet"
VALIDATION_BYTES = 657_209
VALIDATION_SHA256 = (
    "204929b7ff9d6184953f867dedb860e40aa69c078fc1e54b3baaa8fb28511c4c"
)
SELECTED_TOKEN_IDS_SHA256 = (
    "1bb36c91d441379596361ae779ca0542c85457e9902a290a6ab6945cb2513453"
)
EXPECTED_VERSIONS = {
    "numpy": "2.5.1",
    "pyarrow": "23.0.1",
    "torch": "2.13.0",
    "transformers": "5.14.1",
    "huggingface-hub": "1.25.1",
}
BLOCK_INDICES = tuple(range(64, 72))
BLOCK_TOKENS = 512
PREFILL_TOKENS = 383
PREDICTIONS = 128
LAYERS = 24
VOCAB_SIZE = 151_936
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_CONTAINER_BYTES = 8 * 1024 * 1024
LOSS_ABSOLUTE_TOLERANCE = 2e-5
LOSS_RELATIVE_TOLERANCE = 2e-6


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON value is forbidden: {value}")


def _reject_duplicate_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path, maximum_bytes: int) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path.name} is missing or symlinked")
    size = path.stat().st_size
    if size <= 0 or size > maximum_bytes:
        raise ValueError(f"{path.name} exceeds its resource bound")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path.name} is invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _canonical_json(value: Any) -> bytes:
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


def _verified_cache_file(
    path: Path,
    *,
    hf_home: Path,
    expected_bytes: int,
    expected_sha256: str,
    label: str,
) -> Path:
    if not path.exists():
        raise ValueError(f"pinned {label} is missing from the offline cache")
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(hf_home.resolve(strict=True))
    except ValueError as error:
        raise ValueError(f"pinned {label} escapes HF_HOME") from error
    status = resolved.stat()
    if (
        not stat.S_ISREG(status.st_mode)
        or status.st_uid not in {0, os.getuid()}
        or status.st_size != expected_bytes
        or status.st_mode & 0o022
    ):
        raise ValueError(f"pinned {label} has unsafe type, mode, or size")
    if _sha256_file(resolved) != expected_sha256:
        raise ValueError(f"pinned {label} digest is inconsistent")
    return path


def _resolve_pinned_inputs(hf_home: Path) -> tuple[Path, Path]:
    from huggingface_hub import hf_hub_download

    if hf_home.is_symlink() or not hf_home.is_dir():
        raise ValueError("HF_HOME is missing or symlinked")
    home_status = hf_home.stat()
    if home_status.st_uid != os.getuid() or home_status.st_mode & 0o022:
        raise ValueError("HF_HOME is not private and owner-controlled")
    model_snapshot: Path | None = None
    for filename, (expected_bytes, expected_sha256) in MODEL_FILES.items():
        path = Path(
            hf_hub_download(
                MODEL_REPOSITORY,
                revision=MODEL_REVISION,
                filename=filename,
                local_files_only=True,
                token=False,
            )
        )
        _verified_cache_file(
            path,
            hf_home=hf_home,
            expected_bytes=expected_bytes,
            expected_sha256=expected_sha256,
            label=f"model asset {filename}",
        )
        if model_snapshot is None:
            model_snapshot = path.parent
        elif path.parent != model_snapshot:
            raise ValueError("pinned model assets resolved to different snapshots")
    validation = Path(
        hf_hub_download(
            DATASET_REPOSITORY,
            repo_type="dataset",
            revision=DATASET_REVISION,
            filename=VALIDATION_FILE,
            local_files_only=True,
            token=False,
        )
    )
    _verified_cache_file(
        validation,
        hf_home=hf_home,
        expected_bytes=VALIDATION_BYTES,
        expected_sha256=VALIDATION_SHA256,
        label="validation parquet",
    )
    if model_snapshot is None:
        raise ValueError("pinned model snapshot could not be resolved")
    return model_snapshot, validation


def _decompress_canonical(
    stored: bytes, expected_bytes: int, label: str
) -> bytes:
    decompressor = zlib.decompressobj()
    try:
        raw = decompressor.decompress(stored, expected_bytes + 1)
        if len(raw) > expected_bytes or decompressor.unconsumed_tail:
            raise ValueError(f"decompressed {label} exceeds its bound")
        raw += decompressor.flush(expected_bytes + 1 - len(raw))
    except zlib.error as error:
        raise ValueError(f"{label} is not a valid zlib stream") from error
    if (
        len(raw) != expected_bytes
        or not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
        or zlib.compress(raw, level=9) != stored
    ):
        raise ValueError(f"{label} is not canonical zlib-9")
    return raw


def _walsh_hadamard(values: Any, numpy_module: Any) -> Any:
    transformed = numpy_module.asarray(values, dtype=numpy_module.float64).copy()
    width = int(transformed.shape[-1])
    if width <= 0 or width & (width - 1):
        raise ValueError("Hadamard width is not a power of two")
    flattened = transformed.reshape(-1, width)
    half = 1
    while half < width:
        stride = half * 2
        for start in range(0, width, stride):
            left = flattened[:, start : start + half].copy()
            right = flattened[:, start + half : start + stride].copy()
            flattened[:, start : start + half] = left + right
            flattened[:, start + half : start + stride] = left - right
        half = stride
    transformed /= math.sqrt(width)
    return transformed


def _decode_container(raw: bytes, layer_index: int, numpy_module: Any) -> Any:
    label = f"layer {layer_index}"
    if len(raw) <= 8 or len(raw) > MAX_CONTAINER_BYTES:
        raise ValueError(f"{label} container length is invalid")
    magic, metadata_length = struct.unpack_from("<4sI", raw)
    if magic != b"VTL5" or metadata_length <= 0 or metadata_length > 1024 * 1024:
        raise ValueError(f"{label} container header is invalid")
    metadata_end = 8 + metadata_length
    if metadata_end >= len(raw):
        raise ValueError(f"{label} container metadata is truncated")
    metadata_bytes = raw[8:metadata_end]
    try:
        metadata = json.loads(
            metadata_bytes.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} metadata is invalid JSON") from error
    if not isinstance(metadata, dict) or _canonical_json(metadata) != metadata_bytes:
        raise ValueError(f"{label} metadata is not canonical JSON")

    bits = 9 if layer_index in {0, 8} else 8
    code_count = 383 * 256
    packed_bytes = code_count if bits == 8 else code_count + code_count // 8
    expected = {
        "bits": bits,
        "codeCompression": "zlib-9",
        "codeCount": code_count,
        "codeMapping": "zigzag-symmetric-v1",
        "dtype": "float32",
        "format": "voidtoken-rotated-entropy-v5",
        "groupSize": 128,
        "groupsPerRow": 2,
        "layerIndex": layer_index,
        "packedBytes": packed_bytes,
        "packing": (
            "lsb-first-v1"
            if bits == 8
            else "byte-low-plus-lsb-high-fields-v1"
        ),
        "quantization": "symmetric-max-abs-v1",
        "scaleBytes": 383 * 2 * 2,
        "scaleCompression": "zlib-9",
        "scaleCount": 383 * 2,
        "scaleDtype": "float16-le",
        "shape": [383, 256],
        "signDerivation": "shake256-layer-column-v1",
        "signMode": "none",
        "transform": "normalized-walsh-hadamard-v1",
        "transformBlockSize": 128,
    }
    if any(metadata.get(name) != value for name, value in expected.items()):
        raise ValueError(f"{label} metadata differs from the frozen codec")
    expected_keys = set(expected) | {
        "inputSha256",
        "payloadBytes",
        "payloadSha256",
        "reconstructionSha256",
        "storedCodeBytes",
        "storedScaleBytes",
    }
    if set(metadata) != expected_keys:
        raise ValueError(f"{label} metadata fields are not exact")
    payload = raw[metadata_end:]
    stored_scale_bytes = metadata["storedScaleBytes"]
    stored_code_bytes = metadata["storedCodeBytes"]
    if (
        type(stored_scale_bytes) is not int
        or type(stored_code_bytes) is not int
        or stored_scale_bytes <= 0
        or stored_code_bytes <= 0
        or metadata["payloadBytes"] != len(payload)
        or stored_scale_bytes + stored_code_bytes != len(payload)
        or _sha256_bytes(payload) != metadata["payloadSha256"]
    ):
        raise ValueError(f"{label} payload accounting is inconsistent")
    scale_raw = _decompress_canonical(
        payload[:stored_scale_bytes], expected["scaleBytes"], f"{label} scales"
    )
    code_raw = _decompress_canonical(
        payload[stored_scale_bytes:], packed_bytes, f"{label} codes"
    )
    scales = numpy_module.frombuffer(scale_raw, dtype="<f2").reshape(383, 2)
    if (
        not numpy_module.all(numpy_module.isfinite(scales))
        or numpy_module.any(scales < numpy_module.float16(0.0))
        or numpy_module.any(numpy_module.signbit(scales))
    ):
        raise ValueError(f"{label} contains invalid scales")
    if bits == 8:
        codes = numpy_module.frombuffer(code_raw, dtype=numpy_module.uint8)
    else:
        low = numpy_module.frombuffer(
            code_raw[:code_count], dtype=numpy_module.uint8
        ).astype(numpy_module.uint16)
        high_packed = numpy_module.frombuffer(
            code_raw[code_count:], dtype=numpy_module.uint8
        )
        high = numpy_module.unpackbits(
            high_packed, bitorder="little"
        )[:code_count].astype(numpy_module.uint16)
        codes = low | (high << numpy_module.uint16(8))
    qmax = (1 << (bits - 1)) - 1
    if codes.size != code_count or numpy_module.any(codes > 2 * qmax):
        raise ValueError(f"{label} contains an unused quantization code")
    integer_codes = codes.astype(numpy_module.int32)
    quantized = numpy_module.where(
        (integer_codes & numpy_module.int32(1)) == 0,
        integer_codes // 2,
        -((integer_codes + 1) // 2),
    ).reshape(383, 2, 128)
    if numpy_module.any(
        (scales == numpy_module.float16(0.0))
        & numpy_module.any(quantized != 0, axis=2)
    ):
        raise ValueError(f"{label} zero-scale group has non-zero codes")
    transformed = (
        quantized.astype(numpy_module.float64)
        * scales.astype(numpy_module.float64)[:, :, numpy_module.newaxis]
    )
    reconstructed = _walsh_hadamard(transformed, numpy_module).reshape(383, 256)
    reconstructed = numpy_module.ascontiguousarray(
        reconstructed, dtype=numpy_module.float32
    )
    reconstruction_digest = _sha256_bytes(
        numpy_module.ascontiguousarray(reconstructed, dtype="<f4").tobytes()
    )
    if reconstruction_digest != metadata["reconstructionSha256"]:
        raise ValueError(f"{label} reconstruction digest is inconsistent")
    return reconstructed, metadata


def _extract_canonical_layers(prefill: Any, torch_module: Any, numpy_module: Any):
    if len(prefill.past_key_values.layers) != LAYERS:
        raise ValueError("model did not return exactly 24 cache layers")
    layers = []
    raw_bf16 = []
    for layer in prefill.past_key_values.layers:
        keys = layer.keys.detach().float().cpu()
        values = layer.values.detach().float().cpu()
        if tuple(keys.shape) != (1, 2, PREFILL_TOKENS, 64) or values.shape != keys.shape:
            raise ValueError("model returned an unexpected Qwen cache shape")
        joined = torch_module.cat(
            (
                keys[0].permute(1, 0, 2).contiguous().reshape(383, 128),
                values[0].permute(1, 0, 2).contiguous().reshape(383, 128),
            ),
            dim=1,
        )
        bf16 = joined.to(torch_module.bfloat16).contiguous()
        raw_bf16.append(
            bf16.view(torch_module.uint16)
            .numpy()
            .astype("<u2", copy=False)
            .tobytes()
        )
        layers.append(
            numpy_module.ascontiguousarray(
                bf16.float().numpy(), dtype=numpy_module.float32
            )
        )
    return layers, raw_bf16


def _cache_from_layers(layers: list[Any], model: Any, torch_module: Any):
    from transformers import DynamicCache

    cache = DynamicCache(config=model.config)
    for layer_index, trajectory in enumerate(layers):
        if trajectory.shape != (383, 256):
            raise ValueError("decoded replay cache has an unexpected shape")
        keys = (
            torch_module.from_numpy(trajectory[:, :128].copy())
            .reshape(383, 2, 64)
            .permute(1, 0, 2)
            .unsqueeze(0)
            .to("mps")
        )
        values = (
            torch_module.from_numpy(trajectory[:, 128:].copy())
            .reshape(383, 2, 64)
            .permute(1, 0, 2)
            .unsqueeze(0)
            .to("mps")
        )
        cache.update(keys, values, layer_index)
    if int(cache.get_seq_length()) != PREFILL_TOKENS:
        raise ValueError("rebuilt replay cache has an unexpected length")
    return cache


def _model_token_metrics(
    model: Any,
    continuation_ids: Any,
    targets: Any,
    layers: list[Any],
    torch_module: Any,
) -> tuple[list[float], list[int]]:
    import torch.nn.functional as functional

    cache = _cache_from_layers(layers, model, torch_module)
    positions = torch_module.arange(383, 511, dtype=torch_module.long, device="mps")
    attention = torch_module.ones((1, 511), dtype=torch_module.long, device="mps")
    with torch_module.inference_mode():
        logits = model(
            continuation_ids,
            past_key_values=cache,
            attention_mask=attention,
            cache_position=positions,
            position_ids=positions.unsqueeze(0),
            use_cache=False,
            return_dict=True,
        ).logits.float().cpu()
    losses = functional.cross_entropy(
        logits.reshape(-1, logits.shape[-1]),
        targets.reshape(-1),
        reduction="none",
    ).tolist()
    top1 = logits.argmax(dim=-1).reshape(-1).tolist()
    del logits, cache
    return [float(value) for value in losses], [int(value) for value in top1]


def _loss_close(observed: Any, expected: float) -> bool:
    return type(observed) in {int, float} and math.isfinite(float(observed)) and math.isclose(
        float(observed),
        expected,
        rel_tol=LOSS_RELATIVE_TOLERANCE,
        abs_tol=LOSS_ABSOLUTE_TOLERANCE,
    )


def verify_primary_replay(run_directory: Path, hf_home: Path) -> dict[str, Any]:
    verify_primary_evidence(run_directory)
    run = run_directory.resolve(strict=True)
    result_path = run / "validation-064-071.json"
    result = _load_json(result_path, MAX_JSON_BYTES)
    token_document = _load_json(
        run / "primary-evidence" / "token-metrics.json", MAX_JSON_BYTES
    )
    token_blocks = token_document.get("blocks")
    if not isinstance(token_blocks, list) or len(token_blocks) != 8:
        raise ValueError("primary token metrics do not contain eight blocks")

    import importlib.metadata
    import numpy as np
    import pyarrow
    import pyarrow.parquet as parquet
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    observed_versions = {
        "numpy": np.__version__,
        "pyarrow": pyarrow.__version__,
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "huggingface-hub": importlib.metadata.version("huggingface-hub"),
    }
    if observed_versions != EXPECTED_VERSIONS:
        raise ValueError("heavy replay dependency versions are not exact")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("heavy replay requires an Apple-Silicon Mac")
    if not torch.backends.mps.is_available():
        raise ValueError("heavy replay requires the Apple MPS backend")

    model_snapshot, validation_path = _resolve_pinned_inputs(hf_home)
    tokenizer = AutoTokenizer.from_pretrained(
        model_snapshot,
        local_files_only=True,
        trust_remote_code=False,
    )
    rows = parquet.read_table(validation_path, columns=["text"]).column("text")
    corpus = "\n\n".join(rows.to_pylist())
    previous_maximum = tokenizer.model_max_length
    tokenizer.model_max_length = sys.maxsize
    try:
        validation_token_ids = tokenizer(
            corpus,
            add_special_tokens=False,
            return_attention_mask=False,
            return_token_type_ids=False,
        )["input_ids"]
    finally:
        tokenizer.model_max_length = previous_maximum
    selected = validation_token_ids[64 * 512 : 72 * 512]
    if len(selected) != 8 * 512:
        raise ValueError("pinned validation dataset has too few source tokens")
    selected_bytes = np.asarray(selected, dtype="<u4").tobytes()
    if _sha256_bytes(selected_bytes) != SELECTED_TOKEN_IDS_SHA256:
        raise ValueError("independently tokenized source slice digest changed")
    for offset, block in enumerate(token_blocks):
        expected_block = selected[offset * 512 : (offset + 1) * 512]
        if block.get("tokenIds") != expected_block:
            raise ValueError("retained token IDs differ from pinned WikiText")

    torch.manual_seed(20260729)
    np.random.seed(20260729)
    torch.use_deterministic_algorithms(True, warn_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_snapshot,
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.float32,
        attn_implementation="eager",
    ).to("mps")
    model.eval()

    maximum_baseline_loss_difference = 0.0
    maximum_candidate_loss_difference = 0.0
    decisions = 0
    records = result.get("records")
    baselines = result.get("baselines")
    if not isinstance(records, list) or not isinstance(baselines, list):
        raise ValueError("result records or baselines are missing")
    for block_offset, block_index in enumerate(BLOCK_INDICES):
        print(f"heavy replay block {block_index} ({block_offset + 1}/8)", flush=True)
        ids_cpu = torch.tensor(
            token_blocks[block_offset]["tokenIds"], dtype=torch.long
        ).unsqueeze(0)
        prefix = ids_cpu[:, :383].to("mps")
        continuation = ids_cpu[:, 383:-1].to("mps")
        targets = ids_cpu[:, 384:]
        with torch.inference_mode():
            prefill = model(prefix, use_cache=True, return_dict=True)
        baseline_layers, raw_bf16 = _extract_canonical_layers(prefill, torch, np)
        del prefill, prefix

        cache_hasher = hashlib.sha256()
        for layer_index, layer_bytes in enumerate(raw_bf16):
            cache_hasher.update(layer_index.to_bytes(4, "little"))
            cache_hasher.update(len(layer_bytes).to_bytes(8, "little"))
            cache_hasher.update(layer_bytes)
        cache_digest = cache_hasher.hexdigest()
        if (
            records[block_offset].get("canonicalCacheBF16SHA256") != cache_digest
            or baselines[block_offset].get("canonicalCacheBF16SHA256")
            != cache_digest
        ):
            raise ValueError(f"block {block_index} canonical cache digest changed")

        candidate_layers = []
        for layer_index in range(LAYERS):
            path = (
                run
                / "primary-evidence"
                / "containers"
                / f"block-{block_index:03d}"
                / f"layer-{layer_index:02d}.vtl5"
            )
            if path.is_symlink() or not path.is_file():
                raise ValueError("heavy replay container is missing or symlinked")
            raw = path.read_bytes()
            decoded, metadata = _decode_container(raw, layer_index, np)
            input_digest = _sha256_bytes(
                np.ascontiguousarray(baseline_layers[layer_index], dtype="<f4")
                .tobytes()
            )
            if input_digest != metadata.get("inputSha256"):
                raise ValueError(
                    f"block {block_index} layer {layer_index} input cache digest changed"
                )
            candidate_layers.append(decoded)

        baseline_losses, baseline_top1 = _model_token_metrics(
            model, continuation, targets, baseline_layers, torch
        )
        del baseline_layers, raw_bf16
        torch.mps.empty_cache()
        candidate_losses, candidate_top1 = _model_token_metrics(
            model, continuation, targets, candidate_layers, torch
        )
        del candidate_layers, continuation, targets, ids_cpu
        torch.mps.empty_cache()
        gc.collect()

        token_rows = token_blocks[block_offset].get("tokens")
        if not isinstance(token_rows, list) or len(token_rows) != PREDICTIONS:
            raise ValueError(f"block {block_index} token rows are invalid")
        for token_offset, row in enumerate(token_rows):
            if not isinstance(row, dict):
                raise ValueError("token metric row is not an object")
            baseline_difference = abs(
                float(row.get("baselineLossNat")) - baseline_losses[token_offset]
            )
            candidate_difference = abs(
                float(row.get("candidateLossNat")) - candidate_losses[token_offset]
            )
            maximum_baseline_loss_difference = max(
                maximum_baseline_loss_difference, baseline_difference
            )
            maximum_candidate_loss_difference = max(
                maximum_candidate_loss_difference, candidate_difference
            )
            if (
                not _loss_close(
                    row.get("baselineLossNat"), baseline_losses[token_offset]
                )
                or not _loss_close(
                    row.get("candidateLossNat"), candidate_losses[token_offset]
                )
                or row.get("baselineTop1TokenId") != baseline_top1[token_offset]
                or row.get("candidateTop1TokenId") != candidate_top1[token_offset]
            ):
                raise ValueError(
                    f"block {block_index} token {token_offset} does not replay"
                )
            decisions += 1
    del model
    torch.mps.empty_cache()
    if decisions != 1024:
        raise ValueError("heavy replay did not verify exactly 1,024 decisions")
    return {
        "decisions": decisions,
        "maximumBaselineLossDifference": maximum_baseline_loss_difference,
        "maximumCandidateLossDifference": maximum_candidate_loss_difference,
        "lossAbsoluteTolerance": LOSS_ABSOLUTE_TOLERANCE,
        "lossRelativeTolerance": LOSS_RELATIVE_TOLERANCE,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument(
        "--hf-home",
        type=Path,
        default=Path.home() / ".cache" / "corelm-model-assets",
    )
    arguments = parser.parse_args()
    for name in (
        "HF_ENDPOINT",
        "HF_INFERENCE_ENDPOINT",
        "HF_TOKEN",
        "HF_TOKEN_PATH",
        "HUGGING_FACE_HUB_TOKEN",
    ):
        os.environ.pop(name, None)
    for name, value in {
        "HF_HOME": str(arguments.hf_home),
        "HF_HUB_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
        "MKL_NUM_THREADS": "2",
        "VECLIB_MAXIMUM_THREADS": "2",
        "NUMEXPR_NUM_THREADS": "2",
        "PYTORCH_MPS_HIGH_WATERMARK_RATIO": "0.85",
        "PYTORCH_MPS_LOW_WATERMARK_RATIO": "0.75",
    }.items():
        os.environ[name] = value
    try:
        summary = verify_primary_replay(
            arguments.run_directory, arguments.hf_home
        )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OverflowError,
        struct.error,
    ) as error:
        print(f"PRIMARY REPLAY FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "PRIMARY REPLAY PASS: "
        f"{summary['decisions']} Qwen decisions match decoded raw containers; "
        f"max baseline loss error={summary['maximumBaselineLossDifference']:.3g}, "
        f"max candidate loss error={summary['maximumCandidateLossDifference']:.3g}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
