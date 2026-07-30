import json
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
    def _phase_paths(self, root: Path) -> dict[str, Path]:
        return {
            "selectionAttempt": root / "selection.attempt.json",
            "selectionResult": root / "selection.json",
            "holdoutAttempt": root / "holdout.attempt.json",
            "holdoutResult": root / "holdout.json",
        }

    def _write_json(self, path: Path, value: dict) -> None:
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

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
