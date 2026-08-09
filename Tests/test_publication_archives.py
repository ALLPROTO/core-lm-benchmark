import json
import os
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
PAPER_TEST_TAG = "voidtoken-v5-paper-v5"
MISMATCHED_PAPER_TEST_TAG = "voidtoken-v5-paper-v9"

import publication.build_archives as archives  # noqa: E402
from security import generate_build_provenance as build_provenance  # noqa: E402


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
    def test_current_portfolio_schemas_pin_automation_only_v8_contract(self):
        release_input = json.loads(
            (ROOT / "schemas/portfolio-release-input.schema.json").read_text(
                encoding="utf-8"
            )
        )
        source_identity = json.loads(
            (ROOT / "schemas/portfolio-source-identity.schema.json").read_text(
                encoding="utf-8"
            )
        )
        demo_provenance = json.loads(
            (ROOT / "schemas/portfolio-demo-provenance.schema.json").read_text(
                encoding="utf-8"
            )
        )
        runtime_assets = json.loads(
            (ROOT / "schemas/portfolio-runtime-assets.schema.json").read_text(
                encoding="utf-8"
            )
        )

        for schema in (
            release_input,
            source_identity,
            demo_provenance,
            runtime_assets,
        ):
            self.assertEqual(schema["properties"]["schema_version"]["const"], 2)

        presentation = release_input["properties"]["presentation"]
        self.assertFalse(presentation["additionalProperties"])
        self.assertEqual(
            set(presentation["required"]), set(presentation["properties"])
        )
        expected_contract = {
            "automation_contract": "corelm-automated-presentation-v2",
            "classification": "AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE",
            "automation_only": True,
            "human_reviewed": False,
            "manual_edits": False,
            "machine_evidence": False,
            "pixel_semantics_verified": False,
            "independent_human_replication": False,
        }
        self.assertEqual(
            {
                key: descriptor["const"]
                for key, descriptor in presentation["properties"].items()
            },
            expected_contract,
        )

        demo = source_identity["properties"]["demo"]
        self.assertFalse(demo["additionalProperties"])
        self.assertIn("provenance_sha256", demo["required"])
        self.assertEqual(
            demo["properties"]["media_classification"]["const"],
            expected_contract["classification"],
        )
        self.assertEqual(
            demo["properties"]["automation_contract"]["const"],
            expected_contract["automation_contract"],
        )

        capture = demo_provenance["properties"]["capture"]
        self.assertFalse(capture["additionalProperties"])
        self.assertEqual(set(capture["required"]), set(capture["properties"]))
        self.assertEqual(
            capture["properties"]["mode"]["const"],
            "MACOS_SINGLE_WINDOW_ID_V1",
        )
        self.assertEqual(
            capture["properties"]["automation_receipt_sha256"]["$ref"],
            "#/$defs/sha256",
        )
        self.assertEqual(
            capture["properties"]["result_readiness_sha256"]["$ref"],
            "#/$defs/sha256",
        )
        self.assertEqual(
            demo_provenance["properties"]["video"]["properties"][
                "audio_codec"
            ]["const"],
            "silent",
        )

        capture_tools = runtime_assets["properties"]["capture_tools"]
        self.assertFalse(capture_tools["additionalProperties"])
        self.assertEqual(
            set(capture_tools["required"]), set(capture_tools["properties"])
        )
        self.assertEqual(
            capture_tools["properties"]["screencapture"]["properties"][
                "codesign_identifier"
            ]["const"],
            "com.apple.screencapture",
        )
        self.assertEqual(
            capture_tools["properties"]["window_helper"]["properties"][
                "source_sha256"
            ]["$ref"],
            "#/$defs/sha256",
        )
        self.assertIn("capture_tools", runtime_assets["required"])

    def test_archive_output_rejects_symlink_directory_and_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside"
            outside.mkdir(mode=0o700)
            linked_output = root / "linked-output"
            linked_output.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "output directory"):
                archives._safe_output_directory(linked_output)

            output = root / "output"
            output.mkdir(mode=0o700)
            outside_file = outside / "do-not-overwrite"
            outside_file.write_bytes(b"preserve me")
            linked_target = output / "SHA256SUMS"
            linked_target.symlink_to(outside_file)
            with self.assertRaisesRegex(ValueError, "target is unsafe"):
                with archives._atomic_output_path(linked_target):
                    pass
            self.assertEqual(outside_file.read_bytes(), b"preserve me")

    def test_current_software_and_historical_paper_identities_are_separate(self):
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        match = re.search(r'(?m)^version: "([^"]+)"$', citation)
        self.assertIsNotNone(match)
        release_tag = match.group(1)
        self.assertEqual(release_tag, "corelm-portfolio-v8")
        self.assertRegex(citation, r"(?m)^date-released: 2026-08-09$")

        for relative in (
            "publication/README.md",
            "publication/reproducibility/README.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(f"RELEASE_TAG={PAPER_TEST_TAG}", text)

        manuscript = (
            ROOT / "publication/arxiv-v5/main.tex"
        ).read_text(encoding="utf-8")
        self.assertIn(rf"\path{{{PAPER_TEST_TAG}}}", manuscript)

        sbom = json.loads(
            (
                ROOT / "security/direct-dependencies.cdx.json"
            ).read_text(encoding="utf-8")
        )
        component = sbom["metadata"]["component"]
        self.assertEqual(component["version"], release_tag)
        self.assertTrue(component["purl"].endswith(f"@{release_tag}"))
        self.assertEqual(sbom["dependencies"][0]["ref"], component["bom-ref"])

        identifiers = (
            ROOT / "docs/development/SCIENTIFIC_IDENTIFIERS.md"
        ).read_text(encoding="utf-8")
        self.assertIn("corelm-automated-presentation-v2", identifiers)
        self.assertIn("AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE", identifiers)
        self.assertIn("G10", identifiers)
        self.assertIn("**OPEN**", identifiers)

        with self.assertRaisesRegex(ValueError, "outside the historical paper contour"):
            archives._citation_release_tag()

    def test_v4_pre_model_failure_is_preserved_without_consuming_attempt(self):
        for relative in (
            "docs/DEMO.md",
            "docs/development/RELEASE_PROCESS.md",
            "docs/development/SCIENTIFIC_IDENTIFIERS.md",
        ):
            with self.subTest(document=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                normalized = " ".join(text.split())
                self.assertIn("corelm-portfolio-v3", text)
                self.assertIn("corelm-portfolio-v4", text)
                self.assertIn("FFprobe frame-PTS", normalized)
                self.assertIn("AttemptLog.reserve", text)
                self.assertRegex(
                    normalized,
                    r"no (?:V4 )?model attempt (?:was )?(?:invoked or )?consumed",
                )
                self.assertIn("never", normalized.lower())

    def test_v5_github_id_failure_is_preserved_without_consuming_attempt(self):
        for relative in (
            "docs/DEMO.md",
            "docs/development/RELEASE_PROCESS.md",
            "docs/development/SCIENTIFIC_IDENTIFIERS.md",
        ):
            with self.subTest(document=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                normalized = " ".join(text.split())
                self.assertIn("corelm-portfolio-v5", text)
                self.assertIn("corelm-portfolio-v8", text)
                self.assertIn("HTTP 403", normalized)
                self.assertIn("AttemptLog.reserve", text)
                self.assertRegex(normalized, r"(?:signed 32-bit|above `2\^31`)")
                self.assertRegex(
                    normalized,
                    r"no V5 model attempt was invoked or consumed",
                )
                self.assertIn("never", normalized.lower())

    def test_v6_pass_and_post_proof_executable_failure_are_preserved(self):
        for relative in (
            "docs/DEMO.md",
            "docs/ENGINEERING_CASE_STUDY.md",
            "docs/LIMITATIONS.md",
            "docs/PORTFOLIO_READINESS.md",
            "docs/development/RELEASE_PROCESS.md",
            "docs/development/SCIENTIFIC_IDENTIFIERS.md",
            "publication/PORTFOLIO_RELEASE.md",
            "publication/README.md",
            "publication/reproducibility/README.md",
        ):
            with self.subTest(document=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                normalized = " ".join(text.split())
                self.assertIn("corelm-portfolio-v6", text)
                self.assertIn("corelm-portfolio-v8", text)
                self.assertIn("first-attempt tag CI", normalized)
                self.assertIn("2.052384x", normalized)
                self.assertIn("-0.00000846", normalized)
                self.assertIn("99.5117%", normalized)
                self.assertIn("1,024", normalized)
                self.assertIn("zero maximum loss error", normalized)
                self.assertIn("ATTEMPT_FAILED", text)
                self.assertIn("REPLAY_VERIFIED", text)
                self.assertIn("preflight-built", normalized)
                self.assertRegex(normalized, r"proof-(?:driver's )?rebuilt verified app")
                self.assertIn("same-run result", normalized.lower())
                self.assertIn("media sealing", normalized)
                self.assertIn("collection", normalized)
                self.assertIn("never", normalized.lower())

    def test_v7_pre_marker_history_and_v8_single_job_fix_are_preserved(self):
        historical_documents = (
            "docs/DEMO.md",
            "docs/ENGINEERING_CASE_STUDY.md",
            "docs/LIMITATIONS.md",
            "docs/PORTFOLIO_READINESS.md",
            "docs/development/RELEASE_PROCESS.md",
            "docs/development/SCIENTIFIC_IDENTIFIERS.md",
            "publication/PORTFOLIO_RELEASE.md",
            "publication/README.md",
            "publication/reproducibility/README.md",
        )
        for relative in historical_documents:
            with self.subTest(document=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                normalized = " ".join(text.split())
                self.assertIn("corelm-portfolio-v7", text)
                self.assertIn("corelm-portfolio-v8", text)
                self.assertIn("three V7 runner invocations", normalized)
                self.assertIn("two", normalized.lower())
                self.assertIn("50%", normalized)
                self.assertIn("parallel Swift", normalized)
                self.assertIn(
                    "transient pre-marker public tag-CI admission failure",
                    normalized,
                )
                self.assertIn("8-response validation subsequently passed", normalized)
                self.assertIn("AttemptLog.reserve", text)
                self.assertIn("durable state and session remained absent", normalized)
                self.assertIn("no proof or model attempt was consumed", normalized)
                self.assertIn(
                    "single-job/low-peak-memory pre-marker build scheduling",
                    normalized,
                )
                self.assertIn("without weakening the 50%", normalized)
                self.assertIn("exact produced app SHA", normalized)
                self.assertIn("does not claim byte-deterministic", normalized)
                self.assertIn("never", normalized.lower())

        exact_documents = (
            "docs/DEMO.md",
            "docs/development/RELEASE_PROCESS.md",
            "publication/PORTFOLIO_RELEASE.md",
        )
        for relative in exact_documents:
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(exact_identity_document=relative):
                for identity in (
                    "8d53e43208f76141a01bb2c0914459fbc101e7d5",
                    "ea82aa490c008d8560a6d44a70407d8d5e33bdbc",
                    "2c82497617173e3dfd965502860082ab5bf98130",
                    "31328178519",
                    "31328178525",
                ):
                    self.assertIn(identity, text)

    def test_current_publication_readmes_close_beacon_without_overclaim(self):
        evidence_commit = "85c2add1799652a818873a04310b75821728da11"
        for relative in (
            "real-llm-beacon-results/README.md",
            "publication/README.md",
            "publication/reproducibility/README.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            normalized = " ".join(text.split())
            self.assertIn(evidence_commit, text)
            self.assertIn("terminal **PASS**", text)
            self.assertIn("suite is consumed", normalized.lower())
            self.assertNotIn("suite has no result yet", normalized.lower())
            self.assertNotIn(
                "target pulse has not produced a checked-in result",
                normalized.lower(),
            )
            self.assertNotIn(
                "exactly one recorded execution is permitted",
                normalized.lower(),
            )

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
            ("rev-parse", "HEAD^{tree}"): _completed("b" * 40 + "\n"),
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
            patch.object(
                archives, "_citation_release_tag", return_value=PAPER_TEST_TAG
            ),
            self.assertRaisesRegex(ValueError, "clean worktree"),
        ):
            archives._build_context(PAPER_TEST_TAG)

    def test_release_preflight_rejects_portfolio_tag_as_wrong_contour(self):
        responses = self._base_release_responses()
        with (
            patch.object(archives, "_git", side_effect=self._fake_git(responses)),
            self.assertRaisesRegex(ValueError, "SSH-signed replication contour"),
        ):
            archives._build_context("corelm-portfolio-v2")

    def test_release_preflight_rejects_arbitrary_lightweight_tag_name(self):
        responses = self._base_release_responses()
        with (
            patch.object(archives, "_git", side_effect=self._fake_git(responses)),
            self.assertRaisesRegex(ValueError, "historical paper contour"),
        ):
            archives._build_context("v0.4.0")

    def test_release_preflight_rejects_tag_that_disagrees_with_citation(self):
        responses = self._base_release_responses()
        with (
            patch.object(archives, "_git", side_effect=self._fake_git(responses)),
            patch.object(
                archives, "_citation_release_tag", return_value=PAPER_TEST_TAG
            ),
            self.assertRaisesRegex(ValueError, "CITATION.cff version"),
        ):
            archives._build_context(MISMATCHED_PAPER_TEST_TAG)

    def test_release_preflight_rejects_annotated_tag(self):
        responses = self._base_release_responses()
        responses[("cat-file", "-t", f"refs/tags/{PAPER_TEST_TAG}")] = _completed(
            "tag\n"
        )
        with (
            patch.object(archives, "_git", side_effect=self._fake_git(responses)),
            patch.object(
                archives, "_citation_release_tag", return_value=PAPER_TEST_TAG
            ),
            self.assertRaisesRegex(ValueError, "lightweight"),
        ):
            archives._build_context(PAPER_TEST_TAG)

    def test_release_preflight_checks_origin_and_remote_tag(self):
        responses = self._base_release_responses()
        reference = f"refs/tags/{PAPER_TEST_TAG}"
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
        with (
            patch.object(archives, "_git", side_effect=self._fake_git(responses)),
            patch.object(
                archives, "_citation_release_tag", return_value=PAPER_TEST_TAG
            ),
        ):
            context = archives._build_context(PAPER_TEST_TAG)
        self.assertEqual(context["buildMode"], "clean-public-tag-release")
        self.assertTrue(context["remoteTagVerified"])
        self.assertEqual(
            context["releaseContour"],
            archives.HISTORICAL_PAPER_ARCHIVE_CONTOUR,
        )

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
            patch.object(
                archives, "_citation_release_tag", return_value=PAPER_TEST_TAG
            ),
            self.assertRaisesRegex(ValueError, "origin"),
        ):
            archives._build_context(PAPER_TEST_TAG)

    def test_release_documentation_separates_paper_and_portfolio_tags(self):
        publication = (ROOT / "publication/README.md").read_text(
            encoding="utf-8"
        )
        replication = (ROOT / "docs/INDEPENDENT_REPLICATION.md").read_text(
            encoding="utf-8"
        )
        release_process = (
            ROOT / "docs/development/RELEASE_PROCESS.md"
        ).read_text(encoding="utf-8")
        for document in (publication, replication, release_process):
            self.assertIn("voidtoken-v5-paper-vN", document)
            self.assertIn("corelm-portfolio-vN", document)
        self.assertIn("lightweight historical paper", publication)
        self.assertIn("SSH-signed annotated portfolio", publication)
        self.assertIn("historical `CITATION.cff` names the same paper tag", publication)
        self.assertIn("current default branch", publication)
        self.assertIn("differs from `CITATION.cff`", publication)
        self.assertIn("must not be passed to", replication)
        self.assertIn("SSH-signed annotated", release_process)
        self.assertIn("never pass a portfolio tag", release_process)
        self.assertIn("presentation-only C1", release_process)
        self.assertIn("signed linear C2", release_process)
        self.assertIn("new tagged regression proof", release_process)
        self.assertIn("canonical `TMPDIR`", release_process)

    def test_release_source_must_be_tracked(self):
        context = {
            "releaseTag": PAPER_TEST_TAG,
            "trackedFiles": set(),
        }
        with self.assertRaisesRegex(ValueError, "not tracked"):
            archives._assert_release_source(ROOT / "README.md", context)

    def test_reproducibility_archive_contains_v5_evidence_and_provenance(self):
        context = {
            "buildMode": "preview-working-tree",
            "builtFromCleanHead": False,
            "gitHeadCommit": "a" * 40,
            "gitHeadTree": "b" * 40,
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
                    f"{prefix}/SOURCE_ARCHIVE_PROVENANCE.json", names
                )
                archive_provenance_member = bundle.extractfile(
                    f"{prefix}/SOURCE_ARCHIVE_PROVENANCE.json"
                )
                self.assertIsNotNone(archive_provenance_member)
                archive_provenance_raw = archive_provenance_member.read()
                archive_provenance = json.loads(archive_provenance_raw)
                self.assertEqual(
                    archive_provenance_raw,
                    archives.canonical_json_bytes(archive_provenance),
                )
                self.assertEqual(
                    archive_provenance["schemaVersion"],
                    "corelm-source-archive-manifest-v1",
                )
                archived_source_paths = {
                    entry["path"] for entry in archive_provenance["files"]
                }
                self.assertIn(
                    "platforms/macos/scripts/package-app.sh",
                    archived_source_paths,
                )
                self.assertIn(
                    "RealLLM/legacy_voidtoken_adapter.py",
                    archived_source_paths,
                )
                self.assertIn(
                    "security/generate_build_provenance.py",
                    archived_source_paths,
                )
                self.assertIn(
                    "security/validate_python_bootstrap_archive.py",
                    archived_source_paths,
                )
                self.assertIn(
                    "security/proof_process_groups.sh",
                    archived_source_paths,
                )
                self.assertIn(
                    "security/run_process_group_tests.sh",
                    archived_source_paths,
                )
                self.assertIn("signing/allowed_signers", archived_source_paths)
                self.assertIn(
                    "signing/corelm-codec-signing.pub",
                    archived_source_paths,
                )
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
                    "corelm",
                    "platforms/README.md",
                    "platforms/beacon/README.md",
                    "platforms/beacon/scripts/verify-frozen-tag.py",
                    "platforms/macos/scripts/build-app.sh",
                    "platforms/macos/scripts/bootstrap-python.sh",
                    "platforms/macos/scripts/doctor.sh",
                    "platforms/macos/scripts/prepare-offline.sh",
                    "platforms/macos/scripts/find-proof-window.swift",
                    "platforms/macos/scripts/run-automated-portfolio-demo.py",
                    "platforms/macos/scripts/run-proof.sh",
                    "platforms/macos/BUILD_AND_VERIFY.md",
                    "platforms/linux/scripts/bootstrap-python.sh",
                    "platforms/linux/scripts/doctor.sh",
                    "platforms/linux/scripts/find-python312.sh",
                    "platforms/linux/scripts/build-runtime.sh",
                    "platforms/linux/scripts/runtime_safety.py",
                    "platforms/linux/scripts/run-regression.sh",
                    "platforms/linux/RECORDED_RUN_2026-08-01.md",
                    "scripts/verify-python.sh",
                    "requirements.lock",
                    "RealLLM/requirements.lock",
                    "RealLLM/prepare_app_assets.py",
                    "docs/README.md",
                    "docs/DEMO.md",
                    "docs/ENGINEERING_CASE_STUDY.md",
                    "docs/INDEPENDENT_REPLICATION.md",
                    "docs/PORTFOLIO_READINESS.md",
                    "docs/RESULTS.md",
                    "docs/LIMITATIONS.md",
                    "docs/independent-replication-attestation.template.json",
                    "docs/development/BEACON_V1_AUDIT_AND_V2.md",
                    "docs/development/HISTORY.md",
                    "docs/development/SCIENTIFIC_IDENTIFIERS.md",
                    "docs/development/RELEASE_PROCESS.md",
                    "SECURITY.md",
                    "platforms/macos/App/Sources/PrimaryEvidenceValidation.swift",
                    "platforms/macos/App/Sources/PythonRuntimeManifest.swift",
                    "platforms/macos/App/Sources/SecurityValidation.swift",
                    "platforms/macos/Tests/SecurityValidationTests.swift",
                    "Tests/test_platform_boundaries.py",
                    "Tests/test_automated_media.py",
                    "Tests/test_automated_portfolio_demo.py",
                    "Tests/test_automated_window_capture.py",
                    "Tests/test_strict_git_checkout.py",
                    "Tests/test_portfolio_demo_collector.py",
                    "Tests/test_portfolio_python_launcher.py",
                    "Tests/test_portfolio_release.py",
                    "Tests/test_portfolio_tag_ci.py",
                    "security/generate_python_runtime_manifest.py",
                    "security/generate_build_provenance.py",
                    "security/find_python312.sh",
                    "security/manage_local_runtime.py",
                    "security/proof_reports.py",
                    "security/automated_media.py",
                    "security/verify_git_checkout.py",
                    "security/verify_portfolio_tag_ci.py",
                    "security/validate_proof_challenge.sh",
                    "security/verify_app_run_evidence.py",
                    "security/verify_primary_evidence.py",
                    "security/verify_primary_replay.py",
                    "security/verify_local_app_run.py",
                    "security/verify_locked_environment.py",
                    "security/verify_supply_chain.py",
                    "security/verify_app_bundle.sh",
                    "publication/run_portfolio_python.sh",
                    "Tests/test_build_provenance.py",
                    "Tests/test_independent_replication.py",
                    "Tests/test_beacon_protocol.py",
                    "Tests/test_linux_runtime_hardening.py",
                    "Tests/test_swift_security_gate.py",
                    "Tests/fixtures/nist-beacon-certificate-528943a5.pem",
                    "Tests/fixtures/nist-beacon-chain-2-pulse-1884240.json",
                    "schemas/beacon-attempt.schema.json",
                    "schemas/beacon-freeze.schema.json",
                    "schemas/beacon-outcome.schema.json",
                    "schemas/beacon-registration.schema.json",
                    "schemas/beacon-resolution.schema.json",
                    "schemas/beacon-window-ledger.schema.json",
                    "schemas/portfolio-release-input.schema.json",
                    "schemas/portfolio-source-identity.schema.json",
                    "schemas/portfolio-demo-provenance.schema.json",
                    "schemas/portfolio-runtime-assets.schema.json",
                    "RealLLM/BEACON_HELDOUT_PROTOCOL.md",
                    "RealLLM/beacon_evaluation.py",
                    "RealLLM/beacon_protocol.py",
                    "RealLLM/beacon_registration.json",
                    "RealLLM/beacon_window_ledger.json",
                    "RealLLM/prepare_beacon_assets.py",
                    "RealLLM/prepare_beacon_freeze.py",
                    "RealLLM/run_beacon_one_shot.py",
                    "RealLLM/run_beacon_regression.py",
                    "RealLLM/verify_beacon_evidence.py",
                    "real-llm-beacon-results/README.md",
                    "app-real-llm-evidence/README.md",
                    "app-real-llm-evidence/SHA256SUMS",
                    "app-real-llm-evidence/app-run-receipt.json",
                    "app-real-llm-evidence/validation-064-071.json",
                    "publication/arxiv-v5/submission_metadata.md",
                    "signing/allowed_signers",
                    "signing/corelm-codec-signing.pub",
                    "tools/independent_replication.py",
                    "publication/build_portfolio_release.py",
                    "publication/collect_portfolio_demo.py",
                    "RealLLM/pinned_assets.py",
                    "publication/PORTFOLIO_RELEASE.md",
                ):
                    self.assertIn(f"{prefix}/{relative}", names)
                for relative in archives.V5_ARXIV_SOURCE_FILES:
                    self.assertIn(
                        f"{prefix}/publication/arxiv-v5/{relative}",
                        names,
                    )

    def test_reproducibility_archive_can_run_normal_test_gate(self):
        context = {
            "buildMode": "preview-working-tree",
            "builtFromCleanHead": False,
            "gitHeadCommit": "a" * 40,
            "gitHeadTree": "b" * 40,
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
            completed = subprocess.run(
                [
                    "/bin/sh",
                    str(extracted / "scripts/verify-python.sh"),
                ],
                cwd=extracted,
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHON_BIN": sys.executable},
                timeout=180,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=completed.stdout + completed.stderr,
            )

    def test_post_freeze_reproducibility_archive_includes_freeze_manifest(self):
        context = {
            "buildMode": "preview-working-tree",
            "builtFromCleanHead": False,
            "gitHeadCommit": "a" * 40,
            "gitHeadTree": "b" * 40,
            "releaseTag": None,
            "remoteTagVerified": False,
            "trackedFiles": set(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_freeze = root / "beacon_freeze.json"
            frozen_bytes = b'{"schemaVersion":"corelm-beacon-freeze-v1"}\n'
            fake_freeze.write_bytes(frozen_bytes)
            with patch.object(archives, "BEACON_FREEZE_PATH", fake_freeze):
                archive = archives.build_reproducibility(root, context)
            with tarfile.open(archive, "r:gz") as bundle:
                member = bundle.extractfile(
                    "corelm_reproducibility/RealLLM/beacon_freeze.json"
                )
                self.assertIsNotNone(member)
                self.assertEqual(member.read(), frozen_bytes)

    def test_clean_reproducibility_archive_is_accepted_without_git(self):
        context = {
            "buildMode": "preview-working-tree",
            "builtFromCleanHead": True,
            "gitHeadCommit": "a" * 40,
            "gitHeadTree": "b" * 40,
            "releaseTag": None,
            "remoteTagVerified": False,
            "trackedFiles": set(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            validation_result = archives._v5_evidence_state()
            with patch.object(
                archives,
                "_validate_v5_evidence",
                return_value=validation_result,
            ):
                archive = archives.build_reproducibility(root, context)
            extracted_root = root / "extracted"
            extracted_root.mkdir()
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(extracted_root, filter="data")
            extracted = extracted_root / "corelm_reproducibility"
            self.assertFalse((extracted / ".git").exists())
            source = build_provenance.inspect_source_archive(
                extracted,
                extracted / build_provenance.DEFAULT_ARCHIVE_MANIFEST,
            )
            self.assertEqual(source["mode"], "archive")
            self.assertFalse(source["dirty"])
            self.assertEqual(source["commit"], "a" * 40)
            self.assertEqual(source["tree"], "b" * 40)

    def test_v5_arxiv_archive_contains_only_current_submission_sources(self):
        context = {
            "buildMode": "preview-working-tree",
            "builtFromCleanHead": False,
            "gitHeadCommit": "a" * 40,
            "gitHeadTree": "b" * 40,
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
