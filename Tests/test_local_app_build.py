import json
import os
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from RealLLM import prepare_app_assets
from RealLLM import verify_voidtoken_v5_development as shard_verifier
from security import generate_python_runtime_manifest
from security import manage_local_runtime
from security import verify_app_run_evidence
from security import verify_locked_environment
from security import verify_local_app_run


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "app-real-llm-evidence"


class LocalAppBuildTests(unittest.TestCase):
    def test_packager_has_no_author_specific_default_python_digest(self):
        source = (ROOT / "package_app.sh").read_text(encoding="utf-8")
        self.assertNotIn(
            "eb9d74b9c7cfdfb2c9b91614edb2c3607360ba46c5aa7fc4557b3a4a23e97cff",
            source,
        )
        self.assertIn("CORELM_REAL_LLM_PYTHON_SHA256", source)

    def test_local_workflow_shell_scripts_parse(self):
        for name in (
            "build_local_app.sh",
            "package_app.sh",
            "run_local_app_proof.sh",
            "run_tests.sh",
        ):
            completed = subprocess.run(
                ["/bin/sh", "-n", str(ROOT / name)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_proof_cannot_inherit_ci_skip_flags_or_runtime_pycache(self):
        proof = (ROOT / "run_local_app_proof.sh").read_text(encoding="utf-8")
        for variable in (
            "CORELM_SKIP_RUNTIME_INSTALL",
            "CORELM_SKIP_ASSET_PREPARATION",
            "CORELM_ASSETS_OFFLINE_ONLY",
            "CORELM_SKIP_MPS_CHECK",
            "CORELM_SKIP_SMOKE_TEST",
        ):
            self.assertIn(f"{variable}=0", proof)
        self.assertIn('BUILD_CONFIG=release', proof)
        self.assertIn('pycache_prefix=$VERIFY_CACHE', proof)
        tests = (ROOT / "run_tests.sh").read_text(encoding="utf-8")
        self.assertIn('pycache_prefix=$PYTHON_CACHE', tests)

    def test_asset_preparation_downloads_then_proves_offline_resolution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            cache.mkdir(mode=0o700)
            snapshot = cache / "hub" / "snapshot"
            snapshot.mkdir(parents=True)
            model = snapshot / "model.safetensors"
            validation = cache / "hub" / "validation.parquet"
            model.write_bytes(b"model")
            validation.write_bytes(b"validation")
            resolved = {
                "modelSnapshot": snapshot,
                "modelWeights": model,
                "validation": validation,
            }
            hostile_environment = {
                "HF_ENDPOINT": "https://example.invalid",
                "HF_HUB_CACHE": str(root / "escaped-hub"),
                "HF_XET_CACHE": str(root / "escaped-xet"),
                "TRANSFORMERS_CACHE": str(root / "escaped-transformers"),
            }
            with mock.patch.dict(
                    os.environ,
                    hostile_environment,
                    clear=False,
            ), mock.patch.object(
                    prepare_app_assets,
                    "_download_validation_only",
                    side_effect=[resolved, resolved],
            ) as downloader:
                observed = prepare_app_assets.prepare_assets(cache)
                self.assertEqual(
                    os.environ["HF_HOME"],
                    str(cache.resolve()),
                )
                self.assertEqual(
                    os.environ["HF_HUB_CACHE"],
                    str(cache.resolve() / "hub"),
                )
                self.assertEqual(
                    os.environ["HF_XET_CACHE"],
                    str(cache.resolve() / "xet"),
                )
                self.assertNotIn("TRANSFORMERS_CACHE", os.environ)
                self.assertEqual(
                    downloader.call_args_list,
                    [
                        mock.call(local_files_only=False),
                        mock.call(local_files_only=True),
                    ],
                )
            self.assertEqual(observed, resolved)
            self.assertEqual(cache.stat().st_mode & 0o777, 0o700)

    def test_asset_preparation_offline_mode_never_requests_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            cache.mkdir(mode=0o700)
            snapshot = cache / "hub" / "snapshot"
            snapshot.mkdir(parents=True)
            model = snapshot / "model.safetensors"
            validation = cache / "hub" / "validation.parquet"
            model.write_bytes(b"model")
            validation.write_bytes(b"validation")
            resolved = {
                "modelSnapshot": snapshot,
                "modelWeights": model,
                "validation": validation,
            }
            with mock.patch.dict(os.environ), mock.patch.object(
                    prepare_app_assets,
                    "_download_validation_only",
                    return_value=resolved,
            ) as downloader:
                prepare_app_assets.prepare_assets(
                    cache,
                    offline_only=True,
                )
            self.assertEqual(
                downloader.call_args_list,
                [mock.call(local_files_only=True), mock.call(local_files_only=True)],
            )

    def test_portable_macos_shard_accepts_another_312_patch_and_os(self):
        result = json.loads(
            (EVIDENCE / "validation-064-071.json").read_text(encoding="utf-8")
        )
        result["environment"]["python"] = "3.12.99"
        result["environment"]["platform"] = "macOS-27.0-arm64-arm-64bit"
        result["resultSHA256"] = shard_verifier._canonical_digest_without(
            result,
            "resultSHA256",
        )
        artifact = {
            "path": "validation-064-071.json",
            "startBlock": 64,
            "blocks": 8,
            "resultSHA256": result["resultSHA256"],
        }
        errors, records, baselines = shard_verifier._verify_shard(
            result,
            artifact,
            portable_macos_environment=True,
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(records), 8)
        self.assertEqual(len(baselines), 8)

    def test_fresh_run_does_not_require_historical_checksums(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run"
            app = root / "CoreLMBenchmark.app"
            resources = app / "Contents" / "Resources"
            executable = app / "Contents" / "MacOS" / "CoreLMBenchmarkApp"
            runner = resources / "RealLLM" / "develop_voidtoken_v5.py"
            manifest = resources / "python-runtime-manifest.json"
            info_plist = app / "Contents" / "Info.plist"
            run.mkdir()
            runner.parent.mkdir(parents=True)
            executable.parent.mkdir(parents=True)

            result_path = run / "validation-064-071.json"
            receipt_path = run / "app-run-receipt.json"
            shutil.copy2(EVIDENCE / result_path.name, result_path)
            shutil.copy2(ROOT / "RealLLM" / runner.name, runner)
            executable.write_bytes(b"locally built executable")

            receipt = json.loads(
                (EVIDENCE / receipt_path.name).read_text(encoding="utf-8")
            )
            manifest.write_text(
                json.dumps(
                    {
                        "pythonExecutableSHA256":
                            receipt["worker"]["pythonExecutableSHA256"],
                        "pythonVersion": "3.12.13",
                    }
                ),
                encoding="utf-8",
            )
            with info_plist.open("wb") as handle:
                plistlib.dump(
                    {
                        "CFBundleIdentifier": "com.corelm.benchmark",
                        "CFBundleShortVersionString":
                            receipt["application"]["version"],
                    },
                    handle,
                )
            receipt["application"]["executableSHA256"] = (
                verify_app_run_evidence._sha256(executable)
            )
            receipt["worker"]["runtimeManifestSHA256"] = (
                verify_app_run_evidence._sha256(manifest)
            )
            receipt["result"]["resultFileSHA256"] = (
                verify_app_run_evidence._sha256(result_path)
            )
            receipt_path.write_text(
                json.dumps(receipt, sort_keys=True),
                encoding="utf-8",
            )

            with (
                mock.patch.object(
                    verify_app_run_evidence,
                    "_verify_local_bundle",
                ),
                mock.patch.object(
                    verify_app_run_evidence,
                    "validate_manifest_files",
                ),
            ):
                result = verify_app_run_evidence.verify_fresh_run(run, app)
            self.assertTrue(result["aggregates"][0]["pass"])

    def test_fresh_challenge_must_be_bound_to_v3_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run"
            app = root / "CoreLMBenchmark.app"
            resources = app / "Contents" / "Resources"
            executable = app / "Contents" / "MacOS" / "CoreLMBenchmarkApp"
            runner = resources / "RealLLM" / "develop_voidtoken_v5.py"
            manifest = resources / "python-runtime-manifest.json"
            info_plist = app / "Contents" / "Info.plist"
            run.mkdir()
            runner.parent.mkdir(parents=True)
            executable.parent.mkdir(parents=True)
            result_path = run / "validation-064-071.json"
            receipt_path = run / "app-run-receipt.json"
            shutil.copy2(EVIDENCE / result_path.name, result_path)
            shutil.copy2(ROOT / "RealLLM" / runner.name, runner)
            executable.write_bytes(b"locally built executable")
            receipt = json.loads(
                (EVIDENCE / receipt_path.name).read_text(encoding="utf-8")
            )
            manifest.write_text(
                json.dumps(
                    {
                        "pythonExecutableSHA256":
                            receipt["worker"]["pythonExecutableSHA256"],
                        "pythonVersion": "3.12.13",
                    }
                ),
                encoding="utf-8",
            )
            receipt["application"]["executableSHA256"] = (
                verify_app_run_evidence._sha256(executable)
            )
            receipt["worker"]["runtimeManifestSHA256"] = (
                verify_app_run_evidence._sha256(manifest)
            )
            receipt["result"]["resultFileSHA256"] = (
                verify_app_run_evidence._sha256(result_path)
            )
            with info_plist.open("wb") as handle:
                plistlib.dump(
                    {
                        "CFBundleIdentifier": "com.corelm.benchmark",
                        "CFBundleShortVersionString":
                            receipt["application"]["version"],
                    },
                    handle,
                )
            challenge = "a" * 64
            receipt["schemaVersion"] = "corelm-macos-app-real-llm-run-v3"
            receipt["challengeNonce"] = challenge
            receipt_path.write_text(
                json.dumps(receipt, sort_keys=True),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    verify_app_run_evidence,
                    "_verify_local_bundle",
                ),
                mock.patch.object(
                    verify_app_run_evidence,
                    "validate_manifest_files",
                ),
            ):
                verify_app_run_evidence.verify_fresh_run(
                    run,
                    app,
                    challenge_nonce=challenge,
                )
                with self.assertRaisesRegex(ValueError, "proof challenge"):
                    verify_app_run_evidence.verify_fresh_run(
                        run,
                        app,
                        challenge_nonce="b" * 64,
                    )

    def test_minimal_runtime_manifest_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "fields are not exact"):
            generate_python_runtime_manifest.validate_manifest_files(
                {"pythonExecutableSHA256": "0" * 64}
            )

    def test_runtime_marker_is_required_and_validated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / "runtime"
            base = root / "base"
            runtime.mkdir(mode=0o700)
            base.mkdir(mode=0o700)
            (runtime / "bin").mkdir()
            (runtime / "bin").chmod(0o700)
            base_python = base / "python3.12"
            base_python.write_bytes(b"#!/bin/sh\nexit 0\n")
            base_python.chmod(0o700)
            configuration = runtime / "pyvenv.cfg"
            configuration.write_text(
                "home = /usr/bin\n",
                encoding="utf-8",
            )
            configuration.chmod(0o600)
            (runtime / "bin" / "python").symlink_to(base_python)
            with self.assertRaises(OSError):
                manage_local_runtime.validate_existing_runtime(runtime)
            marker = runtime / manage_local_runtime.MARKER_NAME
            marker.write_bytes(manage_local_runtime.MARKER_BYTES)
            marker.chmod(0o600)
            with mock.patch.object(
                manage_local_runtime,
                "_safe_existing_chain",
            ):
                manage_local_runtime.validate_existing_runtime(runtime)

    def test_runtime_path_alias_and_project_interior_are_rejected(self):
        with mock.patch.object(
            manage_local_runtime,
            "_safe_existing_chain",
        ):
            with self.assertRaisesRegex(ValueError, "canonical"):
                manage_local_runtime.canonical_target(
                    "/tmp/../tmp/corelm-runtime",
                    str(ROOT),
                )
            with self.assertRaisesRegex(ValueError, "unsafe runtime target"):
                manage_local_runtime.canonical_target(
                    str(ROOT / "runtime"),
                    str(ROOT),
                )

    def test_loadable_runtime_symlink_cannot_escape_or_target_pycache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base"
            runtime = root / "runtime"
            outside = root / "outside.py"
            cached = base / "lib" / "__pycache__" / "cached.pyc"
            link = runtime / "lib" / "module.py"
            cached.parent.mkdir(parents=True)
            link.parent.mkdir(parents=True)
            outside.write_bytes(b"outside")
            cached.write_bytes(b"cached")
            link.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "escapes"):
                generate_python_runtime_manifest._require_symlink_within_roots(
                    link,
                    "lib/module.py",
                    (base, runtime),
                )
            link.unlink()
            link.symlink_to(cached)
            with self.assertRaisesRegex(ValueError, "excluded bytecode"):
                generate_python_runtime_manifest._require_symlink_within_roots(
                    link,
                    "lib/module.py",
                    (base, runtime),
                )

    def test_exact_locked_distribution_closure_rejects_extras(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / "runtime"
            runtime.mkdir()
            lock = root / "requirements.lock"
            lock.write_text(
                "Example_Package==1.2.3 \\\n"
                "    --hash=sha256:" + "0" * 64 + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                verify_locked_environment.locked_distributions([lock]),
                {"example-package": "1.2.3"},
            )
            with (
                mock.patch.object(
                    verify_locked_environment.sys,
                    "prefix",
                    str(runtime),
                ),
                mock.patch.object(
                    verify_locked_environment.sys,
                    "base_prefix",
                    str(root),
                ),
                mock.patch.object(
                    verify_locked_environment,
                    "installed_distributions",
                    return_value={
                        "example-package": "1.2.3",
                        "unexpected": "9.9",
                    },
                ),
                self.assertRaisesRegex(ValueError, "extra=unexpected"),
            ):
                verify_locked_environment.verify_environment(runtime, [lock])

    def test_latest_complete_run_ignores_incomplete_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incomplete = root / "incomplete"
            complete = root / "complete"
            incomplete.mkdir()
            complete.mkdir()
            (incomplete / "app-run-receipt.json").write_text("{}", encoding="utf-8")
            (complete / "app-run-receipt.json").write_text("{}", encoding="utf-8")
            (complete / "validation-064-071.json").write_text("{}", encoding="utf-8")
            self.assertEqual(
                verify_local_app_run.latest_complete_run(root),
                complete.resolve(),
            )


if __name__ == "__main__":
    unittest.main()
