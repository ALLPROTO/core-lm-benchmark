"""Deterministic packed group quantization for real-LLM telemetry.

The wire format is intentionally small and self-describing:

    b"RLGQ" | uint32_le(metadata_length) | canonical_json | binary_payload

The payload stores row-major little-endian float16 group scales followed by a
row-major LSB-first bitstream of offset-binary quantized values.  Timing data is
kept outside the container so repeated encodes of the same matrix are
byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import struct
import time
import zlib
from dataclasses import dataclass
from typing import Any

import numpy as np


PACKED_GROUP_QUANT_FORMAT = "packed-group-quant-v1"
PACKED_GROUP_QUANT_MAGIC = b"RLGQ"
PACKED_GROUP_QUANT_BITS = frozenset((4, 5, 6, 7, 8))

_CONTAINER_HEADER = struct.Struct("<4sI")
_SCALE_DTYPE = np.dtype("<f2")
_FLOAT32_LE_DTYPE = np.dtype("<f4")
_SHA256_HEX_LENGTH = 64


def _bytes_like(value: bytes | bytearray | memoryview, name: str) -> bytes:
    try:
        return bytes(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be bytes-like") from error


def canonical_json_bytes(value: Any) -> bytes:
    """Return the single canonical JSON encoding used by the container."""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("value is not canonical-JSON serializable") from error


def sha256_bytes(value: bytes | bytearray | memoryview) -> str:
    """Return the lowercase SHA-256 digest of a bytes-like value."""

    return hashlib.sha256(_bytes_like(value, "value")).hexdigest()


def float32_le_bytes(value: np.ndarray) -> bytes:
    """Return an array in canonical row-major little-endian float32 form."""

    array = np.asarray(value)
    canonical = np.ascontiguousarray(array, dtype=_FLOAT32_LE_DTYPE)
    return canonical.tobytes(order="C")


def sha256_float32(value: np.ndarray) -> str:
    """Hash an array after canonical float32/little-endian normalization."""

    return hashlib.sha256(float32_le_bytes(value)).hexdigest()


def _require_positive_int(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _require_sha256(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _pack_codes(codes: np.ndarray, bits: int) -> bytes:
    mask = (1 << bits) - 1
    output = bytearray()
    accumulator = 0
    buffered_bits = 0

    for raw_code in np.asarray(codes).reshape(-1):
        code = int(raw_code)
        if code < 0 or code > mask:
            raise ValueError("quantized code does not fit the selected bit width")
        accumulator |= code << buffered_bits
        buffered_bits += bits
        while buffered_bits >= 8:
            output.append(accumulator & 0xFF)
            accumulator >>= 8
            buffered_bits -= 8

    if buffered_bits:
        output.append(accumulator & 0xFF)
    return bytes(output)


def _unpack_codes(packed: bytes, bits: int, count: int) -> np.ndarray:
    expected_bytes = (count * bits + 7) // 8
    if len(packed) != expected_bytes:
        raise ValueError(
            f"packed code length mismatch: expected {expected_bytes}, "
            f"got {len(packed)}"
        )

    mask = (1 << bits) - 1
    if bits <= 8:
        code_dtype = np.uint8
    elif bits <= 16:
        code_dtype = np.uint16
    else:
        code_dtype = np.uint32
    codes = np.empty(count, dtype=code_dtype)
    accumulator = 0
    buffered_bits = 0
    output_index = 0

    for byte in packed:
        accumulator |= int(byte) << buffered_bits
        buffered_bits += 8
        while buffered_bits >= bits and output_index < count:
            codes[output_index] = accumulator & mask
            output_index += 1
            accumulator >>= bits
            buffered_bits -= bits

    if output_index != count:
        raise ValueError("truncated packed code stream")
    if accumulator != 0:
        raise ValueError("non-zero padding bits in packed code stream")
    return codes


def _build_container(metadata: dict[str, Any], payload: bytes) -> bytes:
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    raw_payload = _bytes_like(payload, "payload")
    metadata_bytes = canonical_json_bytes(metadata)
    if len(metadata_bytes) > 0xFFFFFFFF:
        raise ValueError("metadata is too large for the container")
    return (
        _CONTAINER_HEADER.pack(PACKED_GROUP_QUANT_MAGIC, len(metadata_bytes))
        + metadata_bytes
        + raw_payload
    )


def _parse_container(
    container: bytes | bytearray | memoryview,
) -> tuple[bytes, dict[str, Any], bytes]:
    raw = _bytes_like(container, "container")
    if len(raw) < _CONTAINER_HEADER.size:
        raise ValueError("truncated packed-group container header")

    magic, metadata_length = _CONTAINER_HEADER.unpack_from(raw)
    if magic != PACKED_GROUP_QUANT_MAGIC:
        raise ValueError("invalid packed-group container magic")

    metadata_start = _CONTAINER_HEADER.size
    metadata_end = metadata_start + metadata_length
    if metadata_end > len(raw):
        raise ValueError("truncated packed-group container metadata")

    metadata_bytes = raw[metadata_start:metadata_end]
    try:
        metadata = json.loads(metadata_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid packed-group container metadata") from error
    if not isinstance(metadata, dict):
        raise ValueError("packed-group container metadata must be an object")
    if canonical_json_bytes(metadata) != metadata_bytes:
        raise ValueError("packed-group container metadata is not canonical JSON")

    return raw, metadata, raw[metadata_end:]


@dataclass(frozen=True)
class CodecTiming:
    """Wall-clock measurements that are deliberately excluded from the wire."""

    encode_nanoseconds: int
    decode_nanoseconds: int


@dataclass(frozen=True)
class PackedGroupQuantRepresentation:
    """An encoded payload, its canonical container, reconstruction, and timing."""

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
    ) -> "PackedGroupQuantRepresentation":
        return PackedGroupQuantBackend.from_bytes(container)


class PackedGroupQuantBackend:
    """Symmetric per-row/per-group quantization with packed 4-8-bit codes."""

    FORMAT = PACKED_GROUP_QUANT_FORMAT
    MAGIC = PACKED_GROUP_QUANT_MAGIC
    SUPPORTED_BITS = PACKED_GROUP_QUANT_BITS

    @staticmethod
    def _validate_input(
        matrix: np.ndarray, bits: int, group_size: int
    ) -> tuple[np.ndarray, int, int, int]:
        array = np.asarray(matrix)
        if array.ndim != 2:
            raise ValueError("matrix must be two-dimensional")
        if array.dtype != np.dtype(np.float32):
            raise ValueError("matrix dtype must be float32")
        rows, columns = array.shape
        if rows <= 0 or columns <= 0:
            raise ValueError("matrix dimensions must be positive")
        if not np.all(np.isfinite(array)):
            raise ValueError("matrix contains non-finite values")
        if type(bits) is not int or bits not in PACKED_GROUP_QUANT_BITS:
            raise ValueError("bits must be one of 4, 5, 6, 7, or 8")
        group_size = _require_positive_int(group_size, "group_size")
        if columns % group_size != 0:
            raise ValueError("group_size must divide the matrix column count")
        return np.ascontiguousarray(array), rows, columns, columns // group_size

    @staticmethod
    def _validate_metadata(
        metadata: dict[str, Any],
    ) -> tuple[int, int, int, int, int, int, int, int]:
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        if metadata.get("format") != PACKED_GROUP_QUANT_FORMAT:
            raise ValueError("unsupported packed-group quantization format")
        if metadata.get("dtype") != "float32":
            raise ValueError("packed-group dtype must be float32")
        if metadata.get("scaleDtype") != "float16-le":
            raise ValueError("packed-group scales must be little-endian float16")
        scale_compression = metadata.get("scaleCompression")
        if scale_compression not in {"none", "zlib-9"}:
            raise ValueError("unsupported packed-group scale compression")
        if metadata.get("quantization") != "symmetric-max-abs-v1":
            raise ValueError("unsupported packed-group quantization rule")
        if metadata.get("codeMapping") != "offset-binary-symmetric-v1":
            raise ValueError("unsupported packed-group code mapping")
        if metadata.get("packing") != "lsb-first-v1":
            raise ValueError("unsupported packed-group bit packing")
        if metadata.get("groupAxis") != 1:
            raise ValueError("packed-group groupAxis must be 1")

        shape = metadata.get("shape")
        if (
            not isinstance(shape, list)
            or len(shape) != 2
            or any(type(dimension) is not int or dimension <= 0 for dimension in shape)
        ):
            raise ValueError("shape must contain two positive integers")
        rows, columns = shape

        bits = metadata.get("bits")
        if type(bits) is not int or bits not in PACKED_GROUP_QUANT_BITS:
            raise ValueError("bits must be one of 4, 5, 6, 7, or 8")
        group_size = _require_positive_int(metadata.get("groupSize"), "groupSize")
        if columns % group_size != 0:
            raise ValueError("groupSize must divide the matrix column count")

        groups_per_row = columns // group_size
        scale_count = rows * groups_per_row
        code_count = rows * columns
        scale_bytes = scale_count * _SCALE_DTYPE.itemsize
        packed_bytes = (code_count * bits + 7) // 8
        stored_scale_bytes = metadata.get("storedScaleBytes")
        if type(stored_scale_bytes) is not int or stored_scale_bytes <= 0:
            raise ValueError("storedScaleBytes must be a positive integer")
        if scale_compression == "none" and stored_scale_bytes != scale_bytes:
            raise ValueError("uncompressed scale length mismatch")
        payload_bytes = stored_scale_bytes + packed_bytes

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
                raise ValueError(f"{name} does not match the declared layout")

        _require_sha256(metadata.get("inputSha256"), "inputSha256")
        _require_sha256(metadata.get("payloadSha256"), "payloadSha256")
        _require_sha256(
            metadata.get("reconstructionSha256"), "reconstructionSha256"
        )
        return (
            rows,
            columns,
            bits,
            group_size,
            scale_count,
            scale_bytes,
            stored_scale_bytes,
            packed_bytes,
        )

    @classmethod
    def encode(
        cls,
        matrix: np.ndarray,
        *,
        bits: int = 4,
        group_size: int = 64,
        scale_compression: str = "none",
    ) -> PackedGroupQuantRepresentation:
        """Encode a finite 2D float32 matrix into the canonical container."""

        encode_started = time.perf_counter_ns()
        (
            array,
            rows,
            columns,
            groups_per_row,
        ) = cls._validate_input(matrix, bits, group_size)
        if scale_compression not in {"none", "zlib-9"}:
            raise ValueError("scale_compression must be none or zlib-9")

        qmax = (1 << (bits - 1)) - 1
        grouped = array.reshape(rows, groups_per_row, group_size)
        grouped64 = grouped.astype(np.float64)
        max_abs = np.max(np.abs(grouped64), axis=2)
        scale_values = max_abs / float(qmax)

        maximum_float16 = float(np.finfo(np.float16).max)
        if np.any(scale_values > maximum_float16):
            raise ValueError("a quantization scale is not representable as float16")

        scales = scale_values.astype(np.float16)
        smallest_float16 = np.nextafter(np.float16(0.0), np.float16(1.0))
        underflowed = (max_abs > 0.0) & (scales == np.float16(0.0))
        scales[underflowed] = smallest_float16

        scale64 = scales.astype(np.float64)
        ratios = np.zeros_like(grouped64)
        np.divide(
            grouped64,
            scale64[:, :, np.newaxis],
            out=ratios,
            where=scale64[:, :, np.newaxis] != 0.0,
        )
        quantized = np.clip(np.rint(ratios), -qmax, qmax).astype(np.int16)
        codes = (quantized + qmax).astype(np.uint8).reshape(-1)

        scales_le = np.ascontiguousarray(scales, dtype=_SCALE_DTYPE)
        scale_payload = scales_le.tobytes(order="C")
        stored_scale_payload = (
            scale_payload
            if scale_compression == "none"
            else zlib.compress(scale_payload, level=9)
        )
        packed_payload = _pack_codes(codes, bits)
        payload = stored_scale_payload + packed_payload

        scale_count = rows * groups_per_row
        code_count = rows * columns
        metadata: dict[str, Any] = {
            "bits": bits,
            "codeCount": code_count,
            "codeMapping": "offset-binary-symmetric-v1",
            "dtype": "float32",
            "format": PACKED_GROUP_QUANT_FORMAT,
            "groupAxis": 1,
            "groupSize": group_size,
            "groupsPerRow": groups_per_row,
            "inputSha256": sha256_float32(array),
            "packedBytes": len(packed_payload),
            "packing": "lsb-first-v1",
            "payloadBytes": len(payload),
            "payloadSha256": sha256_bytes(payload),
            "quantization": "symmetric-max-abs-v1",
            "scaleBytes": len(scale_payload),
            "scaleCompression": scale_compression,
            "scaleCount": scale_count,
            "scaleDtype": "float16-le",
            "shape": [rows, columns],
            "storedScaleBytes": len(stored_scale_payload),
        }

        reconstructed = cls._decode_payload(
            payload, metadata, require_reconstruction_digest=False
        )
        metadata["reconstructionSha256"] = sha256_float32(reconstructed)
        container = _build_container(metadata, payload)
        encode_nanoseconds = time.perf_counter_ns() - encode_started

        decode_started = time.perf_counter_ns()
        verified_reconstruction = cls.decode(payload, metadata)
        decode_nanoseconds = time.perf_counter_ns() - decode_started
        if not np.array_equal(reconstructed, verified_reconstruction):
            raise RuntimeError("packed-group internal reconstruction mismatch")

        return PackedGroupQuantRepresentation(
            payload=payload,
            container=container,
            metadata=metadata,
            reconstructed=verified_reconstruction,
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

        if require_reconstruction_digest:
            (
                rows,
                columns,
                bits,
                group_size,
                scale_count,
                scale_bytes,
                stored_scale_bytes,
                packed_bytes,
            ) = cls._validate_metadata(metadata)
        else:
            temporary_metadata = dict(metadata)
            temporary_metadata.setdefault("reconstructionSha256", "0" * 64)
            (
                rows,
                columns,
                bits,
                group_size,
                scale_count,
                scale_bytes,
                stored_scale_bytes,
                packed_bytes,
            ) = cls._validate_metadata(temporary_metadata)

        if len(raw) != stored_scale_bytes + packed_bytes:
            raise ValueError(
                f"payload length mismatch: expected "
                f"{stored_scale_bytes + packed_bytes}, "
                f"got {len(raw)}"
            )
        if sha256_bytes(raw) != metadata["payloadSha256"]:
            raise ValueError("packed-group payload SHA-256 mismatch")

        stored_scale_payload = raw[:stored_scale_bytes]
        if metadata["scaleCompression"] == "none":
            scale_payload = stored_scale_payload
        else:
            decompressor = zlib.decompressobj()
            try:
                scale_payload = decompressor.decompress(stored_scale_payload)
                scale_payload += decompressor.flush()
            except zlib.error as error:
                raise ValueError(
                    "invalid compressed packed-group scales"
                ) from error
            if (
                not decompressor.eof
                or decompressor.unused_data
                or decompressor.unconsumed_tail
            ):
                raise ValueError("non-canonical compressed scale stream")
        if len(scale_payload) != scale_bytes:
            raise ValueError("decoded packed-group scale length mismatch")
        scales = np.frombuffer(
            scale_payload, dtype=_SCALE_DTYPE, count=scale_count, offset=0
        )
        if not np.all(np.isfinite(scales)):
            raise ValueError("packed-group payload contains non-finite scales")
        if np.any(scales < np.float16(0.0)) or np.any(np.signbit(scales)):
            raise ValueError("packed-group payload contains negative scales")

        codes = _unpack_codes(raw[stored_scale_bytes:], bits, rows * columns)
        qmax = (1 << (bits - 1)) - 1
        if np.any(codes > 2 * qmax):
            raise ValueError("packed-group payload contains an unused code")
        quantized = codes.astype(np.int16) - qmax

        groups_per_row = columns // group_size
        quantized_groups = quantized.reshape(rows, groups_per_row, group_size)
        scale_groups = scales.reshape(rows, groups_per_row)
        zero_scale_groups = scale_groups == np.float16(0.0)
        if np.any(
            zero_scale_groups
            & np.any(quantized_groups != 0, axis=2)
        ):
            raise ValueError("zero-scale group contains non-zero quantized values")

        reconstructed = (
            quantized_groups.astype(np.float32)
            * scale_groups.astype(np.float32)[:, :, np.newaxis]
        ).reshape(rows, columns)
        reconstructed = np.ascontiguousarray(reconstructed, dtype=np.float32)

        if require_reconstruction_digest:
            expected_digest = metadata["reconstructionSha256"]
            if sha256_float32(reconstructed) != expected_digest:
                raise ValueError("packed-group reconstruction SHA-256 mismatch")
        return reconstructed

    @classmethod
    def decode(
        cls,
        payload: bytes | bytearray | memoryview,
        metadata: dict[str, Any],
    ) -> np.ndarray:
        """Decode and verify a packed payload using its canonical metadata."""

        return cls._decode_payload(
            payload, metadata, require_reconstruction_digest=True
        )

    @classmethod
    def from_bytes(
        cls, container: bytes | bytearray | memoryview
    ) -> PackedGroupQuantRepresentation:
        """Parse, validate, and decode a canonical packed-group container."""

        decode_started = time.perf_counter_ns()
        raw, metadata, payload = _parse_container(container)
        reconstructed = cls.decode(payload, metadata)
        decode_nanoseconds = time.perf_counter_ns() - decode_started
        return PackedGroupQuantRepresentation(
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
        """Decode a canonical container and return only its reconstruction."""

        return cls.from_bytes(container).reconstructed


__all__ = [
    "CodecTiming",
    "PACKED_GROUP_QUANT_BITS",
    "PACKED_GROUP_QUANT_FORMAT",
    "PACKED_GROUP_QUANT_MAGIC",
    "PackedGroupQuantBackend",
    "PackedGroupQuantRepresentation",
    "canonical_json_bytes",
    "float32_le_bytes",
    "sha256_bytes",
    "sha256_float32",
]
