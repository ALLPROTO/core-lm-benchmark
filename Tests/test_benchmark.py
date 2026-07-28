import json
import hashlib
import struct
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "BenchmarkCore"))

from corelm_benchmark import (  # noqa: E402
    CoreLMAdapter,
    DenseBackend,
    DeterministicInputGenerator,
    EncodedRepresentation,
    ExperimentConfiguration,
    PCABackend,
    Thresholds,
    VoidTokenBackend,
    choose_verdict,
    invariant_violations,
    method_metrics,
    markdown_report,
    run_benchmark,
    save_result,
)


class InputTests(unittest.TestCase):
    def test_same_seed_is_byte_identical(self):
        config = ExperimentConfiguration(dimension=32, steps=20, seed=7, top_k=8)
        first = DeterministicInputGenerator.generate(config)
        second = DeterministicInputGenerator.generate(config)
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(
            DeterministicInputGenerator.digest(first),
            DeterministicInputGenerator.digest(second),
        )

    def test_scenarios_are_bounded(self):
        for scenario in ("zero", "gaussian_bounded", "uniform_bounded", "impulse", "repeating_structured"):
            config = ExperimentConfiguration(
                dimension=32, steps=20, seed=7, input_scenario=scenario, top_k=8
            )
            values = DeterministicInputGenerator.generate(config)
            self.assertLessEqual(float(np.max(np.abs(values))), config.input_bound + 1e-7)

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            ExperimentConfiguration(dimension=8, steps=20, top_k=9).validate()
        with self.assertRaises(ValueError):
            ExperimentConfiguration(
                dimension=65535, steps=2, pca_components=1, top_k=65535
            ).validate()

    def test_core_golden_trajectory(self):
        config = ExperimentConfiguration(
            dimension=8, steps=3, seed=7, input_scenario="uniform_bounded",
            pca_components=2, top_k=2,
        )
        inputs = DeterministicInputGenerator.generate(config)
        states = CoreLMAdapter(8).run(inputs)
        # BLAS implementations may differ by a few float32 ULPs. Quantizing to
        # 1e-6 before hashing preserves a strict semantic golden value across
        # macOS Accelerate and Linux OpenBLAS.
        canonical = np.rint(states.astype(np.float64) * 1_000_000).astype("<i4")
        digest = hashlib.sha256(canonical.tobytes()).hexdigest()
        self.assertEqual(
            digest,
            "3c9298157faed2d910ee835befe9e03c624c679ecd8e469d6ce3106304686e18",
        )


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.config = ExperimentConfiguration(dimension=32, steps=40, seed=7, top_k=8)
        self.inputs = DeterministicInputGenerator.generate(self.config)
        self.states = CoreLMAdapter(32).run(self.inputs)

    def test_dense_is_lossless_and_size_is_exact(self):
        encoded = DenseBackend.encode(self.states)
        self.assertTrue(np.array_equal(self.states, encoded.reconstructed))
        self.assertEqual(encoded.payload_bytes, self.states.size * 4)

    def test_pca_full_rank_reconstructs(self):
        small = self.states[:10, :8]
        encoded = PCABackend.encode(small, components=8)
        self.assertLess(float(np.max(np.abs(small - encoded.reconstructed))), 1e-5)

    def test_container_round_trip_decodes_all_backends_from_bytes(self):
        representations = (
            DenseBackend.encode(self.states),
            PCABackend.encode(self.states, components=8),
            VoidTokenBackend.encode(
                self.states, top_k=8, qmax=127, keyframe_interval=4
            ),
        )
        for encoded in representations:
            with self.subTest(backend=encoded.name):
                container = encoded.to_bytes()
                parsed = EncodedRepresentation.from_bytes(container)
                self.assertEqual(parsed.name, encoded.name)
                self.assertEqual(parsed.metadata, encoded.metadata)
                self.assertEqual(parsed.payload, encoded.payload)
                self.assertEqual(len(container), encoded.file_bytes)
                self.assertTrue(
                    np.array_equal(parsed.reconstructed, encoded.reconstructed)
                )

    def test_container_rejects_bad_header_metadata_and_trailing_payload(self):
        encoded = DenseBackend.encode(self.states)
        container = encoded.to_bytes()
        with self.assertRaises(ValueError):
            EncodedRepresentation.from_bytes(container[:7])
        with self.assertRaises(ValueError):
            EncodedRepresentation.from_bytes(b"FAIL" + container[4:])
        with self.assertRaises(ValueError):
            EncodedRepresentation.from_bytes(
                EncodedRepresentation.CONTAINER_MAGIC
                + struct.pack("<I", len(container))
                + container[8:]
            )
        invalid_json = b"{"
        with self.assertRaises(ValueError):
            EncodedRepresentation.from_bytes(
                EncodedRepresentation.CONTAINER_MAGIC
                + struct.pack("<I", len(invalid_json))
                + invalid_json
            )
        noncanonical_metadata = json.dumps(
            encoded.metadata, sort_keys=False, indent=2
        ).encode()
        with self.assertRaises(ValueError):
            EncodedRepresentation.from_bytes(
                EncodedRepresentation.CONTAINER_MAGIC
                + struct.pack("<I", len(noncanonical_metadata))
                + noncanonical_metadata
                + encoded.payload
            )
        with self.assertRaises(ValueError):
            EncodedRepresentation.from_bytes(container + b"\x00")

    def test_dense_and_pca_reject_malformed_payloads(self):
        dense = DenseBackend.encode(self.states)
        with self.assertRaises(ValueError):
            DenseBackend.decode(dense.payload[:-1], dense.metadata)

        pca = PCABackend.encode(self.states, components=8)
        with self.assertRaises(ValueError):
            PCABackend.decode(pca.payload[:-4], pca.metadata)
        corrupted_pca = bytearray(pca.payload)
        struct.pack_into("<f", corrupted_pca, 0, float("nan"))
        with self.assertRaises(ValueError):
            PCABackend.decode(corrupted_pca, pca.metadata)

    def test_void_zero_is_compact_and_exact(self):
        zero = np.zeros((21, 32), dtype=np.float32)
        encoded = VoidTokenBackend.encode(zero, top_k=8, qmax=127)
        self.assertTrue(np.array_equal(zero, encoded.reconstructed))
        self.assertEqual(encoded.payload_bytes, 32 * 4 + 20 * 6)

    def test_void_canonicalizes_sub_epsilon_residual_to_zero_token(self):
        states = np.array([[0.0, 0.0], [1e-13, 0.0]], dtype=np.float32)
        encoded = VoidTokenBackend.encode(states, top_k=1, qmax=127)
        norm, count = struct.unpack_from("<fH", encoded.payload, states.shape[1] * 4)
        self.assertEqual(norm, 0.0)
        self.assertEqual(count, 0)
        parsed = EncodedRepresentation.from_bytes(encoded.to_bytes())
        self.assertTrue(np.array_equal(parsed.reconstructed, encoded.reconstructed))

    def test_void_payload_formula(self):
        encoded = VoidTokenBackend.encode(
            self.states, top_k=8, qmax=127, keyframe_interval=16
        )
        residual_tokens = 38
        keyframes = 2
        expected = (
            32 * 4
            + residual_tokens * (4 + 2 + 8 * 2 + 8)
            + keyframes * (4 + 2 + 32 * 4)
        )
        self.assertEqual(encoded.payload_bytes, expected)

    def test_void_rejects_truncation_bounds_quantization_and_bad_sentinel(self):
        encoded = VoidTokenBackend.encode(
            self.states, top_k=8, qmax=127, keyframe_interval=4
        )
        with self.assertRaises(ValueError):
            VoidTokenBackend.decode(encoded.payload[:-1], encoded.metadata)

        first_header = self.states.shape[1] * 4
        count = struct.unpack_from("<H", encoded.payload, first_header + 4)[0]
        self.assertGreater(count, 1)

        out_of_bounds = bytearray(encoded.payload)
        struct.pack_into("<H", out_of_bounds, first_header + 6, self.states.shape[1])
        with self.assertRaises(ValueError):
            VoidTokenBackend.decode(out_of_bounds, encoded.metadata)

        invalid_quantized = bytearray(encoded.payload)
        first_quantized = first_header + 6 + count * 2
        struct.pack_into("<b", invalid_quantized, first_quantized, -128)
        with self.assertRaises(ValueError):
            VoidTokenBackend.decode(invalid_quantized, encoded.metadata)

        invalid_sentinel = bytearray(encoded.payload)
        struct.pack_into("<H", invalid_sentinel, first_header + 4, 0xFFFF)
        with self.assertRaises(ValueError):
            VoidTokenBackend.decode(invalid_sentinel, encoded.metadata)

    def test_error_feedback_prevents_nonzero_drift_accumulation(self):
        config = ExperimentConfiguration(
            dimension=32, steps=200, seed=7,
            input_scenario="gaussian_bounded", top_k=4,
        )
        states = CoreLMAdapter(32).run(DeterministicInputGenerator.generate(config))
        encoded = VoidTokenBackend.encode(states, top_k=4, qmax=127)
        dense = DenseBackend.encode(states)
        metrics = method_metrics(
            encoded, states, dense.payload_bytes, elapsed_seconds=0.01
        )
        self.assertLess(metrics["normalizedRMSE"], 0.10)
        self.assertGreater(metrics["cosineSimilarity"], 0.95)
        self.assertLess(metrics["meanEnergyRelativeDrift"], 0.05)
        self.assertGreater(metrics["compressionRatio"], 4.0)


class IntegrationTests(unittest.TestCase):
    def test_replay_and_reports(self):
        config = ExperimentConfiguration(dimension=32, steps=40, seed=17, top_k=8)
        first = run_benchmark(config)
        second = run_benchmark(config)
        self.assertEqual(first["runId"], second["runId"])
        self.assertEqual(first["inputDigest"], second["inputDigest"])
        self.assertTrue(first["invariants"]["deterministicReplay"])
        with TemporaryDirectory() as directory:
            json_path, markdown_path = save_result(first, Path(directory))
            loaded = json.loads(json_path.read_text())
            self.assertEqual(loaded["runId"], first["runId"])
            self.assertIn("Verdict:", markdown_path.read_text())
            required = {
                "schemaVersion", "runId", "createdAt", "configuration",
                "environment", "inputDigest", "coreRuntimeNanoseconds",
                "methods", "timeSeries", "invariants", "verdict", "verdictReasons",
            }
            self.assertEqual(set(loaded), required)
            self.assertEqual({m["name"] for m in loaded["methods"]}, {"dense", "pca", "voidtoken"})
            self.assertGreater(len(loaded["timeSeries"]), 1)
            self.assertEqual(loaded["timeSeries"][0]["step"], 0)

    def test_failed_threshold_is_fail(self):
        methods = [{
            "name": "voidtoken",
            "compressionRatio": 1.0,
            "normalizedRMSE": 0.0,
            "cosineSimilarity": 1.0,
            "meanEnergyRelativeDrift": 0.0,
        }]
        verdict, reasons = choose_verdict(methods, [], True, Thresholds())
        self.assertEqual(verdict, "FAIL")
        self.assertTrue(reasons)

    def test_invariant_checker_detects_nonfinite_and_bound(self):
        inputs = np.array([[np.nan, 2.0]], dtype=np.float32)
        states = np.zeros((2, 2), dtype=np.float32)
        problems = invariant_violations(inputs, states, 0.05)
        self.assertIn("non-finite input", problems)
        self.assertIn("input bound", problems)

    def test_dense_metrics_are_exact(self):
        states = np.zeros((3, 4), dtype=np.float32)
        dense = DenseBackend.encode(states)
        metrics = method_metrics(dense, states, dense.payload_bytes, 0.01)
        self.assertEqual(metrics["normalizedRMSE"], 0)
        self.assertEqual(metrics["cosineSimilarity"], 1)
        self.assertEqual(metrics["compressionRatio"], 1)

    def test_markdown_contains_real_method_rows(self):
        result = run_benchmark(
            ExperimentConfiguration(
                dimension=8, steps=20, seed=7, input_scenario="zero",
                pca_components=4, top_k=2,
            )
        )
        report = markdown_report(result)
        self.assertIn("| dense |", report)
        self.assertIn("| pca |", report)
        self.assertIn("| voidtoken |", report)


if __name__ == "__main__":
    unittest.main()
