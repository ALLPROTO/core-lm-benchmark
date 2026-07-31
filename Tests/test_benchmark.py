import json
import hashlib
import math
import subprocess
import struct
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "BenchmarkCore"))

import corelm_benchmark as benchmark_module  # noqa: E402
from corelm_benchmark import (  # noqa: E402
    CORE_ARITHMETIC_VERSION,
    MAX_DECODED_MATRIX_ELEMENTS,
    VOIDTOKEN_CANONICALIZATION_VERSION,
    VOIDTOKEN_FORMAT,
    VOIDTOKEN_LEGACY_FORMAT,
    CoreLMAdapter,
    DenseBackend,
    DeterministicInputGenerator,
    EncodedRepresentation,
    ExperimentConfiguration,
    PCABackend,
    Thresholds,
    VoidTokenBackend,
    _canonical_float32,
    _deterministic_tanh,
    _fixed_l2_norm,
    _fixed_pairwise_sum_last,
    choose_verdict,
    invariant_violations,
    method_metrics,
    markdown_report,
    run_benchmark,
    save_result,
    stable_run_id,
)
from verify_evidence import (  # noqa: E402
    FLOAT_ABSOLUTE_TOLERANCE,
    FLOAT_RELATIVE_TOLERANCE,
    compare_values,
    verify_evidence,
)


class InputTests(unittest.TestCase):
    def test_fixed_order_reduction_has_a_declared_binary_tree(self):
        values = np.array(
            [
                [1e16, 1.0, -1e16, 1.0],
                [1.0, 2.0, 3.0, 4.0],
            ],
            dtype=np.float64,
        )
        reduced = _fixed_pairwise_sum_last(values)
        self.assertTrue(np.array_equal(reduced, np.array([0.0, 10.0])))

    def test_deterministic_tanh_matches_reference_to_float64_precision(self):
        values = np.linspace(-16.0, 16.0, 4097, dtype=np.float64)
        candidate = np.asarray(_deterministic_tanh(values))
        maximum_error = float(np.max(np.abs(candidate - np.tanh(values))))
        self.assertLess(maximum_error, 3e-14)
        self.assertEqual(_deterministic_tanh(-20.0), -1.0)
        self.assertEqual(_deterministic_tanh(20.0), 1.0)

    def test_same_seed_is_byte_identical(self):
        config = ExperimentConfiguration(dimension=32, steps=20, seed=7, top_k=8)
        first = DeterministicInputGenerator.generate(config)
        second = DeterministicInputGenerator.generate(config)
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(
            DeterministicInputGenerator.digest(first),
            DeterministicInputGenerator.digest(second),
        )

    def test_run_id_covers_all_provenance_fields(self):
        base = ExperimentConfiguration(
            dimension=32,
            steps=20,
            seed=7,
            input_scenario="gaussian_bounded",
            input_bound=0.05,
            pca_components=8,
            top_k=4,
            qmax=127,
            keyframe_interval=0,
        )
        input_digest = "a" * 64
        reference = stable_run_id(base, input_digest)
        variants = [
            replace(base, dimension=33),
            replace(base, steps=21),
            replace(base, seed=8),
            replace(base, input_scenario="uniform_bounded"),
            replace(base, input_bound=0.04),
            replace(base, pca_components=7),
            replace(base, top_k=5),
            replace(base, qmax=32767),
            replace(base, keyframe_interval=16),
            replace(
                base,
                thresholds=replace(
                    base.thresholds,
                    minimum_compression_ratio=4.1,
                ),
            ),
        ]
        variant_ids = [stable_run_id(config, input_digest) for config in variants]
        variant_ids.append(stable_run_id(base, "b" * 64))
        self.assertTrue(all(run_id != reference for run_id in variant_ids))
        self.assertEqual(len(set(variant_ids)), len(variant_ids))

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

    def test_configuration_rejects_large_matrices_before_allocation(self):
        oversized_trajectory = ExperimentConfiguration(
            dimension=2,
            steps=MAX_DECODED_MATRIX_ELEMENTS // 2,
            pca_components=1,
            top_k=1,
        )
        with patch.object(DeterministicInputGenerator, "generate") as generate:
            with self.assertRaisesRegex(
                ValueError, "state trajectory.*resource limit"
            ):
                run_benchmark(oversized_trajectory)
        generate.assert_not_called()
        oversized_dimension = math.isqrt(MAX_DECODED_MATRIX_ELEMENTS) + 1
        with self.assertRaisesRegex(ValueError, "weight matrix.*resource limit"):
            ExperimentConfiguration(
                dimension=oversized_dimension,
                steps=2,
                pca_components=1,
                top_k=1,
            ).validate()

    def test_core_golden_trajectory(self):
        config = ExperimentConfiguration(
            dimension=8, steps=3, seed=7, input_scenario="uniform_bounded",
            pca_components=2, top_k=2,
        )
        inputs = DeterministicInputGenerator.generate(config)
        states = CoreLMAdapter(8).run(inputs)
        digest = hashlib.sha256(states.astype("<f4").tobytes()).hexdigest()
        self.assertEqual(
            digest,
            "3db2e25ca09ca65d728d689cc0fda0f29555653d7ae8e72253b1d550e934da16",
        )
        self.assertEqual(
            stable_run_id(config, DeterministicInputGenerator.digest(inputs)),
            "71c9e70df5b836ba",
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

    def test_decoders_reject_shapes_over_the_resource_budget(self):
        oversized_shape = [MAX_DECODED_MATRIX_ELEMENTS + 1, 1]
        with self.assertRaisesRegex(ValueError, "resource limit"):
            PCABackend.decode(
                b"",
                {
                    "format": "pca-v1",
                    "dtype": "float32",
                    "shape": oversized_shape,
                    "components": 1,
                },
            )
        with self.assertRaisesRegex(ValueError, "resource limit"):
            VoidTokenBackend.decode(
                b"",
                {
                    "format": VOIDTOKEN_FORMAT,
                    "dtype": "float32",
                    "shape": oversized_shape,
                    "topK": 1,
                    "qmax": 127,
                    "keyframeInterval": 0,
                    "indexBytes": 2,
                    "quantizedValueBytes": 1,
                    "canonicalizationVersion": (
                        VOIDTOKEN_CANONICALIZATION_VERSION
                    ),
                },
            )

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
        for invalid in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(invalid=invalid):
                nonfinite = states.copy()
                nonfinite[1, 0] = invalid
                with self.assertRaisesRegex(ValueError, "finite"):
                    VoidTokenBackend.encode(
                        nonfinite, top_k=1, qmax=127
                    )

    def test_void_uses_wire_norm_and_coordinate_tie_break(self):
        states = np.array(
            [[0.0, 0.0, 0.0, 0.0], [1.0, -1.0, 1.0, -1.0]],
            dtype=np.float32,
        )
        encoded = VoidTokenBackend.encode(states, top_k=2, qmax=127)
        token_offset = states.shape[1] * 4
        norm, count = struct.unpack_from("<fH", encoded.payload, token_offset)
        indices = struct.unpack_from("<HH", encoded.payload, token_offset + 6)
        quantized = struct.unpack_from("<bb", encoded.payload, token_offset + 10)
        self.assertEqual(norm, _canonical_float32(_fixed_l2_norm(states[1])))
        self.assertEqual(count, 2)
        self.assertEqual(indices, (0, 1))
        self.assertEqual(quantized, (64, -64))
        self.assertEqual(
            encoded.metadata["canonicalizationVersion"],
            VOIDTOKEN_CANONICALIZATION_VERSION,
        )
        self.assertEqual(encoded.metadata["format"], VOIDTOKEN_FORMAT)
        parsed = EncodedRepresentation.from_bytes(encoded.to_bytes())
        self.assertTrue(np.array_equal(parsed.reconstructed, encoded.reconstructed))

        unsupported_metadata = {
            **encoded.metadata,
            "canonicalizationVersion": "unknown",
        }
        with self.assertRaises(ValueError):
            VoidTokenBackend.decode(encoded.payload, unsupported_metadata)
        with self.assertRaises(ValueError):
            VoidTokenBackend.decode(
                encoded.payload,
                {
                    **encoded.metadata,
                    "format": VOIDTOKEN_LEGACY_FORMAT,
                },
            )

        legacy_norm = struct.unpack("<f", struct.pack("<I", 0x3D0004D5))[0]
        legacy_payload = (
            struct.pack("<f", 0.0)
            + struct.pack("<fH", legacy_norm, 1)
            + struct.pack("<H", 0)
            + struct.pack("<b", -126)
        )
        legacy_metadata = {
            "shape": [2, 1],
            "topK": 1,
            "qmax": 127,
            "keyframeInterval": 0,
            "indexBytes": 2,
            "quantizedValueBytes": 1,
            "format": VOIDTOKEN_LEGACY_FORMAT,
        }
        legacy = VoidTokenBackend.decode(legacy_payload, legacy_metadata)
        canonical = VoidTokenBackend.decode(
            legacy_payload,
            {
                **legacy_metadata,
                "format": VOIDTOKEN_FORMAT,
                "canonicalizationVersion": VOIDTOKEN_CANONICALIZATION_VERSION,
            },
        )
        expected_legacy = (
            np.array([-126], dtype=np.int8).astype(np.float32) / 127.0
        ) * legacy_norm
        self.assertEqual(legacy[1, 0].tobytes(), expected_legacy[0].tobytes())
        self.assertNotEqual(legacy[1, 0].tobytes(), canonical[1, 0].tobytes())

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
    def test_evidence_verifier_bootstraps_in_isolated_python(self):
        with TemporaryDirectory(prefix="corelm-child-pycache-") as cache:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-X",
                    f"pycache_prefix={cache}",
                    str(ROOT / "BenchmarkCore" / "verify_evidence.py"),
                    "--help",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Replay and verify", completed.stdout)

    def test_evidence_tolerance_excludes_configuration(self):
        expected = {
            "configuration": {
                "inputBound": 0.05,
                "thresholds": {"maximumNormalizedRMSE": 0.1},
            },
            "methods": [{"normalizedRMSE": 0.05}],
        }
        observed = {
            "configuration": {
                "inputBound": 0.050005,
                "thresholds": {"maximumNormalizedRMSE": 0.100005},
            },
            "methods": [{"normalizedRMSE": 0.050005}],
        }
        differences: list[str] = []
        compare_values(
            expected,
            observed,
            "run[0]",
            differences,
            relative_tolerance=FLOAT_RELATIVE_TOLERANCE,
            absolute_tolerance=FLOAT_ABSOLUTE_TOLERANCE,
        )
        self.assertEqual(len(differences), 2)
        self.assertTrue(
            all(".configuration." in difference for difference in differences)
        )

    def test_replay_and_reports(self):
        config = ExperimentConfiguration(dimension=32, steps=40, seed=17, top_k=8)
        first = run_benchmark(config)
        second = run_benchmark(config)
        self.assertEqual(first["runId"], second["runId"])
        self.assertEqual(first["inputDigest"], second["inputDigest"])
        self.assertEqual(first["coreStateDigest"], second["coreStateDigest"])
        self.assertEqual(
            first["voidTokenPayloadDigest"], second["voidTokenPayloadDigest"]
        )
        self.assertEqual(
            first["voidTokenContainerDigest"], second["voidTokenContainerDigest"]
        )
        self.assertEqual(
            first["voidTokenReconstructionDigest"],
            second["voidTokenReconstructionDigest"],
        )
        self.assertEqual(first["coreArithmeticVersion"], CORE_ARITHMETIC_VERSION)
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
                "coreArithmeticVersion", "coreStateDigest",
                "voidTokenPayloadDigest", "voidTokenContainerDigest",
                "voidTokenReconstructionDigest",
            }
            self.assertEqual(set(loaded), required)
            self.assertEqual({m["name"] for m in loaded["methods"]}, {"dense", "pca", "voidtoken"})
            self.assertGreater(len(loaded["timeSeries"]), 1)
            self.assertEqual(loaded["timeSeries"][0]["step"], 0)
            with self.assertRaises(FileExistsError):
                save_result(first, Path(directory))

    def test_evidence_verifier_rejects_unsafe_run_ids_before_replay(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "aggregate.json").write_text(
                json.dumps({"runIds": ["../outside"]}),
                encoding="utf-8",
            )
            self.assertEqual(
                verify_evidence(root),
                [
                    "aggregate.runIds: every run ID must be exactly 16 "
                    "lowercase hexadecimal characters"
                ],
            )

    def test_single_run_cli_returns_nonzero_for_scientific_fail(self):
        arguments = SimpleNamespace(
            dimension=8,
            steps=20,
            seed=7,
            scenario="zero",
            pca_components=4,
            top_k=2,
            qmax=127,
            keyframe_interval=0,
            minimum_compression_ratio=4.0,
            maximum_normalized_rmse=0.1,
            minimum_cosine_similarity=0.95,
            maximum_energy_drift=0.05,
            output=Path("/unused"),
        )
        with (
            patch.object(
                benchmark_module, "parse_arguments", return_value=arguments
            ),
            patch.object(
                benchmark_module,
                "run_benchmark",
                return_value={
                    "runId": "0000000000000000",
                    "verdict": "FAIL",
                    "verdictReasons": [],
                },
            ),
            patch.object(
                benchmark_module,
                "save_result",
                return_value=(Path("result.json"), Path("result.md")),
            ),
        ):
            self.assertEqual(benchmark_module.main(), 2)

    def test_result_digests_match_core_and_void_bytes(self):
        config = ExperimentConfiguration(
            dimension=8,
            steps=20,
            seed=7,
            input_scenario="uniform_bounded",
            pca_components=4,
            top_k=2,
        )
        inputs = DeterministicInputGenerator.generate(config)
        states = CoreLMAdapter(config.dimension).run(inputs)
        void = VoidTokenBackend.encode(
            states,
            top_k=config.top_k,
            qmax=config.qmax,
            keyframe_interval=config.keyframe_interval,
        )
        result = run_benchmark(config)
        self.assertEqual(
            result["coreStateDigest"],
            hashlib.sha256(states.astype("<f4").tobytes()).hexdigest(),
        )
        self.assertEqual(
            result["voidTokenPayloadDigest"],
            hashlib.sha256(void.payload).hexdigest(),
        )
        self.assertEqual(
            result["voidTokenContainerDigest"],
            hashlib.sha256(void.to_bytes()).hexdigest(),
        )
        self.assertEqual(
            result["voidTokenReconstructionDigest"],
            hashlib.sha256(
                void.reconstructed.astype("<f4").tobytes()
            ).hexdigest(),
        )

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
