import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from security import generate_build_provenance as provenance


ROOT = Path(__file__).resolve().parents[1]
FAKE_TOOLCHAIN = {
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
        "version": "Apple Swift version 6.3.3 (swiftlang-6.3.3.1.3)",
    },
}


class BuildProvenanceTests(unittest.TestCase):
    @staticmethod
    def _build_document(*, dirty: bool = False) -> dict[str, object]:
        return {
            "schemaVersion": provenance.BUILD_SCHEMA_VERSION,
            "source": {
                "archiveManifestSHA256": None,
                "commit": "1" * 40,
                "dirty": dirty,
                "exactTag": None,
                "mode": "git",
                "remote": (
                    "https://github.com/ALLPROTO/core-lm-benchmark.git"
                ),
                "tree": "2" * 40,
            },
            "toolchain": copy.deepcopy(FAKE_TOOLCHAIN),
        }

    def _git(self, root: Path, *arguments: str) -> str:
        completed = subprocess.run(
            ["/usr/bin/git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    def _repository(self, root: Path) -> None:
        self._git(root, "init", "-q")
        self._git(root, "config", "user.name", "Provenance Test")
        self._git(root, "config", "user.email", "provenance@example.invalid")
        self._git(
            root,
            "remote",
            "add",
            "origin",
            "https://github.com/ALLPROTO/core-lm-benchmark.git",
        )
        (root / "source.txt").write_text("frozen source\n", encoding="utf-8")
        self._git(root, "add", "source.txt")
        self._git(root, "commit", "-q", "-m", "fixture")

    def test_git_source_records_commit_tree_remote_dirty_and_exact_tag(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._repository(root)
            source = provenance.inspect_git_source(root)
            self.assertEqual(source["mode"], "git")
            self.assertEqual(source["commit"], self._git(root, "rev-parse", "HEAD"))
            self.assertEqual(
                source["tree"], self._git(root, "rev-parse", "HEAD^{tree}")
            )
            self.assertEqual(
                source["remote"],
                "https://github.com/ALLPROTO/core-lm-benchmark.git",
            )
            self.assertFalse(source["dirty"])
            self.assertIsNone(source["exactTag"])
            self.assertIsNone(source["archiveManifestSHA256"])

            self._git(root, "tag", "proof-v1")
            self.assertEqual(
                provenance.inspect_git_source(root)["exactTag"], "proof-v1"
            )
            (root / "source.txt").write_text("changed source\n", encoding="utf-8")
            self.assertTrue(provenance.inspect_git_source(root)["dirty"])

    def test_evidence_build_rejects_dirty_git_unless_explicitly_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._repository(root)
            (root / "source.txt").write_text("changed source\n", encoding="utf-8")
            with (
                mock.patch.object(
                    provenance,
                    "inspect_toolchain",
                    return_value=copy.deepcopy(FAKE_TOOLCHAIN),
                ),
                self.assertRaisesRegex(ValueError, "source is dirty"),
            ):
                provenance.build_manifest(root)
            with mock.patch.object(
                provenance,
                "inspect_toolchain",
                return_value=copy.deepcopy(FAKE_TOOLCHAIN),
            ):
                manifest = provenance.build_manifest(root, allow_dirty=True)
            self.assertTrue(manifest["source"]["dirty"])

    def test_documented_source_archive_is_verified_before_use(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "RealLLM").mkdir()
            source_file = root / "RealLLM" / "worker.py"
            source_file.write_text("print('real')\n", encoding="utf-8")
            archive_path = root / provenance.DEFAULT_ARCHIVE_MANIFEST
            archive = provenance.build_source_archive_manifest(
                root,
                commit="1" * 40,
                tree="2" * 40,
                remote="https://github.com/ALLPROTO/core-lm-benchmark.git",
                exact_tag="proof-v1",
                dirty=False,
                output=archive_path,
            )
            archive_path.write_bytes(provenance.canonical_json_bytes(archive))

            with mock.patch.object(
                provenance,
                "inspect_toolchain",
                return_value=copy.deepcopy(FAKE_TOOLCHAIN),
            ):
                manifest = provenance.build_manifest(root)
            self.assertEqual(manifest["source"]["mode"], "archive")
            self.assertFalse(manifest["source"]["dirty"])
            self.assertRegex(
                manifest["source"]["archiveManifestSHA256"], r"^[0-9a-f]{64}$"
            )

            alias = root / "manifest-alias.json"
            alias.symlink_to(archive_path)
            with self.assertRaisesRegex(ValueError, "unsupported entry"):
                provenance.inspect_source_archive(root, archive_path)
            alias.unlink()

            source_file.write_text("print('tampered')\n", encoding="utf-8")
            with (
                mock.patch.object(
                    provenance,
                    "inspect_toolchain",
                    return_value=copy.deepcopy(FAKE_TOOLCHAIN),
                ),
                self.assertRaisesRegex(ValueError, "source is dirty"),
            ):
                provenance.build_manifest(root)

    def test_build_manifest_verifier_requires_canonical_exact_schema(self):
        manifest = self._build_document()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "build-provenance.json"
            path.write_bytes(provenance.canonical_json_bytes(manifest))
            self.assertEqual(provenance.verify_build_manifest(path), manifest)

            path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "canonical"):
                provenance.verify_build_manifest(path)

            malformed = copy.deepcopy(manifest)
            malformed["unexpected"] = True
            path.write_bytes(provenance.canonical_json_bytes(malformed))
            with self.assertRaisesRegex(ValueError, "fields are not exact"):
                provenance.verify_build_manifest(path)

            path_disclosure = copy.deepcopy(manifest)
            path_disclosure["toolchain"]["swift"]["version"] = (
                "Swift from /Users/example/private-toolchain"
            )
            path.write_bytes(provenance.canonical_json_bytes(path_disclosure))
            with self.assertRaisesRegex(ValueError, "local path"):
                provenance.verify_build_manifest(path)

    def test_archive_manifest_must_be_regular_and_inside_source_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            external = root / provenance.DEFAULT_ARCHIVE_MANIFEST
            external.write_bytes(
                provenance.canonical_json_bytes(
                    {
                        "files": [],
                        "schemaVersion": provenance.ARCHIVE_SCHEMA_VERSION,
                        "source": {
                            "commit": "1" * 40,
                            "dirty": False,
                            "exactTag": None,
                            "remote": (
                                "https://github.com/ALLPROTO/"
                                "core-lm-benchmark.git"
                            ),
                            "tree": "2" * 40,
                        },
                    }
                )
            )
            with self.assertRaisesRegex(ValueError, "inside the source tree"):
                provenance.inspect_source_archive(source, external)

            linked = source / provenance.DEFAULT_ARCHIVE_MANIFEST
            linked.symlink_to(external)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                provenance.inspect_source_archive(source, linked)

    def test_packager_and_bundle_verifier_bind_provenance_resource(self):
        package = (ROOT / "platforms/macos/scripts/package-app.sh").read_text(encoding="utf-8")
        verifier = (ROOT / "security/verify_app_bundle.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("build-provenance.json", package)
        self.assertIn("generate_build_provenance.py", package)
        self.assertIn("CORELM_ALLOW_DIRTY_SOURCE", package)
        self.assertIn("CORELM_SOURCE_ARCHIVE_MANIFEST", package)
        first_probe = package.index('"$@" --output "$PROVENANCE_BEFORE"')
        output_validation = package.index("prepare_dist_directory\n")
        build = package.index('/usr/bin/xcrun --sdk macosx swift build')
        second_probe = package.index('"$@" --output "$PROVENANCE_AFTER"')
        comparison = package.index('cmp -s "$PROVENANCE_BEFORE" "$PROVENANCE_AFTER"')
        final_probe = package.index('"$@" --output "$PROVENANCE_FINAL"')
        final_comparison = package.index(
            'cmp -s "$PROVENANCE_BEFORE" "$PROVENANCE_FINAL"'
        )
        runtime_manifest = package.index("generate_python_runtime_manifest.py")
        signing = package.index("codesign --force")
        self.assertLess(first_probe, build)
        self.assertLess(output_validation, first_probe)
        self.assertLess(build, second_probe)
        self.assertLess(second_probe, comparison)
        self.assertLess(runtime_manifest, final_probe)
        self.assertLess(final_probe, final_comparison)
        self.assertLess(final_comparison, signing)
        self.assertIn('[ ! -L "$directory" ]', package)
        self.assertIn('require_owned_directory "dist directory"', package)
        self.assertIn('resolved_dist" = "$DIST_DIR', package)
        self.assertNotIn('rm -rf "$FINAL_DIR"', package)
        self.assertIn("Previous application moved to Trash", package)
        self.assertIn("build-provenance.json", verifier)
        self.assertIn("generate_build_provenance.py", verifier)
        self.assertIn("exactly seven declared resources", verifier)


if __name__ == "__main__":
    unittest.main()
