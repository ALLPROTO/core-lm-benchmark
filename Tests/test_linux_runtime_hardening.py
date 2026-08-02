import os
import platform
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from platforms.linux.scripts import runtime_safety


ROOT = Path(__file__).resolve().parents[1]
LINUX_SCRIPTS = ROOT / "platforms" / "linux" / "scripts"


class LinuxRuntimePathTests(unittest.TestCase):
    def test_private_anchor_below_root_owned_sticky_temp_is_allowed(self):
        system_temp = Path("/tmp").resolve(strict=True)
        status = system_temp.stat()
        if status.st_uid != 0 or not status.st_mode & stat.S_ISVTX:
            self.skipTest("system temp is not a root-owned sticky directory")
        with tempfile.TemporaryDirectory(dir=system_temp) as temporary:
            private_anchor = Path(temporary).resolve(strict=True)
            private_anchor.chmod(0o700)
            runtime_safety._safe_existing_chain(private_anchor / "runtime")

    def test_missing_target_directly_below_sticky_temp_is_rejected(self):
        system_temp = Path("/tmp").resolve(strict=True)
        status = system_temp.stat()
        if status.st_uid != 0 or not status.st_mode & stat.S_ISVTX:
            self.skipTest("system temp is not a root-owned sticky directory")
        target = system_temp / f"corelm-missing-target-{os.getpid()}"
        self.assertFalse(target.exists())
        with self.assertRaisesRegex(ValueError, "unsafe directory"):
            runtime_safety._safe_existing_chain(target)

    def test_root_owned_world_writable_non_sticky_ancestor_is_rejected(self):
        candidate = mock.Mock()
        candidate.lstat.return_value = SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o777,
            st_uid=0,
        )
        with self.assertRaisesRegex(ValueError, "unsafe directory"):
            runtime_safety._safe_directory(candidate, current_owner=False)

    def test_non_root_sticky_world_writable_ancestor_is_rejected(self):
        candidate = mock.Mock()
        candidate.lstat.return_value = SimpleNamespace(
            st_mode=stat.S_IFDIR | stat.S_ISVTX | 0o777,
            st_uid=os.getuid() if os.getuid() != 0 else 1,
        )
        with self.assertRaisesRegex(ValueError, "unsafe directory"):
            runtime_safety._safe_directory(candidate, current_owner=False)

    def test_targets_are_canonical_disjoint_and_checked_on_target_volume(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            paths, volumes = runtime_safety.validate_targets(
                project=str(ROOT),
                runtime=str(base / "runtime"),
                cache=str(base / "model-assets"),
                run=str(base / "runs" / "new-run"),
                minimum_free_kib=1,
            )
        self.assertEqual(
            set(paths),
            {"runtime", "cache", "run"},
        )
        self.assertEqual(len(volumes), 1)
        self.assertEqual(volumes[0]["labels"], ["cache", "run", "runtime"])

    def test_overlapping_targets_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            with self.assertRaisesRegex(ValueError, "paths overlap"):
                runtime_safety.validate_targets(
                    project=str(ROOT),
                    runtime=str(base / "runtime"),
                    cache=str(base / "runtime" / "assets"),
                    run=str(base / "runs"),
                    minimum_free_kib=1,
                )

    def test_checkout_destination_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            with self.assertRaisesRegex(ValueError, "unsafe runtime target"):
                runtime_safety.validate_targets(
                    project=str(ROOT),
                    runtime=str(ROOT / "local-runtime"),
                    cache=str(base / "assets"),
                    run=str(base / "runs"),
                    minimum_free_kib=1,
                )

    def test_low_space_is_reported_for_the_destination_volume(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            paths = {
                "runtime": base / "runtime",
                "cache": base / "assets",
                "run": base / "runs",
            }
            with mock.patch.object(
                runtime_safety.shutil,
                "disk_usage",
                return_value=SimpleNamespace(total=10, used=10, free=0),
            ) as disk_usage:
                with self.assertRaisesRegex(ValueError, "runtime"):
                    runtime_safety.verify_target_disk_space(
                        paths, minimum_free_kib=1
                    )
            disk_usage.assert_called_once_with(base)


class LinuxRuntimeIdentityTests(unittest.TestCase):
    def _create_venv(self, root: Path) -> Path:
        runtime = root / "runtime"
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-m", "venv", str(runtime)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        runtime_safety.initialize_runtime_marker(runtime)
        return runtime

    def test_marker_is_exclusive_private_and_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary).resolve() / "runtime"
            runtime.mkdir(mode=0o700)
            runtime_safety.initialize_runtime_marker(runtime)
            marker = runtime / runtime_safety.RUNTIME_MARKER_NAME
            self.assertEqual(
                marker.read_bytes(), runtime_safety.RUNTIME_MARKER_BYTES
            )
            self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                runtime_safety.initialize_runtime_marker(runtime)

    @unittest.skipUnless(
        platform.python_version() == runtime_safety.EXPECTED_PYTHON_VERSION,
        "exact runtime validation requires the registered Python",
    )
    def test_real_venv_passes_strict_reuse_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self._create_venv(Path(temporary).resolve())
            result = runtime_safety.validate_existing_runtime(runtime)
        self.assertEqual(
            result["version"], runtime_safety.EXPECTED_PYTHON_VERSION
        )
        self.assertEqual(result["runtime"], str(runtime))

    @unittest.skipUnless(
        platform.python_version() == runtime_safety.EXPECTED_PYTHON_VERSION,
        "exact runtime validation requires the registered Python",
    )
    def test_group_writable_reused_runtime_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self._create_venv(Path(temporary).resolve())
            runtime.chmod(0o770)
            with self.assertRaisesRegex(ValueError, "unsafe directory"):
                runtime_safety.validate_existing_runtime(runtime)

    def test_observation_rejects_wrong_version_and_base_prefix(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            runtime = base / "runtime"
            runtime.mkdir(mode=0o700)
            executable = base / "python"
            executable.write_bytes(b"python")
            observation = {
                "basePrefix": str(base),
                "executable": str(executable),
                "prefix": str(runtime),
                "version": "3.12.12",
            }
            with self.assertRaisesRegex(ValueError, "3.12.13 is required"):
                runtime_safety.validate_runtime_observation(
                    observation,
                    runtime=runtime,
                    resolved_python=executable,
                )
            observation["version"] = runtime_safety.EXPECTED_PYTHON_VERSION
            observation["basePrefix"] = str(runtime)
            with self.assertRaisesRegex(
                ValueError, "dedicated virtual environment"
            ):
                runtime_safety.validate_runtime_observation(
                    observation,
                    runtime=runtime,
                    resolved_python=executable,
                )

    def test_staged_runtime_is_published_with_one_rename(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            parent.chmod(0o700)
            staging = parent / ".corelm-linux-runtime-stage.test"
            staging.mkdir(mode=0o700)
            payload = staging / "payload"
            payload.write_text("complete\n", encoding="utf-8")
            destination = parent / "runtime"
            runtime_safety.publish_runtime(staging, destination)
            self.assertFalse(staging.exists())
            self.assertEqual(
                (destination / "payload").read_text(encoding="utf-8"),
                "complete\n",
            )

    @unittest.skipUnless(
        platform.python_version() == runtime_safety.EXPECTED_PYTHON_VERSION,
        "exact runtime validation requires the registered Python",
    )
    def test_moved_venv_reports_the_published_prefix(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            parent.chmod(0o700)
            staging = parent / ".corelm-linux-runtime-stage.test"
            completed = subprocess.run(
                [sys.executable, "-I", "-B", "-m", "venv", str(staging)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            runtime_safety.initialize_runtime_marker(staging)
            runtime_safety.validate_existing_runtime(staging)
            destination = parent / "runtime"
            runtime_safety.publish_runtime(staging, destination)
            result = runtime_safety.validate_existing_runtime(destination)
        self.assertEqual(result["runtime"], str(destination))


class LinuxRuntimeShellContractTests(unittest.TestCase):
    def test_first_offline_build_fails_before_staging_is_created(self):
        source = (LINUX_SCRIPTS / "build-runtime.sh").read_text(
            encoding="utf-8"
        )
        offline_rejection = source.index(
            'fail "first runtime build requires network access to registered wheels"'
        )
        staging_creation = source.index("mktemp -d")
        self.assertLess(offline_rejection, staging_creation)
        self.assertIn("trap cleanup EXIT", source)
        self.assertIn("publish-runtime", source)
        self.assertNotIn('rm -rf -- "$RUNTIME_DIR"', source)

    def test_doctor_checks_destinations_instead_of_checkout_disk(self):
        source = (LINUX_SCRIPTS / "doctor.sh").read_text(encoding="utf-8")
        self.assertIn("runtime_safety.py", source)
        self.assertIn("validate-paths", source)
        self.assertIn('--runtime "$RUNTIME_DIR"', source)
        self.assertIn('--cache "$HF_CACHE"', source)
        self.assertIn('--run "$RUN_TARGET"', source)
        self.assertNotIn('df -Pk "$PROJECT_DIR"', source)

    def test_run_passes_exact_evidence_target_to_build_preflight(self):
        source = (LINUX_SCRIPTS / "run-regression.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('CORELM_RUN_DIR="$RUN_DIR"', source)
        self.assertIn("build-runtime.sh", source)


if __name__ == "__main__":
    unittest.main()
