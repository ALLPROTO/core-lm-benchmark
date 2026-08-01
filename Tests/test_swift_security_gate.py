import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT_DIR = Path(__file__).resolve().parents[1]
GATE = PROJECT_DIR / "security" / "run_swift_security_tests.sh"


class SwiftSecurityGateTests(unittest.TestCase):
    def _run_gate(
        self,
        standalone_framework: bool,
        summary: str,
        should_pass: bool = True,
    ) -> list[str]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            developer = root / "Developer"
            frameworks = developer / "Library" / "Developer" / "Frameworks"
            fake_bin = root / "bin"
            fake_bin.mkdir()
            if standalone_framework:
                (frameworks / "Testing.framework").mkdir(parents=True)
            else:
                developer.mkdir()

            arguments_log = root / "swift-arguments.txt"
            fake_swift = fake_bin / "swift"
            fake_swift.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$@\" > \"$CORELM_SWIFT_ARGUMENTS_LOG\"\n"
                "printf '%s\\n' \"$CORELM_SWIFT_TEST_SUMMARY\"\n",
                encoding="utf-8",
            )
            fake_swift.chmod(0o700)

            environment = os.environ.copy()
            environment.update(
                {
                    "CORELM_SWIFT_ARGUMENTS_LOG": str(arguments_log),
                    "CORELM_SWIFT_TEST_SUMMARY": summary,
                    "CORELM_SWIFT_GATE_TEST_MODE": "1",
                    "CORELM_TEST_DEVELOPER_DIR": str(developer),
                    "CORELM_TEST_SWIFT_LAUNCHER": str(fake_swift),
                }
            )
            completed = subprocess.run(
                ["/bin/bash", str(GATE)],
                cwd=PROJECT_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            if should_pass:
                self.assertEqual(
                    completed.returncode,
                    0,
                    completed.stdout + completed.stderr,
                )
                self.assertIn("SWIFT SECURITY TESTS PASS", completed.stdout)
            else:
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(
                    "no non-empty passing test run",
                    completed.stderr,
                )
            return arguments_log.read_text(encoding="utf-8").splitlines()

    def test_standalone_framework_adds_explicit_framework_search_path(self):
        arguments = self._run_gate(
            standalone_framework=True,
            summary=(
                "Test run with 11 tests in 1 suite passed "
                "after 0.001 seconds."
            ),
        )
        self.assertEqual(arguments[0], "test")
        self.assertEqual(arguments[1], "--scratch-path")
        self.assertTrue(arguments[2].endswith("/build"))
        self.assertIn("--enable-swift-testing", arguments)
        self.assertIn("--disable-xctest", arguments)
        self.assertEqual(arguments.count("-Xswiftc"), 2)
        self.assertIn("-F", arguments)
        self.assertTrue(arguments[-1].endswith("/Library/Developer/Frameworks"))

    def test_xcode_toolchain_layout_uses_native_swiftpm_integration(self):
        arguments = self._run_gate(
            standalone_framework=False,
            summary="Test run with 11 tests passed after 0.001 seconds.",
        )
        self.assertEqual(arguments[0], "test")
        self.assertEqual(arguments[1], "--scratch-path")
        self.assertTrue(arguments[2].endswith("/build"))
        self.assertEqual(
            arguments[3:],
            ["--enable-swift-testing", "--disable-xctest"],
        )

    def test_zero_test_summary_is_rejected(self):
        self._run_gate(
            standalone_framework=False,
            summary="Test run with 0 tests passed after 0.001 seconds.",
            should_pass=False,
        )


if __name__ == "__main__":
    unittest.main()
