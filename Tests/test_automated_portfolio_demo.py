import ast
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "platforms"
    / "macos"
    / "scripts"
    / "run-automated-portfolio-demo.py"
)
SPEC = importlib.util.spec_from_file_location("corelm_automated_demo", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
demo = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = demo
SPEC.loader.exec_module(demo)


class FakeProcess:
    def __init__(self, pid=4242, returncode=0):
        self.pid = pid
        self.returncode = returncode
        self.wait_calls = 0

    def wait(self, timeout=None):
        self.wait_calls += 1
        return self.returncode

    def poll(self):
        return self.returncode if self.wait_calls else None


class AutomatedPortfolioDemoTests(unittest.TestCase):
    def _preflight_segment(self):
        return demo.CaptureSegment(
            "preflight", 4141, 4242, 1280, 720, 1.0, "e" * 64,
            requested_duration_seconds=1.0, frame_count=30, pts_sha256="f" * 64,
        )

    def _configuration(self, root: Path):
        home = root / "home"
        home.mkdir(mode=0o700)
        wheelhouse = root / "wheelhouse"
        wheelhouse.mkdir(mode=0o700)
        output = root / "output"
        return demo.Configuration(
            tag="corelm-portfolio-v4",
            output=output,
            ffmpeg=Path("/fixture/ffmpeg"),
            ffprobe=Path("/fixture/ffprobe"),
            home=home,
            wheelhouse=wheelhouse,
        )

    def test_corelm_routes_one_explicit_automated_demo_command(self):
        dispatcher = (ROOT / "corelm").read_text(encoding="utf-8")
        self.assertIn("./corelm macos portfolio-demo [options]", dispatcher)
        self.assertIn("macos:portfolio-demo)", dispatcher)
        self.assertIn(
            '"$PROJECT_DIR/platforms/macos/scripts/run-automated-portfolio-demo.py"',
            dispatcher,
        )
        self.assertIn("/usr/bin/env -i", dispatcher)
        self.assertIn('CORELM_OFFLINE="${CORELM_OFFLINE:-}"', dispatcher)
        self.assertIn('CORELM_WHEELHOUSE="${CORELM_WHEELHOUSE:-}"', dispatcher)
        self.assertNotIn("SSL_CERT_FILE=", dispatcher)
        self.assertNotIn("SSL_CERT_DIR=", dispatcher)

    def test_corelm_allows_ignored_app_bundle_but_rejects_ignored_bytecode(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            repository = fixture / "source"
            repository.mkdir()
            home = fixture / "home"
            runtime = home / ".cache/corelm/macos/runtime/bin"
            runtime.mkdir(parents=True)
            invocation_log = fixture / "python-invocations.log"
            python = runtime / "python"
            python.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' invoked >> {invocation_log!s}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            python.chmod(0o700)
            temporary_root = fixture / "tmp"
            temporary_root.mkdir(mode=0o700)

            shutil.copy2(ROOT / "corelm", repository / "corelm")
            (repository / "corelm").chmod(0o755)
            (repository / ".gitignore").write_text(
                "dist/\n**/__pycache__/\n*.py[cod]\n",
                encoding="utf-8",
            )
            for relative in (
                "publication/.keep",
                "security/.keep",
                "RealLLM/.keep",
                "platforms/macos/scripts/run-automated-portfolio-demo.py",
            ):
                target = repository / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

            git = "/usr/bin/git"
            subprocess.run((git, "init", "-q", str(repository)), check=True)
            subprocess.run(
                (git, "-C", str(repository), "config", "user.name", "Fixture"),
                check=True,
            )
            subprocess.run(
                (
                    git,
                    "-C",
                    str(repository),
                    "config",
                    "user.email",
                    "fixture@example.invalid",
                ),
                check=True,
            )
            subprocess.run((git, "-C", str(repository), "add", "."), check=True)
            subprocess.run(
                (git, "-C", str(repository), "commit", "-qm", "fixture"),
                check=True,
            )

            app = repository / "dist/CoreLMBenchmark.app"
            app.mkdir(parents=True)
            environment = {
                "HOME": str(home),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "TMPDIR": str(temporary_root),
            }
            command = (
                str(repository / "corelm"),
                "macos",
                "portfolio-demo",
                "--tag",
                "corelm-portfolio-v4",
            )
            accepted = subprocess.run(
                command,
                cwd=repository,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr.decode())
            self.assertEqual(invocation_log.read_text(encoding="utf-8"), "invoked\n")

            cache = repository / "security/__pycache__"
            cache.mkdir()
            (cache / "attack.cpython-312.pyc").write_bytes(b"ignored-bytecode")
            rejected = subprocess.run(
                command,
                cwd=repository,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn(
                b"forbids ignored paths outside the verified app bundle",
                rejected.stderr,
            )
            self.assertEqual(invocation_log.read_text(encoding="utf-8"), "invoked\n")

            (cache / "attack.cpython-312.pyc").unlink()
            cache.rmdir()
            root_shadow = repository / "security.pyc"
            root_shadow.write_bytes(b"ignored-namespace-shadow")
            root_rejected = subprocess.run(
                command,
                cwd=repository,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertNotEqual(root_rejected.returncode, 0)
            self.assertIn(
                b"forbids ignored paths outside the verified app bundle",
                root_rejected.stderr,
            )
            self.assertEqual(invocation_log.read_text(encoding="utf-8"), "invoked\n")

            root_shadow.unlink()
            with (repository / ".git/info/exclude").open(
                "a", encoding="utf-8"
            ) as exclude:
                exclude.write("\nsecurity/__init__.py\n")
            initializer = repository / "security/__init__.py"
            initializer.write_text("raise SystemExit('injected')\n", encoding="utf-8")
            exclude_rejected = subprocess.run(
                command,
                cwd=repository,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertNotEqual(exclude_rejected.returncode, 0)
            self.assertIn(
                b"forbids ignored paths outside the verified app bundle",
                exclude_rejected.stderr,
            )
            self.assertEqual(invocation_log.read_text(encoding="utf-8"), "invoked\n")

    def test_configuration_rejects_future_tag_without_running_preflight(self):
        arguments = mock.Mock(tag="corelm-portfolio-v5")
        with self.assertRaisesRegex(demo.AutomatedDemoError, "exact corelm-portfolio-v4"):
            demo._validate_configuration(arguments)

    def test_preflight_is_nonprompting_and_precedes_attempt_and_proof(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('(str(helper), "--preflight")', source)
        self.assertIn('b\'{"screen_capture_authorized":true}\\n\'', source)
        self.assertIn('return (str(APP_EXECUTABLE), "--portfolio-capture-live")', source)
        self.assertNotIn("CGRequestScreenCaptureAccess", source)
        self.assertNotIn("_descendant_pids", source)
        self.assertNotIn("include_descendants", source)
        self.assertNotIn('PGREP = "/usr/bin/pgrep"', source)
        self.assertIn(
            '"https://github.com/ALLPROTO/core-lm-benchmark.git"', source
        )
        self.assertIn('f"{configuration.tag}-demo.mp4"', source)
        self.assertIn('f"{configuration.tag}-demo-poster.png"', source)
        tree = ast.parse(source)
        window_owners = {
            ast.unparse(node.args[0])
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_wait_for_window"
        }
        self.assertNotIn("proof_process.pid", window_owners)
        proof_argv_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_proof_argv"
        ]
        self.assertEqual(len(proof_argv_calls), 1)
        orchestrate = source[source.index("def orchestrate(") :]
        self.assertLess(
            orchestrate.index("_host_and_tool_preflight"),
            orchestrate.index("AttemptLog.reserve"),
        )
        self.assertEqual(orchestrate.count("_source_preflight"), 2)
        self.assertLess(
            orchestrate.rindex("_source_preflight"),
            orchestrate.index("AttemptLog.reserve"),
        )
        self.assertLess(
            orchestrate.rindex("_pre_marker_resources"),
            orchestrate.index("AttemptLog.reserve"),
        )
        self.assertLess(
            orchestrate.rindex("_recheck_prepared_tools"),
            orchestrate.index("AttemptLog.reserve"),
        )
        self.assertLess(
            orchestrate.index("_prepare_verified_tag_ci_receipt"),
            orchestrate.index("AttemptLog.reserve"),
        )
        self.assertLess(
            orchestrate.index("AttemptLog.reserve"),
            orchestrate.index("_execute_reserved_attempt"),
        )

    def test_pre_marker_resources_require_ac_half_memory_and_twelve_gib(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            configuration = self._configuration(root)
            success = (
                subprocess.CompletedProcess([], 0, b"Now drawing from 'AC Power'\n", b""),
                subprocess.CompletedProcess(
                    [], 0, b"System-wide memory free percentage: 50%\n", b""
                ),
            )
            exact_disk = mock.Mock(
                f_bavail=demo.MINIMUM_AVAILABLE_DISK_BYTES // 4096,
                f_frsize=4096,
            )
            with mock.patch.object(
                demo, "_run", side_effect=success
            ), mock.patch.object(demo.os, "statvfs", return_value=exact_disk):
                demo._pre_marker_resources(configuration)

            low_memory = (
                subprocess.CompletedProcess([], 0, b"AC Power\n", b""),
                subprocess.CompletedProcess(
                    [], 0, b"System-wide memory free percentage: 49%\n", b""
                ),
            )
            with mock.patch.object(
                demo, "_run", side_effect=low_memory
            ), mock.patch.object(demo.os, "statvfs", return_value=exact_disk):
                with self.assertRaisesRegex(demo.AutomatedDemoError, "50%"):
                    demo._pre_marker_resources(configuration)

            low_disk = mock.Mock(
                f_bavail=(demo.MINIMUM_AVAILABLE_DISK_BYTES // 4096) - 1,
                f_frsize=4096,
            )
            with mock.patch.object(
                demo, "_run", side_effect=success
            ), mock.patch.object(demo.os, "statvfs", return_value=low_disk):
                with self.assertRaisesRegex(demo.AutomatedDemoError, "12 GiB"):
                    demo._pre_marker_resources(configuration)

    def test_origin_identity_rejects_ssh_and_split_push_remote(self):
        canonical = "https://github.com/ALLPROTO/core-lm-benchmark.git"
        demo._validate_origin([canonical], [canonical])
        demo._validate_origin(
            ["https://github.com/ALLPROTO/core-lm-benchmark"],
            ["https://github.com/ALLPROTO/core-lm-benchmark"],
        )
        for fetch, push in (
            (["git@github.com:ALLPROTO/core-lm-benchmark.git"], [canonical]),
            ([canonical], ["https://evil.example/core-lm-benchmark.git"]),
            ([canonical, canonical], [canonical]),
        ):
            with self.subTest(fetch=fetch, push=push), self.assertRaisesRegex(
                demo.AutomatedDemoError, "canonical public repository"
            ):
                demo._validate_origin(fetch, push)

    def test_attempt_state_is_owner_only_exclusive_and_durable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            configuration = self._configuration(root)
            attempt = demo.AttemptLog.reserve(configuration.home, configuration.tag)
            try:
                state_path = attempt.path
                self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o600)
                first_digest = attempt.sha256()
                self.assertRegex(first_digest, r"^[0-9a-f]{64}$")
                attempt.append("PREPROOF_FAILURE")
                self.assertEqual(attempt.proof_invocation_count, 0)
                with self.assertRaisesRegex(
                    demo.AutomatedDemoError, "already consumed"
                ):
                    demo.AttemptLog.reserve(configuration.home, configuration.tag)
            finally:
                attempt.close()
            self.assertTrue(state_path.is_file())
            events = [
                json.loads(line)
                for line in state_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [event["event"] for event in events],
                ["ATTEMPT_STARTED", "PREPROOF_FAILURE"],
            )
            self.assertEqual(
                [event["proof_invocation_count"] for event in events], [0, 0]
            )

    def test_attempt_marker_directory_sync_failure_is_fail_closed_and_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            configuration = self._configuration(root)
            with mock.patch.object(
                demo, "_sync_containing_directory",
                side_effect=OSError("directory sync fixture"),
            ), mock.patch.object(demo.subprocess, "Popen") as popen:
                with self.assertRaisesRegex(OSError, "directory sync fixture"):
                    demo.AttemptLog.reserve(configuration.home, configuration.tag)
            marker = (
                configuration.home
                / "Library/Application Support/CoreLMBenchmark/portfolio-automation"
                / f"{configuration.tag}.jsonl"
            )
            self.assertTrue(marker.is_file())
            self.assertEqual(marker.read_bytes(), b"")
            self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o600)
            popen.assert_not_called()

    def test_live_capture_failure_preserves_terminal_and_never_runs_second_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            configuration = self._configuration(root)
            configuration.output.mkdir(mode=0o700)
            helper = configuration.output / "find-proof-window"
            helper.write_bytes(b"fixture")
            prepared = demo.PreparedTools(
                staging=configuration.output,
                helper=helper,
                report={},
                preflight_capture=self._preflight_segment(),
                tag_ci_receipt_sha256="d" * 64,
                local_tag_trust_receipt_sha256="c" * 64,
            )
            source = demo.SourceIdentity(
                tag=configuration.tag,
                commit="1" * 40,
                tree="2" * 40,
            )
            proof = demo.ProofIdentity(
                run_directory=root / "run",
                identifier="12345678-1234-4234-8234-123456789abc",
                challenge_sha256="3" * 64,
                receipt_sha256="4" * 64,
                result_sha256="5" * 64,
                application_executable_sha256="6" * 64,
                metric_verdict="FAIL",
                terminal_outcome="END-TO-END PROOF VERIFIED — METRIC FAIL",
                compression_ratio_vs_bf16="2.052384",
                delta_nll_nat_per_token="-0.000008",
                top1_agreement="0.995117",
            )
            live_process = FakeProcess(pid=5151)
            proof_process = FakeProcess(pid=4242)
            live_window = demo.WindowIdentity(
                pid=5151,
                window_id=6161,
                width=1280,
                height=720,
                executable_path=str(demo.APP_EXECUTABLE),
                executable_sha256="6" * 64,
            )
            attempt = demo.AttemptLog.reserve(configuration.home, configuration.tag)
            try:
                with mock.patch.object(
                    demo.subprocess,
                    "Popen",
                    side_effect=(live_process, proof_process),
                ) as popen, mock.patch.object(
                    demo, "_snapshot_runs", return_value=set()
                ), mock.patch.object(
                    demo, "_wait_for_window", return_value=live_window
                ) as wait_window, mock.patch.object(
                    demo, "_validate_window_executable"
                ) as validate_window, mock.patch.object(
                    demo, "_recheck_window"
                ) as recheck_window, mock.patch.object(
                    demo,
                    "_capture_segment",
                    side_effect=demo.AutomatedDemoError("capture fixture failed"),
                ), mock.patch.object(
                    demo, "_new_run_directory", return_value=proof.run_directory
                ), mock.patch.object(
                    demo, "_inspect_proof", return_value=proof
                ), mock.patch.object(
                    demo, "_terminate_process"
                ) as terminate, mock.patch.object(
                    demo, "_sha256_path", return_value="6" * 64
                ):
                    with self.assertRaisesRegex(
                        demo.AutomatedDemoError,
                        "live presentation capture failed after proof invocation",
                    ):
                        demo._execute_reserved_attempt(
                            configuration, source, prepared, attempt
                        )

                self.assertEqual(popen.call_count, 2)
                live_call, proof_call = popen.call_args_list
                self.assertEqual(live_call.args[0], demo._live_presentation_argv())
                self.assertEqual(
                    live_call.args[0],
                    (str(demo.APP_EXECUTABLE), "--portfolio-capture-live"),
                )
                positional, keyword = proof_call
                self.assertEqual(positional[0], demo._proof_argv())
                self.assertEqual(
                    positional[0],
                    (str(ROOT / "corelm"), "macos", "proof"),
                )
                self.assertEqual(keyword["env"]["CORELM_OFFLINE"], "1")
                self.assertRegex(
                    keyword["env"]["CORELM_PROOF_CHALLENGE"],
                    r"^[0-9a-f]{64}$",
                )
                self.assertEqual(proof_process.wait_calls, 1)
                self.assertEqual(wait_window.call_args.args[0], live_process.pid)
                self.assertNotEqual(wait_window.call_args.args[0], proof_process.pid)
                validate_window.assert_called_once_with(
                    live_window,
                    expected_sha256="6" * 64,
                    label="live presentation window",
                )
                self.assertGreaterEqual(recheck_window.call_count, 2)
                terminate.assert_called_once_with(live_process)

                state_lines = attempt.path.read_text(encoding="utf-8").splitlines()
                events = [json.loads(line) for line in state_lines]
                self.assertEqual(
                    [event["event"] for event in events],
                    [
                        "ATTEMPT_STARTED",
                        "LIVE_SURFACE_READY",
                        "PROOF_INVOKED",
                        "PROOF_TERMINAL",
                        "REPLAY_VERIFIED",
                    ],
                )
                terminal = next(
                    event for event in events if event["event"] == "PROOF_TERMINAL"
                )
                self.assertEqual(terminal["metric_verdict"], "FAIL")
                with self.assertRaisesRegex(
                    demo.AutomatedDemoError, "already consumed"
                ):
                    demo.AttemptLog.reserve(configuration.home, configuration.tag)
                self.assertEqual(popen.call_count, 2)
            finally:
                attempt.close()

    def test_live_surface_must_bind_before_the_only_proof_invocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            configuration = self._configuration(root)
            configuration.output.mkdir(mode=0o700)
            helper = configuration.output / "find-proof-window"
            helper.write_bytes(b"fixture")
            prepared = demo.PreparedTools(
                configuration.output,
                helper,
                {},
                self._preflight_segment(),
                "d" * 64,
                "c" * 64,
            )
            source = demo.SourceIdentity(configuration.tag, "1" * 40, "2" * 40)
            live_process = FakeProcess(pid=5151)
            attempt = demo.AttemptLog.reserve(configuration.home, configuration.tag)
            try:
                with mock.patch.object(
                    demo.subprocess, "Popen", return_value=live_process
                ) as popen, mock.patch.object(
                    demo, "_snapshot_runs", return_value=set()
                ), mock.patch.object(
                    demo,
                    "_wait_for_window",
                    side_effect=demo.AutomatedDemoError("safe window unavailable"),
                ) as wait_window, mock.patch.object(
                    demo, "_terminate_process"
                ) as terminate, mock.patch.object(
                    demo, "_sha256_path", return_value="6" * 64
                ):
                    with self.assertRaisesRegex(
                        demo.AutomatedDemoError, "safe window unavailable"
                    ):
                        demo._execute_reserved_attempt(
                            configuration, source, prepared, attempt
                        )
                self.assertEqual(popen.call_count, 1)
                self.assertEqual(popen.call_args.args[0], demo._live_presentation_argv())
                self.assertEqual(wait_window.call_args.args[0], live_process.pid)
                terminate.assert_called_once_with(live_process)
                events = [
                    json.loads(line)["event"]
                    for line in attempt.path.read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual(events, ["ATTEMPT_STARTED"])
            finally:
                attempt.close()

    def test_permission_window_or_capture_failure_precedes_marker_and_proof(self):
        for failure in (
            "screen capture is not already authorized",
            "timed out waiting for the exact application window",
            "preflight exact-window capture failed",
        ):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve(strict=True)
                configuration = self._configuration(root)
                source = demo.SourceIdentity(
                    tag=configuration.tag,
                    commit="1" * 40,
                    tree="2" * 40,
                )
                with mock.patch.object(
                    demo, "_source_preflight", return_value=source
                ), mock.patch.object(
                    demo,
                    "_host_and_tool_preflight",
                    side_effect=demo.AutomatedDemoError(failure),
                ), mock.patch.object(
                    demo.AttemptLog, "reserve"
                ) as reserve, mock.patch.object(
                    demo, "_execute_reserved_attempt"
                ) as execute, mock.patch.object(
                    demo.subprocess, "Popen"
                ) as popen:
                    with self.assertRaisesRegex(demo.AutomatedDemoError, failure):
                        demo.orchestrate(configuration)
                reserve.assert_not_called()
                execute.assert_not_called()
                popen.assert_not_called()
                self.assertFalse(configuration.output.exists())

    def test_ui_preflight_uses_safe_mode_exact_pid_and_one_second_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            configuration = self._configuration(root)
            helper = root / "helper"
            helper.write_bytes(b"fixture")
            process = FakeProcess(pid=5151)
            window = demo.WindowIdentity(
                pid=5151,
                window_id=6161,
                width=1280,
                height=720,
                executable_path=None,
                executable_sha256=None,
            )
            captured = demo.CaptureSegment(
                "preflight", 5151, 6161, 1280, 720, 1.0, "a" * 64
            )
            with mock.patch.object(
                demo.subprocess, "Popen", return_value=process
            ) as popen, mock.patch.object(
                demo, "_wait_for_window", return_value=window
            ) as wait_window, mock.patch.object(
                demo, "_validate_window_executable"
            ) as validate_window, mock.patch.object(
                demo, "_recheck_window"
            ) as recheck_window, mock.patch.object(
                demo, "_capture_segment", return_value=captured
            ) as capture, mock.patch.object(
                demo, "_terminate_process"
            ) as terminate, mock.patch.object(
                demo, "_sha256_path", return_value="b" * 64
            ):
                observed = demo._application_capture_preflight(
                    configuration=configuration,
                    helper=helper,
                    staging=root,
                )
            self.assertEqual(observed, captured)
            self.assertEqual(
                popen.call_args.args[0],
                (str(demo.APP_EXECUTABLE), "--portfolio-capture-preflight"),
            )
            self.assertEqual(wait_window.call_args.args[0], 5151)
            validate_window.assert_called_once()
            self.assertEqual(recheck_window.call_count, 2)
            self.assertEqual(capture.call_args.kwargs["duration"], 1.0)
            self.assertEqual(capture.call_args.kwargs["window"], window)
            terminate.assert_called_once_with(process)

    def test_result_readiness_is_exact_owner_only_and_proof_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            path = root / "result-readiness.json"
            self.assertEqual(
                demo._fixed_metric(
                    2.052383755053835,
                    "compression ratio",
                    minimum=0,
                    maximum=64,
                    minimum_exclusive=True,
                ),
                "2.052384",
            )
            self.assertEqual(
                demo._fixed_metric(
                    -8.493661880493164e-06,
                    "delta NLL",
                    minimum=-1,
                    maximum=1,
                ),
                "-0.000008",
            )
            proof = demo.ProofIdentity(
                root / "run",
                "12345678-1234-4234-8234-123456789abc",
                "3" * 64,
                "4" * 64,
                "5" * 64,
                "6" * 64,
                "PASS",
                "END-TO-END PROOF PASS",
                "2.052384",
                "-0.000008",
                "0.995117",
            )
            payload = demo._result_readiness_bytes(proof)
            expected = {
                "application_executable_sha256": "6" * 64,
                "compression_ratio_vs_bf16": "2.052384",
                "delta_nll_nat_per_token": "-0.000008",
                "metric_verdict": "PASS",
                "module_states": {
                    "compression": "COMPLETE",
                    "heavy_replay": "PASS",
                    "kv_cache": "COMPLETE",
                    "primary_evidence": "COMPLETE",
                    "qwen_model": "COMPLETE",
                },
                "receipt_sha256": "4" * 64,
                "result_sha256": "5" * 64,
                "run_identifier": "12345678-1234-4234-8234-123456789abc",
                "schema_version": 1,
                "status": "CAPTURE_RESULT_READY",
                "top1_agreement": "0.995117",
                "verifier_state": "PASS",
            }
            self.assertEqual(
                payload,
                json.dumps(
                    expected,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n",
            )
            self.assertEqual(json.loads(payload), expected)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                self.assertEqual(os.write(descriptor, payload), len(payload))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            identity = demo._read_result_readiness(path, proof)
            self.assertEqual(
                identity.sha256,
                demo.hashlib.sha256(payload).hexdigest(),
            )
            path.chmod(0o644)
            with self.assertRaisesRegex(demo.AutomatedDemoError, "owner-only"):
                demo._read_result_readiness(path, proof)
            with self.assertRaisesRegex(demo.AutomatedDemoError, "timed out"):
                demo._wait_for_result_readiness(
                    root / "absent-readiness.json", proof, timeout=0
                )

    def test_result_capture_waits_for_ready_receipt_before_exact_window_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            configuration = self._configuration(root)
            configuration.output.mkdir(mode=0o700)
            helper = configuration.output / "find-proof-window"
            helper.write_bytes(b"fixture")
            proof = demo.ProofIdentity(
                root / "run",
                "12345678-1234-4234-8234-123456789abc",
                "3" * 64,
                "4" * 64,
                "5" * 64,
                "6" * 64,
                "PASS",
                "END-TO-END PROOF PASS",
                "2.052384",
                "-0.000008",
                "0.995117",
            )
            process = FakeProcess(pid=7171)
            window = demo.WindowIdentity(
                7171,
                8181,
                1280,
                720,
                str(demo.APP_EXECUTABLE),
                "6" * 64,
            )
            segment = demo.CaptureSegment(
                "same_run_result", 7171, 8181, 1280, 720, 18.0, "7" * 64
            )
            readiness = demo.ReadinessIdentity("8" * 64, 1, 2, 3, 4, 5)
            order = []
            attempt = demo.AttemptLog.reserve(configuration.home, configuration.tag)
            try:
                with mock.patch.object(
                    demo.subprocess, "Popen", return_value=process
                ) as popen, mock.patch.object(
                    demo, "_wait_for_window", return_value=window
                ), mock.patch.object(
                    demo, "_validate_window_executable"
                ), mock.patch.object(
                    demo, "_recheck_window"
                ) as recheck, mock.patch.object(
                    demo,
                    "_wait_for_result_readiness",
                    side_effect=lambda *_args, **_kwargs: (
                        order.append("ready") or readiness
                    ),
                ) as wait_ready, mock.patch.object(
                    demo,
                    "_capture_segment",
                    side_effect=lambda **_kwargs: (
                        order.append("capture") or segment
                    ),
                ), mock.patch.object(
                    demo,
                    "_read_result_readiness",
                    side_effect=lambda *_args, **_kwargs: (
                        order.append("ready-recheck") or readiness
                    ),
                ), mock.patch.object(
                    demo, "_terminate_process"
                ) as terminate:
                    observed = demo._launch_result_capture(
                        configuration, helper, proof, attempt
                    )
                self.assertEqual(observed, (segment, readiness.sha256))
                readiness_path = configuration.output / "result-readiness.json"
                self.assertEqual(
                    popen.call_args.args[0],
                    (
                        str(demo.APP_EXECUTABLE),
                        "--portfolio-capture",
                        "--portfolio-result-id",
                        proof.identifier,
                        "--portfolio-ready-file",
                        str(readiness_path),
                    ),
                )
                self.assertEqual(order, ["ready", "capture", "ready-recheck"])
                self.assertEqual(wait_ready.call_args.args, (readiness_path, proof))
                self.assertEqual(recheck.call_count, 2)
                terminate.assert_called_once_with(process)
                events = [
                    json.loads(line)
                    for line in attempt.path.read_text(encoding="utf-8").splitlines()
                ]
                reopened = next(
                    event for event in events if event["event"] == "SAME_RUN_REOPENED"
                )
                self.assertEqual(
                    reopened["result_readiness_sha256"], readiness.sha256
                )
            finally:
                attempt.close()

    def test_screencapture_targets_only_exact_window_id_for_fixed_duration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            destination = root / "live-presentation.mov"
            observed = []

            def fake_run(arguments, **_kwargs):
                observed.append(tuple(arguments))
                destination.write_bytes(b"real capture fixture bytes")
                return subprocess.CompletedProcess(arguments, 0, b"", b"")

            window = demo.WindowIdentity(
                pid=100,
                window_id=321,
                width=1280,
                height=720,
                executable_path=None,
                executable_sha256=None,
            )
            with mock.patch.object(demo, "_run", side_effect=fake_run), mock.patch.object(
                demo,
                "_probe_segment",
                return_value=(1280, 720, 12.0, 360, "a" * 64),
            ):
                segment = demo._capture_segment(
                    role="live_presentation",
                    window=window,
                    destination=destination,
                    duration=demo.automated_media.LIVE_SEGMENT_SECONDS,
                    ffprobe=Path("/fixture/ffprobe"),
                )
            self.assertEqual(
                observed,
                [
                    (
                        "/usr/sbin/screencapture",
                        "-x",
                        "-o",
                        "-v",
                        "-V12",
                        "-l321",
                        str(destination),
                    )
                ],
            )
            self.assertEqual(segment.role, "live_presentation")
            self.assertEqual(segment.duration_seconds, 12.0)
            self.assertRegex(segment.sha256, r"^[0-9a-f]{64}$")

    def test_window_helper_output_is_canonical_and_pid_bound(self):
        value = {
            "bounds": {"height": 720, "width": 1280, "x": 0, "y": 25},
            "bundle_identifier": demo.automated_media.BUNDLE_IDENTIFIER,
            "mode": "MACOS_WINDOW_ID_ONLY",
            "owner_name": "CoreLMBenchmark",
            "pid": 700,
            "schema_version": 1,
            "window_id": 701,
        }
        raw = demo.automated_media.canonical_json_bytes(value)
        parsed = demo._parse_window(raw, 700)
        self.assertEqual(parsed.window_id, 701)
        moved_value = json.loads(raw)
        moved_value["bounds"]["x"] = 1
        moved = demo._parse_window(
            demo.automated_media.canonical_json_bytes(moved_value), 700
        )
        self.assertNotEqual(parsed, moved)
        with self.assertRaisesRegex(demo.AutomatedDemoError, "identity is invalid"):
            demo._parse_window(raw, 702)
        pretty = json.dumps(value, indent=2).encode("utf-8")
        with self.assertRaisesRegex(demo.AutomatedDemoError, "not canonical"):
            demo._parse_window(pretty, 700)

    def test_fixed_pipeline_and_canonical_automation_report(self):
        filter_value = demo._fixed_filter()
        self.assertIn("trim=duration=12", filter_value)
        self.assertIn("trim=duration=18", filter_value)
        self.assertIn("concat=n=2:v=1:a=0", filter_value)
        self.assertEqual(demo.EXPECTED_FRAME_COUNT, 900)
        video = Path("/private/final.mp4")
        poster = Path("/private/poster.png")
        ffmpeg = Path("/private/ffmpeg")
        ffprobe = Path("/private/ffprobe")
        self.assertEqual(
            demo._poster_argv(ffmpeg, video, poster),
            (
                "/private/ffmpeg",
                "-v",
                "error",
                "-ss",
                "15.000000",
                "-i",
                "/private/final.mp4",
                "-frames:v",
                "1",
                "-an",
                "-map_metadata",
                "-1",
                "-compression_level",
                "9",
                "-pred",
                "mixed",
                "/private/poster.png",
            ),
        )
        self.assertEqual(
            demo._frame_probe_argv(video, ffprobe),
            (
                "/private/ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_frames",
                "-show_entries",
                "frame=best_effort_timestamp_time,pkt_duration_time,width,height",
                "-of",
                "json",
                "/private/final.mp4",
            ),
        )
        self.assertEqual(
            demo._framemd5_argv(video, ffmpeg),
            (
                "/private/ffmpeg",
                "-v",
                "error",
                "-i",
                "/private/final.mp4",
                "-map",
                "0:v:0",
                "-f",
                "framemd5",
                "-",
            ),
        )

        source = demo.SourceIdentity("corelm-portfolio-v4", "1" * 40, "2" * 40)
        proof = demo.ProofIdentity(
            Path("/private/run"),
            "12345678-1234-4234-8234-123456789abc",
            "3" * 64,
            "4" * 64,
            "5" * 64,
            "6" * 64,
            "PASS",
            "END-TO-END PROOF PASS",
            "2.052384",
            "-0.000008",
            "0.995117",
        )
        live = demo.CaptureSegment(
            "live_presentation", 10, 11, 1280, 720, 12.0, "7" * 64,
            requested_duration_seconds=12.0, frame_count=360, pts_sha256="7" * 64,
        )
        result = demo.CaptureSegment(
            "same_run_result", 12, 13, 1280, 720, 18.0, "8" * 64,
            requested_duration_seconds=18.0, frame_count=540, pts_sha256="8" * 64,
        )
        preflight = self._preflight_segment()
        tools = {
            "window_helper": {
                "source_sha256": "9" * 64,
                "executable_sha256": "a" * 64,
                "swift_version": "Apple Swift version 6.3.3 fixture",
            },
            "screencapture": {
                "executable_sha256": "b" * 64,
                "codesign_identifier": "com.apple.screencapture",
            },
            "ffmpeg": {
                "executable_sha256": "c" * 64,
                "version": "ffmpeg version 8.1.2 fixture",
            },
            "ffprobe": {
                "executable_sha256": "d" * 64,
                "version": "ffprobe version 8.1.2 fixture",
            },
        }
        media = demo.MediaIdentity(
            Path("/private/video.mp4"),
            Path("/private/poster.png"),
            "e" * 64,
            "f" * 64,
            30.0,
            1280,
            720,
            900,
            "0" * 64,
            "1" * 64,
        )
        report = demo._build_report(
            source=source,
            proof=proof,
            preflight=preflight,
            live=live,
            result=result,
            tools=tools,
            media=media,
            state_sha256="2" * 64,
            result_readiness_sha256="3" * 64,
            tag_ci_receipt_sha256="4" * 64,
            local_tag_trust_receipt_sha256="5" * 64,
        )
        self.assertFalse(report["human_reviewed"])
        self.assertFalse(report["pixel_semantics_verified"])
        self.assertEqual(
            report["classification"],
            "AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE",
        )
        self.assertEqual(report["capture"]["result_readiness_sha256"], "3" * 64)
        self.assertIs(demo.automated_media.validate_report(report), report)


if __name__ == "__main__":
    unittest.main()
