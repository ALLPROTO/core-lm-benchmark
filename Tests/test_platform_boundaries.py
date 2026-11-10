import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = ROOT / "platforms"
MACOS = PLATFORMS / "macos"
LINUX = PLATFORMS / "linux"
BEACON = PLATFORMS / "beacon"


def _text_files(root: Path) -> str:
    values = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in {".md", ".py", ".sh", ".swift"}:
            values.append(path.read_text(encoding="utf-8"))
    return "\n".join(values)


class PlatformBoundaryTests(unittest.TestCase):
    def test_dispatcher_routes_three_independent_contours(self):
        dispatcher = (ROOT / "corelm").read_text(encoding="utf-8")
        for expected in (
            "platforms/macos/scripts/build-app.sh",
            "platforms/linux/scripts/build-runtime.sh",
            "platforms/beacon/scripts/verify-frozen-tag.py",
        ):
            self.assertIn(expected, dispatcher)
        self.assertNotIn("run_beacon_one_shot.py", dispatcher)

    def test_active_builds_exclude_frozen_compatibility_payload(self):
        macos = _text_files(MACOS)
        linux = _text_files(LINUX)
        for source in (macos, linux):
            self.assertNotIn("BenchmarkCore/corelm_benchmark.py", source)
            self.assertNotIn("legacy_voidtoken_adapter", source)
            self.assertNotIn("run_beacon_one_shot.py", source)
            self.assertNotIn("RealLLM/requirements.lock", source)
            self.assertNotIn(".github/locks/pip-bootstrap.txt", source)
            self.assertIn(".github/locks/pip-maintained.txt", source)
        self.assertNotIn("platforms/linux", macos)
        self.assertNotIn("platforms/macos", linux)
        self.assertNotIn("Package.swift", linux)

    def test_active_runtime_defaults_do_not_reuse_historical_destinations(self):
        for platform, relatives in {
            "macos": (
                "corelm",
                "scripts/verify-python.sh",
                "platforms/macos/scripts/build-app.sh",
                "platforms/macos/scripts/package-app.sh",
                "platforms/macos/App/Sources/BenchmarkStore.swift",
            ),
            "linux": (
                "scripts/verify-python.sh",
                "platforms/linux/scripts/doctor.sh",
                "platforms/linux/scripts/build-runtime.sh",
                "platforms/linux/scripts/run-regression.sh",
            ),
        }.items():
            for relative in relatives:
                with self.subTest(platform=platform, source=relative):
                    source = (ROOT / relative).read_text(encoding="utf-8")
                    prefix = f".cache/corelm/{platform}/runtime"
                    self.assertIn(prefix + "-maintained-20261110", source)
                    self.assertNotIn(prefix + '"', source)
                    self.assertNotIn(prefix + "/bin/python", source)

    def test_runtime_and_output_namespaces_do_not_overlap(self):
        macos = _text_files(MACOS)
        linux = _text_files(LINUX)
        self.assertIn(".cache/corelm/macos/runtime-maintained-20261110", macos)
        self.assertIn(".cache/corelm/macos/model-assets", macos)
        self.assertIn(".cache/corelm/macos/proof-runtimes", macos)
        self.assertIn(".cache/corelm/linux/runtime-maintained-20261110", linux)
        self.assertIn(".cache/corelm/linux/model-assets", linux)
        self.assertIn(".cache/corelm/linux/runs", linux)
        self.assertNotIn(".cache/corelm/linux/", macos)
        self.assertNotIn(".cache/corelm/macos/", linux)
        self.assertNotIn("Application Support", linux)
        self.assertNotIn("CoreLMBenchmark.app", linux)

    def test_beacon_contour_is_read_only_git_object_verification(self):
        verifier = BEACON / "scripts" / "verify-frozen-tag.py"
        source = verifier.read_text(encoding="utf-8")
        compile(source, str(verifier), "exec")
        for forbidden in (
            "run_beacon_one_shot",
            "fetch_nist_pulse",
            "huggingface",
            "transformers",
            "torch",
            "requests",
            "urllib",
        ):
            self.assertNotIn(forbidden, source.lower())
        self.assertIn('FREEZE_TAG = "corelm-beacon-heldout-v1"', source)
        self.assertIn("EXPECTED_FILE_COUNT = 26", source)
        self.assertIn('"GIT_NO_REPLACE_OBJECTS": "1"', source)
        self.assertIn('"--no-replace-objects"', source)
        self.assertIn('"cat-file", "-s"', source)
        self.assertIn("NOT A SCIENTIFIC RESULT", source)

    def test_registered_payload_remains_regular_and_byte_identical(self):
        payload = ROOT / "BenchmarkCore" / "corelm_benchmark.py"
        self.assertTrue(payload.is_file())
        self.assertFalse(payload.is_symlink())
        freeze = json.loads(
            (ROOT / "RealLLM" / "beacon_freeze.json").read_text(
                encoding="utf-8"
            )
        )
        entry = next(
            item
            for item in freeze["normativeFiles"]
            if item["path"] == "BenchmarkCore/corelm_benchmark.py"
        )
        content = payload.read_bytes()
        self.assertEqual(len(content), entry["bytes"])
        self.assertEqual(hashlib.sha256(content).hexdigest(), entry["sha256"])


if __name__ == "__main__":
    unittest.main()
