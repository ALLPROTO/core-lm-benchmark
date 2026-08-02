import ast
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from security.audit_beacon_evidence_ref import (
    ATTEMPT_PATH,
    AUDIT_DISTRIBUTIONS,
    AuditFailure,
    EVIDENCE_TAG,
    FROZEN_RELEASE_API,
    FREEZE_COMMIT,
    FROZEN_TAG_API,
    OUTCOME_PATH,
    PRIMARY_MANIFEST_PATH,
    RELEASE_BODY,
    RELEASE_TITLE,
    RELEASE_URL,
    RESULT_DIRECTORY,
    TOKEN_METRICS_PATH,
    VerifierResult,
    _bounded_regular_bytes,
    _fetch_public_github_object,
    _run_verifier_process,
    _verifier_environment,
    apply_artifact_set_classification,
    classification_exit_code,
    classify_artifacts,
    is_allowed_runner_artifact_path,
    main,
    minimal_audit_lock,
    parse_ls_tree_z,
    parse_name_status_z,
    validate_added_artifact_changes,
    validate_added_blob_entries,
    validate_release_metadata,
    validate_latest_release_metadata,
    verify_frozen_audit_files,
    verify_local_topology,
    verify_terminal_artifact_set,
    verifier_network_guard_source,
)


ROOT = Path(__file__).resolve().parents[1]


class BeaconPublicationAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name)
        (self.repository / ATTEMPT_PATH.parent).mkdir(parents=True)

    def tearDown(self):
        self.temporary.cleanup()

    def _write_json(self, relative: Path, value: object) -> None:
        path = self.repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def _container_paths(start: int) -> list[str]:
        return [
            (
                RESULT_DIRECTORY
                / "primary-evidence/containers"
                / f"block-{block:03d}"
                / f"layer-{layer:02d}.vtl5"
            ).as_posix()
            for block in range(start, start + 32)
            for layer in range(24)
        ]

    @staticmethod
    def _pass(_repository: Path) -> VerifierResult:
        return VerifierResult(0, stdout="verified")

    @staticmethod
    def _fail(_repository: Path) -> VerifierResult:
        return VerifierResult(1, stderr="frozen verifier rejected evidence")

    def test_minimal_lock_is_only_the_frozen_verifier_closure(self):
        source = (ROOT / "RealLLM/requirements.lock").read_text(encoding="utf-8")
        lock = minimal_audit_lock(source)
        for name, version in AUDIT_DISTRIBUTIONS.items():
            self.assertIn(f"{name}=={version}", lock)
        self.assertEqual(lock.count("=="), len(AUDIT_DISTRIBUTIONS))
        self.assertIn("--hash=sha256:", lock)
        for forbidden in (
            "huggingface-hub==",
            "pyarrow==",
            "safetensors==",
            "tokenizers==",
            "torch==",
            "transformers==",
        ):
            self.assertNotIn(forbidden, lock)
        with self.assertRaises(ValueError):
            minimal_audit_lock(source.replace("attrs==26.1.0", "attrs==0.0.0"))
        with self.assertRaises(ValueError):
            minimal_audit_lock("attrs==26.1.0 \\\n    # missing hash\n")

    def test_bounded_reads_reject_symlinks_and_oversize_files(self):
        target = self.repository / "target.lock"
        target.write_bytes(b"ab")
        link = self.repository / "link.lock"
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            _bounded_regular_bytes(link, 8, label="symlink lock")
        with self.assertRaises(ValueError):
            _bounded_regular_bytes(target, 1, label="oversize lock")

    def test_network_and_subprocess_environments_are_fail_closed(self):
        with self.assertRaises(ValueError):
            _fetch_public_github_object(
                "https://beacon.nist.gov/", label="forbidden endpoint"
            )
        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "must-not-propagate", "HF_HOME": "/untrusted"},
        ):
            environment = _verifier_environment()
        self.assertNotIn("GITHUB_TOKEN", environment)
        self.assertNotIn("HF_HOME", environment)
        self.assertEqual(
            environment["PATH"], "/usr/bin:/bin:/usr/sbin:/sbin"
        )

    def test_frozen_verifier_uses_offline_allowlisted_responses(self):
        resources = {
            FROZEN_RELEASE_API: b'{"release":true}',
            FROZEN_TAG_API: b'{"tag":true}',
        }
        source = verifier_network_guard_source(resources) + f"""
import socket
import urllib.request
observed = urllib.request.urlopen({FROZEN_RELEASE_API!r}).read()
assert observed == {resources[FROZEN_RELEASE_API]!r}
for target in ('https://beacon.nist.gov/', 'https://example.com/'):
    try:
        urllib.request.urlopen(target)
    except RuntimeError:
        pass
    else:
        raise AssertionError('non-allowlisted URL was accepted')
try:
    socket.create_connection(('beacon.nist.gov', 443))
except RuntimeError:
    pass
else:
    raise AssertionError('outbound socket was accepted')
"""
        result = _run_verifier_process(
            self.repository, ["-c", source], timeout=10
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("beacon.nist.gov", repr(resources))

    def test_frozen_preinstall_files_match_the_registered_digests(self):
        verified = verify_frozen_audit_files(ROOT)
        self.assertEqual(
            set(verified),
            {
                "RealLLM/requirements.lock",
                ".github/locks/pip-bootstrap.txt",
                "security/verify_locked_environment.py",
                "RealLLM/verify_beacon_evidence.py",
                "RealLLM/beacon_protocol.py",
            },
        )

    def test_pinned_verifier_call_graph_cannot_start_the_experiment(self):
        source = (ROOT / "RealLLM/verify_beacon_evidence.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertTrue(
            {
                "fetch_nist_pulse",
                "build_resolution",
                "select_window",
                "run_registered_beacon",
                "run_registered_pilot",
            }.isdisjoint(called_names)
        )
        self.assertIn("verify_resolution", called_names)

    def test_topology_accepts_only_added_runner_artifact_paths(self):
        container = (
            "real-llm-beacon-results/primary-evidence/containers/"
            "block-016/layer-00.vtl5"
        )
        raw = f"A\0{ATTEMPT_PATH.as_posix()}\0A\0{container}\0"
        changes = parse_name_status_z(raw)
        self.assertEqual(
            validate_added_artifact_changes(changes),
            [ATTEMPT_PATH.as_posix(), container],
        )
        self.assertTrue(is_allowed_runner_artifact_path(container))
        for status in ("M", "D", "T", "R100"):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    validate_added_artifact_changes(
                        [(status, ATTEMPT_PATH.as_posix())]
                    )
        for path in (
            "real-llm-beacon-results/README.md",
            "real-llm-beacon-results/regressions/retry.json",
            "real-llm-beacon-results/arbitrary.bin",
            "real-llm-beacon-results/primary-evidence/containers/"
            "block-000/layer-00.vtl5",
            "real-llm-beacon-results/primary-evidence/containers/"
            "block-016/layer-24.vtl5",
        ):
            with self.subTest(path=path):
                self.assertFalse(is_allowed_runner_artifact_path(path))
                with self.assertRaises(ValueError):
                    validate_added_artifact_changes([("A", path)])
        for malformed in ("A\0path", "A\0path\0M\0"):
            with self.subTest(raw=malformed):
                with self.assertRaises(ValueError):
                    parse_name_status_z(malformed)

    def test_topology_reads_name_status_and_rejects_non_additions(self):
        head = "1" * 40

        def run(change: str, *, remote_head: str = head):
            def fake_git(_repository: Path, *arguments: str) -> str:
                if arguments[0] == "status":
                    return ""
                if arguments == ("rev-parse", "HEAD"):
                    return head
                if arguments[0] == "cat-file":
                    return "commit"
                if arguments[0] == "rev-parse":
                    return head
                if arguments[0] == "rev-list":
                    return f"{head} {FREEZE_COMMIT}"
                if arguments[0] == "diff-tree":
                    self.assertIn("--name-status", arguments)
                    self.assertIn("--no-renames", arguments)
                    self.assertIn("-z", arguments)
                    return change
                if arguments[0] == "ls-tree":
                    return (
                        "100644 blob "
                        + "2" * 40
                        + f"\t{ATTEMPT_PATH.as_posix()}\0"
                    )
                if arguments[:2] == ("remote", "get-url"):
                    return "https://github.com/ALLPROTO/core-lm-benchmark"
                if arguments[0] == "ls-remote":
                    return f"{remote_head}\trefs/tags/{EVIDENCE_TAG}"
                self.fail(f"unexpected Git invocation: {arguments}")

            with patch(
                "security.audit_beacon_evidence_ref._git",
                side_effect=fake_git,
            ):
                return verify_local_topology(self.repository)

        added = f"A\0{ATTEMPT_PATH.as_posix()}\0"
        self.assertEqual(run(added)["addedPaths"], [ATTEMPT_PATH.as_posix()])
        modified = f"M\0{ATTEMPT_PATH.as_posix()}\0"
        with self.assertRaises(ValueError):
            run(modified)
        with self.assertRaises(ValueError):
            run(added, remote_head="3" * 40)

    def test_added_artifacts_must_be_regular_non_executable_git_blobs(self):
        path = ATTEMPT_PATH.as_posix()
        valid = f"100644 blob {'2' * 40}\t{path}\0"
        validate_added_blob_entries([path], parse_ls_tree_z(valid))
        for mode, object_type in (
            ("120000", "blob"),
            ("100755", "blob"),
            ("160000", "commit"),
        ):
            with self.subTest(mode=mode, object_type=object_type):
                raw = f"{mode} {object_type} {'2' * 40}\t{path}\0"
                with self.assertRaises(ValueError):
                    validate_added_blob_entries([path], parse_ls_tree_z(raw))
        with self.assertRaises(ValueError):
            validate_added_blob_entries([path], {})

    def test_scientific_terminal_set_is_exactly_manifest_declared(self):
        start = 16
        self._write_json(
            RESULT_DIRECTORY / "resolution.json",
            {"selection": {"selectedWindow": {"startBlock": start}}},
        )
        containers = self._container_paths(start)
        entries = []
        for path in containers:
            parts = path.split("/")
            entries.append(
                {
                    "blockIndex": int(parts[-2].removeprefix("block-")),
                    "layerIndex": int(
                        parts[-1].removeprefix("layer-").removesuffix(".vtl5")
                    ),
                    "path": path.removeprefix(
                        RESULT_DIRECTORY.as_posix() + "/"
                    ),
                    "bytes": 1,
                    "sha256": "0" * 64,
                }
            )
        self._write_json(
            PRIMARY_MANIFEST_PATH,
            {
                "schemaVersion": "corelm-real-llm-primary-evidence-v1",
                "resultFile": "outcome.json",
                "containers": entries,
                "tokenMetrics": {
                    "path": "primary-evidence/token-metrics.json",
                    "bytes": 1,
                    "sha256": "0" * 64,
                    "blocks": 32,
                    "predictionTokens": 4096,
                },
            },
        )
        added = [
            ATTEMPT_PATH.as_posix(),
            (RESULT_DIRECTORY / "resolution.json").as_posix(),
            OUTCOME_PATH.as_posix(),
            PRIMARY_MANIFEST_PATH.as_posix(),
            TOKEN_METRICS_PATH.as_posix(),
            *containers,
        ]
        verify_terminal_artifact_set(self.repository, added, "PASS")
        extra = (
            "real-llm-beacon-results/primary-evidence/containers/"
            "block-048/layer-00.vtl5"
        )
        self.assertTrue(is_allowed_runner_artifact_path(extra))
        for changed in (added + [extra], added[:-1]):
            with self.subTest(count=len(changed)):
                with self.assertRaises(ValueError):
                    verify_terminal_artifact_set(
                        self.repository, changed, "PASS"
                    )

    def test_failure_terminal_allows_only_a_writer_order_partial_prefix(self):
        self._write_json(
            RESULT_DIRECTORY / "resolution.json",
            {"selection": {"selectedWindow": {"startBlock": 16}}},
        )
        containers = self._container_paths(16)
        base = [
            ATTEMPT_PATH.as_posix(),
            (RESULT_DIRECTORY / "resolution.json").as_posix(),
            OUTCOME_PATH.as_posix(),
        ]
        verify_terminal_artifact_set(
            self.repository, base + containers[:2], "FAIL_EXECUTION"
        )
        with self.assertRaises(ValueError):
            verify_terminal_artifact_set(
                self.repository,
                base + [containers[0], containers[2]],
                "FAIL_EXECUTION",
            )

    def test_top_level_audit_failure_reports_consumption_as_unknown(self):
        output = io.StringIO()
        with patch(
            "security.audit_beacon_evidence_ref.audit_repository",
            side_effect=AuditFailure("topology changed"),
        ), contextlib.redirect_stdout(output):
            exit_code = main(["audit", "--repository", str(self.repository)])
        self.assertEqual(exit_code, 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["classification"], "AUDIT_FAILURE")
        self.assertIsNone(result["evidenceConsumed"])

    def test_no_attempt_is_a_non_consuming_preflight_rejection(self):
        result = classify_artifacts(
            self.repository,
            verify_attempt=self._pass,
            verify_outcome=self._pass,
        )
        self.assertEqual(result["classification"], "NOT_STARTED_PREFLIGHT_REJECTION")
        self.assertFalse(result["evidenceConsumed"])
        self.assertEqual(classification_exit_code(result["classification"]), 1)

    def test_outcome_without_attempt_is_consumed_invalid_evidence(self):
        self._write_json(OUTCOME_PATH, {"verdict": "PASS"})
        result = classify_artifacts(
            self.repository,
            verify_attempt=self._pass,
            verify_outcome=self._pass,
        )
        self.assertEqual(result["classification"], "CONSUMED_INVALID_EVIDENCE")
        self.assertTrue(result["evidenceConsumed"])
        self.assertEqual(classification_exit_code(result["classification"]), 2)

    def test_verified_attempt_without_outcome_is_consumed_incomplete(self):
        self._write_json(ATTEMPT_PATH, {"marker": True})
        result = classify_artifacts(
            self.repository,
            verify_attempt=self._pass,
            verify_outcome=self._fail,
        )
        self.assertEqual(result["classification"], "CONSUMED_INCOMPLETE")
        self.assertEqual(result["attemptVerifierExitCode"], 0)
        self.assertIsNone(result["verifierExitCode"])
        self.assertEqual(classification_exit_code(result["classification"]), 2)

    def test_invalid_attempt_or_attempt_verifier_is_consumed(self):
        (self.repository / ATTEMPT_PATH).write_text("not-json", encoding="utf-8")
        malformed = classify_artifacts(
            self.repository,
            verify_attempt=self._pass,
            verify_outcome=self._pass,
        )
        self.assertEqual(malformed["classification"], "CONSUMED_INVALID_EVIDENCE")

        self._write_json(ATTEMPT_PATH, {"marker": True})
        rejected = classify_artifacts(
            self.repository,
            verify_attempt=self._fail,
            verify_outcome=self._pass,
        )
        self.assertEqual(rejected["classification"], "CONSUMED_INVALID_EVIDENCE")
        self.assertEqual(rejected["attemptVerifierExitCode"], 1)

    def test_invalid_outcome_is_consumed_without_verifier_execution(self):
        self._write_json(ATTEMPT_PATH, {"marker": True})
        self._write_json(OUTCOME_PATH, {"verdict": "RUNNING"})

        def forbidden(_repository: Path) -> VerifierResult:
            self.fail("invalid artifacts must not invoke a verifier process")

        result = classify_artifacts(
            self.repository,
            verify_attempt=forbidden,
            verify_outcome=forbidden,
        )
        self.assertEqual(result["classification"], "CONSUMED_INVALID_EVIDENCE")
        self.assertTrue(result["evidenceConsumed"])

    def test_all_registered_terminal_outcomes_are_integrity_results(self):
        self._write_json(ATTEMPT_PATH, {"marker": True})
        for verdict in ("PASS", "FAIL_GATES", "FAIL_EXECUTION"):
            with self.subTest(verdict=verdict):
                self._write_json(OUTCOME_PATH, {"verdict": verdict})
                result = classify_artifacts(
                    self.repository,
                    verify_attempt=self._fail,
                    verify_outcome=self._pass,
                )
                self.assertEqual(result["classification"], verdict)
                self.assertEqual(result["scientificVerdict"], verdict)
                self.assertEqual(result["verifierExitCode"], 0)
                self.assertEqual(classification_exit_code(verdict), 0)
                self.assertFalse(result["modelLoadedByAudit"])
                self.assertFalse(result["nistNetworkFetchedByAudit"])
                self.assertFalse(result["newScientificAttemptPerformedByAudit"])

    def test_rejected_terminal_outcome_is_consumed_invalid_evidence(self):
        self._write_json(ATTEMPT_PATH, {"marker": True})
        self._write_json(OUTCOME_PATH, {"verdict": "PASS"})
        result = classify_artifacts(
            self.repository,
            verify_attempt=self._pass,
            verify_outcome=self._fail,
        )
        self.assertEqual(result["classification"], "CONSUMED_INVALID_EVIDENCE")
        self.assertEqual(result["claimedVerdict"], "PASS")
        self.assertIsNone(result["scientificVerdict"])
        self.assertEqual(classification_exit_code(result["classification"]), 2)

    def test_invalid_terminal_set_overrides_verifier_accepted_verdict(self):
        self._write_json(ATTEMPT_PATH, {"marker": True})
        self._write_json(OUTCOME_PATH, {"verdict": "PASS"})
        accepted = classify_artifacts(
            self.repository,
            verify_attempt=self._fail,
            verify_outcome=self._pass,
        )
        malformed = apply_artifact_set_classification(
            self.repository,
            [ATTEMPT_PATH.as_posix(), OUTCOME_PATH.as_posix()],
            accepted,
        )
        self.assertEqual(malformed["classification"], "CONSUMED_INVALID_EVIDENCE")
        self.assertEqual(malformed["claimedVerdict"], "PASS")
        self.assertTrue(malformed["evidenceConsumed"])
        self.assertIsNone(malformed["scientificVerdict"])
        self.assertEqual(classification_exit_code(malformed["classification"]), 2)

    def test_incomplete_primary_files_require_resolution_and_exact_prefix(self):
        self._write_json(ATTEMPT_PATH, {"marker": True})
        incomplete = classify_artifacts(
            self.repository,
            verify_attempt=self._pass,
            verify_outcome=self._fail,
        )
        container = self._container_paths(16)[0]
        rejected = apply_artifact_set_classification(
            self.repository,
            [ATTEMPT_PATH.as_posix(), container],
            incomplete,
        )
        self.assertEqual(rejected["classification"], "CONSUMED_INVALID_EVIDENCE")
        self.assertTrue(rejected["evidenceConsumed"])

        self._write_json(
            RESULT_DIRECTORY / "resolution.json",
            {"selection": {"selectedWindow": {"startBlock": 16}}},
        )
        accepted = apply_artifact_set_classification(
            self.repository,
            [
                ATTEMPT_PATH.as_posix(),
                (RESULT_DIRECTORY / "resolution.json").as_posix(),
                container,
            ],
            incomplete,
        )
        self.assertEqual(accepted["classification"], "CONSUMED_INCOMPLETE")

    def test_release_metadata_must_be_exact_and_immutable(self):
        self.assertIn("CONSUMED_INVALID_EVIDENCE", RELEASE_BODY)
        metadata = {
            "tag_name": EVIDENCE_TAG,
            "name": RELEASE_TITLE,
            "html_url": RELEASE_URL,
            "draft": False,
            "prerelease": False,
            "immutable": True,
            "body": RELEASE_BODY,
            "assets": [],
            "published_at": "2026-08-02T20:30:00Z",
        }
        self.assertTrue(validate_release_metadata(metadata)["immutable"])
        for key, value in (
            ("immutable", False),
            ("assets", [{"name": "mutable.zip"}]),
            ("body", "different disclosure"),
            ("body", RELEASE_BODY + "\n"),
            ("published_at", "2026-02-30T20:30:00Z"),
            ("published_at", "2026-08-02T20:30:00.000Z"),
        ):
            with self.subTest(key=key):
                changed = dict(metadata)
                changed[key] = value
                with self.assertRaises(ValueError):
                    validate_release_metadata(changed)

    def test_evidence_release_must_not_become_latest(self):
        self.assertEqual(
            validate_latest_release_metadata({"tag_name": "any-later-paper-v6"}),
            {"latestReleaseTag": "any-later-paper-v6"},
        )
        with self.assertRaises(ValueError):
            validate_latest_release_metadata({"tag_name": EVIDENCE_TAG})


if __name__ == "__main__":
    unittest.main()
