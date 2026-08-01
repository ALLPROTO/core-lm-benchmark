from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REHEARSAL = PROJECT_ROOT / "security" / "rehearse_beacon_protocol.py"
MODEL_REHEARSAL = PROJECT_ROOT / "security" / "rehearse_beacon_model.py"
REHEARSAL_WRAPPER = PROJECT_ROOT / "security" / "run_beacon_rehearsal.sh"
MODEL_SUPERVISOR = (
    PROJECT_ROOT / "security" / "supervise_beacon_model_rehearsal.py"
)
LAUNCH_RUNBOOK = PROJECT_ROOT / "docs" / "BEACON_LAUNCH_RUNBOOK.md"
RESULT_DIRECTORY = PROJECT_ROOT / "real-llm-beacon-results"
PROOF_LOCK = Path.home() / ".cache" / "corelm-proof-runtimes" / ".proof-run.lock"


def _snapshot(path: Path):
    try:
        status = path.lstat()
    except FileNotFoundError:
        return ("absent",)
    if path.is_symlink():
        return ("symlink", os.readlink(path))
    if path.is_file():
        return ("file", status.st_size, hashlib.sha256(path.read_bytes()).hexdigest())
    if path.is_dir():
        return (
            "directory",
            tuple((child.name, _snapshot(child)) for child in sorted(path.iterdir())),
        )
    return ("other", status.st_mode)


class BeaconRehearsalTests(unittest.TestCase):
    def test_source_has_no_normative_execution_import_or_call(self):
        source = REHEARSAL.read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_modules = {
            "RealLLM.run_beacon_one_shot",
            "RealLLM.run_beacon_regression",
            "RealLLM.beacon_evaluation",
            "RealLLM.benchmark_real_llm",
            "torch",
            "numpy",
            "transformers",
            "huggingface_hub",
            "pyarrow",
            "tokenizers",
            "safetensors",
        }
        forbidden_calls = {
            "build_resolution",
            "fetch_nist_pulse",
            "run_one_shot",
            "_run_one_shot_locked",
            "_create_attempt",
            "run_selected_window",
            "_resolve_model_and_test",
            "_token_blocks",
        }
        imports: set[str] = set()
        calls: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.add(module)
                imports.update(f"{module}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
        self.assertFalse(imports & forbidden_modules)
        self.assertFalse(calls & forbidden_calls)

    def test_rehearsal_is_temp_only_and_silent_about_selection(self):
        before_results = _snapshot(RESULT_DIRECTORY)
        before_lock = _snapshot(PROOF_LOCK)
        freeze = PROJECT_ROOT / "RealLLM" / "beacon_freeze.json"
        before_freeze = _snapshot(freeze)
        with tempfile.TemporaryDirectory() as temporary:
            code = """
import datetime
import pathlib
import sys
root = pathlib.Path(sys.argv[1]).resolve(strict=True)
sys.argv = [sys.argv[0]]
sys.path.insert(0, str(root))
from security import rehearse_beacon_protocol as rehearsal
rehearsal._utc_now = lambda: datetime.datetime(
    2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc
)
raise SystemExit(rehearsal.main())
"""
            completed = subprocess.run(
                [sys.executable, "-I", "-B", "-c", code, str(PROJECT_ROOT)],
                cwd=PROJECT_ROOT,
                env={
                    "HOME": str(Path.home()),
                    "TMPDIR": temporary,
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "LANG": "C",
                    "LC_ALL": "C",
                },
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("SYNTHETIC REHEARSAL PASS", completed.stdout)
            lowered = completed.stdout.lower()
            for leaked in ("candidateindex", "startblock", "selectedwindow"):
                self.assertNotIn(leaked, lowered)
            self.assertEqual(list(Path(temporary).iterdir()), [])
        self.assertEqual(_snapshot(RESULT_DIRECTORY), before_results)
        self.assertEqual(_snapshot(PROOF_LOCK), before_lock)
        self.assertEqual(_snapshot(freeze), before_freeze)

    def test_cli_overrides_are_rejected_before_any_work(self):
        completed = subprocess.run(
            [sys.executable, "-I", "-B", str(REHEARSAL), "--synthetic"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("overrides are forbidden", completed.stderr)

    def test_protocol_guard_denies_two_path_destination_escape(self):
        code = """
import os
import pathlib
import shutil
import sys
import tempfile
root = pathlib.Path(sys.argv[1]).resolve(strict=True)
sys.path.insert(0, str(root))
from security import rehearse_beacon_protocol as rehearsal
allowed = pathlib.Path(tempfile.mkdtemp(prefix="protocol-guard-test-"))
outside = allowed.parent / (allowed.name + "-escape")
rehearsal._install_audit_guard(allowed)
blocked = 0
for operation in (
    lambda: os.link("/etc/hosts", outside),
    lambda: os.symlink("/etc/hosts", outside),
    lambda: shutil.copyfile("/etc/hosts", outside),
):
    try:
        operation()
    except PermissionError:
        blocked += 1
allowed.rmdir()
raise SystemExit(0 if blocked == 3 and not os.path.lexists(outside) else 1)
"""
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code, str(PROJECT_ROOT)],
            cwd=PROJECT_ROOT,
            env={
                "HOME": str(Path.home()),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "C",
                "LC_ALL": "C",
            },
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_one_shot_parser_has_no_rehearsal_escape_hatch(self):
        from RealLLM.run_beacon_one_shot import parse_arguments

        for argument in (
            "--dry-run",
            "--synthetic",
            "--rehearsal",
            "--pulse",
            "--start-block",
            "--output",
        ):
            with self.subTest(argument=argument):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        parse_arguments([argument])

    def test_scientific_launch_block_is_fail_fast_and_propagates_status(self):
        document = LAUNCH_RUNBOOK.read_text(encoding="utf-8")
        marker = "BEACON_TAG_SHA=0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44"
        marker_offset = document.rindex(marker)
        fence_start = document.rindex("```sh\n", 0, marker_offset) + len("```sh\n")
        fence_end = document.index("```", marker_offset)
        block = document[fence_start:fence_end]
        self.assertTrue(block.startswith("(\nset -eu\n"))
        self.assertTrue(block.rstrip().endswith('exit "$BEACON_EXIT"\n)'))
        self.assertLess(
            block.index('test "$(/bin/date -u +%s)"'),
            block.index("RealLLM/run_beacon_one_shot.py"),
        )
        self.assertLess(
            block.index("Now drawing from 'AC Power'"),
            block.index("RealLLM/run_beacon_one_shot.py"),
        )

    def test_model_rehearsal_has_no_runner_or_corpus_execution_call(self):
        source = MODEL_REHEARSAL.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        calls: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.add(module)
                imports.update(
                    f"{module}.{alias.name}" for alias in node.names
                )
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
        self.assertNotIn("RealLLM.run_beacon_one_shot", imports)
        self.assertNotIn("RealLLM.run_beacon_regression", imports)
        self.assertFalse(
            calls
            & {
                "run_one_shot",
                "_run_one_shot_locked",
                "_create_attempt",
                "fetch_nist_pulse",
                "build_resolution",
                "select_window",
                "run_selected_window",
                "_resolve_model_and_test",
                "_token_blocks",
            }
        )
        self.assertIn("_evaluate_block", calls)
        self.assertIn("test-00000-of-00001.parquet", source)
        self.assertIn("real-llm-beacon-results", source)
        self.assertNotIn(
            "run_beacon_one_shot.py",
            REHEARSAL_WRAPPER.read_text(encoding="utf-8"),
        )
        self.assertNotIn(
            "1785693600000",
            source + REHEARSAL_WRAPPER.read_text(encoding="utf-8"),
        )

    def test_model_rehearsal_cutoff_fails_before_heavy_imports(self):
        code = """
import datetime
import pathlib
import sys
root = pathlib.Path(sys.argv[1]).resolve(strict=True)
sys.argv = [sys.argv[0]]
sys.path.insert(0, str(root))
from security import rehearse_beacon_model as rehearsal
rehearsal._utc_now = lambda: datetime.datetime(
    2026, 8, 2, 17, 0, tzinfo=datetime.timezone.utc
)
raise SystemExit(rehearsal.main())
"""
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code, str(PROJECT_ROOT)],
            cwd=PROJECT_ROOT,
            env={
                "HOME": str(Path.home()),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "C",
                "LC_ALL": "C",
            },
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("cutoff has passed", completed.stderr)

    def test_model_guard_denies_result_write_and_test_corpus_open(self):
        before_results = _snapshot(RESULT_DIRECTORY)
        code = """
import os
import pathlib
import shutil
import sys
root = pathlib.Path(sys.argv[1]).resolve(strict=True)
sys.path.insert(0, str(root))
from security import rehearse_beacon_model as rehearsal
rehearsal._install_model_guard()
blocked = 0
targets = (
    root / "real-llm-beacon-results" / "attempt.json",
    root / "test-00000-of-00001.parquet",
    root / "guard-must-not-write.tmp",
)
for target in targets:
    try:
        target.open("wb")
    except PermissionError:
        blocked += 1
two_path_operations = (
    lambda: os.link("/etc/hosts", root / "guard-hardlink.tmp"),
    lambda: os.symlink("/etc/hosts", root / "guard-symlink.tmp"),
    lambda: shutil.copyfile("/etc/hosts", root / "guard-copy.tmp"),
)
for operation in two_path_operations:
    try:
        operation()
    except PermissionError:
        blocked += 1
targets = targets + (
    root / "guard-hardlink.tmp",
    root / "guard-symlink.tmp",
    root / "guard-copy.tmp",
)
raise SystemExit(0 if blocked == len(targets) else 1)
"""
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code, str(PROJECT_ROOT)],
            cwd=PROJECT_ROOT,
            env={
                "HOME": str(Path.home()),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "C",
                "LC_ALL": "C",
            },
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(_snapshot(RESULT_DIRECTORY), before_results)
        self.assertFalse((PROJECT_ROOT / "test-00000-of-00001.parquet").exists())
        self.assertFalse((PROJECT_ROOT / "guard-must-not-write.tmp").exists())
        self.assertFalse((PROJECT_ROOT / "guard-hardlink.tmp").exists())
        self.assertFalse((PROJECT_ROOT / "guard-symlink.tmp").exists())
        self.assertFalse((PROJECT_ROOT / "guard-copy.tmp").exists())

    def test_model_failure_still_runs_lock_and_snapshot_postconditions(self):
        from security import rehearse_beacon_model as rehearsal

        expected_frozen = (("file", 1, "a" * 64),)
        expected_results = {"kind": "directory"}
        expected_proof = {"kind": "absent"}
        fake_lock = Path("/tmp/corelm-test-proof.lock")
        with (
            mock.patch.object(
                rehearsal, "_acquire_proof_lock", return_value=fake_lock
            ),
            mock.patch.object(rehearsal, "_release_proof_lock") as release,
            mock.patch.object(rehearsal, "_install_model_guard"),
            mock.patch.object(
                rehearsal,
                "_run_model_block",
                side_effect=RuntimeError("injected model failure"),
            ),
            mock.patch.object(
                rehearsal, "_verify_postconditions"
            ) as postconditions,
        ):
            with self.assertRaisesRegex(RuntimeError, "injected model failure"):
                rehearsal._execute_model_rehearsal(
                    Path("/tmp/cache"),
                    expected_frozen,
                    expected_results,
                    expected_proof,
                )
        release.assert_called_once_with(fake_lock)
        postconditions.assert_called_once_with(
            expected_frozen, expected_results, expected_proof
        )

    def test_lock_release_failure_still_runs_snapshot_postconditions(self):
        from security import rehearse_beacon_model as rehearsal

        expected_frozen = (("file", 1, "a" * 64),)
        expected_results = {"kind": "directory"}
        expected_proof = {"kind": "absent"}
        fake_lock = Path("/tmp/corelm-test-proof.lock")
        with (
            mock.patch.object(
                rehearsal, "_acquire_proof_lock", return_value=fake_lock
            ),
            mock.patch.object(
                rehearsal,
                "_release_proof_lock",
                side_effect=RuntimeError("injected release failure"),
            ),
            mock.patch.object(rehearsal, "_install_model_guard"),
            mock.patch.object(rehearsal, "_run_model_block", return_value={}),
            mock.patch.object(
                rehearsal, "_verify_postconditions"
            ) as postconditions,
        ):
            with self.assertRaisesRegex(RuntimeError, "injected release failure"):
                rehearsal._execute_model_rehearsal(
                    Path("/tmp/cache"),
                    expected_frozen,
                    expected_results,
                    expected_proof,
                )
        postconditions.assert_called_once_with(
            expected_frozen, expected_results, expected_proof
        )

    def test_direct_model_rehearsal_rejects_unregistered_mps_variable(self):
        from security import rehearse_beacon_model as rehearsal

        registration = rehearsal.protocol_rehearsal.protocol.load_registration()
        with mock.patch.dict(
            os.environ, {"PYTORCH_MPS_UNREGISTERED": "1"}, clear=True
        ):
            with self.assertRaisesRegex(ValueError, "unregistered MPS"):
                rehearsal._configure_environment(
                    registration, Path("/tmp/model-cache")
                )

    def test_direct_model_rehearsal_rejects_repo_temp_parent(self):
        from security import rehearse_beacon_model as rehearsal

        with mock.patch.object(tempfile, "tempdir", str(PROJECT_ROOT)):
            with self.assertRaisesRegex(ValueError, "TMPDIR resolves inside"):
                rehearsal._require_safe_temp_parent()

    def test_protocol_rehearsal_rejects_repo_temp_parent_before_creation(self):
        from security import rehearse_beacon_protocol as rehearsal

        with mock.patch.object(tempfile, "tempdir", str(PROJECT_ROOT)):
            with self.assertRaisesRegex(ValueError, "TMPDIR resolves inside"):
                rehearsal._validated_temp_parent()

    def test_model_and_supervisor_cli_overrides_are_rejected(self):
        for script in (MODEL_REHEARSAL, MODEL_SUPERVISOR):
            with self.subTest(script=script.name):
                completed = subprocess.run(
                    [sys.executable, "-I", "-B", str(script), "--override"],
                    cwd=PROJECT_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertIn("overrides are forbidden", completed.stderr)

    def test_supervisor_removes_only_a_proven_dead_owned_lock(self):
        from security import supervise_beacon_model_rehearsal as supervisor

        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / ".proof-run.lock"
            dead_process_id = 99_999_999
            lock.write_text(f"{dead_process_id}\n", encoding="ascii")
            lock.chmod(0o600)
            with mock.patch.object(supervisor, "PROOF_LOCK", lock):
                self.assertTrue(
                    supervisor._cleanup_owned_lock(dead_process_id)
                )
            self.assertFalse(lock.exists())

    def test_supervisor_does_not_follow_replaced_temp_symlink(self):
        from security import supervise_beacon_model_rehearsal as supervisor

        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            target = parent / "target"
            target.mkdir()
            protected = target / "keep.txt"
            protected.write_text("keep\n", encoding="ascii")
            link = parent / "replaced-root"
            link.symlink_to(target, target_is_directory=True)
            self.assertFalse(supervisor._remove_private_temp(link))
            self.assertFalse(os.path.lexists(link))
            self.assertEqual(protected.read_text(encoding="ascii"), "keep\n")

    def test_supervisor_never_removes_an_unproven_lock(self):
        from security import supervise_beacon_model_rehearsal as supervisor

        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / ".proof-run.lock"
            lock.write_text("99999998\n", encoding="ascii")
            lock.chmod(0o600)
            with mock.patch.object(supervisor, "PROOF_LOCK", lock):
                self.assertFalse(supervisor._cleanup_owned_lock(99_999_999))
            self.assertTrue(lock.is_file())

    def test_supervisor_lock_parser_is_total_and_pid_bounded(self):
        from security import supervise_beacon_model_rehearsal as supervisor

        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / ".proof-run.lock"
            lock.write_bytes(b"\xff\xfe\n")
            lock.chmod(0o600)
            with mock.patch.object(supervisor, "PROOF_LOCK", lock):
                self.assertIsNone(supervisor._safe_lock_owner())
            lock.write_text("2147483648\n", encoding="ascii")
            with mock.patch.object(supervisor, "PROOF_LOCK", lock):
                self.assertIsNone(supervisor._safe_lock_owner())

    def test_supervisor_lock_observation_cannot_interrupt_termination(self):
        from security import supervise_beacon_model_rehearsal as supervisor

        with (
            mock.patch.object(supervisor, "_safe_lock_owner", return_value=42),
            mock.patch.object(
                supervisor.os, "getpgid", side_effect=OverflowError
            ),
        ):
            self.assertIsNone(supervisor._observe_owned_lock(42))

    def test_supervisor_rejects_repo_temp_parent_before_creation(self):
        from security import supervise_beacon_model_rehearsal as supervisor

        with mock.patch.object(tempfile, "tempdir", str(PROJECT_ROOT)):
            with self.assertRaisesRegex(RuntimeError, "TMPDIR resolves inside"):
                supervisor._validated_temp_parent()

    def test_supervisor_sigkill_follows_surviving_process_group(self):
        from security import supervise_beacon_model_rehearsal as supervisor

        process = mock.Mock()
        process.pid = 424_242
        process.wait.return_value = 0
        with (
            mock.patch.object(
                supervisor,
                "_group_exists",
                side_effect=(True, True, True, False, False),
            ),
            mock.patch.object(
                supervisor.time,
                "monotonic",
                side_effect=(0.0, 6.0, 10.0),
            ),
            mock.patch.object(supervisor.time, "sleep"),
            mock.patch.object(supervisor.os, "killpg") as kill_group,
        ):
            self.assertTrue(supervisor._terminate_group(process))
        self.assertEqual(
            kill_group.call_args_list,
            [
                mock.call(process.pid, signal.SIGTERM),
                mock.call(process.pid, signal.SIGKILL),
            ],
        )

    def test_supervisor_signal_handler_requests_orderly_cleanup(self):
        from security import supervise_beacon_model_rehearsal as supervisor

        with mock.patch.object(supervisor, "_STOP_SIGNAL", None):
            supervisor._request_stop(signal.SIGHUP, None)
            self.assertEqual(supervisor._stop_message(), "supervisor received SIGHUP")


if __name__ == "__main__":
    unittest.main()
