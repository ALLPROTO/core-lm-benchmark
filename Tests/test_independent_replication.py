import contextlib
import json
import io
import os
import py_compile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import independent_replication as replication


ROOT = Path(__file__).resolve().parents[1]


def attestation(profile: str = "https://github.com/external-reviewer"):
    return {
        "attestedAt": "2026-08-05T12:00:00Z",
        "declaration": replication.DECLARATION,
        "publicProfileURL": profile,
        "schemaVersion": replication.ATTESTATION_SCHEMA,
        "statements": {
            "differentIndependentlyControlledMachine": True,
            "freshPublicClone": True,
            "humanOperated": True,
            "notAIAgent": True,
            "notProjectAuthor": True,
            "reportedWithoutOutcomeSelection": True,
            "sourceUnmodifiedBeforeRun": True,
        },
    }


class IndependentReplicationTests(unittest.TestCase):
    def test_release_tag_must_be_annotated_signed_and_exact(self):
        tag_object = "a" * 40
        commit = "b" * 40
        tree = "c" * 40
        with mock.patch.object(
            replication,
            "_git",
            side_effect=[
                "",
                ".git",
                "tag",
                tag_object,
                commit,
                tree,
                f"object {commit}\ntype commit\ntag corelm-portfolio-v1\n"
                "tagger External Reviewer <reviewer@example.com> "
                "1785931200 +0000\n\ntag message\n"
                "-----BEGIN SSH SIGNATURE-----\n"
                "fixture\n-----END SSH SIGNATURE-----",
            ],
        ) as git, mock.patch.object(
            replication,
            "_git_process",
            return_value=mock.Mock(
                returncode=0,
                stdout="",
                stderr=(
                    "Good \"git\" signature for "
                    + replication.EXPECTED_SIGNING_PRINCIPAL
                ),
            ),
        ) as git_process, mock.patch.object(
            replication,
            "_remote_git",
            return_value=(
                f"{tag_object}\trefs/tags/corelm-portfolio-v1\n"
                f"{commit}\trefs/tags/corelm-portfolio-v1^{{}}"
            ),
        ) as remote_git:
            observed = replication._verify_release_tag(
                "corelm-portfolio-v1", commit, tree, tag_object
            )
        self.assertEqual(observed["releaseTagObject"], tag_object)
        self.assertEqual(
            observed["signatureVerification"],
            "SSH_ALLOWED_SIGNER_VERIFIED",
        )
        self.assertIn("verify-tag", git_process.call_args.args)
        self.assertIn("ls-remote", remote_git.call_args.args)
        with self.assertRaises(replication.ReplicationError):
            replication._verify_release_tag("--unsafe")
        with self.assertRaisesRegex(
            replication.ReplicationError, "canonical corelm-portfolio-vN"
        ):
            replication._source_identity("corelm-codec-source-2e8d3b-v1")

    def test_annotated_tag_embedded_name_and_object_are_exact(self):
        commit = "b" * 40
        valid = (
            f"object {commit}\ntype commit\ntag corelm-portfolio-v2\n"
            "tagger Reviewer <reviewer@example.com> 1785931200 +0000\n\n"
            "message\n-----BEGIN SSH SIGNATURE-----\nx\n"
            "-----END SSH SIGNATURE-----"
        )
        replication._parse_annotated_tag_header(
            valid, "corelm-portfolio-v2", commit
        )
        with self.assertRaisesRegex(
            replication.ReplicationError, "header identity"
        ):
            replication._parse_annotated_tag_header(
                valid.replace(
                    "tag corelm-portfolio-v2", "tag corelm-portfolio-v1"
                ),
                "corelm-portfolio-v2",
                commit,
            )

    def test_remote_git_is_detached_from_repo_and_all_git_config(self):
        completed = mock.Mock(returncode=0, stdout="ok\n", stderr="")
        with mock.patch.object(
            replication.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(replication._remote_git("ls-remote", "https://example"), "ok")
        _command = run.call_args.args[0]
        options = run.call_args.kwargs
        self.assertEqual(options["cwd"], "/")
        self.assertNotIn("-C", _command)
        self.assertEqual(options["env"]["GIT_CEILING_DIRECTORIES"], "/")
        self.assertEqual(options["env"]["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(options["env"]["GIT_CONFIG_SYSTEM"], "/dev/null")
        self.assertEqual(options["env"]["GIT_CONFIG_GLOBAL"], "/dev/null")
        self.assertEqual(options["env"]["GIT_CONFIG_COUNT"], "0")
        self.assertIn("protocol.file.allow=never", _command)

    def test_https_and_ssh_origins_canonicalize_without_url_rewrites(self):
        for value in (
            "https://github.com/ALLPROTO/core-lm-benchmark",
            "https://github.com/ALLPROTO/core-lm-benchmark.git",
            "git@github.com:ALLPROTO/core-lm-benchmark.git",
            "ssh://git@github.com/ALLPROTO/core-lm-benchmark.git",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    replication._canonicalize_origin(value),
                    replication.CANONICAL_REMOTE,
                )
        for value in (
            "https://github.com/ALLPROTO/core-lm-benchmark.git?token=secret",
            "https://evil.example/ALLPROTO/core-lm-benchmark.git",
            "git@github.com:ALLPROTO/core-lm-benchmark.git@evil.example",
        ):
            with self.subTest(value=value), self.assertRaises(
                replication.ReplicationError
            ):
                replication._canonicalize_origin(value)

    def test_every_execution_policy_file_must_be_a_tracked_regular_blob(self):
        entries = {
            relative: ("100644", "a" * 40)
            for relative in replication.CRITICAL_TRACKED_FILES
        }
        replication._require_critical_tracked_files(entries)
        missing = dict(entries)
        missing.pop("tools/independent_replication.py")
        with self.assertRaisesRegex(replication.ReplicationError, "not tracked"):
            replication._require_critical_tracked_files(missing)
        symlinked = dict(entries)
        symlinked["signing/allowed_signers"] = ("120000", "a" * 40)
        with self.assertRaisesRegex(replication.ReplicationError, "regular blob"):
            replication._require_critical_tracked_files(symlinked)

    def test_any_tracked_symlink_is_rejected_not_only_known_critical_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            (root / "unlisted-import.py").symlink_to("/tmp/outside.py")
            tree = mock.Mock(
                returncode=0,
                stdout=(
                    "120000 blob "
                    + "a" * 40
                    + "\tunlisted-import.py\0"
                ),
                stderr="",
            )
            with mock.patch.object(
                replication, "_git_at", return_value="sha1"
            ), mock.patch.object(
                replication, "_git_process_at", return_value=tree
            ), self.assertRaisesRegex(
                replication.ReplicationError, "regular blobs only"
            ):
                replication._verify_tracked_worktree(root)

    def test_human_attestation_is_declared_not_software_verified(self):
        observed = replication._validate_attestation(attestation())
        self.assertEqual(
            observed["publicProfileURL"],
            "https://github.com/external-reviewer",
        )
        for forbidden in (
            "https://github.com/ALLPROTO",
            "https://github.com/REPLACE-WITH-YOUR-ACCOUNT",
        ):
            with self.subTest(profile=forbidden):
                with self.assertRaises(replication.ReplicationError):
                    replication._validate_attestation(attestation(forbidden))
        false_statement = attestation()
        false_statement["statements"]["humanOperated"] = False
        with self.assertRaises(replication.ReplicationError):
            replication._validate_attestation(false_statement)

    def test_terminal_sanitizer_removes_local_identity_and_credentials(self):
        token = "gh" + "p_" + ("A" * 30)
        text = (
            f"repo={ROOT}\n"
            f"home={Path.home()}\n"
            f"user={replication.os.environ.get('USER', '')}\n"
            f"token={token}\n"
        )
        sanitized, replacements = replication._sanitize_text(text)
        self.assertGreaterEqual(replacements, 3)
        self.assertNotIn(str(ROOT), sanitized)
        self.assertNotIn(str(Path.home()), sanitized)
        self.assertNotIn(token, sanitized)
        self.assertIn("$REPOSITORY", sanitized)
        self.assertIn("[REDACTED_CREDENTIAL]", sanitized)
        replication._assert_public_bytes(sanitized.encode(), "test log")

    def test_endpoint_bearer_and_query_credentials_are_not_publishable(self):
        endpoint = "https://mirror.example/simple?channel=public"
        hf_endpoint = "https://hf-mirror.example"
        with mock.patch.dict(
            os.environ,
            {
                "CORELM_PYPI_INDEX_URL": endpoint,
                "CORELM_HF_ENDPOINT": hf_endpoint,
            },
        ):
            sanitized, _count = replication._sanitize_text(
                f"index={endpoint}\nhf={hf_endpoint}\n"
                "Authorization: Bearer abcdefghijklmnopqrstuvwxyz\n"
                "url=https://example.test/x?access_token=abcdefghijklmno\n"
            )
        self.assertNotIn(endpoint, sanitized)
        self.assertNotIn(hf_endpoint, sanitized)
        self.assertIn("$PYPI_ENDPOINT", sanitized)
        self.assertIn("$HF_ENDPOINT", sanitized)
        self.assertGreaterEqual(sanitized.count("[REDACTED_CREDENTIAL]"), 2)
        replication._assert_public_bytes(sanitized.encode(), "sanitized log")

    def test_public_bundle_rejects_private_paths_and_keys(self):
        with self.assertRaisesRegex(
            replication.ReplicationError, "private home path"
        ):
            replication._assert_public_bytes(
                b"/Users/private-person/project", "fixture"
            )
        marker = b"-----BEGIN " + b"RSA PRIVATE KEY-----"
        with self.assertRaisesRegex(
            replication.ReplicationError, "private key"
        ):
            replication._assert_public_bytes(marker, "fixture")
        with self.assertRaisesRegex(replication.ReplicationError, "private key"):
            replication._assert_public_bytes(
                b"-----BEGIN " + b"ENCRYPTED PRIVATE KEY-----", "fixture"
            )

    def test_binary_container_with_credential_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run"
            destination = root / "copy"
            (run / "primary-evidence/containers").mkdir(parents=True)
            for name in (
                "run-manifest.json",
                "validation-064-071.json",
                "pre-run-contract.json",
            ):
                (run / name).write_text("{}\n", encoding="utf-8")
            token = b"github_pat_" + b"A" * 35
            (run / "primary-evidence/containers/malicious.vtl5").write_bytes(
                b"VTL5\x00binary\x00" + token
            )
            with self.assertRaisesRegex(
                replication.ReplicationError, "credential-like"
            ):
                replication._copy_run_evidence("linux", run, destination)
            private_endpoint = "https://private-mirror.example/simple"
            (run / "primary-evidence/containers/malicious.vtl5").write_bytes(
                b"VTL5\x00" + private_endpoint.encode("utf-8")
            )
            with mock.patch.dict(
                os.environ, {"CORELM_PYPI_INDEX_URL": private_endpoint}
            ), self.assertRaisesRegex(
                replication.ReplicationError, "configured endpoint"
            ):
                replication._copy_run_evidence("linux", run, root / "copy-2")

    def test_ignored_valid_pyc_fails_before_any_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            cache = root / "tools/__pycache__"
            cache.mkdir(parents=True)
            source = root / "payload.py"
            source.write_text("raise RuntimeError('executed')\n", encoding="utf-8")
            compiled = cache / "payload.cpython-312.pyc"
            py_compile.compile(str(source), cfile=str(compiled), doraise=True)
            source.unlink()
            with mock.patch.object(
                replication, "_verify_tracked_worktree", return_value={}
            ), mock.patch.object(
                replication, "_require_critical_tracked_files"
            ), mock.patch.object(replication.subprocess, "Popen") as popen:
                with self.assertRaisesRegex(
                    replication.ReplicationError, "__pycache__"
                ):
                    replication._verify_exact_checkout(root)
            popen.assert_not_called()

    def test_post_run_topology_allows_only_declared_generated_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            app = root / "dist/CoreLMBenchmark.app/Contents/MacOS/App"
            app.parent.mkdir(parents=True)
            app.write_bytes(b"generated app")
            app.chmod(0o700)
            replication._reject_untracked_artifacts(
                root, {}, allowed_generated_prefixes=("dist",)
            )
            generated_file_symlink = root / "dist/generated-file-symlink"
            generated_file_symlink.symlink_to("/dev/null")
            with self.assertRaisesRegex(replication.ReplicationError, "symlink"):
                replication._reject_untracked_artifacts(
                    root, {}, allowed_generated_prefixes=("dist",)
                )
            generated_file_symlink.unlink()
            generated_directory_symlink = root / "dist/generated-directory-symlink"
            generated_directory_symlink.symlink_to("/tmp", target_is_directory=True)
            with self.assertRaisesRegex(replication.ReplicationError, "symlink"):
                replication._reject_untracked_artifacts(
                    root, {}, allowed_generated_prefixes=("dist",)
                )
            generated_directory_symlink.unlink()
            cache = root / "security/__pycache__/inject.cpython-312.pyc"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"malicious")
            with self.assertRaisesRegex(
                replication.ReplicationError, "__pycache__"
            ):
                replication._reject_untracked_artifacts(
                    root, {}, allowed_generated_prefixes=("dist",)
                )

    def test_inode_ctime_seal_detects_modify_execute_restore_attack(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tracked = root / "runner.py"
            original = b"print('signed')\n"
            tracked.write_bytes(original)
            entries = {"runner.py": ("100644", "a" * 40)}
            sealed = replication._worktree_seal(root, entries)
            tracked.write_bytes(b"print('malicious')\n")
            tracked.write_bytes(original)
            self.assertEqual(tracked.read_bytes(), original)
            with self.assertRaisesRegex(
                replication.ReplicationError, "inode/ctime seal"
            ):
                replication._assert_worktree_seal(root, entries, sealed)

    def test_execution_uses_fresh_exact_canonical_tag_clone(self):
        source = {
            "commit": "1" * 40,
            "tree": "2" * 40,
            "origin": replication.CANONICAL_REMOTE,
            "releaseTag": "corelm-portfolio-v3",
            "releaseTagObject": "3" * 40,
        }
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            replication.subprocess,
            "run",
            return_value=mock.Mock(returncode=0, stdout="", stderr=""),
        ) as run, mock.patch.object(
            replication,
            "_git_at",
            side_effect=[
                source["commit"],
                source["tree"],
                source["releaseTagObject"],
                replication.CANONICAL_REMOTE,
                "",
            ],
        ), mock.patch.object(replication, "_verify_exact_checkout") as exact:
            checkout = replication._fresh_execution_checkout(
                source, Path(temporary)
            )
        command = run.call_args.args[0]
        self.assertEqual(run.call_args.kwargs["cwd"], "/")
        self.assertIn("clone", command)
        self.assertIn("--no-local", command)
        self.assertIn(source["releaseTag"], command)
        self.assertIn(replication.CANONICAL_REMOTE, command)
        exact.assert_called_once_with(checkout)

    def test_macos_post_receipt_failure_and_missing_replay_are_fatal(self):
        receipt = {
            "error": None,
            "result": {
                "metricVerdict": "FAIL",
                "swiftStructuralVerification": "PASS",
            },
        }
        marker = "END-TO-END PROOF VERIFIED — METRIC FAIL: complete"
        with self.assertRaisesRegex(replication.ReplicationError, "exited with 7"):
            replication._macos_completed_outcome(7, receipt, marker)
        with self.assertRaisesRegex(replication.ReplicationError, "heavy-replay"):
            replication._macos_completed_outcome(
                0, receipt, "receipt exists but app-identity replay failed"
            )
        self.assertEqual(
            replication._macos_completed_outcome(0, receipt, marker),
            "METRIC_FAIL_PRESERVED",
        )

    def test_portable_macos_path_invokes_full_existing_receipt_verifier(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = root / "validation-064-071.json"
            receipt = root / "app-run-receipt.json"
            result.write_text("{}\n", encoding="utf-8")
            receipt.write_text("{}\n", encoding="utf-8")
            completed = mock.Mock(
                returncode=0,
                stdout=(
                    "PORTABLE MACOS RECEIPT/APPLICATION/WORKER/PROVENANCE PASS\n"
                ),
            )
            with mock.patch.object(
                replication.subprocess, "run", return_value=completed
            ) as run:
                replication._run_portable_macos_verifier(
                    result, receipt, "a" * 64
                )
        command = run.call_args.args[0]
        self.assertEqual(run.call_args.kwargs["cwd"], "/")
        self.assertIn("_verify_result_and_receipt", command[4])
        self.assertIn("portable_macos_environment=True", command[4])
        self.assertIn("require_metric_pass=False", command[4])

    def test_log_overflow_terminates_and_reaps_the_process(self):
        class FakeProcess:
            def __init__(self):
                self.stdout = io.StringIO("too many bytes\n")
                self.pid = 424242
                self.waits = []

            def wait(self, timeout=None):
                self.waits.append(timeout)
                return 143

        process = FakeProcess()
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            replication.subprocess, "Popen", return_value=process
        ), mock.patch.object(replication.os, "killpg") as killpg, mock.patch.object(
            replication, "MAX_PUBLIC_FILE_BYTES", 1
        ):
            with self.assertRaisesRegex(
                replication.ReplicationError, "terminal log exceeded"
            ):
                replication._capture(
                    ("./corelm", "linux", "run"),
                    {},
                    Path(temporary) / "terminal.log",
                )
        killpg.assert_called_once_with(424242, replication.signal.SIGTERM)
        self.assertIn(15, process.waits)

    def test_linux_metric_fail_bundle_is_explicit_and_integrity_verifies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "unit-fixture-run"
            bundle = root / "bundle"
            run.mkdir()
            bundle.mkdir()
            source = {
                "commit": "1" * 40,
                "tree": "2" * 40,
                "origin": "https://github.com/ALLPROTO/core-lm-benchmark.git",
                "cleanBeforeRun": True,
                "releaseTag": "corelm-portfolio-v1",
                "releaseTagObject": "4" * 40,
                "signingPolicySHA256": replication._sha256(
                    ROOT / "signing/allowed_signers"
                ),
                "signingPublicKeySHA256": replication._sha256(
                    ROOT / "signing/corelm-codec-signing.pub"
                ),
                "signatureVerification": "SSH_ALLOWED_SIGNER_VERIFIED",
            }
            canonical_result = "3" * 64
            result = {
                "fixtureOnly": True,
                "resultSHA256": canonical_result,
                "selectedTokenIdsSHA256": "5" * 64,
                "aggregates": [
                    {
                        "pass": False,
                        "compressionRatioVsBF16": 2.0,
                        "deltaNLLNatPerToken": 0.0,
                        "top1Agreement": 1.0,
                    }
                ],
            }
            result_path = run / "validation-064-071.json"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            receipt = {
                "schemaVersion": "corelm-real-qwen-linux-regression-run-v1",
                "evidenceClass": "regression-only",
                "countsTowardScientificVerdict": False,
                "modelExecuted": True,
                "testDataOpened": False,
                "beaconExecuted": False,
                "sourceCommit": source["commit"],
                "resultSHA256": canonical_result,
                "selectedTokenIdsSHA256": "5" * 64,
                "containerCount": 192,
                "predictionTokens": 1024,
                "compressionRatioVsBF16": 2.0,
                "deltaNLLNatPerToken": 0.0,
                "top1Agreement": 1.0,
                "metricVerdict": "FAIL",
            }
            (run / "run-manifest.json").write_text(
                json.dumps(receipt), encoding="utf-8"
            )
            (run / "pre-run-contract.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "corelm-real-qwen-linux-regression-contract-v1",
                        "evidenceClass": "regression-only",
                        "countsTowardScientificVerdict": False,
                        "dataClass": "real-public-validation",
                        "modelExecutionRequested": True,
                        "modelRepository": "Qwen/Qwen2.5-0.5B",
                        "modelRevision": "060db6499f32faf8b98477b0a26969ef7d8b9987",
                        "datasetRepository": "Salesforce/wikitext",
                        "datasetSplit": "validation",
                        "validationStartBlock": 64,
                        "validationBlocks": 8,
                        "candidateIndex": 32,
                        "device": "cpu",
                        "testDataAccessAllowed": False,
                        "beaconExecutionAllowed": False,
                        "sourceCommit": source["commit"],
                        "sourceTree": source["tree"],
                    }
                ),
                encoding="utf-8",
            )
            (run / "primary-evidence").mkdir()
            containers = run / "primary-evidence" / "containers"
            containers.mkdir()
            for index in range(193):
                (containers / f"unit-{index:03d}.vtl5").write_bytes(
                    b"unit fixture only"
                )
            attestation_path = root / "attestation.json"
            attestation_path.write_bytes(
                replication._canonical_json(attestation())
            )
            terminal = root / "terminal.log"
            terminal.write_text(
                "unit fixture: supported command completed\n", encoding="utf-8"
            )
            environment = {
                "schemaVersion": replication.ENVIRONMENT_SCHEMA,
                "system": "Linux",
                "osRelease": "unit-fixture",
                "architecture": "x86_64",
                "pythonVersion": "3.12.13",
                "cpuCount": 1,
                "memoryBytes": 1,
                "tools": {"git": "git version unit-fixture", "swift": None},
                "privacy": {
                    "hostnameCollected": False,
                    "localUsernameCollected": False,
                    "environmentDumped": False,
                },
            }
            replication._assemble_bundle(
                bundle,
                "linux",
                source,
                environment,
                attestation_path,
                run,
                terminal,
                "PRIMARY EVIDENCE PASS: unit fixture only.\n",
                None,
                "2026-08-05T12:00:00Z",
                "2026-08-05T12:01:00Z",
                0,
            )
            self.assertGreater(
                (bundle / "SHA256SUMS").stat().st_size,
                4096,
            )
            verified = subprocess_result = mock.Mock(
                returncode=0,
                stdout="PRIMARY EVIDENCE PASS: unit fixture only.\n",
            )
            with mock.patch.object(
                replication, "_verify_release_tag", return_value={}
            ), mock.patch.object(
                replication, "_verify_checkout_matches_source"
            ), mock.patch.object(
                replication.subprocess, "run", return_value=subprocess_result
            ) as raw_verifier:
                observed = replication.verify_bundle(bundle)
            self.assertEqual(
                Path(raw_verifier.call_args.args[0][-1]),
                (bundle / "run-evidence").resolve(),
            )
            self.assertFalse(observed["countsTowardScientificVerdict"])
            self.assertEqual(observed["metricVerdict"], "FAIL")
            self.assertEqual(
                observed["humanAttestation"]["softwareAssessment"],
                "DECLARED_ONLY_NOT_VERIFIED_BY_SOFTWARE",
            )

            container = next((bundle / "run-evidence").rglob("*.vtl5"))
            original_container = container.read_bytes()
            container.write_bytes(original_container + b"tampered")
            replication._write_checksums(bundle)
            with mock.patch.object(
                replication, "_verify_release_tag", return_value={}
            ), mock.patch.object(
                replication, "_verify_checkout_matches_source"
            ), mock.patch.object(
                replication.subprocess, "run", return_value=verified
            ), self.assertRaisesRegex(
                replication.ReplicationError, "raw evidence differs"
            ):
                replication.verify_bundle(bundle)
            container.write_bytes(original_container)
            replication._write_checksums(bundle)

            document_path = bundle / "replication.json"
            document = json.loads(document_path.read_text())
            document["claimBoundary"]["humanIdentity"] = "PASS"
            document_path.write_bytes(replication._canonical_json(document))
            replication._write_checksums(bundle)
            with mock.patch.object(
                replication, "_verify_release_tag", return_value={}
            ), mock.patch.object(
                replication, "_verify_checkout_matches_source"
            ), mock.patch.object(
                replication.subprocess, "run", return_value=verified
            ), self.assertRaisesRegex(
                replication.ReplicationError, "claim boundary"
            ):
                replication.verify_bundle(bundle)

    def test_cli_never_headlines_integrity_as_metric_pass(self):
        arguments = mock.Mock(operation="verify", bundle=Path("fixture"))
        document = {"metricVerdict": "FAIL", "source": {"commit": "1" * 40}}
        output = io.StringIO()
        with mock.patch.object(
            replication, "_arguments", return_value=arguments
        ), mock.patch.object(
            replication, "verify_bundle", return_value=document
        ), contextlib.redirect_stdout(output):
            self.assertEqual(replication.main(), 0)
        rendered = output.getvalue()
        self.assertIn("INTEGRITY PASS; METRIC VERDICT FAIL", rendered)
        self.assertIn("Integrity PASS is not metric PASS", rendered)

    def test_documentation_keeps_g10_open_until_public_human_review(self):
        documentation = (ROOT / "docs/INDEPENDENT_REPLICATION.md").read_text(
            encoding="utf-8"
        )
        for required in (
            "DECLARED_ONLY_NOT_VERIFIED_BY_SOFTWARE",
            "does **not** close G10",
            "G10 is complete only after",
            "blind/generalization result",
            "tools/independent_replication.py record",
            "tools/independent_replication.py verify",
        ):
            self.assertIn(required, documentation)
        self.assertNotIn(str(Path.home()), documentation)


if __name__ == "__main__":
    unittest.main()
