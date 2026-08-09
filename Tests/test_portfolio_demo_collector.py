import json
import os
import subprocess
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
from security import automated_media  # noqa: E402


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
    def _readiness(self):
        return {
            "schema_version": 1,
            "status": "CAPTURE_RESULT_READY",
            "run_identifier": "12345678-1234-4234-8234-123456789abc",
            "receipt_sha256": "1" * 64,
            "result_sha256": "2" * 64,
            "application_executable_sha256": "3" * 64,
            "metric_verdict": "PASS",
            "compression_ratio_vs_bf16": "2.000000",
            "delta_nll_nat_per_token": "0.001000",
            "top1_agreement": "0.999000",
            "module_states": {
                "qwen_model": "COMPLETE",
                "kv_cache": "COMPLETE",
                "compression": "COMPLETE",
                "primary_evidence": "COMPLETE",
                "heavy_replay": "PASS",
            },
            "verifier_state": "PASS",
        }

    def test_private_readiness_copy_remains_0600_and_0644_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            source = root / "source-readiness.json"
            target = root / "target-readiness.json"
            source.write_bytes(automated_media.canonical_json_bytes(self._readiness()))
            source.chmod(0o600)
            collector._copy_private_regular(
                source, target, automated_media.MAX_READINESS_BYTES
            )
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                automated_media.read_canonical_readiness(target), self._readiness()
            )
            target.chmod(0o644)
            with self.assertRaisesRegex(
                automated_media.AutomatedMediaError, "owner-only"
            ):
                automated_media.read_canonical_readiness(target)

    def test_fixed_composition_replay_rejects_byte_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            live = root / "live.mov"
            result = root / "result.mov"
            video = root / "video.mp4"
            poster = root / "poster.png"
            for path, payload in (
                (live, b"live"), (result, b"result"),
                (video, b"expected-video"), (poster, b"expected-poster"),
            ):
                path.write_bytes(payload)

            def fake_run(arguments, **_kwargs):
                output = Path(arguments[-1])
                if output.suffix == ".mp4":
                    output.write_bytes(b"tampered-video")
                else:
                    output.write_bytes(b"expected-poster")
                return subprocess.CompletedProcess(arguments, 0, b"", b"")

            with patch.object(portfolio, "_run", side_effect=fake_run):
                with self.assertRaisesRegex(
                    collector.CollectionError, "exact raw composition"
                ):
                    collector._verify_composition_from_raw(
                        live=live,
                        result=result,
                        video=video,
                        poster=poster,
                        ffmpeg=Path("/fixture/ffmpeg"),
                    )

    def test_collector_cli_and_archive_surface_require_full_session_evidence(self):
        source = (ROOT / "publication/collect_portfolio_demo.py").read_text(
            encoding="utf-8"
        )
        for required in (
            'parser.add_argument("--result-readiness", type=Path, required=True)',
            'parser.add_argument("--attempt-state", type=Path, required=True)',
            'parser.add_argument("--tag-ci-bundle", type=Path, required=True)',
            'parser.add_argument("--local-tag-trust-receipt", type=Path, required=True)',
            '"session/preflight-window.mov": preflight_path',
            '"session/live-presentation.mov": live_path',
            '"session/same-run-result.mov": result_segment_path',
            '"session/find-proof-window": helper_path',
        ):
            with self.subTest(required=required):
                self.assertIn(required, source)
        self.assertNotIn('parser.add_argument("--linux-ci-url"', source)
        self.assertNotIn('parser.add_argument("--macos-ci-url"', source)
        self.assertIn('recomputed_tag_ci["workflows"][0]["html_url"]', source)

        for relative in ("docs/DEMO.md", "publication/PORTFOLIO_RELEASE.md"):
            document = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(document=relative):
                for option in (
                    "--result-readiness",
                    "--attempt-state",
                    "--preflight-segment",
                    "--live-segment",
                    "--result-segment",
                    "--window-helper",
                    "--tag-ci-receipt",
                    "--local-tag-trust-receipt",
                    "--tag-ci-bundle",
                ):
                    self.assertIn(option, document)
                self.assertNotIn("--linux-ci-url", document)
                self.assertNotIn("--macos-ci-url", document)
                self.assertNotIn("only the three named", document.lower())
                self.assertNotIn("only the three", document.lower())

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
            python_cache = live / "python-cache"
            python_cache.mkdir(mode=0o700)
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
            self.assertFalse((snapshot / "python-cache").exists())
            (live / "extra.log").write_bytes(b"extra\n")
            with self.assertRaisesRegex(
                collector.CollectionError, "missing or extra top-level"
            ):
                collector._snapshot_run(live, root / "second-sealed")
            (live / "extra.log").unlink()

            (python_cache / "unexpected.pyc").write_bytes(b"not evidence\n")
            with self.assertRaisesRegex(
                collector.CollectionError, "python-cache must be empty"
            ):
                collector._snapshot_run(live, root / "nonempty-sealed")
            (python_cache / "unexpected.pyc").unlink()

            python_cache.chmod(0o750)
            with self.assertRaisesRegex(
                collector.CollectionError, "owner-only non-symlink directory"
            ):
                collector._snapshot_run(live, root / "mode-sealed")
            python_cache.chmod(0o700)

            python_cache.rmdir()
            with self.assertRaisesRegex(
                collector.CollectionError, "missing or extra top-level"
            ):
                collector._snapshot_run(live, root / "missing-cache-sealed")
            python_cache.symlink_to(primary, target_is_directory=True)
            with self.assertRaisesRegex(
                collector.CollectionError, "owner-only non-symlink directory"
            ):
                collector._snapshot_run(live, root / "symlink-cache-sealed")
            python_cache.unlink()
            python_cache.write_bytes(b"not a directory\n")
            python_cache.chmod(0o600)
            with self.assertRaisesRegex(
                collector.CollectionError, "owner-only non-symlink directory"
            ):
                collector._snapshot_run(live, root / "file-cache-sealed")
            python_cache.unlink()
            python_cache.mkdir(mode=0o700)

            original_copy = collector._copy_snapshot_file
            mutated = False

            def mutate_cache(source, destination, maximum_bytes):
                nonlocal mutated
                copied = original_copy(source, destination, maximum_bytes)
                if not mutated:
                    (python_cache / "late.pyc").write_bytes(b"late mutation\n")
                    mutated = True
                return copied

            mutated_parent = root / "mutated-cache-sealed"
            mutated_parent.mkdir(mode=0o700)
            with (
                patch.object(
                    collector,
                    "_copy_snapshot_file",
                    side_effect=mutate_cache,
                ),
                self.assertRaisesRegex(
                    collector.CollectionError, "python-cache changed while sealing"
                ),
            ):
                collector._snapshot_run(live, mutated_parent)
            (python_cache / "late.pyc").unlink()

            replacement = root / "replaced-python-cache"
            replaced = False

            def replace_cache(source, destination, maximum_bytes):
                nonlocal replaced
                copied = original_copy(source, destination, maximum_bytes)
                if not replaced:
                    python_cache.rename(replacement)
                    python_cache.mkdir(mode=0o700)
                    replaced = True
                return copied

            replaced_parent = root / "replaced-cache-sealed"
            replaced_parent.mkdir(mode=0o700)
            with (
                patch.object(
                    collector,
                    "_copy_snapshot_file",
                    side_effect=replace_cache,
                ),
                self.assertRaisesRegex(
                    collector.CollectionError, "python-cache changed while sealing"
                ),
            ):
                collector._snapshot_run(live, replaced_parent)
            python_cache.rmdir()
            replacement.rename(python_cache)

    def test_runtime_manifest_tracks_the_collector_and_report_generator(self):
        for relative in (
            ".github/workflows/verify-linux.yml",
            ".github/workflows/verify-macos.yml",
            "corelm",
            "publication/collect_portfolio_demo.py",
            "publication/run_portfolio_python.sh",
            "scripts/verify-python.sh",
            "security/proof_reports.py",
            "security/verify_portfolio_tag_ci.py",
        ):
            with self.subTest(path=relative):
                self.assertIn(relative, portfolio.VERIFIER_PATHS)
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

    def test_demo_runbook_uses_only_automated_bound_public_media(self):
        runbook = (ROOT / "docs" / "DEMO.md").read_text(encoding="utf-8")
        for required in (
            "AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE",
            "./corelm macos portfolio-demo",
            '--automation-receipt "$AUTOMATION_RECEIPT"',
            '--video "$VIDEO"',
            '--poster "$POSTER"',
            '--ffmpeg "$FFMPEG"',
            '--ffprobe "$FFPROBE"',
            "poster derived automatically at exactly 15.000000 seconds",
            "pixel_semantics_verified:false",
            "NO_CONFIGURED_PATTERN_DETECTED",
        ):
            with self.subTest(required=required):
                self.assertIn(required, runbook)
        self.assertNotIn("RAW_DEMO_SCREENSHOT=", runbook)
        self.assertNotIn("DEMO_SCREENSHOT=", runbook)
        self.assertNotIn("--poster-frame-seconds", runbook)
        self.assertNotIn("HUMAN_REVIEWED_PRESENTATION_NOT_MACHINE_EVIDENCE", runbook)


if __name__ == "__main__":
    unittest.main()
