import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from typing import Optional
import unittest


ROOT = Path(__file__).resolve().parents[1]
RESOLVER = ROOT / "platforms" / "macos" / "scripts" / "find-proof-window.swift"


def _swift_compiler() -> Optional[str]:
    if platform.system() != "Darwin":
        return None
    xcrun = shutil.which("xcrun")
    if xcrun is None:
        return None
    completed = subprocess.run(
        [xcrun, "--find", "swiftc"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    compiler = completed.stdout.strip()
    return compiler if compiler else None


def _swift_environment():
    environment = os.environ.copy()
    xcrun = shutil.which("xcrun")
    if xcrun is None:
        return environment
    completed = subprocess.run(
        [xcrun, "--sdk", "macosx", "--show-sdk-path"],
        check=False,
        capture_output=True,
        text=True,
    )
    sdk = completed.stdout.strip()
    if completed.returncode == 0 and sdk:
        environment["SDKROOT"] = sdk
    return environment


class AutomatedWindowCaptureTests(unittest.TestCase):
    def _required_darwin_compiler(self) -> Optional[str]:
        compiler = _swift_compiler()
        if platform.system() == "Darwin":
            self.assertIsNotNone(
                compiler,
                "Darwin gate requires an available Swift compiler",
            )
            return compiler
        self.assertIsNone(compiler)
        self.assertEqual(RESOLVER.suffix, ".swift")
        return None

    def test_source_is_fail_closed_and_emits_only_window_identity(self):
        source = RESOLVER.read_text(encoding="utf-8")
        for required in (
            "CGWindowListCopyWindowInfo",
            "CGPreflightScreenCaptureAccess()",
            "NSRunningApplication(processIdentifier:",
            ".optionOnScreenOnly",
            ".excludeDesktopElements",
            "layer == 0",
            "alpha > 0",
            "matches.count == 1",
            'value == requiredBundleIdentifier',
            'mode: "MACOS_WINDOW_ID_ONLY"',
            "schemaVersion: 1",
            ".sortedKeys",
            "O_NOFOLLOW",
            "SHA256()",
            "maximumExecutableBytes",
            "value.utf8.allSatisfy",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "URLSession",
            "NSWorkspace.shared.open",
            "CGWindowListCreateImage",
            "CGDisplayCreateImage",
            "CGRequestScreenCaptureAccess",
            "FileManager.default",
            ".write(to:",
        ):
            self.assertNotIn(forbidden, source)

    def test_declared_json_keys_are_canonical_and_minimal(self):
        source = RESOLVER.read_text(encoding="utf-8")
        expected_keys = {
            "schema_version",
            "mode",
            "pid",
            "bundle_identifier",
            "window_id",
            "owner_name",
            "bounds",
            "executable_path",
            "executable_sha256",
        }
        coding_key_lines = {
            line.split('"')[1]
            for line in source.splitlines()
            if " = \"" in line and "case " in line
        }
        direct_key_lines = {
            line.strip().removeprefix("case ")
            for line in source.splitlines()
            if line.strip() in {"case mode", "case pid", "case bounds"}
        }
        self.assertEqual(coding_key_lines | direct_key_lines, expected_keys)

        sample = {
            "bounds": {"height": 600, "width": 800, "x": 10, "y": 20},
            "bundle_identifier": "com.corelm.benchmark",
            "mode": "MACOS_WINDOW_ID_ONLY",
            "owner_name": "CoreLMBenchmark",
            "pid": 123,
            "schema_version": 1,
            "window_id": 456,
            "executable_path": "/Applications/CoreLMBenchmark.app/Contents/MacOS/CoreLMBenchmark",
            "executable_sha256": "0" * 64,
        }
        canonical = json.dumps(sample, sort_keys=True, separators=(",", ":"))
        self.assertNotIn(" ", canonical)
        self.assertEqual(json.loads(canonical), sample)

    def test_swift_source_parses_and_typechecks(self):
        compiler = self._required_darwin_compiler()
        if compiler is None:
            self.assertNotEqual(platform.system(), "Darwin")
            return
        for operation in ("-parse", "-typecheck"):
            completed = subprocess.run(
                [compiler, operation, str(RESOLVER)],
                cwd=ROOT,
                env=_swift_environment(),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stdout + completed.stderr,
            )

    def test_nonmatching_pid_fails_without_emitting_json(self):
        compiler = self._required_darwin_compiler()
        if compiler is None:
            self.assertNotEqual(platform.system(), "Darwin")
            return
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "find-proof-window"
            compiled = subprocess.run(
                [compiler, str(RESOLVER), "-o", str(executable)],
                cwd=ROOT,
                env=_swift_environment(),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                compiled.returncode,
                0,
                compiled.stdout + compiled.stderr,
            )
            completed = subprocess.run(
                [
                    str(executable),
                    "--pid",
                    str(os.getpid()),
                    "--bundle-id",
                    "com.corelm.benchmark",
                ],
                cwd=ROOT,
                env=_swift_environment(),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "")
            self.assertTrue(
                completed.stderr.startswith("ERROR find-proof-window: PID "),
                completed.stderr,
            )

    def test_preflight_never_prompts_and_only_succeeds_with_true_json(self):
        compiler = self._required_darwin_compiler()
        if compiler is None:
            self.assertNotEqual(platform.system(), "Darwin")
            return
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "find-proof-window"
            compiled = subprocess.run(
                [compiler, str(RESOLVER), "-o", str(executable)],
                cwd=ROOT,
                env=_swift_environment(),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                compiled.returncode,
                0,
                compiled.stdout + compiled.stderr,
            )
            completed = subprocess.run(
                [str(executable), "--preflight"],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode == 0:
                self.assertEqual(
                    completed.stdout,
                    '{"screen_capture_authorized":true}\n',
                )
                self.assertEqual(completed.stderr, "")
            else:
                self.assertEqual(completed.stdout, "")
                self.assertIn("screen capture access is not authorized", completed.stderr)


if __name__ == "__main__":
    unittest.main()
