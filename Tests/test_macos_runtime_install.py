"""Isolated installation-control tests; no model or scientific data is executed."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path
from unittest import mock

from security import build_macos_runtime as builder
from security import manage_local_runtime as runtime


ROOT = Path(__file__).resolve().parents[1]


class MacOSRuntimeInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.root.chmod(0o700)
        self.target = self.root / "runtime with spaces"
        self.cache = self.root / "cache"
        self.calls = []
        self.failure = ""
        # The test-only temporary ancestor can be shared /tmp; production keeps
        # the full ownership chain check. All target/marker checks remain real.
        self.chain = mock.patch.object(runtime, "_safe_existing_chain")
        self.chain.start()
        self.addCleanup(self.chain.stop)
        self.runner = mock.patch.object(builder, "_run", side_effect=self.fake_run)
        self.runner.start()
        self.addCleanup(self.runner.stop)

    def fake_run(self, python, arguments, cache, *, lock_fd=None):
        self.assertIsNotNone(lock_fd)
        if arguments[:2] == ["-m", "venv"]:
            phase = "venv"
            self.assertEqual(Path(arguments[-1]), self.target)
            venv.EnvBuilder(with_pip=False, symlinks=False).create(self.target)
        elif arguments[:3] == ["-m", "pip", "install"]:
            phase = "bootstrap" if arguments[-1].endswith("pip-maintained.txt") else "model"
            if phase == "bootstrap":
                (self.target / ".test-bootstrap-complete").touch()
                # A console-script shebang must name the final prefix even
                # when that path contains spaces. Never move this venv later.
                (self.target / "bin/test-entrypoint").write_text(str(self.target / "bin/python"))
            else:
                self.assertTrue((self.target / ".test-bootstrap-complete").exists())
                (self.target / ".test-model-complete").touch()
        elif arguments[:3] == ["-m", "pip", "check"]:
            phase = "check"
        elif arguments[0].endswith("verify_locked_environment.py"):
            phase = "bootstrap-verify" if arguments.count("--lock") == 1 else "model-verify"
            flag = ".test-bootstrap-complete" if phase == "bootstrap-verify" else ".test-model-complete"
            if not (self.target / flag).exists():
                raise subprocess.CalledProcessError(1, arguments)
        else:
            self.fail(f"unexpected test operation: {arguments}")
        self.calls.append((phase, Path(python), arguments))
        if phase == self.failure:
            raise subprocess.CalledProcessError(23, arguments)

    def build(self, **options):
        builder.build_runtime(str(self.target), ROOT, self.cache, **options)

    def snapshot(self):
        return {
            str(path.relative_to(self.target)): (
                "symlink", os.readlink(path)
            ) if path.is_symlink() else ("file", path.read_bytes())
            for path in self.target.rglob("*")
            if path.is_symlink() or path.is_file()
        }

    def test_new_install_bootstraps_only_from_official_index_before_mirror(self):
        mirror = "https://mirror.example.invalid/simple"
        self.build(index_url=mirror)
        phases = [call[0] for call in self.calls]
        self.assertEqual(phases, [
            "venv", "bootstrap", "check", "bootstrap-verify", "model", "check", "model-verify"
        ])
        bootstrap = self.calls[1][2]
        model = self.calls[4][2]
        self.assertIn("https://pypi.org/simple", bootstrap)
        self.assertNotIn(mirror, bootstrap)
        self.assertIn("--no-deps", bootstrap)
        self.assertIn(mirror, model)
        for arguments in (bootstrap, model):
            for flag in ("--isolated", "--no-cache-dir", "--require-hashes", "--only-binary=:all:"):
                self.assertIn(flag, arguments)
        self.assertFalse((self.target / runtime.INSTALLING_MARKER_NAME).exists())
        runtime.validate_existing_runtime(self.target)
        self.assertEqual(
            (self.target / "bin/test-entrypoint").read_text(), str(self.target / "bin/python")
        )
        completed = subprocess.run(
            [str(self.target / "bin/python"), "-I", "-B", "-c", "import sys; print(sys.prefix)"],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(completed.stdout.strip(), str(self.target))

    def test_offline_wheelhouse_never_uses_a_network_index(self):
        self.build(wheelhouse=str(self.root / "wheels"))
        installs = [call[2] for call in self.calls if call[0] in {"bootstrap", "model"}]
        self.assertEqual(len(installs), 2)
        for arguments in installs:
            self.assertIn("--no-index", arguments)
            self.assertIn("--find-links", arguments)
            self.assertNotIn("--index-url", arguments)

    def test_each_first_install_failure_leaves_destination_retryable(self):
        for phase in ("venv", "bootstrap", "bootstrap-verify", "model", "model-verify"):
            with self.subTest(phase=phase):
                self.failure = phase
                with self.assertRaises(subprocess.CalledProcessError):
                    self.build()
                self.assertFalse(self.target.exists())
                self.assertEqual(list(self.root.glob(".corelm-macos-reserve.*")), [])
                self.failure = ""
                self.build()
                runtime.validate_existing_runtime(self.target)
                # The test removes only its own fake completed fixture.
                import shutil
                shutil.rmtree(self.target)

    def test_hard_killed_install_is_recovered_at_the_same_final_path(self):
        script = '''
import os, signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from security import build_macos_runtime as b
target, project = Path(sys.argv[2]), Path(sys.argv[1])
with b._install_lock(target):
    b._reserve(target, b._binding(target, project))
    (target / "partial-before-kill").write_text("test-only partial payload")
    os.kill(os.getpid(), signal.SIGKILL)
'''
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", script, str(ROOT), str(self.target)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, -signal.SIGKILL, completed.stderr)
        self.assertTrue((self.target / runtime.INSTALLING_MARKER_NAME).exists())
        self.build()
        self.assertFalse((self.target / "partial-before-kill").exists())
        runtime.validate_existing_runtime(self.target)

    def test_existing_runtime_is_never_installed_into_or_changed(self):
        self.build()
        before = self.snapshot()
        for skip in (False, True):
            self.calls.clear()
            self.build(skip_install=skip)
            self.assertEqual([call[0] for call in self.calls], ["check", "model-verify"])
            self.assertEqual(self.snapshot(), before)
        self.failure = "model-verify"
        with self.assertRaisesRegex(ValueError, "retain the old runtime"):
            self.build()
        self.assertEqual(self.snapshot(), before)

    def test_unmarked_partial_or_unrelated_directory_is_preserved(self):
        self.target.mkdir(mode=0o700)
        (self.target / "unrelated").write_text("preserve me")
        before = self.snapshot()
        with self.assertRaises(OSError):
            self.build()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.calls, [])

    def test_foreign_or_changed_input_marker_is_preserved(self):
        binding = builder._binding(self.target, ROOT)
        record = builder._reserve(self.target, binding)
        marker = self.target / runtime.INSTALLING_MARKER_NAME
        record["lockfiles"][builder.LOCK_PATHS[0]] = "0" * 64
        marker.write_text(json.dumps(record))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "different inputs"):
            self.build()
        self.assertEqual(self.snapshot(), before)

    def test_live_install_lock_prevents_recovery_by_a_second_process(self):
        binding = builder._binding(self.target, ROOT)
        with builder._install_lock(self.target):
            builder._reserve(self.target, binding)
            before = self.snapshot()
            with self.assertRaisesRegex(ValueError, "another process"):
                self.build()
            self.assertEqual(self.snapshot(), before)

    def test_recovery_does_not_follow_a_symlink_outside_partial_runtime(self):
        builder._reserve(self.target, builder._binding(self.target, ROOT))
        outside = self.root / "retained"
        outside.mkdir()
        (outside / "evidence").write_text("unchanged")
        (self.target / "outside-link").symlink_to(outside, target_is_directory=True)
        self.build()
        self.assertEqual((outside / "evidence").read_text(), "unchanged")

    def test_reservation_does_not_replace_an_existing_empty_directory(self):
        self.target.mkdir(mode=0o700)
        before = self.target.stat().st_ino
        with self.assertRaises(FileExistsError):
            builder._reserve(self.target, builder._binding(self.target, ROOT))
        self.assertEqual(self.target.stat().st_ino, before)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_skip_install_never_creates_or_recovers_a_runtime(self):
        with self.assertRaisesRegex(ValueError, "requires an initialized"):
            self.build(skip_install=True)
        self.assertFalse(self.target.exists())
        builder._reserve(self.target, builder._binding(self.target, ROOT))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "unfinished"):
            self.build(skip_install=True)
        self.assertEqual(self.snapshot(), before)
        with self.assertRaisesRegex(ValueError, "unfinished"):
            runtime.validate_existing_runtime(self.target)

    def test_installer_subprocess_disables_configuration_and_bytecode_writes(self):
        self.runner.stop()
        with mock.patch.object(builder.subprocess, "Popen") as run:
            run.return_value.wait.return_value = 0
            builder._run(self.root / "python", ["-m", "pip", "check"], self.cache, lock_fd=17)
        arguments = run.call_args.args[0]
        self.assertEqual(arguments[1:3], ["-I", "-B"])
        self.assertIn(f"pycache_prefix={self.cache}", arguments)
        self.assertEqual(run.call_args.kwargs["env"]["PIP_CONFIG_FILE"], os.devnull)
        self.assertEqual(run.call_args.kwargs["pass_fds"], (17,))
        self.assertTrue(run.call_args.kwargs["start_new_session"])

    def test_installer_child_keeps_lock_after_coordinator_closes_its_descriptor(self):
        with builder._install_lock(self.target) as descriptor:
            child = subprocess.Popen(
                [sys.executable, "-I", "-B", "-c", "import time; time.sleep(30)"],
                pass_fds=(descriptor,),
            )
        try:
            with self.assertRaisesRegex(ValueError, "another process"):
                with builder._install_lock(self.target):
                    self.fail("orphan installer did not retain its lock")
        finally:
            child.kill()
            child.wait()
        with builder._install_lock(self.target):
            pass

    def test_interrupted_coordinator_stops_installer_process_group_before_cleanup(self):
        self.runner.stop()
        with (
            mock.patch.object(builder.subprocess, "Popen") as popen,
            mock.patch.object(builder.os, "killpg") as killpg,
        ):
            popen.return_value.pid = 123456
            popen.return_value.wait.side_effect = [KeyboardInterrupt, 0]
            with self.assertRaises(KeyboardInterrupt):
                builder._run(self.root / "python", ["-m", "pip", "check"], self.cache)
        killpg.assert_called_once_with(123456, signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
