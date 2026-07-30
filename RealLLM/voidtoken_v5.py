"""Learned-KV redesign of VoidToken with rotation and entropy coding.

The v5 wire format is intentionally independent from the residual-keyframe v4
format:

    b"VTL5" | uint32_le(metadata_length) | canonical_json | binary_payload

Each token-major cache row is split into fixed transform blocks.  A
deterministic sign rotation and normalized Walsh-Hadamard transform spread
outliers before symmetric group quantization.  Float16 scales and the packed
code stream can then be compressed losslessly with canonical zlib level 9.
The decoder reconstructs the original cache domain before model replay.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import time
import zlib
from dataclasses import dataclass
from typing import Any

import numpy as np

from RealLLM.codecs import (
    CodecTiming,
    _pack_codes,
    _unpack_codes,
    canonical_json_bytes,
    sha256_bytes,
    sha256_float32,
)


VOIDTOKEN_V5_FORMAT = "voidtoken-rotated-entropy-v5"
VOIDTOKEN_V5_MAGIC = b"VTL5"
VOIDTOKEN_V5_BITS = frozenset((4, 5, 6, 7, 8, 9, 10, 12, 16))
VOIDTOKEN_V5_TRANSFORM = "normalized-walsh-hadamard-v1"
VOIDTOKEN_V5_SIGN_DERIVATION = "shake256-layer-column-v1"
VOIDTOKEN_V5_SIGN_MODES = frozenset(("none", "shake256"))
VOIDTOKEN_V5_CODE_MAPPING = "zigzag-symmetric-v1"
VOIDTOKEN_V5_MIXED_PACKING = "column-group-major-mixed-v1"

_CONTAINER_HEADER = struct.Struct("<4sI")
_SCALE_DTYPE = np.dtype("<f2")
_SHA256_HEX_LENGTH = 64
_COMPRESSION_MODES = frozenset(("none", "zlib-9"))
MAX_CONTAINER_BYTES = 256 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
MAX_DECODED_MATRIX_ELEMENTS = 2 * 1024 * 1024


def _bytes_like(value: bytes | bytearray | memoryview, name: str) -> bytes:
    try:
        return bytes(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be bytes-like") from error


def _positive_int(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _sha256(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _compression_mode(value: Any, name: str) -> str:
    if not isinstance(value, str) or value not in _COMPRESSION_MODES:
        raise ValueError(f"{name} must be none or zlib-9")
    return str(value)


def _compress(raw: bytes, mode: str) -> bytes:
    return raw if mode == "none" else zlib.compress(raw, level=9)


def _decompress_canonical(
    stored: bytes, mode: str, expected_bytes: int, name: str
) -> bytes:
    if mode == "none":
        raw = stored
    else:
        decompressor = zlib.decompressobj()
        try:
            raw = decompressor.decompress(stored, expected_bytes + 1)
            if len(raw) > expected_bytes or decompressor.unconsumed_tail:
                raise ValueError(f"decompressed {name} exceeds its bound")
            raw += decompressor.flush(expected_bytes + 1 - len(raw))
        except zlib.error as error:
            raise ValueError(f"invalid compressed {name}") from error
        if len(raw) > expected_bytes:
            raise ValueError(f"decompressed {name} exceeds its bound")
        if (
            not decompressor.eof
            or decompressor.unused_data
            or decompressor.unconsumed_tail
        ):
            raise ValueError(f"non-canonical compressed {name} stream")
        if zlib.compress(raw, level=9) != stored:
            raise ValueError(f"{name} stream is not canonical zlib-9")
    if len(raw) != expected_bytes:
        raise ValueError(
            f"{name} length mismatch: expected {expected_bytes}, got {len(raw)}"
        )
    return raw


def _build_container(metadata: dict[str, Any], payload: bytes) -> bytes:
    metadata_bytes = canonical_json_bytes(metadata)
    if len(metadata_bytes) > MAX_METADATA_BYTES:
        raise ValueError("metadata exceeds the v5 container resource limit")
    container = (
        _CONTAINER_HEADER.pack(VOIDTOKEN_V5_MAGIC, len(metadata_bytes))
        + metadata_bytes
        + payload
    )
    if len(container) > MAX_CONTAINER_BYTES:
        raise ValueError("VoidToken v5 container exceeds the resource limit")
    return container


def _parse_container(
    container: bytes | bytearray | memoryview,
) -> tuple[bytes, dict[str, Any], bytes]:
    raw = _bytes_like(container, "container")
    if len(raw) < _CONTAINER_HEADER.size:
        raise ValueError("truncated VoidToken v5 container header")
    if len(raw) > MAX_CONTAINER_BYTES:
        raise ValueError("VoidToken v5 container exceeds the resource limit")
    magic, metadata_length = _CONTAINER_HEADER.unpack_from(raw)
    if magic != VOIDTOKEN_V5_MAGIC:
        raise ValueError("invalid VoidToken v5 container magic")
    if metadata_length > MAX_METADATA_BYTES:
        raise ValueError("VoidToken v5 metadata exceeds the resource limit")
    metadata_start = _CONTAINER_HEADER.size
    metadata_end = metadata_start + metadata_length
    if metadata_end > len(raw):
        raise ValueError("truncated VoidToken v5 container metadata")
    metadata_bytes = raw[metadata_start:metadata_end]
    try:
        metadata = json.loads(metadata_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid VoidToken v5 container metadata") from error
    if not isinstance(metadata, dict):
        raise ValueError("VoidToken v5 metadata must be an object")
    if canonical_json_bytes(metadata) != metadata_bytes:
        raise ValueError("VoidToken v5 metadata is not canonical JSON")
    return raw, metadata, raw[metadata_end:]


def _is_power_of_two(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0


def _packing_name(bits: int) -> str:
    return (
        "lsb-first-v1"
        if bits <= 8
        else "byte-low-plus-lsb-high-fields-v1"
    )


def _pack_v5_codes(codes: np.ndarray, bits: int) -> bytes:
    if bits <= 8:
        return _pack_codes(codes, bits)
    values = np.asarray(codes, dtype=np.uint16).reshape(-1)
    low_bytes = (values & np.uint16(0xFF)).astype(np.uint8).tobytes()
    high_values = values >> np.uint16(8)
    return low_bytes + _pack_codes(high_values, bits - 8)


def _unpack_v5_codes(packed: bytes, bits: int, count: int) -> np.ndarray:
    if bits <= 8:
        return _unpack_codes(packed, bits, count)
    low_bytes = np.frombuffer(packed, dtype=np.uint8, count=count)
    high_values = _unpack_codes(packed[count:], bits - 8, count)
    return (
        low_bytes.astype(np.uint16)
        | (high_values.astype(np.uint16) << np.uint16(8))
    )


def _quantized_to_codes(quantized: np.ndarray, bits: int) -> np.ndarray:
    """Map signed values to small unsigned codes without changing precision."""

    values = np.asarray(quantized, dtype=np.int32)
    codes = np.where(values >= 0, values * 2, -values * 2 - 1)
    code_dtype = np.uint8 if bits <= 8 else np.uint16
    return codes.astype(code_dtype).reshape(-1)


def _codes_to_quantized(codes: np.ndarray) -> np.ndarray:
    """Invert the canonical zigzag mapping in signed int32 arithmetic."""

    values = np.asarray(codes, dtype=np.int32)
    return np.where(
        (values & np.int32(1)) == 0,
        values // 2,
        -((values + 1) // 2),
    )


def _sign_vector(
    columns: int, layer_index: int, sign_mode: str
) -> np.ndarray:
    if sign_mode == "none":
        return np.ones(columns, dtype=np.float64)
    if sign_mode != "shake256":
        raise ValueError("sign_mode must be none or shake256")
    material = (
        f"{VOIDTOKEN_V5_FORMAT}|{VOIDTOKEN_V5_SIGN_DERIVATION}|"
        f"layer={layer_index}|columns={columns}"
    ).encode("ascii")
    raw = hashlib.shake_256(material).digest(columns)
    bits = np.frombuffer(raw, dtype=np.uint8) & np.uint8(1)
    return np.where(bits == 0, -1.0, 1.0).astype(np.float64)


def _walsh_hadamard(values: np.ndarray) -> np.ndarray:
    transformed = np.asarray(values, dtype=np.float64).copy()
    width = transformed.shape[-1]
    if not _is_power_of_two(width):
        raise ValueError("Hadamard width must be a power of two")
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


def _forward_transform(
    matrix: np.ndarray,
    transform_block_size: int,
    layer_index: int,
    sign_mode: str,
) -> np.ndarray:
    rows, columns = matrix.shape
    signs = _sign_vector(columns, layer_index, sign_mode).reshape(
        1, columns // transform_block_size, transform_block_size
    )
    grouped = matrix.astype(np.float64).reshape(
        rows, columns // transform_block_size, transform_block_size
    )
    return _walsh_hadamard(grouped * signs).reshape(rows, columns)


def _inverse_transform(
    transformed: np.ndarray,
    transform_block_size: int,
    layer_index: int,
    sign_mode: str,
) -> np.ndarray:
    rows, columns = transformed.shape
    signs = _sign_vector(columns, layer_index, sign_mode).reshape(
        1, columns // transform_block_size, transform_block_size
    )
    grouped = transformed.astype(np.float64).reshape(
        rows, columns // transform_block_size, transform_block_size
    )
    reconstructed = _walsh_hadamard(grouped) * signs
    return np.ascontiguousarray(
        reconstructed.reshape(rows, columns), dtype=np.float32
    )


@dataclass(frozen=True)
class VoidTokenV5Representation:
    """Canonical v5 bytes, reconstruction, and out-of-band timings."""

    payload: bytes
    container: bytes
    metadata: dict[str, Any]
    reconstructed: np.ndarray
    timing: CodecTiming

    @property
    def encode_nanoseconds(self) -> int:
        return self.timing.encode_nanoseconds

    @property
    def decode_nanoseconds(self) -> int:
        return self.timing.decode_nanoseconds

    @property
    def payload_bytes(self) -> int:
        return len(self.payload)

    @property
    def container_bytes(self) -> int:
        return len(self.container)

    @property
    def payload_sha256(self) -> str:
        return sha256_bytes(self.payload)

    @property
    def container_sha256(self) -> str:
        return sha256_bytes(self.container)

    @property
    def reconstruction_sha256(self) -> str:
        return sha256_float32(self.reconstructed)

    def to_bytes(self) -> bytes:
        return self.container

    @classmethod
    def from_bytes(
        cls, container: bytes | bytearray | memoryview
    ) -> "VoidTokenV5Representation":
        return VoidTokenV5Backend.from_bytes(container)


class VoidTokenV5Backend:
    """Rotated group quantization with optional lossless entropy coding."""

    FORMAT = VOIDTOKEN_V5_FORMAT
    MAGIC = VOIDTOKEN_V5_MAGIC
    SUPPORTED_BITS = VOIDTOKEN_V5_BITS

    @staticmethod
    def _validate_input(
        matrix: np.ndarray,
        bits: int | None,
        bits_by_column_group: tuple[int, ...] | list[int] | None,
        group_size: int,
        transform_block_size: int,
        layer_index: int,
    ) -> tuple[np.ndarray, int, int, int, tuple[int, ...], bool]:
        array = np.asarray(matrix)
        if array.ndim != 2:
            raise ValueError("matrix must be two-dimensional")
        if array.dtype != np.dtype(np.float32):
            raise ValueError("matrix dtype must be float32")
        rows, columns = array.shape
        if rows <= 0 or columns <= 0:
            raise ValueError("matrix dimensions must be positive")
        if rows * columns > MAX_DECODED_MATRIX_ELEMENTS:
            raise ValueError("matrix exceeds the VoidToken v5 resource limit")
        if not np.all(np.isfinite(array)):
            raise ValueError("matrix contains non-finite values")
        group_size = _positive_int(group_size, "group_size")
        transform_block_size = _positive_int(
            transform_block_size, "transform_block_size"
        )
        _nonnegative_int(layer_index, "layer_index")
        if not _is_power_of_two(transform_block_size):
            raise ValueError("transform_block_size must be a power of two")
        if columns % transform_block_size:
            raise ValueError("transform_block_size must divide the column count")
        if columns % group_size:
            raise ValueError("group_size must divide the column count")
        if (
            transform_block_size % group_size
            and group_size % transform_block_size
        ):
            raise ValueError(
                "group_size and transform_block_size must align"
            )
        groups_per_row = columns // group_size
        if bits_by_column_group is None:
            if type(bits) is not int or bits not in VOIDTOKEN_V5_BITS:
                raise ValueError("unsupported VoidToken v5 bit width")
            bits_schedule = (bits,) * groups_per_row
            mixed_precision = False
        else:
            if bits is not None:
                raise ValueError(
                    "bits must be None when bits_by_column_group is declared"
                )
            if (
                not isinstance(bits_by_column_group, (tuple, list))
                or len(bits_by_column_group) != groups_per_row
                or any(
                    type(value) is not int or value not in VOIDTOKEN_V5_BITS
                    for value in bits_by_column_group
                )
            ):
                raise ValueError(
                    "bits_by_column_group must declare one supported width "
                    "per column group"
                )
            bits_schedule = tuple(bits_by_column_group)
            mixed_precision = True
        return (
            np.ascontiguousarray(array),
            rows,
            columns,
            groups_per_row,
            bits_schedule,
            mixed_precision,
        )

    @staticmethod
    def _validate_metadata(
        metadata: dict[str, Any],
    ) -> tuple[
        int,
        int,
        tuple[int, ...],
        str,
        int,
        int,
        int,
        str,
        int,
        int,
        int,
        tuple[int, ...],
        int,
    ]:
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        if len(canonical_json_bytes(metadata)) > MAX_METADATA_BYTES:
            raise ValueError("metadata exceeds the VoidToken v5 resource limit")
        expected_strings = {
            "format": VOIDTOKEN_V5_FORMAT,
            "dtype": "float32",
            "scaleDtype": "float16-le",
            "quantization": "symmetric-max-abs-v1",
            "codeMapping": VOIDTOKEN_V5_CODE_MAPPING,
            "transform": VOIDTOKEN_V5_TRANSFORM,
            "signDerivation": VOIDTOKEN_V5_SIGN_DERIVATION,
        }
        for name, expected in expected_strings.items():
            if metadata.get(name) != expected:
                raise ValueError(f"unsupported VoidToken v5 {name}")
        scale_compression = _compression_mode(
            metadata.get("scaleCompression"), "scaleCompression"
        )
        code_compression = _compression_mode(
            metadata.get("codeCompression"), "codeCompression"
        )
        sign_mode = metadata.get("signMode")
        if (
            not isinstance(sign_mode, str)
            or sign_mode not in VOIDTOKEN_V5_SIGN_MODES
        ):
            raise ValueError("signMode must be none or shake256")

        shape = metadata.get("shape")
        if (
            not isinstance(shape, list)
            or len(shape) != 2
            or any(type(value) is not int or value <= 0 for value in shape)
        ):
            raise ValueError("shape must contain two positive integers")
        rows, columns = shape
        if rows * columns > MAX_DECODED_MATRIX_ELEMENTS:
            raise ValueError("shape exceeds the decoded-matrix resource limit")
        group_size = _positive_int(metadata.get("groupSize"), "groupSize")
        transform_block_size = _positive_int(
            metadata.get("transformBlockSize"), "transformBlockSize"
        )
        layer_index = _nonnegative_int(
            metadata.get("layerIndex"), "layerIndex"
        )
        if (
            not _is_power_of_two(transform_block_size)
            or columns % transform_block_size
            or columns % group_size
            or (
                transform_block_size % group_size
                and group_size % transform_block_size
            )
        ):
            raise ValueError("invalid VoidToken v5 transform/group layout")

        groups_per_row = columns // group_size
        has_uniform_bits = "bits" in metadata
        has_mixed_bits = "bitsByColumnGroup" in metadata
        if has_uniform_bits == has_mixed_bits:
            raise ValueError(
                "metadata must declare exactly one v5 bit-width layout"
            )
        common_keys = {
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
        layout_keys = (
            {"bits", "packing"}
            if has_uniform_bits
            else {
                "bitsByColumnGroup",
                "packedBytesByColumnGroup",
                "packing",
            }
        )
        expected_keys = common_keys | layout_keys
        if set(metadata) != expected_keys:
            unexpected = sorted(set(metadata) - expected_keys)
            missing = sorted(expected_keys - set(metadata))
            raise ValueError(
                "VoidToken v5 metadata key set is non-canonical; "
                f"unexpected={unexpected}, missing={missing}"
            )
        if has_uniform_bits:
            bits = metadata.get("bits")
            if type(bits) is not int or bits not in VOIDTOKEN_V5_BITS:
                raise ValueError("invalid VoidToken v5 bit width")
            if metadata.get("packing") != _packing_name(bits):
                raise ValueError("unsupported VoidToken v5 packing")
            if "packedBytesByColumnGroup" in metadata:
                raise ValueError(
                    "uniform v5 layout must not declare group byte lengths"
                )
            bits_by_group = (bits,) * groups_per_row
            packed_bytes_by_group = (
                (rows * columns * bits + 7) // 8,
            )
            packing = _packing_name(bits)
        else:
            raw_bits_by_group = metadata.get("bitsByColumnGroup")
            if (
                not isinstance(raw_bits_by_group, list)
                or len(raw_bits_by_group) != groups_per_row
                or any(
                    type(value) is not int or value not in VOIDTOKEN_V5_BITS
                    for value in raw_bits_by_group
                )
            ):
                raise ValueError(
                    "bitsByColumnGroup must contain one supported width "
                    "per column group"
                )
            if metadata.get("packing") != VOIDTOKEN_V5_MIXED_PACKING:
                raise ValueError("unsupported mixed VoidToken v5 packing")
            bits_by_group = tuple(raw_bits_by_group)
            packed_bytes_by_group = tuple(
                (rows * group_size * value + 7) // 8
                for value in bits_by_group
            )
            raw_packed_bytes_by_group = metadata.get(
                "packedBytesByColumnGroup"
            )
            if (
                not isinstance(raw_packed_bytes_by_group, list)
                or raw_packed_bytes_by_group != list(packed_bytes_by_group)
            ):
                raise ValueError(
                    "packedBytesByColumnGroup does not match the v5 layout"
                )
            packing = VOIDTOKEN_V5_MIXED_PACKING

        scale_count = rows * groups_per_row
        code_count = rows * columns
        scale_bytes = scale_count * _SCALE_DTYPE.itemsize
        packed_bytes = sum(packed_bytes_by_group)
        stored_scale_bytes = _positive_int(
            metadata.get("storedScaleBytes"), "storedScaleBytes"
        )
        stored_code_bytes = _positive_int(
            metadata.get("storedCodeBytes"), "storedCodeBytes"
        )
        if scale_compression == "none" and stored_scale_bytes != scale_bytes:
            raise ValueError("uncompressed v5 scale length mismatch")
        if code_compression == "none" and stored_code_bytes != packed_bytes:
            raise ValueError("uncompressed v5 code length mismatch")
        payload_bytes = stored_scale_bytes + stored_code_bytes
        if payload_bytes > MAX_CONTAINER_BYTES:
            raise ValueError("payload exceeds the VoidToken v5 resource limit")
        expected_integers = {
            "groupsPerRow": groups_per_row,
            "scaleCount": scale_count,
            "codeCount": code_count,
            "scaleBytes": scale_bytes,
            "packedBytes": packed_bytes,
            "payloadBytes": payload_bytes,
        }
        for name, expected in expected_integers.items():
            if type(metadata.get(name)) is not int or metadata[name] != expected:
                raise ValueError(f"{name} does not match the v5 layout")
        _sha256(metadata.get("inputSha256"), "inputSha256")
        _sha256(metadata.get("payloadSha256"), "payloadSha256")
        _sha256(metadata.get("reconstructionSha256"), "reconstructionSha256")
        return (
            rows,
            columns,
            bits_by_group,
            packing,
            group_size,
            transform_block_size,
            layer_index,
            str(sign_mode),
            scale_count,
            scale_bytes,
            stored_scale_bytes,
            packed_bytes_by_group,
            stored_code_bytes,
        )

    @classmethod
    def validate_metadata_layout(cls, metadata: dict[str, Any]) -> None:
        """Validate canonical v5 metadata without requiring the payload bytes."""
        cls._validate_metadata(metadata)

    @classmethod
    def encode(
        cls,
        matrix: np.ndarray,
        *,
        bits: int | None = 8,
        bits_by_column_group: tuple[int, ...] | list[int] | None = None,
        group_size: int = 64,
        transform_block_size: int = 64,
        layer_index: int = 0,
        scale_compression: str = "zlib-9",
        code_compression: str = "zlib-9",
        sign_mode: str = "shake256",
    ) -> VoidTokenV5Representation:
        """Encode a finite cache trajectory into a canonical v5 container."""

        encode_started = time.perf_counter_ns()
        (
            array,
            rows,
            columns,
            groups_per_row,
            bits_schedule,
            mixed_precision,
        ) = cls._validate_input(
            matrix,
            bits,
            bits_by_column_group,
            group_size,
            transform_block_size,
            layer_index,
        )
        scale_compression = _compression_mode(
            scale_compression, "scale_compression"
        )
        code_compression = _compression_mode(
            code_compression, "code_compression"
        )
        if (
            not isinstance(sign_mode, str)
            or sign_mode not in VOIDTOKEN_V5_SIGN_MODES
        ):
            raise ValueError("sign_mode must be none or shake256")
        transformed = _forward_transform(
            array, transform_block_size, layer_index, sign_mode
        )

        qmax_by_group = np.asarray(
            [(1 << (value - 1)) - 1 for value in bits_schedule],
            dtype=np.float64,
        ).reshape(1, groups_per_row)
        grouped = transformed.reshape(rows, groups_per_row, group_size)
        max_abs = np.max(np.abs(grouped), axis=2)
        scale_values = max_abs / qmax_by_group
        if np.any(scale_values > float(np.finfo(np.float16).max)):
            raise ValueError("a v5 quantization scale is not float16-representable")
        scales = scale_values.astype(np.float16)
        smallest_float16 = np.nextafter(np.float16(0.0), np.float16(1.0))
        underflowed = (max_abs > 0.0) & (scales == np.float16(0.0))
        scales[underflowed] = smallest_float16

        scale64 = scales.astype(np.float64)
        ratios = np.zeros_like(grouped)
        np.divide(
            grouped,
            scale64[:, :, np.newaxis],
            out=ratios,
            where=scale64[:, :, np.newaxis] != 0.0,
        )
        quantized = np.clip(
            np.rint(ratios),
            -qmax_by_group[:, :, np.newaxis],
            qmax_by_group[:, :, np.newaxis],
        ).astype(np.int32)

        scale_payload = np.ascontiguousarray(
            scales, dtype=_SCALE_DTYPE
        ).tobytes(order="C")
        if mixed_precision:
            packed_parts = [
                _pack_v5_codes(
                    _quantized_to_codes(
                        quantized[:, group_index, :],
                        bits_schedule[group_index],
                    ),
                    bits_schedule[group_index],
                )
                for group_index in range(groups_per_row)
            ]
            packed_payload = b"".join(packed_parts)
            packed_bytes_by_group = [len(part) for part in packed_parts]
        else:
            packed_payload = _pack_v5_codes(
                _quantized_to_codes(quantized, bits_schedule[0]),
                bits_schedule[0],
            )
            packed_bytes_by_group = None
        stored_scale_payload = _compress(scale_payload, scale_compression)
        stored_code_payload = _compress(packed_payload, code_compression)
        payload = stored_scale_payload + stored_code_payload

        metadata: dict[str, Any] = {
            "codeCompression": code_compression,
            "codeCount": rows * columns,
            "codeMapping": VOIDTOKEN_V5_CODE_MAPPING,
            "dtype": "float32",
            "format": VOIDTOKEN_V5_FORMAT,
            "groupSize": group_size,
            "groupsPerRow": groups_per_row,
            "inputSha256": sha256_float32(array),
            "layerIndex": layer_index,
            "packedBytes": len(packed_payload),
            "payloadBytes": len(payload),
            "payloadSha256": sha256_bytes(payload),
            "quantization": "symmetric-max-abs-v1",
            "scaleBytes": len(scale_payload),
            "scaleCompression": scale_compression,
            "scaleCount": rows * groups_per_row,
            "scaleDtype": "float16-le",
            "shape": [rows, columns],
            "signDerivation": VOIDTOKEN_V5_SIGN_DERIVATION,
            "signMode": sign_mode,
            "storedCodeBytes": len(stored_code_payload),
            "storedScaleBytes": len(stored_scale_payload),
            "transform": VOIDTOKEN_V5_TRANSFORM,
            "transformBlockSize": transform_block_size,
        }
        if mixed_precision:
            metadata["bitsByColumnGroup"] = list(bits_schedule)
            metadata["packedBytesByColumnGroup"] = packed_bytes_by_group
            metadata["packing"] = VOIDTOKEN_V5_MIXED_PACKING
        else:
            metadata["bits"] = bits_schedule[0]
            metadata["packing"] = _packing_name(bits_schedule[0])
        reconstructed = cls._decode_payload(
            payload, metadata, require_reconstruction_digest=False
        )
        metadata["reconstructionSha256"] = sha256_float32(reconstructed)
        container = _build_container(metadata, payload)
        encode_nanoseconds = time.perf_counter_ns() - encode_started

        decode_started = time.perf_counter_ns()
        verified = cls.decode(payload, metadata)
        decode_nanoseconds = time.perf_counter_ns() - decode_started
        if not np.array_equal(reconstructed, verified):
            raise RuntimeError("VoidToken v5 internal reconstruction mismatch")
        return VoidTokenV5Representation(
            payload=payload,
            container=container,
            metadata=metadata,
            reconstructed=verified,
            timing=CodecTiming(
                encode_nanoseconds=encode_nanoseconds,
                decode_nanoseconds=decode_nanoseconds,
            ),
        )

    @classmethod
    def _decode_payload(
        cls,
        payload: bytes | bytearray | memoryview,
        metadata: dict[str, Any],
        *,
        require_reconstruction_digest: bool,
    ) -> np.ndarray:
        raw = _bytes_like(payload, "payload")
        if len(raw) > MAX_CONTAINER_BYTES:
            raise ValueError("payload exceeds the VoidToken v5 resource limit")
        validation_metadata = metadata
        if not require_reconstruction_digest:
            validation_metadata = dict(metadata)
            validation_metadata.setdefault("reconstructionSha256", "0" * 64)
        (
            rows,
            columns,
            bits_by_group,
            packing,
            group_size,
            transform_block_size,
            layer_index,
            sign_mode,
            scale_count,
            scale_bytes,
            stored_scale_bytes,
            packed_bytes_by_group,
            stored_code_bytes,
        ) = cls._validate_metadata(validation_metadata)
        packed_bytes = sum(packed_bytes_by_group)
        if len(raw) != stored_scale_bytes + stored_code_bytes:
            raise ValueError("VoidToken v5 payload length mismatch")
        if sha256_bytes(raw) != metadata["payloadSha256"]:
            raise ValueError("VoidToken v5 payload SHA-256 mismatch")

        scale_payload = _decompress_canonical(
            raw[:stored_scale_bytes],
            metadata["scaleCompression"],
            scale_bytes,
            "VoidToken v5 scales",
        )
        packed_payload = _decompress_canonical(
            raw[stored_scale_bytes:],
            metadata["codeCompression"],
            packed_bytes,
            "VoidToken v5 codes",
        )
        scales = np.frombuffer(
            scale_payload, dtype=_SCALE_DTYPE, count=scale_count
        )
        if not np.all(np.isfinite(scales)):
            raise ValueError("VoidToken v5 contains non-finite scales")
        if np.any(scales < np.float16(0.0)) or np.any(np.signbit(scales)):
            raise ValueError("VoidToken v5 contains negative scales")

        groups_per_row = columns // group_size
        if packing == VOIDTOKEN_V5_MIXED_PACKING:
            quantized_groups = np.empty(
                (rows, groups_per_row, group_size), dtype=np.int32
            )
            packed_offset = 0
            for group_index, group_bits in enumerate(bits_by_group):
                group_packed_bytes = packed_bytes_by_group[group_index]
                group_codes = _unpack_v5_codes(
                    packed_payload[
                        packed_offset : packed_offset + group_packed_bytes
                    ],
                    group_bits,
                    rows * group_size,
                )
                group_qmax = (1 << (group_bits - 1)) - 1
                if np.any(group_codes > 2 * group_qmax):
                    raise ValueError(
                        "VoidToken v5 payload contains an unused code"
                    )
                quantized_groups[:, group_index, :] = (
                    _codes_to_quantized(group_codes).reshape(rows, group_size)
                )
                packed_offset += group_packed_bytes
            if packed_offset != packed_bytes:
                raise ValueError("mixed VoidToken v5 code layout mismatch")
        else:
            uniform_bits = bits_by_group[0]
            codes = _unpack_v5_codes(
                packed_payload, uniform_bits, rows * columns
            )
            qmax = (1 << (uniform_bits - 1)) - 1
            if np.any(codes > 2 * qmax):
                raise ValueError(
                    "VoidToken v5 payload contains an unused code"
                )
            quantized_groups = _codes_to_quantized(codes).reshape(
                rows, groups_per_row, group_size
            )
        scale_groups = scales.reshape(rows, groups_per_row)
        zero_scales = scale_groups == np.float16(0.0)
        if np.any(zero_scales & np.any(quantized_groups != 0, axis=2)):
            raise ValueError("zero-scale v5 group contains non-zero codes")
        transformed = (
            quantized_groups.astype(np.float64)
            * scale_groups.astype(np.float64)[:, :, np.newaxis]
        ).reshape(rows, columns)
        reconstructed = _inverse_transform(
            transformed, transform_block_size, layer_index, sign_mode
        )
        if require_reconstruction_digest:
            expected = metadata["reconstructionSha256"]
            if sha256_float32(reconstructed) != expected:
                raise ValueError("VoidToken v5 reconstruction SHA-256 mismatch")
        return reconstructed

    @classmethod
    def decode(
        cls,
        payload: bytes | bytearray | memoryview,
        metadata: dict[str, Any],
    ) -> np.ndarray:
        return cls._decode_payload(
            payload, metadata, require_reconstruction_digest=True
        )

    @classmethod
    def from_bytes(
        cls, container: bytes | bytearray | memoryview
    ) -> VoidTokenV5Representation:
        decode_started = time.perf_counter_ns()
        raw, metadata, payload = _parse_container(container)
        reconstructed = cls.decode(payload, metadata)
        decode_nanoseconds = time.perf_counter_ns() - decode_started
        return VoidTokenV5Representation(
            payload=payload,
            container=raw,
            metadata=metadata,
            reconstructed=reconstructed,
            timing=CodecTiming(
                encode_nanoseconds=0,
                decode_nanoseconds=decode_nanoseconds,
            ),
        )

    @classmethod
    def decode_container(
        cls, container: bytes | bytearray | memoryview
    ) -> np.ndarray:
        return cls.from_bytes(container).reconstructed


__all__ = [
    "VOIDTOKEN_V5_BITS",
    "VOIDTOKEN_V5_CODE_MAPPING",
    "VOIDTOKEN_V5_FORMAT",
    "VOIDTOKEN_V5_MAGIC",
    "VOIDTOKEN_V5_SIGN_DERIVATION",
    "VOIDTOKEN_V5_SIGN_MODES",
    "VOIDTOKEN_V5_TRANSFORM",
    "VoidTokenV5Backend",
    "VoidTokenV5Representation",
]
