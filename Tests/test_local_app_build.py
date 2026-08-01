import json
import copy
import hashlib
import io
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import tarfile
import unittest
import struct
from pathlib import Path
from unittest import mock

from RealLLM import prepare_app_assets
from RealLLM import verify_voidtoken_v5_development as shard_verifier
from security import generate_build_provenance
from security import generate_python_runtime_manifest
from security import manage_local_runtime
from security import verify_app_run_evidence
from security import verify_locked_environment
from security import verify_local_app_run
from security import verify_primary_evidence
from security import verify_primary_replay
from security import validate_python_bootstrap_archive
from RealLLM.voidtoken_v5 import VoidTokenV5Backend

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "app-real-llm-evidence"


class LocalAppBuildTests(unittest.TestCase):
    def test_primary_verifier_derives_dense_bytes_from_fixed_geometry(self):
        expected = verify_primary_evidence.EXPECTED_BF16_BYTES_PER_BLOCK
        records = [
            {"denseBF16Bytes": expected}
            for _ in verify_primary_evidence.EXPECTED_BLOCKS
        ]
        baselines = copy.deepcopy(records)
        self.assertEqual(
            verify_primary_evidence._verify_dense_bf16_geometry(
                records, baselines
            ),
            verify_primary_evidence.EXPECTED_DENSE_BF16_BYTES,
        )

        for record in records:
            record["denseBF16Bytes"] += 2
        for baseline in baselines:
            baseline["denseBF16Bytes"] += 2
        with self.assertRaisesRegex(
            ValueError, "dense BF16 geometry is inconsistent"
        ):
            verify_primary_evidence._verify_dense_bf16_geometry(
                records, baselines
            )

    def test_python_bootstrap_archive_uses_tar_hardlink_semantics(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "runtime.tar.gz"
            with tarfile.open(archive_path, mode="w:gz") as archive:
                payload = b"registered-runtime"
                regular = tarfile.TarInfo("python/lib/runtime")
                regular.size = len(payload)
                archive.addfile(regular, io.BytesIO(payload))
                hardlink = tarfile.TarInfo("python/a/escape")
                hardlink.type = tarfile.LNKTYPE
                hardlink.linkname = "../outside"
                archive.addfile(hardlink)

            with self.assertRaisesRegex(
                validate_python_bootstrap_archive.ArchiveValidationError,
                "archive link escapes Python root",
            ):
                validate_python_bootstrap_archive.validate_archive(
                    archive_path
                )

    def test_python_bootstrap_archive_rejects_normalized_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "runtime.tar.gz"
            with tarfile.open(archive_path, mode="w:gz") as archive:
                first = tarfile.TarInfo("python/lib/runtime")
                first.size = 0
                archive.addfile(first, io.BytesIO())
                duplicate = tarfile.TarInfo("python/lib/./runtime")
                duplicate.size = 0
                archive.addfile(duplicate, io.BytesIO())

            with self.assertRaisesRegex(
                validate_python_bootstrap_archive.ArchiveValidationError,
                "duplicate archive entry",
            ):
                validate_python_bootstrap_archive.validate_archive(
                    archive_path
                )

    def test_heavy_replay_decoder_is_clean_room_and_byte_exact(self):
        source = (
            ROOT / "security" / "verify_primary_replay.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("from RealLLM", source)
        self.assertNotIn("import RealLLM", source)

        rng = np.random.default_rng(20260731)
        matrix = rng.normal(size=(383, 256)).astype(np.float32)
        representation = VoidTokenV5Backend.encode(
            matrix,
            bits=9,
            group_size=128,
            transform_block_size=128,
            layer_index=0,
            scale_compression="zlib-9",
            code_compression="zlib-9",
            sign_mode="none",
        )
        decoded, metadata = verify_primary_replay._decode_container(
            representation.to_bytes(), 0, np
        )
        self.assertTrue(np.array_equal(decoded, representation.reconstructed))
        self.assertEqual(
            metadata["reconstructionSha256"],
            representation.metadata["reconstructionSha256"],
        )

        corrupted = bytearray(representation.to_bytes())
        corrupted[-1] ^= 1
        with self.assertRaises(ValueError):
            verify_primary_replay._decode_container(bytes(corrupted), 0, np)

    def test_heavy_replay_loss_tolerance_is_explicit_and_fail_closed(self):
        self.assertTrue(verify_primary_replay._loss_close(1.0, 1.0))
        self.assertTrue(
            verify_primary_replay._loss_close(
                1.0 + verify_primary_replay.LOSS_ABSOLUTE_TOLERANCE / 2,
                1.0,
            )
        )
        self.assertFalse(verify_primary_replay._loss_close(1.001, 1.0))
        self.assertFalse(verify_primary_replay._loss_close("1.0", 1.0))

    def test_fresh_receipt_binds_clean_source_and_bundled_provenance(self):
        document = {
            "schemaVersion": "corelm-build-provenance-v1",
            "source": {
                "archiveManifestSHA256": None,
                "commit": "1" * 40,
                "dirty": False,
                "exactTag": None,
                "mode": "git",
                "remote": (
                    "https://github.com/ALLPROTO/core-lm-benchmark.git"
                ),
                "tree": "2" * 40,
            },
            "toolchain": {
                "developerTools": {
                    "buildVersion": None,
                    "identifier": "com.apple.pkg.CLTools_Executables",
                    "kind": "command-line-tools",
                    "version": "26.6.0.0.1781586589",
                },
                "macOS": {
                    "architecture": "arm64",
                    "buildVersion": "25D125",
                    "productName": "macOS",
                    "productVersion": "26.3",
                },
                "sdk": {
                    "buildVersion": "25F70",
                    "canonicalName": "macosx",
                    "version": "26.5",
                },
                "swift": {
                    "compiler": "swift-frontend",
                    "compilerSHA256": "a" * 64,
                    "target": "arm64-apple-macosx26.0",
                    "version": (
                        "Apple Swift version 6.3.3 "
                        "(swiftlang-6.3.3.1.3)"
                    ),
                },
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            app = Path(temporary) / "CoreLMBenchmark.app"
            bundled = (
                app
                / "Contents"
                / "Resources"
                / "build-provenance.json"
            )
            bundled.parent.mkdir(parents=True)
            raw = generate_build_provenance.canonical_json_bytes(document)
            bundled.write_bytes(raw)
            receipt = {
                "document": document,
                "path": "Resources/build-provenance.json",
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            observed = (
                verify_app_run_evidence._verify_build_provenance_receipt(
                    receipt,
                    app,
                    compare_source_tree=False,
                )
            )
            self.assertEqual(observed, document)

            forged = copy.deepcopy(receipt)
            forged["document"]["source"]["dirty"] = True
            forged_raw = generate_build_provenance.canonical_json_bytes(
                forged["document"]
            )
            forged["sha256"] = hashlib.sha256(forged_raw).hexdigest()
            with self.assertRaisesRegex(ValueError, "dirty source"):
                verify_app_run_evidence._verify_build_provenance_receipt(
                    forged,
                    None,
                    compare_source_tree=False,
                )

    def test_clean_room_parser_reads_raw_container_and_rejects_tampering(self):
        matrix = np.zeros((383, 256), dtype=np.float32)
        representation = VoidTokenV5Backend.encode(
            matrix,
            bits=9,
            group_size=128,
            transform_block_size=128,
            layer_index=0,
            scale_compression="zlib-9",
            code_compression="zlib-9",
            sign_mode="none",
        )
        raw = representation.to_bytes()
        expected = {
            "layerIndex": 0,
            "metadata": representation.metadata,
            "payloadBytes": representation.payload_bytes,
            "containerBytes": len(raw),
            "containerSHA256": hashlib.sha256(raw).hexdigest(),
        }
        payload_bytes, _ = verify_primary_evidence._parse_container(
            raw,
            block_index=64,
            layer_index=0,
            expected_manifest=expected,
        )
        self.assertEqual(payload_bytes, representation.payload_bytes)
        corrupted = bytearray(raw)
        corrupted[-1] ^= 1
        with self.assertRaises(ValueError):
            verify_primary_evidence._parse_container(
                bytes(corrupted),
                block_index=64,
                layer_index=0,
                expected_manifest=expected,
            )

    @staticmethod
    def _token_metric_fixture():
        blocks = []
        records = []
        baselines = []
        for block_index in range(64, 72):
            token_ids = [
                (block_index * 512 + offset) % 151_936
                for offset in range(512)
            ]
            token_bytes = b"".join(
                struct.pack("<I", token_id) for token_id in token_ids
            )
            token_sha = hashlib.sha256(token_bytes).hexdigest()
            tokens = [
                {
                    "offset": offset,
                    "targetTokenId": token_ids[384 + offset],
                    "baselineLossNat": 1.0 + (offset / 10_000),
                    "candidateLossNat": 1.001 + (offset / 10_000),
                    "baselineTop1TokenId": offset,
                    "candidateTop1TokenId": offset,
                    "top1Agrees": True,
                }
                for offset in range(128)
            ]
            baseline_mean = verify_primary_evidence._ordered_binary64_mean(
                [token["baselineLossNat"] for token in tokens]
            )
            candidate_mean = verify_primary_evidence._ordered_binary64_mean(
                [token["candidateLossNat"] for token in tokens]
            )
            blocks.append(
                {
                    "blockIndex": block_index,
                    "tokenIds": token_ids,
                    "predictionTokens": 128,
                    "tokens": tokens,
                }
            )
            records.append(
                {
                    "blockIndex": block_index,
                    "tokenIdsSHA256": token_sha,
                    "baselineNLLNatPerToken": baseline_mean,
                    "candidateNLLNatPerToken": candidate_mean,
                    "deltaNLLNatPerToken": candidate_mean - baseline_mean,
                    "top1AgreementCount": 128,
                    "top1Agreement": 1.0,
                }
            )
            baselines.append({"tokenIdsSHA256": token_sha})
        return (
            {
                "schemaVersion": verify_primary_evidence.TOKEN_SCHEMA,
                "blocks": blocks,
            },
            {"records": records, "baselines": baselines},
        )

    def test_token_metric_recomputation_rejects_loss_target_and_id_tampering(
        self,
    ):
        token_document, result = self._token_metric_fixture()
        summary = verify_primary_evidence._verify_token_metrics(
            token_document, result
        )
        self.assertEqual(summary["predictionTokens"], 1024)
        self.assertEqual(summary["top1Agreement"], 1.0)

        forged_loss = copy.deepcopy(token_document)
        forged_loss["blocks"][0]["tokens"][0]["candidateLossNat"] += 0.5
        with self.assertRaisesRegex(ValueError, "recompute"):
            verify_primary_evidence._verify_token_metrics(forged_loss, result)

        forged_target = copy.deepcopy(token_document)
        forged_target["blocks"][0]["tokens"][0]["targetTokenId"] += 1
        with self.assertRaisesRegex(ValueError, "target"):
            verify_primary_evidence._verify_token_metrics(forged_target, result)

        forged_source = copy.deepcopy(token_document)
        forged_source["blocks"][0]["tokenIds"][0] += 1
        with self.assertRaisesRegex(ValueError, "digest"):
            verify_primary_evidence._verify_token_metrics(forged_source, result)

    def test_release_surface_is_version_free_and_proof_only(self):
        content = (ROOT / "App" / "Sources" / "ContentView.swift").read_text(
            encoding="utf-8"
        )
        store = (
            ROOT / "App" / "Sources" / "BenchmarkStore.swift"
        ).read_text(encoding="utf-8")
        application = (
            ROOT / "App" / "Sources" / "CoreLMBenchmarkApp.swift"
        ).read_text(encoding="utf-8")

        self.assertIn('Label("Compression Proof"', content)
        self.assertIn('Button("Run Compression Proof")', content)
        self.assertIn('"VoidToken Codec"', content)
        for stale in (
            "Development Run",
            "Compression Comparison",
            "Stability and Invariants",
            "Saved Runs",
            "Evidence Report",
            "Input Generator",
            "struct ControlsView",
            "struct LiveRunView",
            "struct MethodTable",
            '"VoidToken v5"',
            '"VoidToken v5 · candidate 32 · MPS"',
            '"Run Real Qwen"',
            '"Real Qwen Test"',
            '? "Real LLM" : "Live Run"',
        ):
            self.assertNotIn(stale, content)
        for stale in (
            'format: "Qwen v5 ',
            "The app result does not use frozen candidate 32.",
            "The result configuration is not the frozen VoidToken v5 candidate.",
        ):
            self.assertNotIn(stale, store)
        self.assertNotIn('Button("Open Development Result…")', application)

        models = (ROOT / "App" / "Sources" / "Models.swift").read_text(
            encoding="utf-8"
        )
        self.assertIn("enum Verdict", models)
        self.assertIn("enum ModuleState", models)
        self.assertNotIn("BenchmarkResult", models)
        self.assertNotIn("RunSettings", models)

    def test_final_bundle_and_default_gates_exclude_synthetic_benchmark(self):
        package = (ROOT / "package_app.sh").read_text(encoding="utf-8")
        verifier = (
            ROOT / "security" / "verify_app_bundle.sh"
        ).read_text(encoding="utf-8")
        build = (ROOT / "build_local_app.sh").read_text(encoding="utf-8")
        tests = (ROOT / "run_tests.sh").read_text(encoding="utf-8")
        workflow = (
            ROOT / ".github" / "workflows" / "verify.yml"
        ).read_text(encoding="utf-8")

        self.assertNotIn("BenchmarkCore", package)
        self.assertIn(
            "release bundle must not contain the synthetic BenchmarkCore",
            verifier,
        )
        self.assertIn(
            "release bundle must contain exactly seven declared resources",
            verifier,
        )
        self.assertIn(
            "'BenchmarkCore|corelm_benchmark|synthetic'",
            verifier,
        )
        self.assertNotIn("BenchmarkCore/corelm_benchmark.py", verifier)
        self.assertIn("--app-smoke-run", build)
        self.assertNotIn('CoreLMBenchmarkApp" --smoke-run', build)
        self.assertNotIn("Tests.test_benchmark", tests)
        self.assertNotIn("Tests.test_publication_archives", tests)
        self.assertNotIn("unittest discover", tests)
        self.assertNotIn("BenchmarkCore/verify_evidence.py", workflow)

    def test_packaged_real_llm_runner_lists_candidates_without_benchmark_core(
        self,
    ):
        packaged_files = (
            "__init__.py",
            "benchmark_real_llm.py",
            "codecs.py",
            "develop_voidtoken_v5.py",
            "voidtoken_v5.py",
        )
        package_source = (ROOT / "package_app.sh").read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            resources = (
                temporary_root
                / "CoreLMBenchmark.app"
                / "Contents"
                / "Resources"
            )
            bundled_real_llm = resources / "RealLLM"
            isolated_working_directory = (
                temporary_root / "empty-working-directory"
            )
            bundled_real_llm.mkdir(parents=True)
            isolated_working_directory.mkdir()

            for filename in packaged_files:
                self.assertIn(filename, package_source)
                shutil.copy2(
                    ROOT / "RealLLM" / filename,
                    bundled_real_llm / filename,
                )

            self.assertFalse((resources / "BenchmarkCore").exists())

            environment = os.environ.copy()
            for variable in ("PYTHONHOME", "PYTHONPATH"):
                environment.pop(variable, None)
            environment.update(
                {
                    "HF_DATASETS_OFFLINE": "1",
                    "HF_HUB_OFFLINE": "1",
                    "PYTHONNOUSERSITE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                }
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(bundled_real_llm / "develop_voidtoken_v5.py"),
                    "--list-candidates",
                ],
                cwd=isolated_working_directory,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            candidate_lines = completed.stdout.splitlines()
            self.assertGreater(len(candidate_lines), 1)
            self.assertTrue(candidate_lines[0].startswith("0: {"))
            self.assertNotIn("BenchmarkCore", completed.stderr)
            self.assertNotIn("corelm_benchmark", completed.stderr)

    def test_final_user_docs_and_paths_are_separate_from_versions(self):
        for relative in (
            "README.md",
            "ARCHITECTURE.md",
            "docs/BUILD_AND_VERIFY.md",
            "docs/RESULTS.md",
            "docs/LIMITATIONS.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            for versioned_label in (
                "VoidToken v3",
                "VoidToken v4",
                "VoidToken v5",
                "Qwen v5",
                "candidate 32",
            ):
                self.assertNotIn(versioned_label, text, relative)

        history = (
            ROOT / "docs" / "development" / "HISTORY.md"
        ).read_text(encoding="utf-8")
        self.assertIn("VoidToken v3", history)
        self.assertIn("VoidToken v5", history)

        build_script = (ROOT / "build_local_app.sh").read_text(
            encoding="utf-8"
        )
        package_script = (ROOT / "package_app.sh").read_text(
            encoding="utf-8"
        )
        proof_script = (ROOT / "run_local_app_proof.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(".cache/corelm-app-runtime", build_script)
        self.assertIn(".cache/corelm-model-assets", build_script)
        self.assertIn(".cache/corelm-app-runtime", package_script)
        self.assertIn(".cache/corelm-proof-runtimes", proof_script)
        for source in (build_script, package_script, proof_script):
            self.assertNotIn("corelm-real-llm-app-runtime-v1", source)

        plist = plistlib.loads((ROOT / "App" / "Info.plist").read_bytes())
        self.assertEqual(plist["CFBundleName"], "Core LM Benchmark")
        self.assertEqual(plist["CFBundleShortVersionString"], "1.0.0")
        self.assertEqual(plist["CFBundleVersion"], "6")

    def test_packager_has_no_author_specific_default_python_digest(self):
        source = (ROOT / "package_app.sh").read_text(encoding="utf-8")
        self.assertNotIn(
            "eb9d74b9c7cfdfb2c9b91614edb2c3607360ba46c5aa7fc4557b3a4a23e97cff",
            source,
        )
        self.assertIn("CORELM_REAL_LLM_PYTHON_SHA256", source)

    def test_local_workflow_shell_scripts_parse(self):
        for name in (
            "bootstrap_python312_macos.sh",
            "build_local_app.sh",
            "doctor.sh",
            "package_app.sh",
            "prepare_offline_inputs.sh",
            "run_local_app_proof.sh",
            "run_tests.sh",
            "security/find_python312.sh",
            "security/validate_proof_challenge.sh",
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
            "CORELM_SKIP_MEMORY_CHECK",
            "CORELM_SKIP_MPS_CHECK",
            "CORELM_SKIP_SMOKE_TEST",
        ):
            self.assertIn(f"{variable}=0", proof)
        self.assertIn('CORELM_ASSETS_OFFLINE_ONLY="$OFFLINE"', proof)
        self.assertIn('CORELM_OFFLINE="$OFFLINE"', proof)
        self.assertIn(
            'CORELM_PYPI_INDEX_URL="$PYPI_INDEX_URL"', proof
        )
        self.assertIn('CORELM_HF_ENDPOINT="$HF_ENDPOINT"', proof)
        self.assertIn('BUILD_CONFIG=release', proof)
        self.assertIn('pycache_prefix=$VERIFY_CACHE', proof)
        self.assertIn("security/verify_primary_replay.py", proof)
        self.assertIn("independent heavy replay", proof)
        self.assertGreaterEqual(proof.count("/usr/bin/env -i"), 3)
        self.assertIn(
            'run_clean "$PROJECT_DIR/security/verify_app_bundle.sh"',
            proof,
        )
        self.assertIn(
            'run_clean "$RUNTIME_DIR/bin/python" -I -B -X', proof
        )
        self.assertIn(
            "/usr/bin/nice -n 10 /usr/bin/env -i", proof
        )
        for hostile in (
            "DYLD_INSERT_LIBRARIES",
            "DYLD_LIBRARY_PATH",
            "PYTORCH_MPS_FAST_MATH",
            "PYTORCH_ENABLE_MPS_FALLBACK",
        ):
            self.assertNotIn(f'${{{hostile}', proof)
        tests = (ROOT / "run_tests.sh").read_text(encoding="utf-8")
        self.assertIn('pycache_prefix=$PYTHON_CACHE', tests)

    def test_doctor_and_build_enforce_random_mac_prerequisites(self):
        doctor = (ROOT / "doctor.sh").read_text(encoding="utf-8")
        build = (ROOT / "build_local_app.sh").read_text(encoding="utf-8")
        proof = (ROOT / "run_local_app_proof.sh").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/verify.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('swift_major" -ge 6', doctor)
        self.assertIn("MINIMUM_FREE_GB=6", doctor)
        self.assertIn("MINIMUM_MEMORY_GB=8", doctor)
        self.assertIn("--skip-memory-check", doctor)
        self.assertIn("CORELM_SKIP_MEMORY_CHECK", build)
        self.assertIn("CORELM_SKIP_MEMORY_CHECK=1", workflow)
        self.assertIn('launchctl print "gui/$current_uid"', doctor)
        self.assertIn("--proto '=https'", doctor)
        self.assertIn('"$PROJECT_DIR/doctor.sh" "$@"', build)
        self.assertIn('/usr/bin/shlock -p "$$"', proof)

    def test_owner_local_python_bootstrap_is_pinned_and_has_no_sudo(self):
        bootstrap = (ROOT / "bootstrap_python312_macos.sh").read_text(
            encoding="utf-8"
        )
        resolver = (
            ROOT / "security" / "find_python312.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("PYTHON_RELEASE=3.12.13", bootstrap)
        self.assertIn("BUILD_RELEASE=20260718", bootstrap)
        self.assertIn(
            "62aeee6161d57303a71a138b75fd5cc6f"
            "b8c89c4b1d9c7f0a052d89fa0b6652b",
            bootstrap,
        )
        self.assertIn("--connect-timeout 30", bootstrap)
        self.assertIn("--max-time 600", bootstrap)
        self.assertIn(
            "validate_python_bootstrap_archive.py", bootstrap
        )
        validator = (
            ROOT / "security" / "validate_python_bootstrap_archive.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Tar hardlink", validator)
        self.assertIn("duplicate archive entry", validator)
        self.assertIn("archive link escapes Python root", validator)
        self.assertIn("extracted symlink escapes runtime", bootstrap)
        self.assertNotIn("/usr/bin/sudo", bootstrap)
        self.assertIn(
            '.local/share/corelm/python-3.12.13/bin/python3.12',
            resolver,
        )

    def test_random_user_docs_expose_bootstrap_offline_and_hardware_boundary(
        self,
    ):
        documents = {
            relative: (ROOT / relative).read_text(encoding="utf-8")
            for relative in (
                "README.md",
                "docs/BUILD_AND_VERIFY.md",
                "SECURITY.md",
                "publication/reproducibility/README.md",
            )
        }
        digest = (
            "62aeee6161d57303a71a138b75fd5cc6f"
            "b8c89c4b1d9c7f0a052d89fa0b6652b"
        )
        for relative, text in documents.items():
            self.assertIn("3.12.13", text, relative)
            self.assertIn("python-build-standalone", text, relative)
            self.assertIn(digest, text, relative)
            self.assertNotIn("/Users/", text, relative)
            self.assertNotIn(".cache/codex", text, relative)

        for relative in (
            "README.md",
            "docs/BUILD_AND_VERIFY.md",
            "publication/reproducibility/README.md",
        ):
            text = documents[relative]
            self.assertIn("./doctor.sh", text, relative)
            self.assertIn("./prepare_offline_inputs.sh", text, relative)
            self.assertIn("CORELM_OFFLINE=1", text, relative)
            self.assertIn("8 GB", text, relative)
            self.assertIn("6 GiB", text, relative)
            self.assertIn("notarization", text, relative)

    def test_offline_proof_keeps_hash_checks_and_disables_indexes(self):
        build = (ROOT / "build_local_app.sh").read_text(encoding="utf-8")
        proof = (ROOT / "run_local_app_proof.sh").read_text(encoding="utf-8")

        self.assertIn("CORELM_WHEELHOUSE", build)
        self.assertIn("--no-index", build)
        self.assertIn('--find-links "$WHEELHOUSE"', build)
        self.assertIn("--require-hashes", build)
        self.assertIn('CORELM_ASSETS_OFFLINE_ONLY="$OFFLINE"', proof)
        self.assertIn('CORELM_WHEELHOUSE="$WHEELHOUSE"', proof)

    def test_external_proof_challenge_validation_and_exact_propagation(self):
        validator = ROOT / "security" / "validate_proof_challenge.sh"
        valid = "a1" * 32
        accepted = subprocess.run(
            ["/bin/sh", str(validator), valid],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(accepted.stdout.strip(), valid)
        for invalid in ("a" * 63, "A" * 64, "g" * 64, "a" * 65):
            rejected = subprocess.run(
                ["/bin/sh", str(validator), invalid],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(rejected.returncode, 0, invalid)

        proof = (ROOT / "run_local_app_proof.sh").read_text(encoding="utf-8")
        self.assertIn('--proof-challenge "$challenge"', proof)

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
                "HF_TOKEN": "must-not-leak",
                "HF_TOKEN_PATH": str(root / "hostile-token"),
                "HUGGING_FACE_HUB_TOKEN": "must-not-leak-either",
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
                self.assertNotIn("HF_TOKEN", os.environ)
                self.assertNotIn("HF_TOKEN_PATH", os.environ)
                self.assertNotIn("HUGGING_FACE_HUB_TOKEN", os.environ)
                self.assertEqual(
                    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"], "1"
                )
                self.assertEqual(
                    downloader.call_args_list,
                    [
                        mock.call(local_files_only=False),
                        mock.call(local_files_only=True),
                    ],
                )
            self.assertEqual(observed, resolved)
            self.assertEqual(cache.stat().st_mode & 0o777, 0o700)

    def test_asset_endpoint_is_explicit_https_and_hash_verification_remains(self):
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
            with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(
                prepare_app_assets,
                "_download_validation_only",
                return_value=resolved,
            ):
                prepare_app_assets.prepare_assets(
                    cache,
                    endpoint="https://mirror.example/huggingface/",
                )
                self.assertEqual(
                    os.environ["HF_ENDPOINT"],
                    "https://mirror.example/huggingface",
                )
            for invalid in (
                "http://huggingface.co",
                "https://user:secret@example.test",
                "https://example.test?q=unsafe",
                "https://example.test/#unsafe",
                "https://example.test:invalid",
                "https://example.test/unsafe\\path",
                "https://example.test/unsafe path",
            ):
                with self.subTest(endpoint=invalid), self.assertRaises(
                    ValueError
                ):
                    prepare_app_assets._validated_endpoint(invalid)

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
            receipt["worker"]["scriptSHA256"] = (
                verify_app_run_evidence._sha256(runner)
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

    def test_fresh_challenge_rejects_legacy_v3_without_primary_evidence(self):
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
            receipt["worker"]["scriptSHA256"] = (
                verify_app_run_evidence._sha256(runner)
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
                with self.assertRaisesRegex(ValueError, "proof challenge"):
                    verify_app_run_evidence.verify_fresh_run(
                        run,
                        app,
                        challenge_nonce=challenge,
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
