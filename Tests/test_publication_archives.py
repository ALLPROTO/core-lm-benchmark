import json
import re
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import publication.build_archives as archives  # noqa: E402


def _completed(
    stdout: str = "",
    *,
    returncode: int = 0,
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["git"],
        returncode,
        stdout=stdout,
        stderr=stderr,
    )


class PublicationArchiveTests(unittest.TestCase):
    def test_publication_release_identifier_is_synchronized(self):
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        match = re.search(r'(?m)^version: "([^"]+)"$', citation)
        self.assertIsNotNone(match)
        release_tag = match.group(1)
        self.assertRegex(release_tag, r"^voidtoken-v5-paper-v[1-9][0-9]*$")

        for relative in (
            "publication/README.md",
            "publication/reproducibility/README.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(f"RELEASE_TAG={release_tag}", text)

        manuscript = (
            ROOT / "publication/arxiv-v5/main.tex"
        ).read_text(encoding="utf-8")
        self.assertIn(rf"\path{{{release_tag}}}", manuscript)

        sbom = json.loads(
            (
                ROOT / "security/direct-dependencies.cdx.json"
            ).read_text(encoding="utf-8")
        )
        component = sbom["metadata"]["component"]
        self.assertEqual(component["version"], release_tag)
        self.assertTrue(component["purl"].endswith(f"@{release_tag}"))
        self.assertEqual(sbom["dependencies"][0]["ref"], component["bom-ref"])

    def _phase_paths(self, root: Path) -> dict[str, Path]:
        return {
            "selectionAttempt": root / "selection.attempt.json",
            "selectionResult": root / "selection.json",
            "holdoutAttempt": root / "holdout.attempt.json",
            "holdoutResult": root / "holdout.json",
        }

    def _write_json(self, path: Path, value: dict) -> None:
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    def test_submission_metadata_discloses_historical_accounting_limit(self):
        metadata = (
            ROOT / "publication/arxiv-v5/submission_metadata.md"
        ).read_text(encoding="utf-8")
        self.assertIn("73,346,513 runner-recorded bytes", metadata)
        self.assertIn("not independently reconstructible", metadata)
        self.assertNotIn("73,346,513 bytes (2.05329x", metadata)

    def test_v5_evidence_state_accepts_every_terminal_or_pending_state(self):
        cases = [
            ("registration-only", {}),
            ("selection-consumed-incomplete", {"selectionAttempt": {}}),
            (
                "selection-fail-terminal",
                {"selectionAttempt": {}, "selectionResult": {"pass": False}},
            ),
            (
                "selection-pass-awaiting-holdout",
                {"selectionAttempt": {}, "selectionResult": {"pass": True}},
            ),
            (
                "holdout-consumed-incomplete",
                {
                    "selectionAttempt": {},
                    "selectionResult": {"pass": True},
                    "holdoutAttempt": {},
                },
            ),
            (
                "holdout-pass",
                {
                    "selectionAttempt": {},
                    "selectionResult": {"pass": True},
                    "holdoutAttempt": {},
                    "holdoutResult": {"pass": True},
                },
            ),
            (
                "holdout-fail",
                {
                    "selectionAttempt": {},
                    "selectionResult": {"pass": True},
                    "holdoutAttempt": {},
                    "holdoutResult": {"pass": False},
                },
            ),
        ]
        for expected, files in cases:
            with self.subTest(expected=expected):
                with tempfile.TemporaryDirectory() as temporary:
                    paths = self._phase_paths(Path(temporary))
                    for name, value in files.items():
                        self._write_json(paths[name], value)
                    with patch.object(
                        archives, "V5_PHASE_PATHS", paths
                    ):
                        state, included = archives._v5_evidence_state()
                    self.assertEqual(state, expected)
                    self.assertEqual(len(included), len(files))

    def test_v5_evidence_state_rejects_invalid_permutations(self):
        cases = [
            {"selectionResult": {"pass": True}},
            {"holdoutAttempt": {}},
            {
                "selectionAttempt": {},
                "selectionResult": {"pass": False},
                "holdoutAttempt": {},
            },
            {
                "selectionAttempt": {},
                "selectionResult": {"pass": True},
                "holdoutResult": {"pass": True},
            },
        ]
        for files in cases:
            with self.subTest(files=tuple(files)):
                with tempfile.TemporaryDirectory() as temporary:
                    paths = self._phase_paths(Path(temporary))
                    for name, value in files.items():
                        self._write_json(paths[name], value)
                    with (
                        patch.object(archives, "V5_PHASE_PATHS", paths),
                        self.assertRaises(ValueError),
                    ):
                        archives._v5_evidence_state()

    def _fake_git(self, responses):
        def invoke(*arguments, check=True):
            response = responses.get(tuple(arguments))
            if response is None:
                self.fail(f"unexpected git call: {arguments}")
            if check and response.returncode:
                raise ValueError("simulated git failure")
            return response

        return invoke

    def _base_release_responses(self, *, dirty: bool = False):
        return {
            ("rev-parse", "--show-toplevel"): _completed(f"{ROOT}\n"),
            ("rev-parse", "HEAD"): _completed("a" * 40 + "\n"),
            (
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignored=no",
            ): _completed(" M README.md\n" if dirty else ""),
            ("ls-files", "-z"): _completed("README.md\0"),
        }

    def test_release_preflight_rejects_dirty_worktree(self):
        responses = self._base_release_responses(dirty=True)
        with (
            patch.object(archives, "_git", side_effect=self._fake_git(responses)),
            self.assertRaisesRegex(ValueError, "clean worktree"),
        ):
            archives._build_context("v0.4.0")

    def test_release_preflight_rejects_annotated_tag(self):
        responses = self._base_release_responses()
        responses[("cat-file", "-t", "refs/tags/v0.4.0")] = _completed(
            "tag\n"
        )
        with (
            patch.object(archives, "_git", side_effect=self._fake_git(responses)),
            self.assertRaisesRegex(ValueError, "lightweight"),
        ):
            archives._build_context("v0.4.0")

    def test_release_preflight_checks_origin_and_remote_tag(self):
        responses = self._base_release_responses()
        reference = "refs/tags/v0.4.0"
        responses[("cat-file", "-t", reference)] = _completed("commit\n")
        responses[
            ("rev-parse", "--verify", f"{reference}^{{commit}}")
        ] = _completed("a" * 40 + "\n")
        responses[("remote", "get-url", "origin")] = _completed(
            archives.PUBLIC_ORIGIN + ".git\n"
        )
        responses[
            ("ls-remote", "--exit-code", "origin", reference)
        ] = _completed(f"{'a' * 40}\t{reference}\n")
        with patch.object(
            archives, "_git", side_effect=self._fake_git(responses)
        ):
            context = archives._build_context("v0.4.0")
        self.assertEqual(context["buildMode"], "clean-public-tag-release")
        self.assertTrue(context["remoteTagVerified"])

        wrong_origin = dict(responses)
        wrong_origin[("remote", "get-url", "origin")] = _completed(
            "https://github.com/example/wrong.git\n"
        )
        with (
            patch.object(
                archives,
                "_git",
                side_effect=self._fake_git(wrong_origin),
            ),
            self.assertRaisesRegex(ValueError, "origin"),
        ):
            archives._build_context("v0.4.0")

    def test_release_source_must_be_tracked(self):
        context = {
            "releaseTag": "v0.4.0",
            "trackedFiles": set(),
        }
        with self.assertRaisesRegex(ValueError, "not tracked"):
            archives._assert_release_source(ROOT / "README.md", context)

    def test_reproducibility_archive_contains_v5_evidence_and_provenance(self):
        context = {
            "buildMode": "preview-working-tree",
            "builtFromCleanHead": False,
            "gitHeadCommit": "a" * 40,
            "releaseTag": None,
            "remoteTagVerified": False,
            "trackedFiles": set(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            archive = archives.build_reproducibility(
                Path(temporary), context
            )
            with tarfile.open(archive, "r:gz") as bundle:
                names = set(bundle.getnames())
                prefix = "corelm_reproducibility"
                self.assertIn(f"{prefix}/PROVENANCE.json", names)
                provenance_member = bundle.extractfile(
                    f"{prefix}/PROVENANCE.json"
                )
                self.assertIsNotNone(provenance_member)
                provenance = json.load(provenance_member)
                evidence_paths = {
                    entry["path"] for entry in provenance["evidenceFiles"]
                }
                self.assertTrue(
                    {
                        "app-real-llm-evidence/validation-064-071.json",
                        "app-real-llm-evidence/app-run-receipt.json",
                        "app-real-llm-evidence/SHA256SUMS",
                    }.issubset(evidence_paths)
                )
                self.assertIn(
                    f"{prefix}/real-llm-v5-development/manifest.json",
                    names,
                )
                self.assertIn(
                    f"{prefix}/RealLLM/verify_voidtoken_v5_development.py",
                    names,
                )
                self.assertIn(
                    f"{prefix}/publication/arxiv-v5/generate_figures.py",
                    names,
                )
                for relative in (
                    "build_local_app.sh",
                    "run_local_app_proof.sh",
                    "requirements.lock",
                    "RealLLM/requirements.lock",
                    "RealLLM/prepare_app_assets.py",
                    "SECURITY.md",
                    "App/Sources/PythonRuntimeManifest.swift",
                    "App/Sources/SecurityValidation.swift",
                    "TestsSwift/SecurityValidationTests.swift",
                    "security/generate_python_runtime_manifest.py",
                    "security/manage_local_runtime.py",
                    "security/verify_app_run_evidence.py",
                    "security/verify_local_app_run.py",
                    "security/verify_locked_environment.py",
                    "security/verify_supply_chain.py",
                    "security/verify_app_bundle.sh",
                    "Tests/test_swift_security_gate.py",
                    "app-real-llm-evidence/README.md",
                    "app-real-llm-evidence/SHA256SUMS",
                    "app-real-llm-evidence/app-run-receipt.json",
                    "app-real-llm-evidence/validation-064-071.json",
                    "publication/arxiv-v5/submission_metadata.md",
                ):
                    self.assertIn(f"{prefix}/{relative}", names)
                for relative in archives.V5_ARXIV_SOURCE_FILES:
                    self.assertIn(
                        f"{prefix}/publication/arxiv-v5/{relative}",
                        names,
                    )

    def test_reproducibility_archive_can_run_publication_archive_test(self):
        context = {
            "buildMode": "preview-working-tree",
            "builtFromCleanHead": False,
            "gitHeadCommit": "a" * 40,
            "releaseTag": None,
            "remoteTagVerified": False,
            "trackedFiles": set(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = archives.build_reproducibility(root, context)
            extract_root = root / "extracted"
            extract_root.mkdir()
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(extract_root, filter="data")
            extracted = extract_root / "corelm_reproducibility"
            child_cache = root / "child-pycache"
            child_cache.mkdir()
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-X",
                    f"pycache_prefix={child_cache}",
                    "-m",
                    "unittest",
                    (
                        "Tests.test_publication_archives."
                        "PublicationArchiveTests."
                        "test_v5_arxiv_archive_contains_only_current_"
                        "submission_sources"
                    ),
                    "-v",
                ],
                cwd=extracted,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=completed.stdout + completed.stderr,
            )

    def test_v5_arxiv_archive_contains_only_current_submission_sources(self):
        context = {
            "buildMode": "preview-working-tree",
            "builtFromCleanHead": False,
            "gitHeadCommit": "a" * 40,
            "releaseTag": None,
            "remoteTagVerified": False,
            "trackedFiles": set(),
        }
        expected = {
            "main.tex",
            "author.tex",
            "references.bib",
            "main.bbl",
            "results_table.tex",
            "figures/block_metrics.pdf",
            "figures/codec_pipeline.pdf",
            "figures/protocol_timeline.pdf",
        }
        with tempfile.TemporaryDirectory() as temporary:
            archive = archives.build_arxiv_v5(
                Path(temporary), context
            )
            self.assertEqual(
                archive.name,
                "corelm_voidtoken_v5_arxiv_source.tar.gz",
            )
            with tarfile.open(archive, "r:gz") as bundle:
                self.assertEqual(set(bundle.getnames()), expected)
                main = bundle.extractfile("main.tex")
                results = bundle.extractfile("results_table.tex")
                self.assertIsNotNone(main)
                self.assertIsNotNone(results)
                main_text = main.read().decode("ascii")
                results_text = results.read().decode("ascii")
            self.assertIn(
                "VoidToken v5: Prospectively Frozen Evidence",
                main_text,
            )
            self.assertIn("voidtoken-v5-evidence-v1", main_text)
            self.assertIn(
                "d1c16e88655c1fbc9884324742dee3f",
                main_text,
            )
            self.assertIn("Holdout", results_text)
            self.assertIn("2.053291", results_text)
            self.assertNotIn("metrics_by_dimension.pdf", main_text)
            self.assertNotIn("error_feedback.pdf", main_text)

    def test_determinism_flag_also_writes_requested_output(self):
        context = {"buildMode": "preview-working-tree"}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            artifacts = [
                output / "corelm_voidtoken_v5_arxiv_source.tar.gz",
                output / "corelm_reproducibility.tar.gz",
            ]
            arguments = types.SimpleNamespace(
                output=output,
                verify_determinism=True,
                release_tag=None,
            )
            with (
                patch.object(
                    archives,
                    "parse_arguments",
                    return_value=arguments,
                ),
                patch.object(
                    archives,
                    "_build_context",
                    return_value=context,
                ),
                patch.object(
                    archives,
                    "verify_determinism",
                    return_value=True,
                ) as determinism,
                patch.object(
                    archives,
                    "build_all",
                    return_value=artifacts,
                ) as build,
                patch.object(
                    archives,
                    "write_checksums",
                    return_value=output / "SHA256SUMS",
                ) as checksums,
            ):
                self.assertEqual(archives.main(), 0)
            determinism.assert_called_once_with(context)
            build.assert_called_once_with(output, context)
            checksums.assert_called_once_with(artifacts, output)


if __name__ == "__main__":
    unittest.main()
