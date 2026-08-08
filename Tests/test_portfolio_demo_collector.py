import json
import os
import tarfile
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]

from publication import build_portfolio_release as portfolio  # noqa: E402
from publication import collect_portfolio_demo as collector  # noqa: E402
from security import proof_reports  # noqa: E402


SOURCE = {"commit": "1" * 40, "tree": "2" * 40}
BINDING = {
    "schema_version": 1,
    "verdict": "PASS",
    "metric_verdict": "FAIL",
    "source": SOURCE,
    "receipt_sha256": "3" * 64,
    "result_sha256": "4" * 64,
    "workload_classification": "AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION",
    "synthetic_data": False,
}
REPLAY = {
    "decisions": 1024,
    "lossAbsoluteTolerance": 2e-5,
    "lossRelativeTolerance": 2e-6,
    "maximumBaselineLossDifference": 1e-7,
    "maximumCandidateLossDifference": 2e-7,
}
REPLAY_INTEGRITY = {
    "maximumAllowedBaselineDifference": 2e-5,
    "maximumAllowedCandidateDifference": 2e-5,
    "primaryManifestSHA256": "5" * 64,
    "tokenMetricsSHA256": "6" * 64,
    "perDecisionEvidenceSHA256": "7" * 64,
}


class ProofReportTests(unittest.TestCase):
    def _run(self, root: Path) -> Path:
        run = root / str(uuid.uuid4())
        run.mkdir(mode=0o700)
        reports = run / proof_reports.REPORT_DIRECTORY_NAME
        reports.mkdir(mode=0o700)
        return run

    def test_reports_are_exclusive_canonical_and_evidence_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = self._run(Path(temporary).resolve(strict=True))
            structural = run / "proof-reports" / "structural-verifier.json"
            replay = run / "proof-reports" / "fresh-model-replay.json"
            with (
                patch.object(proof_reports, "derive_binding", return_value=BINDING),
                patch.object(
                    proof_reports,
                    "_replay_integrity",
                    return_value=REPLAY_INTEGRITY,
                ),
            ):
                proof_reports.write_report(
                    structural, run, "structural_verifier"
                )
                proof_reports.write_report(
                    replay,
                    run,
                    "fresh_model_replay",
                    replay_summary=REPLAY,
                )
                self.assertEqual(
                    proof_reports.verify_report(
                        structural, run, "structural_verifier"
                    )["metric_verdict"],
                    "FAIL",
                )
                observed = proof_reports.verify_report(
                    replay, run, "fresh_model_replay"
                )
                self.assertEqual(observed["replay"], {**REPLAY, **REPLAY_INTEGRITY})
                self.assertEqual(
                    observed["verdict"],
                    "AUTHOR_RECORDED_HEAVY_REPLAY_INTEGRITY_PASS",
                )
                self.assertEqual(structural.stat().st_mode & 0o777, 0o600)
                self.assertEqual(replay.stat().st_mode & 0o777, 0o600)
                with self.assertRaisesRegex(ValueError, "already exists"):
                    proof_reports.write_report(
                        structural, run, "structural_verifier"
                    )

                tampered = json.loads(replay.read_text(encoding="utf-8"))
                tampered["replay"]["decisions"] = 1023
                replay.write_bytes(proof_reports.canonical_json_bytes(tampered))
                with self.assertRaisesRegex(ValueError, "1,024"):
                    proof_reports.verify_report(
                        replay, run, "fresh_model_replay"
                    )

                tampered = json.loads(
                    proof_reports.canonical_json_bytes(observed).decode("utf-8")
                )
                tampered["replay"]["tokenMetricsSHA256"] = "0" * 64
                replay.write_bytes(proof_reports.canonical_json_bytes(tampered))
                with self.assertRaisesRegex(ValueError, "retained evidence"):
                    proof_reports.verify_report(
                        replay, run, "fresh_model_replay"
                    )

    def test_replay_report_rejects_declared_or_nonfinite_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = self._run(Path(temporary).resolve(strict=True))
            target = run / "proof-reports" / "fresh-model-replay.json"
            with (
                patch.object(proof_reports, "derive_binding", return_value=BINDING),
                patch.object(
                    proof_reports,
                    "_replay_integrity",
                    return_value=REPLAY_INTEGRITY,
                ),
            ):
                declared = dict(REPLAY)
                declared["maximumCandidateLossDifference"] = float("nan")
                with self.assertRaisesRegex(ValueError, "invalid"):
                    proof_reports.write_report(
                        target,
                        run,
                        "fresh_model_replay",
                        replay_summary=declared,
                    )
                self.assertFalse(target.exists())

                too_large = dict(REPLAY)
                too_large["maximumCandidateLossDifference"] = 3e-5
                with self.assertRaisesRegex(ValueError, "tolerance envelope"):
                    proof_reports.write_report(
                        target,
                        run,
                        "fresh_model_replay",
                        replay_summary=too_large,
                    )


class PortfolioDemoCollectorTests(unittest.TestCase):
    def test_terminal_outcome_preserves_metric_fail_without_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            terminal = Path(temporary) / "terminal.log"
            terminal.write_text(
                "END-TO-END PROOF VERIFIED — METRIC FAIL\n",
                encoding="utf-8",
            )
            terminal.chmod(0o600)
            self.assertEqual(
                collector._read_terminal(terminal, "FAIL"),
                "END-TO-END PROOF VERIFIED — METRIC FAIL\n".encode("utf-8"),
            )
            with self.assertRaisesRegex(
                collector.CollectionError, "metric-selection-tainted"
            ):
                collector._read_terminal(terminal, "PASS")
            terminal.write_text(
                "END-TO-END PROOF VERIFIED — METRIC FAIL\nrerun-to-pass\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                collector.CollectionError, "metric-selection-tainted"
            ):
                collector._read_terminal(terminal, "FAIL")

    def test_evidence_archive_is_byte_deterministic_and_sorted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            retained = root / "retained.json"
            retained.write_bytes(b'{"retained":true}\n')
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            members = {
                "reports/structural-verifier.json": b'{"kind":"structural"}\n',
                "run/primary-evidence/manifest.json": retained,
                "logs/terminal.log": b"END-TO-END PROOF PASS\n",
            }
            collector._write_evidence_archive(first, members)
            collector._write_evidence_archive(second, members)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            portfolio._validate_tar(
                first,
                label="collector evidence fixture",
                source_commit=None,
                source_prefix=None,
            )
            with tarfile.open(first, mode="r:gz") as archive:
                names = archive.getnames()
                self.assertEqual(
                    names,
                    sorted(names, key=lambda item: item.encode("utf-8")),
                )
                for member in archive.getmembers():
                    self.assertTrue(member.isfile())
                    self.assertEqual(member.mtime, 0)
                    self.assertEqual(member.uid, 0)
                    self.assertEqual(member.gid, 0)
                    self.assertEqual(member.mode & 0o777, 0o600)
                self.assertEqual(
                    portfolio._canonical_evidence_archive_bytes(archive),
                    first.read_bytes(),
                )

    def test_run_snapshot_is_private_stable_and_rejects_extra_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            live = root / str(uuid.uuid4())
            live.mkdir(mode=0o700)
            (live / "app-run-receipt.json").write_bytes(b"receipt\n")
            (live / "validation-064-071.json").write_bytes(b"result\n")
            primary = live / "primary-evidence"
            primary.mkdir(mode=0o700)
            (primary / "manifest.json").write_bytes(b"manifest\n")
            reports = live / "proof-reports"
            reports.mkdir(mode=0o700)
            for name in (
                "structural-verifier.json",
                "fresh-model-replay.json",
                "terminal.log",
            ):
                (reports / name).write_bytes(name.encode("ascii") + b"\n")
            for artifact in live.rglob("*"):
                if artifact.is_file():
                    artifact.chmod(0o600)
            parent = root / "sealed"
            parent.mkdir(mode=0o700)
            snapshot = collector._snapshot_run(live, parent)
            (live / "validation-064-071.json").write_bytes(b"mutated\n")
            self.assertEqual(
                (snapshot / "validation-064-071.json").read_bytes(), b"result\n"
            )
            self.assertEqual(snapshot.stat().st_mode & 0o777, 0o700)
            (live / "extra.log").write_bytes(b"extra\n")
            with self.assertRaisesRegex(
                collector.CollectionError, "missing or extra top-level"
            ):
                collector._snapshot_run(live, root / "second-sealed")

    def test_runtime_manifest_tracks_the_collector_and_report_generator(self):
        self.assertIn(
            "publication/collect_portfolio_demo.py", portfolio.VERIFIER_PATHS
        )
        self.assertIn("security/proof_reports.py", portfolio.VERIFIER_PATHS)
        self.assertEqual(tuple(sorted(portfolio.VERIFIER_PATHS)), portfolio.VERIFIER_PATHS)

    def test_release_validator_rejects_declared_replay_counts(self):
        report = {
            **BINDING,
            "report_kind": "fresh_model_replay",
            "verdict": "AUTHOR_RECORDED_HEAVY_REPLAY_INTEGRITY_PASS",
            "execution_scope": (
                "AUTHOR_RECORDED_NOT_INDEPENDENTLY_REEXECUTED_BY_RELEASE_VERIFIER"
            ),
            "model": {
                "repository": portfolio.EXPECTED_MODEL,
                "revision": portfolio.EXPECTED_MODEL_REVISION,
            },
            "replay": {**REPLAY, **REPLAY_INTEGRITY, "decisions": 1023},
        }
        with self.assertRaisesRegex(
            portfolio.PortfolioReleaseError,
            "recorded model replay identity",
        ):
            portfolio._validate_evidence_report(
                report,
                kind="fresh_model_replay",
                source=SOURCE,
                receipt_sha256=BINDING["receipt_sha256"],
                result_sha256=BINDING["result_sha256"],
                metric_verdict="FAIL",
            )

    def test_runtime_toolchain_must_equal_demo_build_provenance(self):
        toolchain = {
            "developerTools": {
                "buildVersion": None,
                "identifier": "com.apple.pkg.CLTools_Executables",
                "kind": "command-line-tools",
                "version": "26.3.0.0.1.1773958034",
            },
            "macOS": {
                "architecture": "arm64",
                "buildVersion": "25D125",
                "productName": "macOS",
                "productVersion": "26.3",
            },
            "sdk": {
                "buildVersion": "25C57",
                "canonicalName": "macosx",
                "version": "26.2",
            },
            "swift": {
                "compiler": "swift-frontend",
                "compilerSHA256": "5" * 64,
                "target": "arm64-apple-macosx26.0",
                "version": "6.3.3",
            },
        }
        portfolio._validate_evidence_toolchain_binding(
            {"toolchain": toolchain}, toolchain
        )
        different = json.loads(json.dumps(toolchain))
        different["swift"]["version"] = "6.3.2"
        with self.assertRaisesRegex(
            portfolio.PortfolioReleaseError,
            "differs from demo build provenance",
        ):
            portfolio._validate_evidence_toolchain_binding(
                {"toolchain": toolchain}, different
            )

    def test_run_proof_retains_reports_only_after_real_verifiers(self):
        proof = (
            ROOT / "platforms" / "macos" / "scripts" / "run-proof.sh"
        ).read_text(encoding="utf-8")
        structural = proof.index('    --report "$STRUCTURAL_REPORT"')
        replay_command = proof.index("security/verify_primary_replay.py")
        replay_report = proof.index('    --report "$REPLAY_REPORT"')
        terminal = proof.index('printf \'%s\\n\' "$proof_summary" >"$TERMINAL_REPORT"')
        self.assertLess(structural, replay_command)
        self.assertLess(replay_command, replay_report)
        self.assertLess(replay_report, terminal)
        self.assertIn('--structural-report "$STRUCTURAL_REPORT"', proof)
        self.assertIn("END-TO-END PROOF VERIFIED — METRIC FAIL", proof)
        self.assertNotIn("rerun-to-pass", proof)


if __name__ == "__main__":
    unittest.main()
