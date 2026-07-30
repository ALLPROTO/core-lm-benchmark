import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from security import verify_app_run_evidence as verifier


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "app-real-llm-evidence"


class AppRealLLMEvidenceTests(unittest.TestCase):
    def test_recorded_evidence_passes(self):
        verifier.verify(EVIDENCE)

    @unittest.skipUnless(
        (ROOT / "dist" / "CoreLMBenchmark.app").is_dir(),
        "local packaged app is unavailable",
    )
    def test_recorded_evidence_matches_current_app(self):
        verifier.verify(EVIDENCE, ROOT / "dist" / "CoreLMBenchmark.app")

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
