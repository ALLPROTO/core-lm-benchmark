import json
import hashlib
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

    def test_void_zero_is_compact_and_exact(self):
        zero = np.zeros((21, 32), dtype=np.float32)
        encoded = VoidTokenBackend.encode(zero, top_k=8, qmax=127)
        self.assertTrue(np.array_equal(zero, encoded.reconstructed))
        self.assertEqual(encoded.payload_bytes, 32 * 4 + 20 * 6)

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
