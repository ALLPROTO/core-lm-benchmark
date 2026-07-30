import copy
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import RealLLM.benchmark_real_llm as benchmark_module  # noqa: E402
import RealLLM.develop_voidtoken_v5 as development_module  # noqa: E402
from RealLLM.benchmark_real_llm import (  # noqa: E402
    DATASET_FILES,
    GROUP_QUANT_GRID,
    MODEL_ASSET_FILES,
    MODEL_WEIGHTS_BYTES,
    MODEL_WEIGHTS_SHA256,
    PREDICTIONS_PER_BLOCK,
    REGISTERED_TEST_START_BLOCK,
    THRESHOLDS,
    VOIDTOKEN_GRID,
    _download_and_verify_inputs,
    _exclusive_write_bytes,
    aggregate_candidate_records,
    canonical_json_bytes,
    configuration_id,
    select_validation_configuration,
    validate_registered_protocol,
)
from RealLLM.codecs import (  # noqa: E402
    MAX_DECODED_MATRIX_ELEMENTS,
    PackedGroupQuantBackend,
    PackedGroupQuantRepresentation,
    sha256_bytes,
)
from RealLLM.verify_real_llm_evidence import verify_result  # noqa: E402


class PackedGroupQuantTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(20260729)
        self.matrix = rng.normal(0.0, 0.5, size=(17, 32)).astype(np.float32)

    def test_all_registered_bit_widths_round_trip_through_container(self):
        previous_error = float("inf")
        for bits in (4, 5, 6, 7, 8):
            with self.subTest(bits=bits):
                encoded = PackedGroupQuantBackend.encode(
                    self.matrix, bits=bits, group_size=16
                )
                parsed = PackedGroupQuantRepresentation.from_bytes(
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

    def test_container_is_byte_identical_and_counts_every_byte(self):
        first = PackedGroupQuantBackend.encode(
            self.matrix, bits=7, group_size=32
        )
        second = PackedGroupQuantBackend.encode(
            self.matrix.copy(), bits=7, group_size=32
        )
        self.assertEqual(first.to_bytes(), second.to_bytes())
        expected_scale_bytes = self.matrix.shape[0] * 2
        expected_packed_bytes = (
            self.matrix.size * 7 + 7
        ) // 8
        self.assertEqual(first.metadata["scaleBytes"], expected_scale_bytes)
        self.assertEqual(first.metadata["packedBytes"], expected_packed_bytes)
        self.assertEqual(
            first.payload_bytes, expected_scale_bytes + expected_packed_bytes
        )
        self.assertEqual(first.container_bytes, len(first.to_bytes()))

    def test_zero_matrix_is_exact(self):
        zero = np.zeros((5, 32), dtype=np.float32)
        encoded = PackedGroupQuantBackend.encode(
            zero, bits=7, group_size=16
        )
        self.assertTrue(np.array_equal(encoded.reconstructed, zero))

    def test_zlib_scale_storage_is_lossless_and_counted(self):
        tiled = np.tile(self.matrix, (16, 1))
        raw = PackedGroupQuantBackend.encode(
            tiled, bits=7, group_size=16, scale_compression="none"
        )
        compressed = PackedGroupQuantBackend.encode(
            tiled, bits=7, group_size=16, scale_compression="zlib-9"
        )
        self.assertTrue(
            np.array_equal(raw.reconstructed, compressed.reconstructed)
        )
        self.assertLess(
            compressed.metadata["storedScaleBytes"],
            compressed.metadata["scaleBytes"],
        )
        self.assertLess(compressed.container_bytes, raw.container_bytes)
        parsed = PackedGroupQuantBackend.from_bytes(compressed.to_bytes())
        self.assertTrue(
            np.array_equal(parsed.reconstructed, compressed.reconstructed)
        )

    def test_invalid_inputs_and_corruption_are_rejected(self):
        with self.assertRaises(ValueError):
            PackedGroupQuantBackend.encode(
                self.matrix.astype(np.float64), bits=7, group_size=16
            )
        with self.assertRaises(ValueError):
            PackedGroupQuantBackend.encode(
                self.matrix, bits=9, group_size=16
            )
        with self.assertRaises(ValueError):
            PackedGroupQuantBackend.encode(
                self.matrix, bits=7, group_size=12
            )
        with self.assertRaises(ValueError):
            PackedGroupQuantBackend.encode(
                self.matrix,
                bits=7,
                group_size=16,
                scale_compression="gzip",
            )
        encoded = PackedGroupQuantBackend.encode(
            self.matrix, bits=7, group_size=16
        )
        corrupted = bytearray(encoded.to_bytes())
        corrupted[-1] ^= 1
        with self.assertRaises(ValueError):
            PackedGroupQuantBackend.from_bytes(corrupted)
        with self.assertRaises(ValueError):
            PackedGroupQuantBackend.from_bytes(encoded.to_bytes()[:-1])

    def test_decoder_rejects_metadata_that_declares_an_oversized_matrix(self):
        encoded = PackedGroupQuantBackend.encode(
            self.matrix, bits=7, group_size=16
        )
        metadata = dict(encoded.metadata)
        metadata["shape"] = [MAX_DECODED_MATRIX_ELEMENTS + 1, 1]
        with self.assertRaisesRegex(ValueError, "resource limit"):
            PackedGroupQuantBackend.decode(encoded.payload, metadata)

    def test_zlib_decoder_stops_when_scales_exceed_declared_bound(self):
        encoded = PackedGroupQuantBackend.encode(
            self.matrix, bits=7, group_size=16, scale_compression="zlib-9"
        )
        import zlib

        oversized_scales = zlib.compress(
            b"\0" * (encoded.metadata["scaleBytes"] + 1024), level=9
        )
        packed = encoded.payload[encoded.metadata["storedScaleBytes"] :]
        payload = oversized_scales + packed
        metadata = dict(encoded.metadata)
        metadata["storedScaleBytes"] = len(oversized_scales)
        metadata["payloadBytes"] = len(payload)
        metadata["payloadSha256"] = sha256_bytes(payload)
        with self.assertRaisesRegex(ValueError, "exceed"):
            PackedGroupQuantBackend.decode(payload, metadata)


def _record(
    *,
    baseline_nll: float,
    candidate_nll: float,
    encoded_bytes: int,
    agreement: int,
    kl: float,
) -> dict:
    return {
        "predictionTokens": 100,
        "denseBF16Bytes": 1000,
        "encodedFileBytes": encoded_bytes,
        "top1AgreementCount": agreement,
        "cacheDifferenceSumSquares": 1.0,
        "cacheReferenceSumSquares": 100.0,
        "cacheCandidateSumSquares": 99.0,
        "cacheDotProduct": 99.0,
        "cacheMaximumAbsoluteError": 0.25,
        "baselineNLLNatPerToken": baseline_nll,
        "candidateNLLNatPerToken": candidate_nll,
        "meanKLDivergenceNat": kl,
        "encodeNanoseconds": 10,
        "decodeNanoseconds": 5,
        "modelContinuationNanoseconds": 100,
        "payloadSHA256": f"{encoded_bytes:064x}",
    }


class RealLLMProtocolTests(unittest.TestCase):
    def test_registered_protocol_is_fixed_and_has_no_duplicate_candidates(self):
        validate_registered_protocol()
        self.assertEqual(PREDICTIONS_PER_BLOCK, 128)
        self.assertEqual(REGISTERED_TEST_START_BLOCK, 8)
        identifiers = [
            configuration_id(configuration)
            for configuration in (*VOIDTOKEN_GRID, *GROUP_QUANT_GRID)
        ]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertIn(
            {
                "backend": "group-quant",
                "bits": 7,
                "groupSize": 16,
                "scaleCompression": "zlib-9",
            },
            GROUP_QUANT_GRID,
        )

    def test_configuration_id_uses_canonical_full_configuration(self):
        left = {
            "backend": "group-quant",
            "bits": 7,
            "groupSize": 32,
            "scaleCompression": "none",
        }
        reordered = {
            "scaleCompression": "none",
            "groupSize": 32,
            "bits": 7,
            "backend": "group-quant",
        }
        changed = {
            "backend": "group-quant",
            "bits": 7,
            "groupSize": 64,
            "scaleCompression": "none",
        }
        self.assertEqual(configuration_id(left), configuration_id(reordered))
        self.assertNotEqual(configuration_id(left), configuration_id(changed))
        self.assertEqual(
            canonical_json_bytes(left),
            json.dumps(
                left, sort_keys=True, separators=(",", ":")
            ).encode("utf-8"),
        )

    def test_aggregate_recomputes_gates_from_raw_counts(self):
        configuration = {
            "backend": "group-quant",
            "bits": 7,
            "groupSize": 32,
            "scaleCompression": "none",
        }
        records = [
            _record(
                baseline_nll=2.0,
                candidate_nll=2.005,
                encoded_bytes=480,
                agreement=100,
                kl=0.001,
            ),
            _record(
                baseline_nll=3.0,
                candidate_nll=3.005,
                encoded_bytes=480,
                agreement=99,
                kl=0.003,
            ),
        ]
        aggregate = aggregate_candidate_records(configuration, records)
        self.assertAlmostEqual(aggregate["compressionRatioVsBF16"], 2000 / 960)
        self.assertAlmostEqual(aggregate["deltaNLLNatPerToken"], 0.005)
        self.assertAlmostEqual(aggregate["top1Agreement"], 0.995)
        self.assertAlmostEqual(aggregate["meanKLDivergenceNat"], 0.002)
        self.assertAlmostEqual(aggregate["cacheNormalizedRMSE"], 0.1)
        self.assertTrue(aggregate["pass"])
        self.assertEqual(
            aggregate["gates"],
            {
                "compression": True,
                "deltaNLL": True,
                "top1Agreement": True,
            },
        )

    def test_validation_selection_uses_kl_and_compression_gate(self):
        family = "group-quant"
        configurations = [
            {
                "backend": family,
                "bits": 5,
                "groupSize": 16,
                "scaleCompression": "none",
            },
            {
                "backend": family,
                "bits": 6,
                "groupSize": 16,
                "scaleCompression": "none",
            },
            {
                "backend": family,
                "bits": 7,
                "groupSize": 32,
                "scaleCompression": "none",
            },
        ]
        aggregates = []
        for index, configuration in enumerate(configurations):
            record = _record(
                baseline_nll=2.0,
                candidate_nll=2.0 + index * 0.001,
                encoded_bytes=(600, 450, 470)[index],
                agreement=(100, 98, 99)[index],
                kl=(0.0001, 0.003, 0.001)[index],
            )
            aggregates.append(
                aggregate_candidate_records(configuration, [record])
            )
        # The lowest-KL option is ineligible (1000/600 < 2). The selected
        # candidate is therefore bits=7, whose KL beats the other eligible one.
        selected = select_validation_configuration(aggregates, family)
        self.assertEqual(selected["configuration"], configurations[2])
        self.assertGreaterEqual(
            selected["compressionRatioVsBF16"],
            THRESHOLDS["minimumCompressionRatioVsBF16"],
        )

    def test_evidence_rejects_duplicate_block_coverage(self):
        with (ROOT / "real-llm-results" / "aggregate.json").open(
            encoding="utf-8"
        ) as handle:
            result = json.load(handle)
        forged = copy.deepcopy(result)
        for baseline in forged["validation"]["baselines"]:
            baseline["blockIndex"] = 0
        for record in forged["validation"]["records"]:
            record["blockIndex"] = 0
        errors = verify_result(forged)
        self.assertTrue(
            any("cover the registered blocks exactly" in error for error in errors)
        )
        self.assertTrue(
            any("duplicate baseline block indices" in error for error in errors)
        )

    def test_evidence_recomputes_record_level_metrics(self):
        with (ROOT / "real-llm-results" / "aggregate.json").open(
            encoding="utf-8"
        ) as handle:
            result = json.load(handle)
        forged = copy.deepcopy(result)
        record = forged["validation"]["records"][0]
        record["deltaNLLNatPerToken"] += 0.25
        record["perplexityRatio"] += 0.25
        record["top1Agreement"] = 1.0 - record["top1Agreement"]
        errors = verify_result(forged)
        self.assertTrue(any("delta NLL is inconsistent" in error for error in errors))
        self.assertTrue(
            any("perplexity ratio is inconsistent" in error for error in errors)
        )
        self.assertTrue(any("top-1 fields are inconsistent" in error for error in errors))

    def test_evidence_handles_exponential_overflow_as_a_verification_error(self):
        with (ROOT / "real-llm-results" / "aggregate.json").open(
            encoding="utf-8"
        ) as handle:
            result = json.load(handle)
        forged = copy.deepcopy(result)
        forged["validation"]["records"][0][
            "candidateNLLNatPerToken"
        ] = 1e300
        errors = verify_result(forged)
        self.assertTrue(
            any(
                "invalid derived fields" in error
                or "cannot be aggregated" in error
                for error in errors
            )
        )

    def test_real_llm_cli_returns_nonzero_for_scientific_fail(self):
        arguments = SimpleNamespace(
            output=Path("/unused"),
            device="cpu",
            validation_blocks=4,
            test_blocks=8,
            test_start_block=REGISTERED_TEST_START_BLOCK,
            local_files_only=True,
        )
        result = {"test": {"allPassed": False}}
        with (
            patch.object(
                benchmark_module, "parse_arguments", return_value=arguments
            ),
            patch.object(
                benchmark_module, "run_registered_pilot", return_value=result
            ),
            patch.object(benchmark_module, "_summary", return_value="FAIL"),
        ):
            self.assertEqual(benchmark_module.main(), 2)

    def test_result_output_is_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            _exclusive_write_bytes(path, b"first")
            with self.assertRaises(FileExistsError):
                _exclusive_write_bytes(path, b"second")
            self.assertEqual(path.read_bytes(), b"first")

    def test_all_model_runtime_assets_are_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "snapshot"
            dataset_root = root / "dataset"
            snapshot.mkdir()
            requested: list[tuple[str, str]] = []
            digests: dict[Path, str] = {}

            model_path = snapshot / "model.safetensors"
            with model_path.open("wb") as handle:
                handle.truncate(MODEL_WEIGHTS_BYTES)
            digests[model_path] = MODEL_WEIGHTS_SHA256
            for filename, specification in MODEL_ASSET_FILES.items():
                path = snapshot / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("wb") as handle:
                    handle.truncate(specification["bytes"])
                digests[path] = specification["sha256"]
            for specification in DATASET_FILES.values():
                path = dataset_root / specification["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("wb") as handle:
                    handle.truncate(specification["bytes"])
                digests[path] = specification["sha256"]

            def fake_download(repository, *, filename, **kwargs):
                requested.append((repository, filename))
                if kwargs.get("repo_type") == "dataset":
                    return dataset_root / filename
                return snapshot / filename

            fake_hub = types.SimpleNamespace(hf_hub_download=fake_download)
            with (
                patch.dict(sys.modules, {"huggingface_hub": fake_hub}),
                patch.object(
                    benchmark_module,
                    "sha256_file",
                    side_effect=lambda path: digests[Path(path)],
                ),
                patch.object(
                    development_module,
                    "sha256_file",
                    side_effect=lambda path: digests[Path(path)],
                ),
            ):
                resolved = _download_and_verify_inputs(True)
                validation_only = development_module._download_validation_only(
                    True
                )

            requested_names = {filename for _, filename in requested}
            self.assertTrue(MODEL_ASSET_FILES.keys() <= requested_names)
            self.assertEqual(resolved["modelSnapshot"], snapshot)
            self.assertEqual(validation_only["modelSnapshot"], snapshot)
            self.assertNotIn(
                DATASET_FILES["test"]["path"],
                [
                    filename
                    for repository, filename in requested[
                        len(MODEL_ASSET_FILES) + 3 :
                    ]
                    if repository != benchmark_module.MODEL_REPOSITORY
                ],
            )


if __name__ == "__main__":
    unittest.main()
