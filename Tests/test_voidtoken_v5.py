import sys
import unittest
import zlib
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from RealLLM.voidtoken_v5 import (  # noqa: E402
    VOIDTOKEN_V5_CODE_MAPPING,
    VOIDTOKEN_V5_FORMAT,
    VoidTokenV5Backend,
    VoidTokenV5Representation,
    _build_container,
    _codes_to_quantized,
    _decompress_canonical,
    _pack_v5_codes,
    _quantized_to_codes,
    _unpack_v5_codes,
)
from RealLLM.codecs import sha256_bytes  # noqa: E402


class VoidTokenV5Tests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(20260729)
        self.matrix = rng.normal(0.0, 0.5, size=(17, 256)).astype(np.float32)

    def test_all_development_bit_widths_round_trip_fresh_container(self):
        previous_error = float("inf")
        for bits in (4, 5, 6, 7, 8, 9, 10, 12, 16):
            with self.subTest(bits=bits):
                encoded = VoidTokenV5Backend.encode(
                    self.matrix,
                    bits=bits,
                    group_size=32,
                    transform_block_size=64,
                    layer_index=8,
                )
                parsed = VoidTokenV5Representation.from_bytes(
                    encoded.to_bytes()
                )
                self.assertEqual(parsed.metadata, encoded.metadata)
                self.assertEqual(parsed.payload, encoded.payload)
                self.assertTrue(
                    np.array_equal(
                        parsed.reconstructed, encoded.reconstructed
                    )
                )
                error = float(
                    np.sqrt(
                        np.mean(
                            (
                                parsed.reconstructed.astype(np.float64)
                                - self.matrix.astype(np.float64)
                            )
                            ** 2
                        )
                    )
                )
                self.assertLess(error, previous_error)
                previous_error = error

    def test_high_field_packing_has_independent_golden_vectors(self):
        vectors = {
            9: (
                np.asarray([0, 1, 255, 256, 510], dtype=np.uint16),
                "0001ff00fe18",
            ),
            10: (
                np.asarray([0, 1, 255, 256, 1022], dtype=np.uint16),
                "0001ff00fe4003",
            ),
            12: (
                np.asarray([0, 1, 255, 256, 4094], dtype=np.uint16),
                "0001ff00fe00100f",
            ),
            16: (
                np.asarray([0, 1, 255, 256, 65534], dtype=np.uint16),
                "0001ff00fe00000001ff",
            ),
        }
        for bits, (codes, expected_hex) in vectors.items():
            with self.subTest(bits=bits):
                packed = _pack_v5_codes(codes, bits)
                self.assertEqual(packed.hex(), expected_hex)
                self.assertTrue(
                    np.array_equal(
                        _unpack_v5_codes(packed, bits, len(codes)),
                        codes,
                    )
                )

        padded = bytearray.fromhex(vectors[9][1])
        padded[-1] |= 0x80
        with self.assertRaises(ValueError):
            _unpack_v5_codes(bytes(padded), 9, 5)

    def test_zigzag_code_mapping_has_independent_golden_vector(self):
        quantized = np.asarray([-3, -2, -1, 0, 1, 2, 3], dtype=np.int32)
        expected = np.asarray([5, 3, 1, 0, 2, 4, 6], dtype=np.uint8)
        codes = _quantized_to_codes(quantized, 4)
        self.assertEqual(VOIDTOKEN_V5_CODE_MAPPING, "zigzag-symmetric-v1")
        self.assertTrue(np.array_equal(codes, expected))
        self.assertTrue(
            np.array_equal(_codes_to_quantized(codes), quantized)
        )

    def test_container_is_deterministic_and_counts_stored_bytes(self):
        first = VoidTokenV5Backend.encode(
            self.matrix,
            bits=8,
            group_size=64,
            transform_block_size=64,
            layer_index=3,
        )
        second = VoidTokenV5Backend.encode(
            self.matrix.copy(),
            bits=8,
            group_size=64,
            transform_block_size=64,
            layer_index=3,
        )
        self.assertEqual(first.to_bytes(), second.to_bytes())
        self.assertEqual(first.metadata["format"], VOIDTOKEN_V5_FORMAT)
        self.assertEqual(
            first.payload_bytes,
            first.metadata["storedScaleBytes"]
            + first.metadata["storedCodeBytes"],
        )
        self.assertEqual(first.container_bytes, len(first.to_bytes()))

    def test_full_container_has_a_frozen_golden_digest(self):
        matrix = (
            np.arange(16, dtype=np.float32).reshape(2, 8) - 7.5
        ) / 8
        encoded = VoidTokenV5Backend.encode(
            matrix,
            bits=9,
            group_size=4,
            transform_block_size=4,
            layer_index=0,
            scale_compression="none",
            code_compression="none",
            sign_mode="none",
        )
        self.assertEqual(encoded.container_bytes, 862)
        self.assertEqual(
            sha256_bytes(encoded.to_bytes()),
            "181ad32341718f1be2b7bec7dfb452e9fbc2a0f26a6210b44d8b013498896fb9",
        )
        self.assertEqual(
            encoded.reconstruction_sha256,
            "35601c79f3c0fa9696036fc97248213c740b5247ca34c22578c6807c6298db91",
        )
        parsed = VoidTokenV5Representation.from_bytes(encoded.to_bytes())
        self.assertTrue(
            np.array_equal(parsed.reconstructed, encoded.reconstructed)
        )

    def test_zero_matrix_is_exact_and_code_stream_is_compressed(self):
        zero = np.zeros((17, 256), dtype=np.float32)
        encoded = VoidTokenV5Backend.encode(
            zero,
            bits=8,
            group_size=64,
            transform_block_size=64,
            layer_index=0,
        )
        self.assertTrue(np.array_equal(encoded.reconstructed, zero))
        self.assertLess(
            encoded.metadata["storedCodeBytes"],
            encoded.metadata["packedBytes"],
        )
        parsed = VoidTokenV5Backend.from_bytes(encoded.to_bytes())
        self.assertTrue(np.array_equal(parsed.reconstructed, zero))

    def test_layer_index_is_part_of_the_transform(self):
        first = VoidTokenV5Backend.encode(
            self.matrix,
            bits=7,
            group_size=64,
            transform_block_size=64,
            layer_index=0,
        )
        second = VoidTokenV5Backend.encode(
            self.matrix,
            bits=7,
            group_size=64,
            transform_block_size=64,
            layer_index=1,
        )
        self.assertNotEqual(first.payload, second.payload)
        self.assertNotEqual(
            first.metadata["reconstructionSha256"],
            second.metadata["reconstructionSha256"],
        )

    def test_scale_group_can_span_aligned_transform_blocks(self):
        encoded = VoidTokenV5Backend.encode(
            self.matrix,
            bits=8,
            group_size=128,
            transform_block_size=64,
            layer_index=2,
            sign_mode="none",
        )
        parsed = VoidTokenV5Backend.from_bytes(encoded.to_bytes())
        self.assertEqual(parsed.metadata["groupsPerRow"], 2)
        self.assertTrue(
            np.array_equal(parsed.reconstructed, encoded.reconstructed)
        )

    def test_mixed_column_group_precision_round_trips_fresh_container(self):
        encoded = VoidTokenV5Backend.encode(
            self.matrix,
            bits=None,
            bits_by_column_group=[8, 9, 10, 8],
            group_size=64,
            transform_block_size=64,
            layer_index=5,
            sign_mode="none",
        )
        parsed = VoidTokenV5Backend.from_bytes(encoded.to_bytes())
        self.assertEqual(
            parsed.metadata["bitsByColumnGroup"], [8, 9, 10, 8]
        )
        self.assertEqual(
            sum(parsed.metadata["packedBytesByColumnGroup"]),
            parsed.metadata["packedBytes"],
        )
        self.assertTrue(
            np.array_equal(parsed.reconstructed, encoded.reconstructed)
        )

    def test_invalid_inputs_and_corruption_are_rejected(self):
        with self.assertRaises(ValueError):
            VoidTokenV5Backend.encode(
                self.matrix.astype(np.float64), bits=8, group_size=64
            )
        with self.assertRaises(ValueError):
            VoidTokenV5Backend.encode(
                self.matrix, bits=11, group_size=64
            )
        with self.assertRaises(ValueError):
            VoidTokenV5Backend.encode(
                self.matrix, bits=8, group_size=12
            )
        with self.assertRaises(ValueError):
            VoidTokenV5Backend.encode(
                self.matrix, bits=8, group_size=64, layer_index=-1
            )
        with self.assertRaises(ValueError):
            VoidTokenV5Backend.encode(
                self.matrix,
                bits=8,
                group_size=64,
                code_compression="gzip",
            )
        with self.assertRaises(ValueError):
            VoidTokenV5Backend.encode(
                self.matrix,
                bits=8,
                group_size=64,
                sign_mode="random",
            )
        with self.assertRaises(ValueError):
            VoidTokenV5Backend.encode(
                self.matrix,
                bits=8,
                bits_by_column_group=[8, 9, 8, 9],
                group_size=64,
            )
        with self.assertRaises(ValueError):
            VoidTokenV5Backend.encode(
                self.matrix,
                bits=None,
                bits_by_column_group=[8, 9],
                group_size=64,
            )

        encoded = VoidTokenV5Backend.encode(
            self.matrix, bits=8, group_size=64, layer_index=4
        )
        corrupted = bytearray(encoded.to_bytes())
        corrupted[-1] ^= 1
        with self.assertRaises(ValueError):
            VoidTokenV5Backend.from_bytes(corrupted)
        with self.assertRaises(ValueError):
            VoidTokenV5Backend.from_bytes(encoded.to_bytes()[:-1])

    def test_unknown_metadata_and_decompression_overflow_are_rejected(self):
        encoded = VoidTokenV5Backend.encode(
            self.matrix,
            bits=8,
            group_size=64,
            transform_block_size=64,
        )
        metadata = dict(encoded.metadata)
        metadata["unregisteredField"] = "forbidden"
        with self.assertRaisesRegex(ValueError, "key set is non-canonical"):
            VoidTokenV5Backend.from_bytes(
                _build_container(metadata, encoded.payload)
            )
        compressed_bomb = zlib.compress(b"x" * 10_000, level=9)
        with self.assertRaisesRegex(ValueError, "exceeds its bound"):
            _decompress_canonical(
                compressed_bomb,
                "zlib-9",
                1,
                "test stream",
            )

        bad_compression = dict(encoded.metadata)
        bad_compression["codeCompression"] = []
        with self.assertRaises(ValueError):
            VoidTokenV5Backend.decode(encoded.payload, bad_compression)
        bad_sign = dict(encoded.metadata)
        bad_sign["signMode"] = []
        with self.assertRaises(ValueError):
            VoidTokenV5Backend.decode(encoded.payload, bad_sign)

    def test_unused_all_ones_code_is_rejected(self):
        zero = np.zeros((1, 256), dtype=np.float32)
        encoded = VoidTokenV5Backend.encode(
            zero,
            bits=9,
            group_size=64,
            transform_block_size=64,
            layer_index=0,
            scale_compression="none",
            code_compression="none",
        )
        metadata = dict(encoded.metadata)
        payload = bytearray(encoded.payload)
        low_start = metadata["storedScaleBytes"]
        high_start = low_start + metadata["codeCount"]
        payload[low_start] = 0xFF
        payload[high_start] |= 0x01
        metadata["payloadSha256"] = sha256_bytes(bytes(payload))
        corrupted = _build_container(metadata, bytes(payload))
        with self.assertRaises(ValueError):
            VoidTokenV5Backend.from_bytes(corrupted)


if __name__ == "__main__":
    unittest.main()
