import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT_DIR = Path(__file__).resolve().parents[1]
GATE = PROJECT_DIR / "security" / "run_swift_security_tests.sh"


class SwiftSecurityGateTests(unittest.TestCase):
    def _run_gate(self, standalone_framework: bool) -> list[str]:
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
                "printf '%s\\n' "
                "'Test run with 1 test in 1 suite passed after 0.001 seconds.'\n",
                encoding="utf-8",
            )
            fake_swift.chmod(0o700)

            environment = os.environ.copy()
            environment.update(
                {
                    "CORELM_SWIFT_ARGUMENTS_LOG": str(arguments_log),
                    "DEVELOPER_DIR": str(developer),
                    "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
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
            self.assertEqual(
                completed.returncode,
                0,
                completed.stdout + completed.stderr,
            )
            self.assertIn("SWIFT SECURITY TESTS PASS", completed.stdout)
            return arguments_log.read_text(encoding="utf-8").splitlines()

    def test_standalone_framework_adds_explicit_framework_search_path(self):
        arguments = self._run_gate(standalone_framework=True)
        self.assertEqual(
            arguments[:3],
            ["test", "--enable-swift-testing", "--disable-xctest"],
        )
        self.assertEqual(arguments.count("-Xswiftc"), 2)
        self.assertIn("-F", arguments)
        self.assertTrue(arguments[-1].endswith("/Library/Developer/Frameworks"))

    def test_xcode_toolchain_layout_uses_native_swiftpm_integration(self):
        arguments = self._run_gate(standalone_framework=False)
        self.assertEqual(
            arguments,
            ["test", "--enable-swift-testing", "--disable-xctest"],
        )


if __name__ == "__main__":
    unittest.main()
