import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import RealLLM.run_voidtoken_v5_frozen as frozen_runner  # noqa: E402
import RealLLM.verify_voidtoken_v5_development as development  # noqa: E402
import RealLLM.verify_voidtoken_v5_evidence as evidence  # noqa: E402
from RealLLM.run_voidtoken_v5_frozen import (  # noqa: E402
    PHASES,
    SELECTION_PROTOCOL_TAG,
    _create_attempt_marker,
    implementation_sha256,
    registration_sha256,
    verify_attempt_artifact_self_consistency,
)


class VoidTokenV5DevelopmentEvidenceTests(unittest.TestCase):
    def test_published_development_artifacts_recompute_exactly(self):
        errors, combined = development.verify_development_evidence()
        self.assertEqual(errors, [])
        self.assertIsNotNone(combined)
        self.assertEqual(combined["blocks"], 32)
        self.assertEqual(combined["predictionTokens"], 4096)
        self.assertEqual(combined["top1AgreementCount"], 4078)
        self.assertAlmostEqual(
            combined["compressionRatioVsBF16"],
            2.0558361700293513,
        )

    def test_development_json_loader_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"status":"a","status":"b"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                development._load_json_object(path)

    def test_manifest_canonical_digest_excludes_only_its_digest_field(self):
        manifest = development._load_json_object(
            development.MANIFEST_PATH
        )
        self.assertEqual(
            manifest["manifestSHA256"],
            development._canonical_digest_without(
                manifest, "manifestSHA256"
            ),
        )
        tampered = dict(manifest)
        tampered["candidateIndex"] = 31
        self.assertNotEqual(
            manifest["manifestSHA256"],
            development._canonical_digest_without(
                tampered, "manifestSHA256"
            ),
        )

    def test_shard_verifier_rejects_numeric_strings_and_invalid_ranges(self):
        artifact = development.DEVELOPMENT_ARTIFACTS[0]
        shard = development._load_json_object(
            ROOT / artifact["path"]
        )
        malformed = copy.deepcopy(shard)
        malformed["records"][0]["baselineNLLNatPerToken"] = "2.0"
        malformed["records"][0]["meanKLDivergenceNat"] = -0.1
        malformed["baselines"][0]["nativeBF16Top1Agreement"] = 2.0
        errors, _, _ = development._verify_shard(
            malformed, artifact
        )
        self.assertTrue(
            any("finite JSON number" in error for error in errors)
        )
        self.assertTrue(any("valid range" in error for error in errors))

    def test_malformed_shard_returns_errors_instead_of_traceback(self):
        artifact = development.DEVELOPMENT_ARTIFACTS[0]
        shard = development._load_json_object(
            ROOT / artifact["path"]
        )
        malformed = copy.deepcopy(shard)
        malformed["records"][0] = "not-an-object"
        errors, _, _ = development._verify_shard(
            malformed, artifact
        )
        self.assertTrue(errors)

    def test_archive_without_git_metadata_uses_artifact_mode_without_git(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "corelm_reproducibility"
            root.mkdir()
            with (
                patch.object(evidence, "PROJECT_ROOT", root),
                patch.dict(os.environ, {}, clear=True),
                patch.object(evidence.subprocess, "run") as git,
            ):
                self.assertEqual(
                    evidence.detect_verification_mode(), "artifact"
                )
                git.assert_not_called()
                with self.assertRaisesRegex(
                    ValueError, "Git provenance was required"
                ):
                    evidence.detect_verification_mode(
                        require_git_provenance=True
                    )

    def test_nested_or_broken_git_metadata_never_downgrades(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            (parent / ".git").mkdir()
            root = parent / "corelm_reproducibility"
            root.mkdir()
            failed = evidence.subprocess.CompletedProcess(
                ["git"], 128, stdout="", stderr="broken metadata"
            )
            with (
                patch.object(evidence, "PROJECT_ROOT", root),
                patch.dict(os.environ, {}, clear=True),
                patch.object(
                    evidence.subprocess, "run", return_value=failed
                ),
            ):
                with self.assertRaisesRegex(
                    ValueError, "invalid or inaccessible"
                ):
                    evidence.detect_verification_mode()

    def test_current_source_tree_uses_the_only_valid_mode(self):
        mode = evidence.detect_verification_mode()
        if mode == "git":
            self.assertEqual(
                evidence.detect_verification_mode(
                    require_git_provenance=True
                ),
                "git",
            )
        else:
            self.assertEqual(mode, "artifact")
            with self.assertRaisesRegex(
                ValueError, "Git provenance was required"
            ):
                evidence.detect_verification_mode(
                    require_git_provenance=True
                )

    def test_git_mode_binds_current_normative_sources_to_head(self):
        with (
            patch.object(evidence, "_head_commit", return_value="a" * 40),
            patch.object(
                evidence,
                "registration_sha256_at_commit",
                return_value="b" * 64,
            ),
            patch.object(
                evidence,
                "implementation_sha256_at_commit",
                return_value="c" * 64,
            ),
        ):
            errors = evidence._verify_current_head_integrity(
                "d" * 64, "e" * 64
            )
        self.assertIn(
            "current registration bytes differ from Git HEAD", errors
        )
        self.assertIn(
            "current normative implementation differs from Git HEAD",
            errors,
        )

    def test_registration_only_git_error_is_not_silently_downgraded(self):
        with patch.object(
            evidence,
            "_verify_current_head_integrity",
            return_value=["simulated HEAD mismatch"],
        ):
            errors, status = evidence.verify_available_evidence(
                git_provenance=True
            )
        self.assertIn("simulated HEAD mismatch", errors)
        self.assertIn("registration-only", status)

    def test_registration_only_artifact_mode_never_reads_git_objects(self):
        with (
            patch.object(
                evidence, "registration_sha256_at_commit"
            ) as registration_at_commit,
            patch.object(
                evidence, "implementation_sha256_at_commit"
            ) as implementation_at_commit,
        ):
            errors, status = evidence.verify_available_evidence(
                git_provenance=False
            )
        self.assertEqual(errors, [])
        self.assertIn("registration-only", status)
        registration_at_commit.assert_not_called()
        implementation_at_commit.assert_not_called()

    def test_missing_selection_marker_returns_errors_without_traceback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selection = root / "selection.json"
            holdout = root / "holdout.json"
            selection.write_text(
                '{"pass":true,"pretestFreeze":null}\n',
                encoding="utf-8",
            )
            holdout.write_text(
                '{"pass":false,"pretestFreeze":{}}\n',
                encoding="utf-8",
            )
            with (
                patch.object(evidence, "SELECTION_PATH", selection),
                patch.object(
                    evidence,
                    "SELECTION_ATTEMPT_PATH",
                    root / "selection.attempt.json",
                ),
                patch.object(evidence, "HOLDOUT_PATH", holdout),
                patch.object(
                    evidence,
                    "HOLDOUT_ATTEMPT_PATH",
                    root / "holdout.attempt.json",
                ),
                patch.object(
                    evidence,
                    "verify_phase_artifact_self_consistency",
                    return_value=[],
                ),
                patch.object(
                    evidence,
                    "_independent_phase_metric_errors",
                    return_value=[],
                ),
            ):
                errors, _ = evidence.verify_available_evidence(
                    git_provenance=False
                )
        self.assertTrue(errors)
        self.assertTrue(
            any("selection.attempt.json" in error for error in errors)
        )

    def test_artifact_marker_verifier_never_reads_execution_commit(self):
        original_attempt = PHASES["selection"]["attempt"]
        with tempfile.TemporaryDirectory() as temporary:
            PHASES["selection"]["attempt"] = (
                Path(temporary) / "selection.attempt.json"
            )
            try:
                marker, _ = _create_attempt_marker(
                    "selection",
                    git_commit="a" * 40,
                    registration_digest=registration_sha256(),
                    implementation_digest=implementation_sha256(),
                    execution_freeze={
                        "freezeGitCommit": "a" * 40,
                        "freezeGitTag": SELECTION_PROTOCOL_TAG,
                        "publicRepository": frozen_runner.PUBLIC_ORIGIN,
                    },
                )
                with (
                    patch.object(
                        frozen_runner,
                        "registration_sha256_at_commit",
                    ) as registration_at_commit,
                    patch.object(
                        frozen_runner,
                        "implementation_sha256_at_commit",
                    ) as implementation_at_commit,
                ):
                    self.assertEqual(
                        verify_attempt_artifact_self_consistency(
                            marker, "selection"
                        ),
                        [],
                    )
                    registration_at_commit.assert_not_called()
                    implementation_at_commit.assert_not_called()
            finally:
                PHASES["selection"]["attempt"] = original_attempt


if __name__ == "__main__":
    unittest.main()
