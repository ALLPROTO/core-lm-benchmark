#!/usr/bin/env python3
"""Independently verify retained app-proof containers and token metrics.

This verifier intentionally uses only the Python standard library.  It does
not import the benchmark writer, the codec implementation, or the historical
manifest validator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Any


PRIMARY_SCHEMA = "corelm-real-llm-primary-evidence-v1"
TOKEN_SCHEMA = "corelm-real-llm-token-metrics-v1"
RESULT_SCHEMA = "corelm-voidtoken-v5-validation-development-v3"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_RESULT_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 512 * 1024
MAX_TOKEN_METRICS_BYTES = 2 * 1024 * 1024
MAX_CONTAINER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_CONTAINER_BYTES = 64 * 1024 * 1024
EXPECTED_BLOCKS = tuple(range(64, 72))
EXPECTED_LAYERS = tuple(range(24))
EXPECTED_PREDICTIONS_PER_BLOCK = 128
EXPECTED_VOCAB_SIZE = 151_936
EXPECTED_TRAJECTORY_ROWS = 383
EXPECTED_TRAJECTORY_COLUMNS = 256
EXPECTED_BF16_BYTES_PER_BLOCK = (
    len(EXPECTED_LAYERS)
    * EXPECTED_TRAJECTORY_ROWS
    * EXPECTED_TRAJECTORY_COLUMNS
    * 2
)
EXPECTED_DENSE_BF16_BYTES = (
    len(EXPECTED_BLOCKS) * EXPECTED_BF16_BYTES_PER_BLOCK
)


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _reject_duplicate_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path, maximum_bytes: int) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path.name} is not a regular file")
    size = path.stat().st_size
    if size <= 0 or size > maximum_bytes:
        raise ValueError(f"{path.name} exceeds its resource bound")
    raw = path.read_bytes()
    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path.name} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value, raw


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


def _exact_object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} fields are not exact")
    return value


def _integer(
    value: Any,
    label: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} is below its bound")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} exceeds its bound")
    return value


def _real(value: Any, label: str, *, minimum: float | None = None) -> float:
    if type(value) not in {int, float} or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"{label} is below its bound")
    return result


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} is not a lowercase SHA-256 digest")
    return value


def _close(left: Any, right: Any) -> bool:
    try:
        return math.isclose(
            _real(left, "observed value"),
            _real(right, "recomputed value"),
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
    except ValueError:
        return False


def _ordered_binary64_mean(values: list[float]) -> float:
    if not values:
        raise ValueError("token metric sequence must not be empty")
    total = 0.0
    for value in values:
        total += float(value)
    return total / len(values)


def _safe_file(run: Path, relative: Any, expected: str | None = None) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("primary evidence path is not a safe relative path")
    if expected is not None and relative != expected:
        raise ValueError(f"primary evidence path must be {expected}")
    path_value = Path(relative)
    if path_value.is_absolute() or any(
        part in {"", ".", ".."} for part in path_value.parts
    ):
        raise ValueError("primary evidence path has unsafe components")
    candidate = run.joinpath(*path_value.parts)
    current = run
    for component in path_value.parts[:-1]:
        current = current / component
        if current.is_symlink() or not current.is_dir():
            raise ValueError("primary evidence directory chain is unsafe")
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("primary evidence artifact is missing or unsafe")
    try:
        candidate.resolve(strict=True).relative_to(run.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise ValueError("primary evidence artifact escapes the run") from error
    return candidate


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


_METADATA_KEYS = {
    "bits",
    "codeCompression",
    "codeCount",
    "codeMapping",
    "dtype",
    "format",
    "groupSize",
    "groupsPerRow",
    "inputSha256",
    "layerIndex",
    "packedBytes",
    "packing",
    "payloadBytes",
    "payloadSha256",
    "quantization",
    "reconstructionSha256",
    "scaleBytes",
    "scaleCompression",
    "scaleCount",
    "scaleDtype",
    "shape",
    "signDerivation",
    "signMode",
    "storedCodeBytes",
    "storedScaleBytes",
    "transform",
    "transformBlockSize",
}


def _parse_container(
    raw: bytes,
    *,
    block_index: int,
    layer_index: int,
    expected_manifest: dict[str, Any],
) -> tuple[int, bytes]:
    label = f"block {block_index} layer {layer_index}"
    if len(raw) < 8 or len(raw) > MAX_CONTAINER_BYTES:
        raise ValueError(f"{label} container size is invalid")
    magic, metadata_length = struct.unpack_from("<4sI", raw)
    if magic != b"VTL5" or metadata_length > 1024 * 1024:
        raise ValueError(f"{label} container header is invalid")
    metadata_end = 8 + metadata_length
    if metadata_end > len(raw):
        raise ValueError(f"{label} container metadata is truncated")
    metadata_bytes = raw[8:metadata_end]
    try:
        metadata = json.loads(
            metadata_bytes.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} metadata is not valid JSON") from error
    if (
        not isinstance(metadata, dict)
        or set(metadata) != _METADATA_KEYS
        or _canonical_json(metadata) != metadata_bytes
    ):
        raise ValueError(f"{label} metadata layout or canonical JSON is invalid")
    if metadata != expected_manifest.get("metadata"):
        raise ValueError(f"{label} raw metadata differs from the result")

    bits = 9 if layer_index in {0, 8} else 8
    code_count = EXPECTED_TRAJECTORY_ROWS * EXPECTED_TRAJECTORY_COLUMNS
    packed_bytes = (
        code_count * bits // 8
        if bits <= 8
        else code_count + math.ceil(code_count * (bits - 8) / 8)
    )
    fixed = {
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
        "scaleBytes": EXPECTED_TRAJECTORY_ROWS * 2 * 2,
        "scaleCompression": "zlib-9",
        "scaleCount": EXPECTED_TRAJECTORY_ROWS * 2,
        "scaleDtype": "float16-le",
        "shape": [EXPECTED_TRAJECTORY_ROWS, EXPECTED_TRAJECTORY_COLUMNS],
        "signDerivation": "shake256-layer-column-v1",
        "signMode": "none",
        "transform": "normalized-walsh-hadamard-v1",
        "transformBlockSize": 128,
    }
    if any(metadata.get(key) != value for key, value in fixed.items()):
        raise ValueError(f"{label} metadata does not match the frozen codec")
    for name in ("inputSha256", "payloadSha256", "reconstructionSha256"):
        _digest(metadata.get(name), f"{label} {name}")

    payload = raw[metadata_end:]
    payload_bytes = _integer(
        metadata.get("payloadBytes"), f"{label} payloadBytes", minimum=1
    )
    stored_scale_bytes = _integer(
        metadata.get("storedScaleBytes"),
        f"{label} storedScaleBytes",
        minimum=1,
    )
    stored_code_bytes = _integer(
        metadata.get("storedCodeBytes"),
        f"{label} storedCodeBytes",
        minimum=1,
    )
    if (
        len(payload) != payload_bytes
        or stored_scale_bytes + stored_code_bytes != payload_bytes
        or _sha256_bytes(payload) != metadata["payloadSha256"]
    ):
        raise ValueError(f"{label} payload accounting or digest is invalid")
    scale_stream = _decompress_canonical(
        payload[:stored_scale_bytes], metadata["scaleBytes"], f"{label} scales"
    )
    code_stream = _decompress_canonical(
        payload[stored_scale_bytes:],
        metadata["packedBytes"],
        f"{label} codes",
    )
    for (scale,) in struct.iter_unpack("<e", scale_stream):
        if not math.isfinite(scale) or scale < 0.0:
            raise ValueError(f"{label} contains an invalid float16 scale")
    if bits == 8:
        if len(code_stream) != code_count or 0xFF in code_stream:
            raise ValueError(f"{label} contains an invalid packed 8-bit code")
    else:
        low_bytes = code_stream[:code_count]
        high_bits = code_stream[code_count:]
        expected_high_bytes = math.ceil(code_count / 8)
        if len(high_bits) != expected_high_bytes:
            raise ValueError(f"{label} packed 9-bit code length is invalid")
        for index, low_byte in enumerate(low_bytes):
            high_bit = (high_bits[index // 8] >> (index % 8)) & 1
            if low_byte == 0xFF and high_bit == 1:
                raise ValueError(f"{label} contains the unused all-ones code")
        unused_bits = (8 - (code_count % 8)) % 8
        if unused_bits and high_bits[-1] >> (8 - unused_bits):
            raise ValueError(f"{label} packed 9-bit padding is non-zero")
    if (
        expected_manifest.get("layerIndex") != layer_index
        or expected_manifest.get("payloadBytes") != payload_bytes
        or expected_manifest.get("containerBytes") != len(raw)
        or expected_manifest.get("containerSHA256") != _sha256_bytes(raw)
    ):
        raise ValueError(f"{label} result manifest differs from raw bytes")
    return payload_bytes, metadata_bytes


def _verify_token_metrics(
    token_document: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    _exact_object(token_document, {"schemaVersion", "blocks"}, "token metrics")
    if token_document["schemaVersion"] != TOKEN_SCHEMA:
        raise ValueError("token metrics schema is unsupported")
    blocks = token_document["blocks"]
    records = result.get("records")
    baselines = result.get("baselines")
    if (
        not isinstance(blocks, list)
        or not isinstance(records, list)
        or not isinstance(baselines, list)
        or len(records) != len(EXPECTED_BLOCKS)
        or len(baselines) != len(EXPECTED_BLOCKS)
    ):
        raise ValueError("token metrics or result records are missing")
    if [block.get("blockIndex") for block in blocks] != list(EXPECTED_BLOCKS):
        raise ValueError("token metric block order is not exact")
    if [record.get("blockIndex") for record in records] != list(
        EXPECTED_BLOCKS
    ):
        raise ValueError("result record block order is not exact")

    block_baseline_means: list[float] = []
    block_candidate_means: list[float] = []
    all_agreements = 0
    token_keys = {
        "offset",
        "targetTokenId",
        "baselineLossNat",
        "candidateLossNat",
        "baselineTop1TokenId",
        "candidateTop1TokenId",
        "top1Agrees",
    }
    for block_index, block, record in zip(EXPECTED_BLOCKS, blocks, records):
        _exact_object(
            block,
            {"blockIndex", "tokenIds", "predictionTokens", "tokens"},
            f"block {block_index} token metrics",
        )
        token_ids = block["tokenIds"]
        if (
            not isinstance(token_ids, list)
            or len(token_ids) != 512
            or any(
                type(token_id) is not int
                or token_id < 0
                or token_id >= EXPECTED_VOCAB_SIZE
                for token_id in token_ids
            )
        ):
            raise ValueError(f"block {block_index} source token IDs are invalid")
        token_id_bytes = b"".join(
            struct.pack("<I", token_id) for token_id in token_ids
        )
        token_ids_sha256 = _sha256_bytes(token_id_bytes)
        baseline = baselines[block_index - EXPECTED_BLOCKS[0]]
        if (
            record.get("tokenIdsSHA256") != token_ids_sha256
            or not isinstance(baseline, dict)
            or baseline.get("tokenIdsSHA256") != token_ids_sha256
        ):
            raise ValueError(
                f"block {block_index} source token digest is inconsistent"
            )
        tokens = block["tokens"]
        if (
            block["predictionTokens"] != EXPECTED_PREDICTIONS_PER_BLOCK
            or not isinstance(tokens, list)
            or len(tokens) != EXPECTED_PREDICTIONS_PER_BLOCK
        ):
            raise ValueError(f"block {block_index} token count is invalid")
        baseline_losses: list[float] = []
        candidate_losses: list[float] = []
        agreements = 0
        for offset, token in enumerate(tokens):
            _exact_object(token, token_keys, f"block {block_index} token {offset}")
            if token.get("offset") != offset:
                raise ValueError(f"block {block_index} token order is invalid")
            for name in (
                "targetTokenId",
                "baselineTop1TokenId",
                "candidateTop1TokenId",
            ):
                _integer(
                    token.get(name),
                    f"block {block_index} token {offset} {name}",
                    minimum=0,
                    maximum=EXPECTED_VOCAB_SIZE - 1,
                )
            baseline_loss = _real(
                token.get("baselineLossNat"),
                f"block {block_index} token {offset} baseline loss",
                minimum=0.0,
            )
            candidate_loss = _real(
                token.get("candidateLossNat"),
                f"block {block_index} token {offset} candidate loss",
                minimum=0.0,
            )
            agrees = (
                token["baselineTop1TokenId"]
                == token["candidateTop1TokenId"]
            )
            if token["targetTokenId"] != token_ids[384 + offset]:
                raise ValueError(
                    f"block {block_index} token {offset} target is inconsistent"
                )
            if type(token.get("top1Agrees")) is not bool or (
                token["top1Agrees"] is not agrees
            ):
                raise ValueError(
                    f"block {block_index} token {offset} agreement is invalid"
                )
            baseline_losses.append(baseline_loss)
            candidate_losses.append(candidate_loss)
            agreements += int(agrees)
        baseline_nll = _ordered_binary64_mean(baseline_losses)
        candidate_nll = _ordered_binary64_mean(candidate_losses)
        if (
            not _close(record.get("baselineNLLNatPerToken"), baseline_nll)
            or not _close(record.get("candidateNLLNatPerToken"), candidate_nll)
            or not _close(
                record.get("deltaNLLNatPerToken"), candidate_nll - baseline_nll
            )
            or record.get("top1AgreementCount") != agreements
            or not _close(
                record.get("top1Agreement"), agreements / len(tokens)
            )
        ):
            raise ValueError(
                f"block {block_index} metrics do not recompute from tokens"
            )
        block_baseline_means.append(baseline_nll)
        block_candidate_means.append(candidate_nll)
        all_agreements += agreements

    baseline_nll = _ordered_binary64_mean(block_baseline_means)
    candidate_nll = _ordered_binary64_mean(block_candidate_means)
    total_predictions = len(blocks) * EXPECTED_PREDICTIONS_PER_BLOCK
    return {
        "predictionTokens": total_predictions,
        "baselineNLLNatPerToken": baseline_nll,
        "candidateNLLNatPerToken": candidate_nll,
        "deltaNLLNatPerToken": candidate_nll - baseline_nll,
        "top1AgreementCount": all_agreements,
        "top1Agreement": all_agreements / total_predictions,
    }


def _verify_dense_bf16_geometry(
    records: list[dict[str, Any]], baselines: list[dict[str, Any]]
) -> int:
    if (
        len(records) != len(EXPECTED_BLOCKS)
        or len(baselines) != len(EXPECTED_BLOCKS)
    ):
        raise ValueError("dense BF16 geometry block count is inconsistent")
    for block_index, record, baseline in zip(
        EXPECTED_BLOCKS, records, baselines
    ):
        if (
            _integer(
                record.get("denseBF16Bytes"),
                f"block {block_index} dense BF16 bytes",
                minimum=1,
            )
            != EXPECTED_BF16_BYTES_PER_BLOCK
            or _integer(
                baseline.get("denseBF16Bytes"),
                f"block {block_index} baseline dense BF16 bytes",
                minimum=1,
            )
            != EXPECTED_BF16_BYTES_PER_BLOCK
        ):
            raise ValueError(
                f"block {block_index} dense BF16 geometry is inconsistent"
            )
    return EXPECTED_DENSE_BF16_BYTES


def verify_primary_evidence(
    run_directory: Path, result: dict[str, Any] | None = None
) -> dict[str, Any]:
    if run_directory.is_symlink() or not run_directory.is_dir():
        raise ValueError("run directory is missing or unsafe")
    run = run_directory.resolve(strict=True)
    if result is None:
        result_files = sorted(run.glob("validation-*.json"))
        if len(result_files) != 1:
            raise ValueError("run must contain exactly one validation result")
        result, _ = _load_json(result_files[0], MAX_RESULT_BYTES)
    if result.get("schemaVersion") != RESULT_SCHEMA:
        raise ValueError("result does not use the primary-evidence schema")

    descriptor = _exact_object(
        result.get("primaryEvidence"),
        {
            "schemaVersion",
            "path",
            "manifestSHA256",
            "manifestBytes",
            "containerCount",
            "containerBytes",
            "blocks",
            "predictionTokens",
        },
        "primary evidence descriptor",
    )
    if descriptor["schemaVersion"] != PRIMARY_SCHEMA:
        raise ValueError("primary evidence descriptor schema is unsupported")
    _digest(descriptor["manifestSHA256"], "primary manifest digest")
    _integer(
        descriptor["manifestBytes"],
        "primary manifest bytes",
        minimum=1,
        maximum=MAX_MANIFEST_BYTES,
    )
    _integer(descriptor["containerCount"], "primary container count", minimum=1)
    _integer(
        descriptor["containerBytes"],
        "primary container bytes",
        minimum=1,
        maximum=MAX_TOTAL_CONTAINER_BYTES,
    )
    _integer(descriptor["blocks"], "primary block count", minimum=1)
    _integer(
        descriptor["predictionTokens"],
        "primary prediction count",
        minimum=1,
    )
    manifest_path = _safe_file(
        run, descriptor["path"], "primary-evidence/manifest.json"
    )
    manifest, manifest_raw = _load_json(manifest_path, MAX_MANIFEST_BYTES)
    if (
        descriptor["manifestSHA256"] != _sha256_bytes(manifest_raw)
        or descriptor["manifestBytes"] != len(manifest_raw)
    ):
        raise ValueError("primary evidence manifest binding is invalid")
    _exact_object(
        manifest,
        {"schemaVersion", "resultFile", "containers", "tokenMetrics"},
        "primary evidence manifest",
    )
    if manifest["schemaVersion"] != PRIMARY_SCHEMA:
        raise ValueError("primary evidence manifest schema is unsupported")
    protocol = result.get("protocol")
    if not isinstance(protocol, dict):
        raise ValueError("result protocol is missing")
    validation_start = _integer(
        protocol.get("validationStartBlock"),
        "validation start block",
        minimum=0,
    )
    validation_blocks = _integer(
        protocol.get("validationBlocks"), "validation blocks", minimum=1
    )
    expected_result_name = (
        f"validation-{validation_start:03d}-"
        f"{validation_start + validation_blocks - 1:03d}.json"
    )
    if manifest["resultFile"] != expected_result_name:
        raise ValueError("primary evidence manifest names a different result")

    containers = manifest["containers"]
    records = result.get("records")
    if not isinstance(containers, list) or not isinstance(records, list):
        raise ValueError("container manifest or result records are missing")
    expected_count = len(EXPECTED_BLOCKS) * len(EXPECTED_LAYERS)
    if len(containers) != expected_count or len(records) != len(EXPECTED_BLOCKS):
        raise ValueError("primary evidence must retain exactly 192 containers")

    total_container_bytes = 0
    observed_paths: set[str] = set()
    for block_offset, block_index in enumerate(EXPECTED_BLOCKS):
        record = records[block_offset]
        record_manifest = record.get("containerManifest")
        if not isinstance(record_manifest, list) or len(record_manifest) != 24:
            raise ValueError(f"block {block_index} result manifest is invalid")
        if record.get("containerManifestSHA256") != _sha256_bytes(
            _canonical_json(record_manifest)
        ):
            raise ValueError(
                f"block {block_index} result container manifest digest is invalid"
            )
        payload_hasher = hashlib.sha256()
        block_payload_bytes = 0
        block_container_bytes = 0
        for layer_index in EXPECTED_LAYERS:
            position = block_offset * 24 + layer_index
            entry = _exact_object(
                containers[position],
                {"blockIndex", "layerIndex", "path", "bytes", "sha256"},
                f"container artifact {position}",
            )
            expected_path = (
                "primary-evidence/containers/"
                f"block-{block_index:03d}/layer-{layer_index:02d}.vtl5"
            )
            if (
                entry["blockIndex"] != block_index
                or entry["layerIndex"] != layer_index
                or entry["path"] != expected_path
                or entry["path"] in observed_paths
            ):
                raise ValueError("container artifact order or path is invalid")
            observed_paths.add(entry["path"])
            _integer(
                entry["bytes"],
                f"block {block_index} layer {layer_index} bytes",
                minimum=1,
                maximum=MAX_CONTAINER_BYTES,
            )
            _digest(
                entry["sha256"],
                f"block {block_index} layer {layer_index} digest",
            )
            path = _safe_file(run, entry["path"], expected_path)
            size = path.stat().st_size
            if (
                size <= 0
                or size > MAX_CONTAINER_BYTES
                or entry["bytes"] != size
                or entry["sha256"] != _sha256_file(path)
            ):
                raise ValueError(
                    f"block {block_index} layer {layer_index} file binding is invalid"
                )
            raw = path.read_bytes()
            expected_layer_manifest = _exact_object(
                record_manifest[layer_index],
                {
                    "layerIndex",
                    "metadata",
                    "payloadBytes",
                    "containerBytes",
                    "containerSHA256",
                },
                f"block {block_index} result layer {layer_index}",
            )
            payload_bytes, _ = _parse_container(
                raw,
                block_index=block_index,
                layer_index=layer_index,
                expected_manifest=expected_layer_manifest,
            )
            payload_hasher.update(layer_index.to_bytes(4, "little"))
            payload_hasher.update(len(raw).to_bytes(8, "little"))
            payload_hasher.update(raw)
            block_payload_bytes += payload_bytes
            block_container_bytes += len(raw)
            total_container_bytes += len(raw)
            if total_container_bytes > MAX_TOTAL_CONTAINER_BYTES:
                raise ValueError("primary container evidence exceeds its bound")
        if (
            record.get("payloadBytes") != block_payload_bytes
            or record.get("encodedFileBytes") != block_container_bytes
            or record.get("payloadSHA256") != payload_hasher.hexdigest()
        ):
            raise ValueError(
                f"block {block_index} raw container aggregate is inconsistent"
            )

    primary_root = run / "primary-evidence"
    expected_files = observed_paths | {
        "primary-evidence/manifest.json",
        "primary-evidence/token-metrics.json",
    }
    expected_directories = {
        "primary-evidence",
        "primary-evidence/containers",
        *{
            f"primary-evidence/containers/block-{block_index:03d}"
            for block_index in EXPECTED_BLOCKS
        },
    }
    actual_files: set[str] = set()
    actual_directories = {"primary-evidence"}
    for artifact in primary_root.rglob("*"):
        if artifact.is_symlink():
            raise ValueError("primary evidence tree contains a symlink")
        relative = artifact.relative_to(run).as_posix()
        if artifact.is_dir():
            actual_directories.add(relative)
        elif artifact.is_file():
            actual_files.add(relative)
        else:
            raise ValueError("primary evidence tree contains a special file")
    if actual_files != expected_files or actual_directories != expected_directories:
        raise ValueError("primary evidence tree contains missing or extra paths")

    token_reference = _exact_object(
        manifest["tokenMetrics"],
        {"path", "bytes", "sha256", "blocks", "predictionTokens"},
        "token metrics reference",
    )
    _integer(
        token_reference["bytes"],
        "token metrics bytes",
        minimum=1,
        maximum=MAX_TOKEN_METRICS_BYTES,
    )
    _digest(token_reference["sha256"], "token metrics digest")
    _integer(token_reference["blocks"], "token metrics blocks", minimum=1)
    _integer(
        token_reference["predictionTokens"],
        "token metrics prediction count",
        minimum=1,
    )
    token_path = _safe_file(
        run,
        token_reference["path"],
        "primary-evidence/token-metrics.json",
    )
    token_document, token_raw = _load_json(
        token_path, MAX_TOKEN_METRICS_BYTES
    )
    if (
        token_reference["bytes"] != len(token_raw)
        or token_reference["sha256"] != _sha256_bytes(token_raw)
        or token_reference["blocks"] != len(EXPECTED_BLOCKS)
        or token_reference["predictionTokens"]
        != len(EXPECTED_BLOCKS) * EXPECTED_PREDICTIONS_PER_BLOCK
    ):
        raise ValueError("token metrics file binding is invalid")
    recomputed = _verify_token_metrics(token_document, result)
    dense_bytes = _verify_dense_bf16_geometry(
        records, result["baselines"]
    )
    selected_token_bytes = b"".join(
        struct.pack("<I", token_id)
        for block in token_document["blocks"]
        for token_id in block["tokenIds"]
    )
    if result.get("selectedTokenIdsSHA256") != _sha256_bytes(
        selected_token_bytes
    ):
        raise ValueError("selected source token digest is inconsistent")

    aggregate_values = result.get("aggregates")
    if not isinstance(aggregate_values, list) or len(aggregate_values) != 1:
        raise ValueError("result must contain one aggregate")
    aggregate = aggregate_values[0]
    ratio = dense_bytes / total_container_bytes
    gates = {
        "compression": ratio >= 2.0,
        "deltaNLL": recomputed["deltaNLLNatPerToken"] <= 0.01,
        "top1Agreement": recomputed["top1Agreement"] >= 0.99,
    }
    if (
        aggregate.get("predictionTokens") != recomputed["predictionTokens"]
        or aggregate.get("denseBF16Bytes") != dense_bytes
        or aggregate.get("encodedFileBytes") != total_container_bytes
        or not _close(aggregate.get("compressionRatioVsBF16"), ratio)
        or not _close(
            aggregate.get("baselineNLLNatPerToken"),
            recomputed["baselineNLLNatPerToken"],
        )
        or not _close(
            aggregate.get("candidateNLLNatPerToken"),
            recomputed["candidateNLLNatPerToken"],
        )
        or not _close(
            aggregate.get("deltaNLLNatPerToken"),
            recomputed["deltaNLLNatPerToken"],
        )
        or not _close(
            aggregate.get("top1Agreement"), recomputed["top1Agreement"]
        )
        or aggregate.get("gates") != gates
        or aggregate.get("pass") is not all(gates.values())
    ):
        raise ValueError("aggregate does not recompute from primary evidence")

    if (
        descriptor["containerCount"] != expected_count
        or descriptor["containerBytes"] != total_container_bytes
        or descriptor["blocks"] != len(EXPECTED_BLOCKS)
        or descriptor["predictionTokens"] != recomputed["predictionTokens"]
    ):
        raise ValueError("result primary evidence totals are inconsistent")

    recorded_result_sha = _digest(result.get("resultSHA256"), "result digest")
    digest_input = dict(result)
    digest_input.pop("resultSHA256", None)
    if recorded_result_sha != _sha256_bytes(_canonical_json(digest_input)):
        raise ValueError("result canonical digest is inconsistent")
    return {
        "containers": expected_count,
        "containerBytes": total_container_bytes,
        **recomputed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    arguments = parser.parse_args()
    try:
        summary = verify_primary_evidence(arguments.run_directory)
    except (
        OSError,
        ValueError,
        OverflowError,
        KeyError,
        TypeError,
        IndexError,
        struct.error,
    ) as error:
        print(f"PRIMARY EVIDENCE FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "PRIMARY EVIDENCE PASS: "
        f"{summary['containers']} raw containers and "
        f"{summary['predictionTokens']} token decisions independently agree."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
