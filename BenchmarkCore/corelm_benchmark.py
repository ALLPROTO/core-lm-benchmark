#!/usr/bin/env python3
"""Reproducible Core LM compression benchmark.

The module intentionally has no UI dependency. It materializes one input stream,
runs one dense Core LM trajectory, then evaluates lossless dense storage, PCA,
and delta-based VoidToken storage against that exact trajectory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import struct
import time
import tracemalloc
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np


VERSION = "0.3.0"
CORE_ARITHMETIC_VERSION = "fixed-order-f64-v1"
VOIDTOKEN_CANONICALIZATION_VERSION = "fixed-order-v1"
VOIDTOKEN_FORMAT = "voidtoken-residual-keyframe-v4"
VOIDTOKEN_LEGACY_FORMAT = "voidtoken-residual-keyframe-v3"
MAX_CONTAINER_BYTES = 256 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
MAX_DECODED_MATRIX_ELEMENTS = 8 * 1024 * 1024
MAX_DECODED_MATRIX_BYTES = MAX_DECODED_MATRIX_ELEMENTS * 4


def _fixed_pairwise_sum_last(values: np.ndarray) -> np.ndarray:
    """Reduce the last axis with one platform-independent binary tree."""
    work = np.ascontiguousarray(values, dtype=np.float64)
    if work.ndim == 0 or work.shape[-1] == 0:
        raise ValueError("fixed-order reduction requires a non-empty axis")
    while work.shape[-1] > 1:
        width = work.shape[-1]
        pair_count = width // 2
        reduced = (
            work[..., : pair_count * 2 : 2]
            + work[..., 1 : pair_count * 2 : 2]
        )
        if width % 2:
            work = np.concatenate((reduced, work[..., -1:]), axis=-1)
        else:
            work = reduced
    return work[..., 0]


def _fixed_sum(values: np.ndarray) -> float:
    flattened = np.ascontiguousarray(values, dtype=np.float64).reshape(1, -1)
    return float(_fixed_pairwise_sum_last(flattened)[0])


def _fixed_mean(values: np.ndarray) -> float:
    array = np.asarray(values)
    if array.size == 0:
        raise ValueError("fixed-order mean requires at least one value")
    return _fixed_sum(array) / array.size


def _fixed_dot(left: np.ndarray, right: np.ndarray) -> float:
    left_array = np.ascontiguousarray(left, dtype=np.float64).reshape(-1)
    right_array = np.ascontiguousarray(right, dtype=np.float64).reshape(-1)
    if left_array.shape != right_array.shape or left_array.size == 0:
        raise ValueError("fixed-order dot operands must have equal non-empty shapes")
    products = left_array * right_array
    return _fixed_sum(products)


def _fixed_matvec(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    matrix_array = np.ascontiguousarray(matrix, dtype=np.float64)
    vector_array = np.ascontiguousarray(vector, dtype=np.float64).reshape(-1)
    if (
        matrix_array.ndim != 2
        or matrix_array.shape[1] != vector_array.size
        or vector_array.size == 0
    ):
        raise ValueError("fixed-order matrix/vector shape mismatch")
    products = matrix_array * vector_array[np.newaxis, :]
    return np.asarray(_fixed_pairwise_sum_last(products), dtype=np.float64)


def _fixed_variance(values: np.ndarray) -> float:
    array = np.ascontiguousarray(values, dtype=np.float64).reshape(-1)
    if array.size == 0:
        raise ValueError("fixed-order variance requires at least one value")
    mean = _fixed_sum(array) / array.size
    deviations = array - mean
    return _fixed_sum(deviations * deviations) / array.size


def _fixed_l2_norm(values: np.ndarray) -> float:
    squared_norm = _fixed_dot(values, values)
    return math.sqrt(max(0.0, squared_norm))


def _deterministic_tanh(values: np.ndarray | float) -> np.ndarray | float:
    """Near-machine-precision tanh using only fixed-order IEEE-754 arithmetic."""
    source = np.asarray(values, dtype=np.float64)
    reduced = np.clip(source, -16.0, 16.0) / 64.0
    squared = reduced * reduced

    polynomial = np.full_like(squared, 21844.0 / 6081075.0)
    polynomial = (-1382.0 / 155925.0) + squared * polynomial
    polynomial = (62.0 / 2835.0) + squared * polynomial
    polynomial = (-17.0 / 315.0) + squared * polynomial
    polynomial = (2.0 / 15.0) + squared * polynomial
    polynomial = (-1.0 / 3.0) + squared * polynomial
    result = reduced * (1.0 + squared * polynomial)

    # tanh(2x) = 2 tanh(x) / (1 + tanh(x)^2). Six fixed
    # doublings undo the division by 64 above.
    for _ in range(6):
        result = (2.0 * result) / (1.0 + result * result)
    result = np.where(source >= 16.0, 1.0, result)
    result = np.where(source <= -16.0, -1.0, result)
    if result.ndim == 0:
        return float(result)
    return result


def _canonical_float32(value: float) -> float:
    """Round once to the little-endian float stored in the wire format."""
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def _void_dequantized_value(quantized: int, qmax: int, norm: float) -> np.float32:
    normalized = float(quantized) / float(qmax)
    return np.float32(normalized * float(norm))


def _void_advance_state(previous: np.ndarray, residual: np.ndarray) -> np.ndarray:
    advanced = (
        np.asarray(previous, dtype=np.float64)
        + np.asarray(residual, dtype=np.float64)
    )
    return advanced.astype(np.float32)


@dataclass(frozen=True)
class Thresholds:
    minimum_compression_ratio: float = 4.0
    maximum_normalized_rmse: float = 0.10
    minimum_cosine_similarity: float = 0.95
    maximum_mean_energy_relative_drift: float = 0.05
    maximum_invariant_violations: int = 0


@dataclass(frozen=True)
class ExperimentConfiguration:
    dimension: int = 96
    steps: int = 200
    seed: int = 42
    input_scenario: str = "gaussian_bounded"
    input_bound: float = 0.05
    pca_components: int = 8
    top_k: int = 16
    qmax: int = 127
    keyframe_interval: int = 0
    thresholds: Thresholds = Thresholds()

    def validate(self) -> None:
        if self.dimension < 2:
            raise ValueError("dimension must be >= 2")
        if self.steps < 2:
            raise ValueError("steps must be >= 2")
        if (self.steps + 1) * self.dimension > MAX_DECODED_MATRIX_ELEMENTS:
            raise ValueError(
                "state trajectory exceeds the decoded-matrix resource limit"
            )
        if self.dimension * self.dimension > MAX_DECODED_MATRIX_ELEMENTS:
            raise ValueError(
                "Core LM weight matrix exceeds the decoded-matrix resource limit"
            )
        if not 1 <= self.pca_components <= min(self.steps + 1, self.dimension):
            raise ValueError("invalid pca_components")
        if not 1 <= self.top_k <= min(self.dimension, 0xFFFE):
            raise ValueError("invalid top_k")
        if self.qmax not in (127, 32767):
            raise ValueError("qmax must be 127 or 32767")
        if self.keyframe_interval < 0:
            raise ValueError("keyframe_interval must be >= 0")
        if self.input_scenario not in {
            "zero",
            "gaussian_bounded",
            "uniform_bounded",
            "impulse",
            "repeating_structured",
        }:
            raise ValueError("unknown input scenario")


class DeterministicInputGenerator:
    @staticmethod
    def generate(config: ExperimentConfiguration) -> np.ndarray:
        rng = np.random.default_rng(config.seed)
        shape = (config.steps, config.dimension)
        bound = np.float32(config.input_bound)
        if config.input_scenario == "zero":
            result = np.zeros(shape, dtype=np.float32)
        elif config.input_scenario == "gaussian_bounded":
            result = np.clip(
                rng.normal(0.0, config.input_bound / 2.0, size=shape),
                -config.input_bound,
                config.input_bound,
            ).astype(np.float32)
        elif config.input_scenario == "uniform_bounded":
            result = rng.uniform(-config.input_bound, config.input_bound, size=shape).astype(np.float32)
        elif config.input_scenario == "impulse":
            result = np.zeros(shape, dtype=np.float32)
            indices = rng.choice(config.dimension, size=max(1, config.dimension // 8), replace=False)
            result[0, indices] = rng.choice(np.array([-bound, bound], dtype=np.float32), size=len(indices))
        else:
            period = min(8, config.steps)
            motif = rng.uniform(-config.input_bound, config.input_bound, size=(period, config.dimension))
            result = np.tile(motif, (math.ceil(config.steps / period), 1))[: config.steps].astype(np.float32)
        return np.ascontiguousarray(result, dtype=np.float32)

    @staticmethod
    def digest(stream: np.ndarray) -> str:
        return hashlib.sha256(np.ascontiguousarray(stream).tobytes()).hexdigest()


class CoreLMAdapter:
    """Numerically equivalent transition to the v1.5 reference dynamics."""

    def __init__(self, dimension: int, seed: int = 42):
        self.dimension = dimension
        rng = np.random.default_rng(seed)
        weights = rng.normal(0.0, 0.02, size=(dimension, dimension)).astype(np.float32)
        vector = rng.normal(0.0, 1.0, size=(dimension,)).astype(np.float32)
        for _ in range(10):
            projected = _fixed_matvec(weights, vector)
            vector64 = _fixed_matvec(weights.T, projected)
            vector_norm = _fixed_l2_norm(vector64)
            vector = (vector64 / (vector_norm + 1e-8)).astype(np.float32)
        weight_scale = _fixed_l2_norm(_fixed_matvec(weights, vector)) + 1e-8
        self.weights = (weights.astype(np.float64) / weight_scale).astype(np.float32)

    def run(self, inputs: np.ndarray) -> np.ndarray:
        if inputs.ndim != 2 or inputs.shape[1] != self.dimension:
            raise ValueError("input dimension mismatch")
        state = np.zeros(self.dimension, dtype=np.float32)
        states = np.empty((len(inputs) + 1, self.dimension), dtype=np.float32)
        states[0] = state
        history: list[np.ndarray] = [state.copy()]
        for index, impulse in enumerate(inputs, 1):
            tail = np.stack(history[-32:])
            hist_var = _fixed_variance(tail) if len(tail) > 1 else 0.0
            state64 = state.astype(np.float64)
            energy = _fixed_dot(state64, state64) + 0.5 * hist_var
            gamma = 0.05 * (
                1.0
                + 0.25
                * float(
                    _deterministic_tanh(
                        energy / max(1.0, float(self.dimension))
                    )
                )
            )
            dynamics = (
                _fixed_matvec(self.weights, state64)
                + np.asarray(_deterministic_tanh(state64), dtype=np.float64)
            )
            next_state = state64 + (0.10 * dynamics)
            next_state = next_state + (0.20 * impulse.astype(np.float64))
            next_state = next_state - ((2.0 * gamma) * state64)
            state = next_state.astype(np.float32)
            states[index] = state
            history.append(state.copy())
        return states


@dataclass
class EncodedRepresentation:
    CONTAINER_MAGIC = b"CLMB"

    name: str
    payload: bytes
    metadata: dict[str, Any]
    reconstructed: np.ndarray
    encode_nanoseconds: int
    decode_nanoseconds: int

    @property
    def payload_bytes(self) -> int:
        return len(self.payload)

    @property
    def file_bytes(self) -> int:
        return len(self.to_bytes())

    def to_bytes(self) -> bytes:
        metadata_bytes = json.dumps(
            self.metadata,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(metadata_bytes) > MAX_METADATA_BYTES:
            raise ValueError("container metadata exceeds the encoder resource limit")
        container = (
            self.CONTAINER_MAGIC
            + struct.pack("<I", len(metadata_bytes))
            + metadata_bytes
            + self.payload
        )
        if len(container) > MAX_CONTAINER_BYTES:
            raise ValueError("container exceeds the encoder resource limit")
        return container

    @classmethod
    def from_bytes(cls, container: bytes) -> EncodedRepresentation:
        try:
            raw = bytes(container)
        except (TypeError, ValueError) as error:
            raise ValueError("container must be bytes-like") from error
        if len(raw) < 8:
            raise ValueError("truncated container header")
        if len(raw) > MAX_CONTAINER_BYTES:
            raise ValueError("container exceeds the decoder resource limit")
        if raw[:4] != cls.CONTAINER_MAGIC:
            raise ValueError("invalid container magic")
        metadata_length = struct.unpack_from("<I", raw, 4)[0]
        if metadata_length > MAX_METADATA_BYTES:
            raise ValueError("container metadata exceeds the decoder resource limit")
        metadata_end = 8 + metadata_length
        if metadata_end > len(raw):
            raise ValueError("truncated container metadata")
        try:
            metadata = json.loads(raw[8:metadata_end].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("invalid container metadata") from error
        if not isinstance(metadata, dict):
            raise ValueError("container metadata must be an object")
        canonical_metadata = json.dumps(
            metadata,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if raw[8:metadata_end] != canonical_metadata:
            raise ValueError("container metadata is not canonical JSON")
        payload = raw[metadata_end:]
        format_name = metadata.get("format")
        decoders = {
            "dense-v1": ("dense", DenseBackend.decode),
            "pca-v1": ("pca", PCABackend.decode),
            VOIDTOKEN_FORMAT: ("voidtoken", VoidTokenBackend.decode),
            VOIDTOKEN_LEGACY_FORMAT: ("voidtoken", VoidTokenBackend.decode),
        }
        if format_name not in decoders:
            raise ValueError(f"unsupported representation format: {format_name!r}")
        name, decoder = decoders[format_name]
        started = time.perf_counter_ns()
        reconstructed = decoder(payload, metadata)
        decode_ns = time.perf_counter_ns() - started
        return cls(
            name,
            payload,
            metadata,
            reconstructed,
            encode_nanoseconds=0,
            decode_nanoseconds=decode_ns,
        )


def _decode_metadata(
    metadata: dict[str, Any],
    expected_format: str,
    *,
    require_dtype: bool = True,
) -> tuple[int, int]:
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    if metadata.get("format") != expected_format:
        raise ValueError(f"expected {expected_format} metadata")
    dtype = metadata.get("dtype")
    if (
        (require_dtype and dtype != "float32")
        or (not require_dtype and dtype not in (None, "float32"))
    ):
        raise ValueError("unsupported dtype")
    shape = metadata.get("shape")
    if (
        not isinstance(shape, list)
        or len(shape) != 2
        or any(type(value) is not int or value <= 0 for value in shape)
    ):
        raise ValueError("shape must contain two positive integers")
    rows, columns = shape
    elements = rows * columns
    if elements > MAX_DECODED_MATRIX_ELEMENTS:
        raise ValueError(
            "shape exceeds the decoded-matrix resource limit"
        )
    return rows, columns


def _payload_bytes(payload: bytes) -> bytes:
    try:
        return bytes(payload)
    except (TypeError, ValueError) as error:
        raise ValueError("payload must be bytes-like") from error


class DenseBackend:
    @staticmethod
    def decode(payload: bytes, metadata: dict[str, Any]) -> np.ndarray:
        rows, columns = _decode_metadata(metadata, "dense-v1")
        raw = _payload_bytes(payload)
        expected_bytes = rows * columns * 4
        if len(raw) != expected_bytes:
            raise ValueError(
                f"dense payload length mismatch: expected {expected_bytes}, got {len(raw)}"
            )
        reconstructed = np.frombuffer(raw, dtype="<f4").reshape(rows, columns).copy()
        if not np.isfinite(reconstructed).all():
            raise ValueError("dense payload contains non-finite values")
        return reconstructed

    @staticmethod
    def encode(states: np.ndarray) -> EncodedRepresentation:
        started = time.perf_counter_ns()
        contiguous = np.ascontiguousarray(states, dtype="<f4")
        payload = contiguous.tobytes()
        encode_ns = time.perf_counter_ns() - started
        metadata = {
            "shape": list(states.shape),
            "dtype": "float32",
            "format": "dense-v1",
        }
        started = time.perf_counter_ns()
        reconstructed = DenseBackend.decode(payload, metadata)
        decode_ns = time.perf_counter_ns() - started
        return EncodedRepresentation(
            "dense",
            payload,
            metadata,
            reconstructed,
            encode_ns,
            decode_ns,
        )


class PCABackend:
    @staticmethod
    def decode(payload: bytes, metadata: dict[str, Any]) -> np.ndarray:
        rows, columns = _decode_metadata(metadata, "pca-v1")
        components = metadata.get("components")
        if (
            type(components) is not int
            or not 1 <= components <= min(rows, columns)
        ):
            raise ValueError("invalid PCA component count")
        raw = _payload_bytes(payload)
        mean_values = columns
        basis_values = components * columns
        score_values = rows * components
        expected_bytes = (mean_values + basis_values + score_values) * 4
        if len(raw) != expected_bytes:
            raise ValueError(
                f"PCA payload length mismatch: expected {expected_bytes}, got {len(raw)}"
            )
        values = np.frombuffer(raw, dtype="<f4")
        mean_end = mean_values
        basis_end = mean_end + basis_values
        mean = values[:mean_end].reshape(1, columns)
        basis = values[mean_end:basis_end].reshape(components, columns)
        scores = values[basis_end:].reshape(rows, components)
        if not np.isfinite(values).all():
            raise ValueError("PCA payload contains non-finite values")
        reconstructed = (scores @ basis + mean).astype(np.float32)
        if not np.isfinite(reconstructed).all():
            raise ValueError("PCA reconstruction contains non-finite values")
        return reconstructed

    @staticmethod
    def encode(states: np.ndarray, components: int) -> EncodedRepresentation:
        started = time.perf_counter_ns()
        source = np.asarray(states, dtype=np.float32)
        mean = source.mean(axis=0, keepdims=True)
        centered = source - mean
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        basis = vt[:components].astype(np.float32)
        scores = (centered @ basis.T).astype(np.float32)
        payload = mean.astype("<f4").tobytes() + basis.astype("<f4").tobytes() + scores.astype("<f4").tobytes()
        encode_ns = time.perf_counter_ns() - started
        metadata = {
            "shape": list(states.shape),
            "components": components,
            "dtype": "float32",
            "format": "pca-v1",
        }
        started = time.perf_counter_ns()
        reconstructed = PCABackend.decode(payload, metadata)
        decode_ns = time.perf_counter_ns() - started
        return EncodedRepresentation(
            "pca",
            payload,
            metadata,
            reconstructed,
            encode_ns,
            decode_ns,
        )


class VoidTokenBackend:
    @staticmethod
    def decode(payload: bytes, metadata: dict[str, Any]) -> np.ndarray:
        format_name = metadata.get("format")
        if format_name not in (VOIDTOKEN_FORMAT, VOIDTOKEN_LEGACY_FORMAT):
            raise ValueError("unsupported VoidToken format")
        rows, columns = _decode_metadata(
            metadata,
            format_name,
            require_dtype=False,
        )
        top_k = metadata.get("topK")
        qmax = metadata.get("qmax")
        keyframe_interval = metadata.get("keyframeInterval")
        index_bytes = metadata.get("indexBytes")
        quantized_value_bytes = metadata.get("quantizedValueBytes")
        canonicalization_version = metadata.get("canonicalizationVersion")
        if type(top_k) is not int or not 1 <= top_k <= min(columns, 0xFFFE):
            raise ValueError("invalid VoidToken topK")
        if qmax not in (127, 32767) or type(qmax) is not int:
            raise ValueError("invalid VoidToken qmax")
        if (
            type(keyframe_interval) is not int
            or keyframe_interval < 0
        ):
            raise ValueError("invalid VoidToken keyframe interval")
        expected_index_bytes = 2 if columns <= 65535 else 4
        expected_quantized_bytes = 1 if qmax == 127 else 2
        if index_bytes != expected_index_bytes:
            raise ValueError("VoidToken index width does not match the shape")
        if quantized_value_bytes != expected_quantized_bytes:
            raise ValueError("VoidToken quantized value width does not match qmax")
        if format_name == VOIDTOKEN_LEGACY_FORMAT:
            if canonicalization_version is not None:
                raise ValueError(
                    "legacy VoidToken v3 must not declare canonicalization"
                )
            canonical = False
        else:
            if canonicalization_version != VOIDTOKEN_CANONICALIZATION_VERSION:
                raise ValueError(
                    "unsupported VoidToken canonicalization version"
                )
            canonical = True

        raw = _payload_bytes(payload)
        initial_state_bytes = columns * 4
        if len(raw) < initial_state_bytes:
            raise ValueError("truncated VoidToken initial state")
        minimum_payload_bytes = initial_state_bytes + (rows - 1) * 6
        if len(raw) < minimum_payload_bytes:
            raise ValueError("truncated VoidToken payload")
        reconstructed = np.empty((rows, columns), dtype=np.float32)
        reconstructed[0] = np.frombuffer(
            raw, dtype="<f4", count=columns, offset=0
        )
        if not np.isfinite(reconstructed[0]).all():
            raise ValueError("VoidToken initial state contains non-finite values")
        offset = initial_state_bytes
        index_dtype = "<u2" if index_bytes == 2 else "<u4"
        quantized_dtype = "<i1" if quantized_value_bytes == 1 else "<i2"

        for row in range(1, rows):
            if offset + 6 > len(raw):
                raise ValueError(f"truncated VoidToken header at row {row}")
            norm, count = struct.unpack_from("<fH", raw, offset)
            offset += 6
            if not math.isfinite(norm) or norm < 0.0:
                raise ValueError(f"invalid VoidToken norm at row {row}")

            if count == 0xFFFF:
                if norm != 0.0:
                    raise ValueError(f"invalid VoidToken keyframe sentinel at row {row}")
                if (
                    keyframe_interval == 0
                    or row % keyframe_interval != 0
                ):
                    raise ValueError(f"unexpected VoidToken keyframe at row {row}")
                keyframe_end = offset + initial_state_bytes
                if keyframe_end > len(raw):
                    raise ValueError(f"truncated VoidToken keyframe at row {row}")
                keyframe = np.frombuffer(
                    raw, dtype="<f4", count=columns, offset=offset
                )
                if not np.isfinite(keyframe).all():
                    raise ValueError(
                        f"VoidToken keyframe contains non-finite values at row {row}"
                    )
                reconstructed[row] = keyframe
                offset = keyframe_end
                continue

            if count > top_k or count > columns:
                raise ValueError(f"invalid VoidToken count at row {row}")
            if (norm == 0.0) != (count == 0):
                raise ValueError(
                    f"VoidToken norm/count mismatch at row {row}"
                )
            indices_end = offset + count * index_bytes
            token_end = indices_end + count * quantized_value_bytes
            if token_end > len(raw):
                raise ValueError(f"truncated VoidToken token at row {row}")
            indices = np.frombuffer(
                raw, dtype=index_dtype, count=count, offset=offset
            )
            quantized = np.frombuffer(
                raw, dtype=quantized_dtype, count=count, offset=indices_end
            )
            if count:
                indices_i64 = indices.astype(np.int64)
                if np.any(indices_i64 >= columns):
                    raise ValueError(
                        f"VoidToken index out of bounds at row {row}"
                    )
                if count > 1 and np.any(np.diff(indices_i64) <= 0):
                    raise ValueError(
                        f"VoidToken indices are not strictly increasing at row {row}"
                    )
                quantized_i64 = quantized.astype(np.int64)
                if np.any(np.abs(quantized_i64) > qmax):
                    raise ValueError(
                        f"VoidToken quantized value out of range at row {row}"
                    )
            residual = np.zeros(columns, dtype=np.float32)
            if count:
                if not canonical:
                    # Preserve the original v3 float32 vector arithmetic for
                    # containers written before canonicalizationVersion existed.
                    residual[indices] = (
                        quantized.astype(np.float32) / float(qmax)
                    ) * norm
                else:
                    for coordinate, value in zip(indices, quantized):
                        residual[int(coordinate)] = _void_dequantized_value(
                            int(value), qmax, norm
                        )
            if not canonical:
                reconstructed[row] = reconstructed[row - 1] + residual
            else:
                reconstructed[row] = _void_advance_state(
                    reconstructed[row - 1], residual
                )
            if not np.isfinite(reconstructed[row]).all():
                raise ValueError(
                    f"VoidToken reconstruction is non-finite at row {row}"
                )
            offset = token_end

        if offset != len(raw):
            raise ValueError(
                f"trailing VoidToken payload bytes: {len(raw) - offset}"
            )
        return reconstructed

    @staticmethod
    def encode(
        states: np.ndarray, top_k: int, qmax: int, keyframe_interval: int = 0
    ) -> EncodedRepresentation:
        started = time.perf_counter_ns()
        source = np.asarray(states, dtype=np.float32)
        if source.ndim != 2 or source.shape[0] < 1 or source.shape[1] < 1:
            raise ValueError("states must be a non-empty two-dimensional array")
        if not np.isfinite(source).all():
            raise ValueError("states must contain only finite values")
        if (
            type(top_k) is not int
            or not 1 <= top_k <= min(source.shape[1], 0xFFFE)
        ):
            raise ValueError("invalid VoidToken topK")
        if type(qmax) is not int or qmax not in (127, 32767):
            raise ValueError("invalid VoidToken qmax")
        if type(keyframe_interval) is not int or keyframe_interval < 0:
            raise ValueError("invalid VoidToken keyframe interval")
        index_format = "<H" if source.shape[1] <= 65535 else "<I"
        quant_format = "<b" if qmax == 127 else "<h"
        requested_keyframe_interval = keyframe_interval
        if keyframe_interval == 0:
            dense_per_state = source.shape[1] * 4
            token_bytes = 6 + top_k * (
                struct.calcsize(index_format) + struct.calcsize(quant_format)
            )
            keyframe_bytes = 6 + dense_per_state
            byte_budget = dense_per_state / 4.1
            if byte_budget > token_bytes:
                required = math.ceil(
                    (keyframe_bytes - token_bytes) / (byte_budget - token_bytes)
                )
                keyframe_interval = max(8, 1 << (max(1, required) - 1).bit_length())
            else:
                keyframe_interval = 0
        effective_keyframe_interval = keyframe_interval
        chunks = [source[0].astype("<f4").tobytes()]
        reconstructed = np.empty_like(source)
        reconstructed[0] = source[0]
        for row in range(1, len(source)):
            # Error-feedback residual: encode the target state relative to what
            # the decoder actually knows, not relative to the previous dense
            # state. Dropped coordinates remain in the next residual and are
            # eventually corrected instead of accumulating forever.
            residual = (
                source[row].astype(np.float64)
                - reconstructed[row - 1].astype(np.float64)
            ).astype(np.float32)
            norm = _canonical_float32(_fixed_l2_norm(residual))
            if (
                effective_keyframe_interval > 0
                and row % effective_keyframe_interval == 0
                and norm >= 1e-12
            ):
                keyframe = source[row].astype("<f4", copy=True)
                chunks.append(struct.pack("<fH", 0.0, 0xFFFF))
                chunks.append(keyframe.tobytes())
                reconstructed[row] = source[row]
                continue
            if norm < 1e-12:
                norm = 0.0
                indices = np.empty(0, dtype=np.int64)
                quantized = np.empty(0, dtype=np.int32)
            else:
                count = min(top_k, len(residual))
                coordinates = np.arange(len(residual), dtype=np.int64)
                magnitudes = np.abs(residual.astype(np.float64))
                indices = np.lexsort((coordinates, -magnitudes))[:count]
                indices = np.sort(indices)
                quantized = np.empty(count, dtype=np.int32)
                for token_index, coordinate in enumerate(indices):
                    normalized = float(residual[int(coordinate)]) / norm
                    rounded = round(normalized * float(qmax))
                    quantized[token_index] = max(-qmax, min(qmax, rounded))
            chunks.append(struct.pack("<fH", norm, len(indices)))
            chunks.extend(struct.pack(index_format, int(item)) for item in indices)
            chunks.extend(struct.pack(quant_format, int(item)) for item in quantized)
            decoded = np.zeros(source.shape[1], dtype=np.float32)
            for coordinate, value in zip(indices, quantized):
                decoded[int(coordinate)] = _void_dequantized_value(
                    int(value), qmax, norm
                )
            reconstructed[row] = _void_advance_state(
                reconstructed[row - 1], decoded
            )
        payload = b"".join(chunks)
        encode_ns = time.perf_counter_ns() - started

        metadata = {
            "shape": list(states.shape),
            "topK": top_k,
            "qmax": qmax,
            "keyframeInterval": effective_keyframe_interval,
            "keyframePolicy": "automatic-byte-budget"
            if requested_keyframe_interval == 0
            else "explicit",
            "indexBytes": struct.calcsize(index_format),
            "quantizedValueBytes": struct.calcsize(quant_format),
            "prediction": "decoder-state-error-feedback",
            "canonicalizationVersion": VOIDTOKEN_CANONICALIZATION_VERSION,
            "format": VOIDTOKEN_FORMAT,
        }
        started = time.perf_counter_ns()
        decoded_states = VoidTokenBackend.decode(payload, metadata)
        decode_ns = time.perf_counter_ns() - started
        return EncodedRepresentation(
            "voidtoken",
            payload,
            metadata,
            decoded_states,
            encode_ns,
            decode_ns,
        )


def trajectory_signals(states: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    energy = np.empty(len(states), dtype=np.float64)
    csi = np.empty(len(states), dtype=np.float64)
    for index in range(len(states)):
        energy[index] = _fixed_dot(states[index], states[index])
        tail = states[max(0, index - 31) : index + 1]
        variance = _fixed_variance(tail) if len(tail) > 1 else 0.0
        csi[index] = 1.0 / (variance + 1e-8)
    drift = np.abs(np.diff(energy, prepend=energy[0]))
    return energy, csi, drift


def relative_mean_drift(reference: np.ndarray, candidate: np.ndarray) -> float:
    reference_mean = _fixed_mean(reference)
    denominator = max(abs(reference_mean), 1e-12)
    return abs(_fixed_mean(candidate) - reference_mean) / denominator


def method_metrics(
    representation: EncodedRepresentation,
    reference: np.ndarray,
    dense_payload_bytes: int,
    elapsed_seconds: float,
) -> dict[str, Any]:
    candidate = representation.reconstructed
    difference = candidate.astype(np.float64) - reference.astype(np.float64)
    rmse = math.sqrt(_fixed_mean(difference * difference))
    reference64 = reference.astype(np.float64)
    scale = max(math.sqrt(_fixed_mean(reference64 * reference64)), 1e-12)
    nrmse = rmse / scale
    ref_flat = reference64.ravel()
    candidate_flat = candidate.astype(np.float64).ravel()
    denominator = _fixed_l2_norm(ref_flat) * _fixed_l2_norm(candidate_flat)
    if denominator < 1e-20:
        cosine = 1.0 if np.array_equal(reference, candidate) else 0.0
    else:
        cosine = _fixed_dot(ref_flat, candidate_flat) / denominator
    ref_energy, ref_csi, ref_drift = trajectory_signals(reference)
    energy, csi, drift = trajectory_signals(candidate)
    return {
        "name": representation.name,
        "payloadBytes": representation.payload_bytes,
        "fileBytes": representation.file_bytes,
        "compressionRatio": dense_payload_bytes / max(1, representation.payload_bytes),
        "rmse": rmse,
        "normalizedRMSE": nrmse,
        "cosineSimilarity": cosine,
        "maximumAbsoluteError": float(np.max(np.abs(difference))),
        "trajectoryRMSE": rmse,
        "meanEnergyRelativeDrift": relative_mean_drift(ref_energy, energy),
        "csiRelativeDrift": relative_mean_drift(ref_csi, csi),
        "energyDriftRelativeDifference": relative_mean_drift(ref_drift, drift),
        "encodeNanoseconds": representation.encode_nanoseconds,
        "decodeNanoseconds": representation.decode_nanoseconds,
        "stepsPerSecond": (len(reference) - 1) / max(elapsed_seconds, 1e-12),
        "peakMemoryBytes": None,
        "metadata": representation.metadata,
    }


def invariant_violations(inputs: np.ndarray, states: np.ndarray, bound: float) -> list[str]:
    problems: list[str] = []
    if states.shape[0] != inputs.shape[0] + 1 or states.shape[1] != inputs.shape[1]:
        problems.append("dimension consistency")
    if not np.isfinite(inputs).all():
        problems.append("non-finite input")
    if not np.isfinite(states).all():
        problems.append("non-finite state")
    if float(np.nanmax(np.abs(inputs))) > bound + 1e-6:
        problems.append("input bound")
    return problems


def stable_run_id(config: ExperimentConfiguration, input_digest: str) -> str:
    material = json.dumps(
        {
            "dimension": config.dimension,
            "steps": config.steps,
            "seed": config.seed,
            "scenario": config.input_scenario,
            "inputBound": config.input_bound,
            "pca": config.pca_components,
            "topK": config.top_k,
            "qmax": config.qmax,
            "keyframeInterval": config.keyframe_interval,
            "thresholds": asdict(config.thresholds),
            "coreArithmeticVersion": CORE_ARITHMETIC_VERSION,
            "voidTokenCanonicalizationVersion": (
                VOIDTOKEN_CANONICALIZATION_VERSION
            ),
            "voidTokenFormat": VOIDTOKEN_FORMAT,
            "inputDigest": input_digest,
        },
        sort_keys=True,
    ).encode()
    return hashlib.sha256(material).hexdigest()[:16]


def build_time_series(
    states: np.ndarray, pca_states: np.ndarray, void_states: np.ndarray, maximum_points: int = 240
) -> list[dict[str, float | int]]:
    energy, csi, drift = trajectory_signals(states)
    indices = np.unique(
        np.linspace(0, len(states) - 1, min(maximum_points, len(states))).astype(int)
    )
    samples: list[dict[str, float | int]] = []
    for index in indices:
        pca_difference = pca_states[index].astype(np.float64) - states[index].astype(np.float64)
        void_difference = void_states[index].astype(np.float64) - states[index].astype(np.float64)
        samples.append({
            "step": int(index),
            "stateNorm": _fixed_l2_norm(states[index]),
            "energy": float(energy[index]),
            "csi": float(csi[index]),
            "energyDrift": float(drift[index]),
            "pcaRMSE": math.sqrt(_fixed_mean(pca_difference * pca_difference)),
            "voidTokenRMSE": math.sqrt(
                _fixed_mean(void_difference * void_difference)
            ),
        })
    return samples


def choose_verdict(methods: list[dict[str, Any]], violations: list[str], deterministic: bool,
                   thresholds: Thresholds) -> tuple[str, list[str]]:
    void = next((item for item in methods if item["name"] == "voidtoken"), None)
    if void is None:
        return "INCONCLUSIVE", ["VoidToken result missing"]
    reasons: list[str] = []
    checks = [
        (void["compressionRatio"] >= thresholds.minimum_compression_ratio,
         f"compression {void['compressionRatio']:.4f}x < {thresholds.minimum_compression_ratio:.4f}x"),
        (void["normalizedRMSE"] <= thresholds.maximum_normalized_rmse,
         f"NRMSE {void['normalizedRMSE']:.6f} > {thresholds.maximum_normalized_rmse:.6f}"),
        (void["cosineSimilarity"] >= thresholds.minimum_cosine_similarity,
         f"cosine {void['cosineSimilarity']:.6f} < {thresholds.minimum_cosine_similarity:.6f}"),
        (void["meanEnergyRelativeDrift"] <= thresholds.maximum_mean_energy_relative_drift,
         f"energy drift {void['meanEnergyRelativeDrift']:.6f} > "
         f"{thresholds.maximum_mean_energy_relative_drift:.6f}"),
        (len(violations) <= thresholds.maximum_invariant_violations,
         f"invariant violations {len(violations)} > {thresholds.maximum_invariant_violations}"),
        (deterministic, "deterministic replay failed"),
    ]
    reasons.extend(message for passed, message in checks if not passed)
    return ("PASS" if not reasons else "FAIL"), reasons


def run_benchmark(config: ExperimentConfiguration) -> dict[str, Any]:
    config.validate()
    tracemalloc.start()
    inputs = DeterministicInputGenerator.generate(config)
    digest = DeterministicInputGenerator.digest(inputs)
    core = CoreLMAdapter(config.dimension)
    started = time.perf_counter()
    states = core.run(inputs)
    elapsed = time.perf_counter() - started

    replay_inputs = DeterministicInputGenerator.generate(config)
    replay_states = CoreLMAdapter(config.dimension).run(replay_inputs)
    deterministic = np.array_equal(inputs, replay_inputs) and np.array_equal(states, replay_states)

    dense = DenseBackend.encode(states)
    pca = PCABackend.encode(states, config.pca_components)
    void = VoidTokenBackend.encode(
        states, config.top_k, config.qmax, config.keyframe_interval
    )
    representations = [dense, pca, void]
    methods = [
        method_metrics(item, states, dense.payload_bytes, elapsed) for item in representations
    ]
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    for item in methods:
        item["peakMemoryBytes"] = peak_memory

    violations = invariant_violations(inputs, states, config.input_bound)
    verdict, reasons = choose_verdict(methods, violations, deterministic, config.thresholds)
    core_state_digest = hashlib.sha256(
        np.ascontiguousarray(states, dtype="<f4").tobytes()
    ).hexdigest()
    void_payload_digest = hashlib.sha256(void.payload).hexdigest()
    void_container_digest = hashlib.sha256(void.to_bytes()).hexdigest()
    void_reconstruction_digest = hashlib.sha256(
        np.ascontiguousarray(void.reconstructed, dtype="<f4").tobytes()
    ).hexdigest()
    return {
        "schemaVersion": "0.3",
        "runId": stable_run_id(config, digest),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "coreArithmeticVersion": CORE_ARITHMETIC_VERSION,
        "configuration": {
            "dimension": config.dimension,
            "steps": config.steps,
            "seed": config.seed,
            "inputScenario": config.input_scenario,
            "inputBound": config.input_bound,
            "pcaComponents": config.pca_components,
            "topK": config.top_k,
            "qmax": config.qmax,
            "keyframeInterval": config.keyframe_interval,
            "thresholds": asdict(config.thresholds),
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "implementationVersion": VERSION,
        },
        "inputDigest": digest,
        "coreStateDigest": core_state_digest,
        "voidTokenPayloadDigest": void_payload_digest,
        "voidTokenContainerDigest": void_container_digest,
        "voidTokenReconstructionDigest": void_reconstruction_digest,
        "coreRuntimeNanoseconds": int(elapsed * 1e9),
        "methods": methods,
        "timeSeries": build_time_series(states, pca.reconstructed, void.reconstructed),
        "invariants": {
            "violations": len(violations),
            "deterministicReplay": deterministic,
            "details": violations,
        },
        "verdict": verdict,
        "verdictReasons": reasons,
    }


def markdown_report(result: dict[str, Any]) -> str:
    configuration = result["configuration"]
    lines = [
        f"# Core LM Benchmark — {result['runId']}",
        "",
        f"Verdict: **{result['verdict']}**",
        "",
        f"Scenario: `{configuration['inputScenario']}`, n={configuration['dimension']}, "
        f"steps={configuration['steps']}, seed={configuration['seed']}.",
        "",
        f"Core arithmetic: `{result['coreArithmeticVersion']}`.",
        f"Core state SHA-256: `{result['coreStateDigest']}`.",
        f"VoidToken payload SHA-256: `{result['voidTokenPayloadDigest']}`.",
        f"VoidToken container SHA-256: `{result['voidTokenContainerDigest']}`.",
        (
            "VoidToken reconstruction SHA-256: "
            f"`{result['voidTokenReconstructionDigest']}`."
        ),
        "",
        "| Method | Payload bytes | File bytes | Ratio | NRMSE | Cosine | Energy drift |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for method in result["methods"]:
        lines.append(
            f"| {method['name']} | {method['payloadBytes']} | {method['fileBytes']} | "
            f"{method['compressionRatio']:.3f}× | {method['normalizedRMSE']:.6f} | "
            f"{method['cosineSimilarity']:.6f} | {method['meanEnergyRelativeDrift']:.6f} |"
        )
    lines += [
        "",
        f"Invariant violations: {result['invariants']['violations']}.",
        f"Deterministic replay: {result['invariants']['deterministicReplay']}.",
        "",
        "## Verdict reasons",
        "",
    ]
    lines.extend(
        [f"- {reason}" for reason in result["verdictReasons"]]
        or ["- All configured PASS thresholds were satisfied."]
    )
    return "\n".join(lines) + "\n"


def _exclusive_write_text(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(content)


def save_result(result: dict[str, Any], output_directory: Path) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    stem = result["runId"]
    json_path = output_directory / f"{stem}.json"
    markdown_path = output_directory / f"{stem}.md"
    _exclusive_write_text(
        json_path,
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )
    _exclusive_write_text(markdown_path, markdown_report(result))
    return json_path, markdown_path


def aggregate_suite(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(results)
    counts = {name: sum(item["verdict"] == name for item in items) for name in ("PASS", "FAIL", "INCONCLUSIVE")}
    void_results = [
        next(method for method in item["methods"] if method["name"] == "voidtoken") for item in items
    ]
    return {
        "coreArithmeticVersion": CORE_ARITHMETIC_VERSION,
        "runs": len(items),
        "verdictCounts": counts,
        "aggregateVerdict": "PASS" if items and counts["PASS"] == len(items)
        else ("INCONCLUSIVE" if counts["INCONCLUSIVE"] else "FAIL"),
        "voidToken": {
            "minimumCompressionRatio": min((x["compressionRatio"] for x in void_results), default=None),
            "maximumNormalizedRMSE": max((x["normalizedRMSE"] for x in void_results), default=None),
            "minimumCosineSimilarity": min((x["cosineSimilarity"] for x in void_results), default=None),
            "maximumMeanEnergyRelativeDrift": max(
                (x["meanEnergyRelativeDrift"] for x in void_results), default=None
            ),
        },
        "runIds": [item["runId"] for item in items],
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dimension", type=int, default=96)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenario", default="gaussian_bounded")
    parser.add_argument("--pca-components", type=int, default=8)
    parser.add_argument("--top-k", type=int, default=16)
    parser.add_argument("--qmax", type=int, default=127)
    parser.add_argument("--keyframe-interval", type=int, default=0)
    parser.add_argument("--minimum-compression-ratio", type=float, default=4.0)
    parser.add_argument("--maximum-normalized-rmse", type=float, default=0.10)
    parser.add_argument("--minimum-cosine-similarity", type=float, default=0.95)
    parser.add_argument("--maximum-energy-drift", type=float, default=0.05)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "benchmark-results",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    configuration = ExperimentConfiguration(
        dimension=args.dimension,
        steps=args.steps,
        seed=args.seed,
        input_scenario=args.scenario,
        pca_components=args.pca_components,
        top_k=args.top_k,
        qmax=args.qmax,
        keyframe_interval=args.keyframe_interval,
        thresholds=Thresholds(
            minimum_compression_ratio=args.minimum_compression_ratio,
            maximum_normalized_rmse=args.maximum_normalized_rmse,
            minimum_cosine_similarity=args.minimum_cosine_similarity,
            maximum_mean_energy_relative_drift=args.maximum_energy_drift,
        ),
    )
    result = run_benchmark(configuration)
    json_path, markdown_path = save_result(result, args.output)
    print(json.dumps({
        "verdict": result["verdict"],
        "runId": result["runId"],
        "json": str(json_path),
        "markdown": str(markdown_path),
        "reasons": result["verdictReasons"],
    }, indent=2))
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
