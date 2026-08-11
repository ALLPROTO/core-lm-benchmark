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

    def test_owner_tree_hardening_is_bounded_and_rejects_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / "runtime"
            root.mkdir(mode=0o775)
            root.chmod(0o775)
            payload = root / "payload"
            payload.write_bytes(b"runtime\n")
            payload.chmod(0o666)
            internal = root / "internal-link"
            internal.symlink_to(payload)
            sibling = base / "sibling"
            sibling.mkdir(mode=0o777)
            sibling.chmod(0o777)

            result = runtime_safety.harden_owner_tree(root)

            self.assertEqual(result["root"], str(root))
            self.assertEqual(result["paths"], 3)
            self.assertEqual(root.stat().st_mode & 0o022, 0)
            self.assertEqual(payload.stat().st_mode & 0o022, 0)
            self.assertTrue(internal.is_symlink())
            self.assertEqual(stat.S_IMODE(sibling.stat().st_mode), 0o777)

            outside = base / "outside"
            outside.write_bytes(b"outside\n")
            escaping = root / "escaping-link"
            escaping.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symlink escapes root"):
                runtime_safety.harden_owner_tree(root)


class LinuxPythonBootstrapContractTests(unittest.TestCase):
    def test_empty_bootstrap_cleanup_preserves_success_status(self):
        source = (LINUX_SCRIPTS / "bootstrap-python.sh").read_text(
            encoding="utf-8"
        )
        cleanup_body = source.split("cleanup() {\n", 1)[1].split(
            "\n}\n\non_signal()", 1
        )[0]
        self.assertIn('[ -n "$TEMP_DIRECTORY" ] || return 0', cleanup_body)
        completed = subprocess.run(
            ["/bin/sh"],
            input=(
                "set -eu\n"
                "TEMP_DIRECTORY=\n"
                "cleanup() {\n"
                f"{cleanup_body}\n"
                "}\n"
                "trap cleanup EXIT\n"
                "exit 0\n"
            ),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_bootstrap_receipt_rejects_installed_tree_byte_drift(self):
        source = (LINUX_SCRIPTS / "bootstrap-python.sh").read_text(
            encoding="utf-8"
        )
        receipt_program = source.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "python"
            root.mkdir(mode=0o700)
            payload = root / "payload.bin"
            payload.write_bytes(b"registered bytes\n")
            arguments = [
                sys.executable,
                "-I",
                "-B",
                "-c",
                receipt_program,
                "create",
                str(root),
                ".receipt.json",
                "3.12.13",
                "20260718",
                "x86_64-unknown-linux-gnu",
                "0" * 64,
            ]
            created = subprocess.run(
                arguments, check=False, capture_output=True, text=True
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            receipt = root / ".receipt.json"
            self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)

            arguments[5] = "validate"
            accepted = subprocess.run(
                arguments, check=False, capture_output=True, text=True
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

            payload.write_bytes(b"unexpected bytes\n")
            rejected = subprocess.run(
                arguments, check=False, capture_output=True, text=True
            )
            self.assertNotEqual(rejected.returncode, 0)

    def test_owner_local_bootstrap_is_fixed_safe_and_sudo_free(self):
        source = (LINUX_SCRIPTS / "bootstrap-python.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("PYTHON_RELEASE=3.12.13", source)
        self.assertIn("BUILD_RELEASE=20260718", source)
        self.assertIn(
            "7eea0959fa425c8aff3ea0a1352ee7d01"
            "d794b51439ed8f5fcfa017dbc0ec661",
            source,
        )
        self.assertIn("x86_64-unknown-linux-gnu-install_only.tar.gz", source)
        self.assertIn("validate_python_bootstrap_archive.py", source)
        self.assertIn("--no-same-owner", source)
        hardener = (LINUX_SCRIPTS / "runtime_safety.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("owner tree symlink escapes root", hardener)
        self.assertIn(".corelm-python312-stage.*", source)
        self.assertIn(".corelm-python-bootstrap-v1.json", source)
        self.assertIn("ARCHIVE_SIZE=111280988", source)
        self.assertIn('"treeSha256": tree_sha256', source)
        self.assertIn('"treeEntries": tree_entries', source)
        self.assertIn("receipt_operation validate", source)
        self.assertIn(
            'fail "owner-local Python changed during identity validation"',
            source,
        )

        prepare_body = source.split(
            "prepare_fresh_python() {\n", 1
        )[1].split("\n}\n\nvalidate_installed_python()", 1)[0]
        prepare_tree_call = 'validate_runtime_tree "$runtime"'
        prepare_identity_call = 'validate_python_identity "$runtime"'
        self.assertEqual(prepare_body.count(prepare_tree_call), 2)
        self.assertEqual(prepare_body.count(prepare_identity_call), 1)
        first_prepare_tree = prepare_body.index(prepare_tree_call)
        prepare_identity = prepare_body.index(prepare_identity_call)
        second_prepare_tree = prepare_body.index(
            prepare_tree_call, first_prepare_tree + 1
        )
        self.assertLess(first_prepare_tree, prepare_identity)
        self.assertLess(prepare_identity, second_prepare_tree)

        installed_body = source.split(
            "validate_installed_python() {\n", 1
        )[1].split('\n}\n\nif [ "$MODE" = harden ]', 1)[0]
        installed_tree_call = 'validate_runtime_tree "$TARGET"'
        installed_receipt_call = 'receipt_operation validate "$TARGET"'
        installed_identity_call = 'validate_python_identity "$TARGET"'
        self.assertEqual(installed_body.count(installed_tree_call), 1)
        self.assertEqual(installed_body.count(installed_receipt_call), 2)
        self.assertEqual(installed_body.count(installed_identity_call), 1)
        first_installed_receipt = installed_body.index(installed_receipt_call)
        installed_identity = installed_body.index(installed_identity_call)
        second_installed_receipt = installed_body.index(
            installed_receipt_call, first_installed_receipt + 1
        )
        self.assertLess(installed_body.index(installed_tree_call), first_installed_receipt)
        self.assertLess(first_installed_receipt, installed_identity)
        self.assertLess(installed_identity, second_installed_receipt)

        install_body = source.split(
            'TEMP_DIRECTORY=$(mktemp -d "$INSTALL_ROOT/', 1
        )[1]
        install_calls = [
            'prepare_fresh_python "$EXTRACT_ROOT/python"',
            'receipt_operation create "$EXTRACT_ROOT/python"',
            'receipt_operation validate "$EXTRACT_ROOT/python"',
            '/bin/mv "$EXTRACT_ROOT/python" "$TARGET"',
            "validate_installed_python",
        ]
        install_offsets = [install_body.index(call) for call in install_calls]
        self.assertEqual(install_offsets, sorted(install_offsets))
        self.assertNotIn("chmod -RP", source)
        self.assertNotIn("/usr/bin/sudo", source)
        self.assertNotIn("\nsudo ", source)

    def test_linux_commands_and_ci_use_owner_local_bootstrap(self):
        dispatcher = (ROOT / "corelm").read_text(encoding="utf-8")
        doctor = (LINUX_SCRIPTS / "doctor.sh").read_text(encoding="utf-8")
        build = (LINUX_SCRIPTS / "build-runtime.sh").read_text(
            encoding="utf-8"
        )
        test_gate = (ROOT / "scripts/verify-python.sh").read_text(
            encoding="utf-8"
        )
        finder = (LINUX_SCRIPTS / "find-python312.sh").read_text(
            encoding="utf-8"
        )
        verify_workflow = (
            ROOT / ".github/workflows/verify-linux.yml"
        ).read_text(encoding="utf-8")
        regression_workflow = (
            ROOT / ".github/workflows/real-qwen-linux-cpu.yml"
        ).read_text(encoding="utf-8")
        bootstrap_path = (
            ".local/share/corelm/linux-x86_64/"
            "python-3.12.13+20260718/bin/python3.12"
        )

        self.assertIn("linux:bootstrap", dispatcher)
        self.assertIn("bootstrap-python.sh", dispatcher)
        self.assertIn(bootstrap_path, finder)
        self.assertIn("${CORELM_LINUX_PYTHON+x}", finder)
        self.assertIn("--harden-installed", finder)
        self.assertIn("pinned Python executable escaped bootstrap root", finder)
        self.assertIn("base_prefix != expected_root", finder)
        self.assertIn("find-python312.sh", doctor)
        self.assertIn("find-python312.sh", build)
        self.assertIn("./corelm linux bootstrap", verify_workflow)
        self.assertIn("corelm-ci-linux-core-runtime", verify_workflow)
        self.assertIn('-m venv --copies "$core_runtime"', verify_workflow)
        workflow_venv = (
            'PYTHONDONTWRITEBYTECODE=1 \\\n'
            '            "$bootstrap_python" -I -B -m venv --copies '
            '"$core_runtime"'
        )
        workflow_harden = "./corelm linux bootstrap --harden-installed"
        build_step = verify_workflow.split(
            "      - name: Build exact-lock core verification runtime\n", 1
        )[1].split("      - name: Run Python and publication gates\n", 1)[0]
        self.assertEqual(build_step.count(workflow_venv), 1)
        self.assertEqual(build_step.count(workflow_harden), 2)
        first_harden = build_step.index(workflow_harden)
        second_harden = build_step.index(
            workflow_harden, first_harden + 1
        )
        self.assertLess(build_step.index(workflow_venv), first_harden)
        self.assertLess(first_harden, build_step.index("--mode initialize"))
        self.assertLess(build_step.index("/usr/bin/cmp"), second_harden)

        build_venv = (
            'PYTHONDONTWRITEBYTECODE=1 \\\n'
            '        "$PYTHON_BIN" -I -B -m venv "$STAGING_DIR"'
        )
        prepublish_python = 'PREPUBLISH_PYTHON=$("$PYTHON_FINDER")'
        prepublish_equality = '[ "$PREPUBLISH_PYTHON" = "$PYTHON_BIN" ]'
        publish_runtime = '"$SAFETY_SCRIPT" publish-runtime'
        final_python = 'FINAL_PYTHON=$("$PYTHON_FINDER")'
        final_equality = '[ "$FINAL_PYTHON" = "$PYTHON_BIN" ]'
        self.assertEqual(build.count(build_venv), 1)
        self.assertEqual(build.count(prepublish_python), 1)
        self.assertEqual(build.count(prepublish_equality), 1)
        self.assertEqual(build.count(final_python), 1)
        self.assertEqual(build.count(final_equality), 1)
        self.assertLess(build.index(build_venv), build.index("runtime_python="))
        self.assertLess(
            build.index(build_venv), build.index(prepublish_python)
        )
        self.assertLess(
            build.index(prepublish_python), build.index(prepublish_equality)
        )
        self.assertLess(
            build.index(prepublish_equality), build.index(publish_runtime)
        )
        self.assertLess(
            build.rindex("prepare_app_assets.py"), build.index(final_python)
        )
        self.assertLess(build.index(publish_runtime), build.index(final_python))
        self.assertLess(build.index(final_python), build.index(final_equality))
        self.assertLess(
            build.index(final_equality), build.index("LINUX RUNTIME BUILD PASS")
        )
        nested_bytecode_guard = "PYTHONDONTWRITEBYTECODE=1 \\"
        self.assertEqual(test_gate.count(nested_bytecode_guard), 1)
        env_start = test_gate.index("/usr/bin/env -i")
        guard_offset = test_gate.index(nested_bytecode_guard, env_start)
        nested_python = test_gate.index(
            '"$PYTHON_EXECUTABLE" -I -B', guard_offset
        )
        self.assertLess(env_start, guard_offset)
        self.assertLess(guard_offset, nested_python)
        python_step = verify_workflow.split(
            "      - name: Run Python and publication gates\n", 1
        )[1].split(
            "      - name: Verify exploratory real-Qwen pilot artifact\n", 1
        )[0]
        self.assertEqual(python_step.count("./corelm verify"), 1)
        self.assertEqual(python_step.count(workflow_harden), 1)
        self.assertLess(
            python_step.index("./corelm verify"),
            python_step.index(workflow_harden),
        )
        self.assertIn("umask 077", verify_workflow)
        self.assertIn("security/manage_local_runtime.py", verify_workflow)
        self.assertIn("security/verify_locked_environment.py", verify_workflow)
        self.assertIn("corelm-linux-base-distributions.before", verify_workflow)
        self.assertIn("corelm-linux-base-distributions.after", verify_workflow)
        self.assertEqual(verify_workflow.count("actions/setup-python"), 1)
        self.assertIn("./corelm linux bootstrap", regression_workflow)
        self.assertNotIn("actions/setup-python", regression_workflow)
        self.assertNotIn("normalize_ci_python_permissions", verify_workflow)
        self.assertNotIn("normalize_ci_python_permissions", regression_workflow)


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
