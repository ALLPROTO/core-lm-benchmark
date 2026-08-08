import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from security import verify_app_run_evidence as verifier


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "app-real-llm-evidence"


class AppRealLLMEvidenceTests(unittest.TestCase):
    def test_full_current_receipt_and_v4_compatibility_contracts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result_path = root / "validation-064-071.json"
            source_result = json.loads(
                (EVIDENCE / result_path.name).read_text(encoding="utf-8")
            )
            primary = {
                "schemaVersion": "corelm-real-llm-primary-evidence-v1",
                "path": "primary-evidence/manifest.json",
                "manifestSHA256": "3" * 64,
                "manifestBytes": 1,
                "containerCount": 192,
                "containerBytes": 1,
                "blocks": 8,
                "predictionTokens": 1024,
            }
            source_result["schemaVersion"] = (
                "corelm-voidtoken-v5-validation-development-v3"
            )
            source_result["primaryEvidence"] = primary
            result_path.write_text(
                json.dumps(source_result, sort_keys=True),
                encoding="utf-8",
            )
            aggregate = source_result["aggregates"][0]
            base_receipt = json.loads(
                (EVIDENCE / "app-run-receipt.json").read_text(
                    encoding="utf-8"
                )
            )
            base_receipt["worker"]["script"] = (
                "Resources/RealLLM/app_proof_runner.py"
            )
            base_receipt["worker"]["scriptSHA256"] = verifier._sha256(
                ROOT / "RealLLM" / "app_proof_runner.py"
            )
            base_receipt["primaryEvidence"] = primary
            base_receipt["buildProvenance"] = {
                "document": {},
                "path": "Resources/build-provenance.json",
                "sha256": "4" * 64,
            }
            challenge = "5" * 64
            base_receipt["challengeNonce"] = challenge

            for schema, verdict_fields in (
                (
                    "corelm-macos-app-real-llm-run-v5",
                    {
                        "metricVerdict": "PASS",
                        "resultRole": "PUBLIC_VALIDATION_REGRESSION",
                    },
                ),
                (
                    "corelm-macos-app-real-llm-run-v4",
                    {"scientificVerdict": "PASS"},
                ),
            ):
                with self.subTest(schema=schema):
                    receipt = copy.deepcopy(base_receipt)
                    receipt["schemaVersion"] = schema
                    receipt["result"] = {
                        "compressionRatioVsBF16": aggregate[
                            "compressionRatioVsBF16"
                        ],
                        "deltaNLLNatPerToken": aggregate[
                            "deltaNLLNatPerToken"
                        ],
                        "path": result_path.name,
                        "resultFileSHA256": verifier._sha256(result_path),
                        "resultSHA256": source_result["resultSHA256"],
                        "swiftStructuralVerification": "PASS",
                        "top1Agreement": aggregate["top1Agreement"],
                        **verdict_fields,
                    }
                    receipt_path = root / "app-run-receipt.json"
                    receipt_path.write_text(
                        json.dumps(receipt, sort_keys=True),
                        encoding="utf-8",
                    )
                    with mock.patch.object(
                        verifier,
                        "_verify_shard",
                        return_value=([], [{}] * 8, [{}] * 8),
                    ), mock.patch.object(
                        verifier, "_verify_build_provenance_receipt"
                    ), mock.patch.object(verifier, "verify_primary_evidence"):
                        observed = verifier._verify_result_and_receipt(
                            result_path,
                            receipt_path,
                            None,
                            portable_macos_environment=True,
                            expected_challenge_nonce=challenge,
                        )
                    self.assertEqual(
                        observed["resultSHA256"],
                        source_result["resultSHA256"],
                    )

    def test_current_receipt_uses_explicit_regression_role(self):
        common = {
            "compressionRatioVsBF16": 2.05,
            "deltaNLLNatPerToken": 0.0,
            "path": "validation-064-071.json",
            "resultFileSHA256": "1" * 64,
            "resultSHA256": "2" * 64,
            "swiftStructuralVerification": "PASS",
            "top1Agreement": 0.995,
        }
        current = {
            **common,
            "metricVerdict": "PASS",
            "resultRole": "PUBLIC_VALIDATION_REGRESSION",
        }
        observed, verdict = verifier._validate_result_receipt_contract(
            "corelm-macos-app-real-llm-run-v5", current
        )
        self.assertEqual(observed, current)
        self.assertEqual(verdict, "PASS")

        misclassified = {**current, "resultRole": "SCIENTIFIC_RESULT"}
        with self.assertRaisesRegex(ValueError, "misclassifies"):
            verifier._validate_result_receipt_contract(
                "corelm-macos-app-real-llm-run-v5", misclassified
            )

        ambiguous = {**current, "scientificVerdict": "PASS"}
        with self.assertRaisesRegex(ValueError, "fields are not exact"):
            verifier._validate_result_receipt_contract(
                "corelm-macos-app-real-llm-run-v5", ambiguous
            )

    def test_current_v5_preserves_a_verified_metric_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result_path = root / "validation-064-071.json"
            result = json.loads(
                (EVIDENCE / result_path.name).read_text(encoding="utf-8")
            )
            result["schemaVersion"] = (
                "corelm-voidtoken-v5-validation-development-v3"
            )
            result["aggregates"][0]["pass"] = False
            primary = {
                "schemaVersion": "corelm-real-llm-primary-evidence-v1",
                "path": "primary-evidence/manifest.json",
                "manifestSHA256": "6" * 64,
                "manifestBytes": 1,
                "containerCount": 192,
                "containerBytes": 1,
                "blocks": 8,
                "predictionTokens": 1024,
            }
            result["primaryEvidence"] = primary
            result_path.write_text(
                json.dumps(result, sort_keys=True), encoding="utf-8"
            )
            aggregate = result["aggregates"][0]
            receipt = json.loads(
                (EVIDENCE / "app-run-receipt.json").read_text(
                    encoding="utf-8"
                )
            )
            challenge = "7" * 64
            receipt.update(
                {
                    "schemaVersion": "corelm-macos-app-real-llm-run-v5",
                    "challengeNonce": challenge,
                    "primaryEvidence": primary,
                    "buildProvenance": {
                        "document": {},
                        "path": "Resources/build-provenance.json",
                        "sha256": "8" * 64,
                    },
                }
            )
            receipt["worker"]["script"] = (
                "Resources/RealLLM/app_proof_runner.py"
            )
            receipt["worker"]["scriptSHA256"] = verifier._sha256(
                ROOT / "RealLLM" / "app_proof_runner.py"
            )
            receipt["result"] = {
                "compressionRatioVsBF16": aggregate[
                    "compressionRatioVsBF16"
                ],
                "deltaNLLNatPerToken": aggregate["deltaNLLNatPerToken"],
                "metricVerdict": "FAIL",
                "path": result_path.name,
                "resultFileSHA256": verifier._sha256(result_path),
                "resultRole": "PUBLIC_VALIDATION_REGRESSION",
                "resultSHA256": result["resultSHA256"],
                "swiftStructuralVerification": "PASS",
                "top1Agreement": aggregate["top1Agreement"],
            }
            receipt_path = root / "app-run-receipt.json"
            receipt_path.write_text(
                json.dumps(receipt, sort_keys=True), encoding="utf-8"
            )
            patches = (
                mock.patch.object(
                    verifier,
                    "_verify_shard",
                    return_value=([], [{}] * 8, [{}] * 8),
                ),
                mock.patch.object(
                    verifier, "_verify_build_provenance_receipt"
                ),
                mock.patch.object(verifier, "verify_primary_evidence"),
            )
            with patches[0], patches[1], patches[2]:
                observed = verifier._verify_result_and_receipt(
                    result_path,
                    receipt_path,
                    None,
                    portable_macos_environment=True,
                    expected_challenge_nonce=challenge,
                    require_metric_pass=False,
                )
            self.assertFalse(observed["aggregates"][0]["pass"])

            with mock.patch.object(
                verifier,
                "_verify_shard",
                return_value=([], [{}] * 8, [{}] * 8),
            ), mock.patch.object(
                verifier, "_verify_build_provenance_receipt"
            ), mock.patch.object(
                verifier, "verify_primary_evidence"
            ), self.assertRaisesRegex(ValueError, "does not bind"):
                verifier._verify_result_and_receipt(
                    result_path,
                    receipt_path,
                    None,
                    portable_macos_environment=True,
                    expected_challenge_nonce=challenge,
                    require_metric_pass=True,
                )

    def test_recorded_evidence_passes(self):
        verifier.verify(EVIDENCE)

    def test_recorded_evidence_binds_archived_app_identity(self):
        verifier.verify(EVIDENCE)
        receipt = json.loads(
            (EVIDENCE / "app-run-receipt.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            receipt["application"],
            {
                "bundleIdentifier": "com.corelm.benchmark",
                "bundleName": "CoreLMBenchmark.app",
                "executableSHA256": (
                    "c5a70cebb8eb59fd098c3218af77f1807e2def9fca526256e9354bc0affdbdae"
                ),
                "processIdentifier": 92537,
                "version": "0.4.0",
            },
        )
        self.assertEqual(
            receipt["worker"]["runtimeManifestSHA256"],
            "0663285d633d4a2223cd59193cd2eb2a8ea09cc0bf50791894bfb9c44975d102",
        )
        self.assertEqual(
            receipt["result"]["resultSHA256"],
            "5b464de8f094a33a90dfdbc2c69ac318bc62a4397b171b5db69ae93d5d39d3c2",
        )

    def test_result_tampering_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "evidence"
            shutil.copytree(EVIDENCE, copied)
            path = copied / "validation-064-071.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["aggregates"][0]["top1Agreement"] = 0.0
            path.write_text(json.dumps(result), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA256SUMS"):
                verifier.verify(copied)

    def test_receipt_path_disclosure_fails_even_with_updated_checksum(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "evidence"
            shutil.copytree(EVIDENCE, copied)
            receipt_path = copied / "app-run-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["result"]["path"] = "/Users/example/private/result.json"
            receipt_path.write_text(
                json.dumps(receipt, sort_keys=True),
                encoding="utf-8",
            )
            checksum_path = copied / "SHA256SUMS"
            checksums = verifier._load_checksums(checksum_path)
            checksums["app-run-receipt.json"] = verifier._sha256(receipt_path)
            checksum_path.write_text(
                "".join(
                    f"{digest}  {name}\n"
                    for name, digest in sorted(checksums.items())
                ),
                encoding="ascii",
            )
            with self.assertRaisesRegex(ValueError, "absolute user path"):
                verifier.verify(copied)

    def test_receipt_metric_tampering_fails_even_with_updated_checksum(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "evidence"
            shutil.copytree(EVIDENCE, copied)
            receipt_path = copied / "app-run-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            tampered = copy.deepcopy(receipt)
            tampered["result"]["compressionRatioVsBF16"] = 99.0
            receipt_path.write_text(
                json.dumps(tampered, sort_keys=True),
                encoding="utf-8",
            )
            checksum_path = copied / "SHA256SUMS"
            checksums = verifier._load_checksums(checksum_path)
            checksums["app-run-receipt.json"] = verifier._sha256(receipt_path)
            checksum_path.write_text(
                "".join(
                    f"{digest}  {name}\n"
                    for name, digest in sorted(checksums.items())
                ),
                encoding="ascii",
            )
            with self.assertRaisesRegex(
                ValueError, "does not bind to the verified result"
            ):
                verifier.verify(copied)


if __name__ == "__main__":
    unittest.main()
