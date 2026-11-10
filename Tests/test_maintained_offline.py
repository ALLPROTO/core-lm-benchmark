"""Test-only shell controls for the private patched wheelhouse downloader."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "platforms/macos/scripts/prepare-offline.sh"


class MaintainedOfflineTests(unittest.TestCase):
    def _exercise(self, *, failure="", preflight="new"):
        source = SCRIPT.read_text(encoding="utf-8")
        controls = source[
            source.index("cleanup_downloader() {")
            : source.index('[ "${CORELM_OFFLINE:-0}" = 0 ]')
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wheelhouse = root / "wheelhouse"
            wheelhouse.mkdir(mode=0o700)
            preserved = wheelhouse / "existing.whl"
            preserved.write_bytes(b"test-only retained wheel")
            log = root / "calls.jsonl"
            bootstrap = root / "bootstrap-python"
            bootstrap.write_text(
                f"#!{sys.executable}\n"
                + '''import json
import os
import sys
from pathlib import Path

arguments = sys.argv[1:]
executable = Path(__file__)
is_base = executable.name == "bootstrap-python"
phase = "unknown"
if any(value.endswith("manage_local_runtime.py") for value in arguments):
    phase = arguments[arguments.index("--mode") + 1]
elif "venv" in arguments:
    phase = "venv"
elif any(value.endswith("verify_locked_environment.py") for value in arguments):
    phase = "verify"
elif "pip" in arguments:
    phase = arguments[arguments.index("pip") + 1]
with Path(os.environ["TEST_LOG"]).open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({
        "base": is_base,
        "phase": phase,
        "arguments": arguments,
        "executable": str(executable),
        "pip_config": os.environ.get("PIP_CONFIG_FILE"),
    }) + "\\n")
if phase == os.environ.get("TEST_FAILURE"):
    raise SystemExit(23)
if phase == "preflight":
    print(os.environ["TEST_PREFLIGHT"])
elif phase == "venv":
    runtime = Path(arguments[-1])
    (runtime / "bin").mkdir(parents=True)
    child = runtime / "bin/python"
    child.write_text(executable.read_text(encoding="utf-8"), encoding="utf-8")
    child.chmod(0o700)
elif phase == "install":
    if is_base:
        raise SystemExit("base installation forbidden")
    (executable.parent.parent / ".patched").write_text("patched", encoding="ascii")
elif phase in {"check", "verify", "download"}:
    if is_base or not (executable.parent.parent / ".patched").is_file():
        raise SystemExit("unpatched downloader forbidden")
    if phase == "download":
        destination = Path(arguments[arguments.index("--dest") + 1])
        (destination / "downloaded.whl").write_bytes(b"test-only downloaded wheel")
elif phase != "initialize":
    raise SystemExit("unexpected bootstrap operation")
''',
                encoding="utf-8",
            )
            bootstrap.chmod(0o700)
            original_bootstrap = bootstrap.read_bytes()
            completed = subprocess.run(
                [
                    "/bin/sh",
                    "-eu",
                    "-c",
                    "umask 077\nDOWNLOADER_DIR=\n"
                    'fail() { printf "%s\\n" "$*" >&2; exit 1; }\n'
                    + controls
                    + "prepare_wheelhouse\n",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={
                    "PATH": "/usr/bin:/bin",
                    "HOME": str(root),
                    "PROJECT_DIR": str(ROOT),
                    "WHEELHOUSE": str(wheelhouse),
                    "PYPI_INDEX_URL": "https://mirror.example.invalid/simple",
                    "bootstrap_path": str(bootstrap),
                    "TEST_LOG": str(log),
                    "TEST_FAILURE": failure,
                    "TEST_PREFLIGHT": preflight,
                },
            )
            self.assertEqual(bootstrap.read_bytes(), original_bootstrap)
            self.assertEqual(preserved.read_bytes(), b"test-only retained wheel")
            self.assertEqual(list(wheelhouse.glob(".corelm-pip-download.*")), [])
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertFalse(
                any(call["base"] and "pip" in call["arguments"] for call in calls)
            )
            return completed, calls, (wheelhouse / "downloaded.whl").exists()

    def test_only_patched_private_python_downloads_the_full_closure(self):
        completed, calls, downloaded = self._exercise()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(downloaded)
        self.assertEqual(
            [call["phase"] for call in calls],
            ["preflight", "venv", "initialize", "install", "check", "verify", "download"],
        )
        install, check, verify, download = calls[3:]
        self.assertEqual(
            {call["executable"] for call in (install, check, verify, download)},
            {install["executable"]},
        )
        self.assertIn("/.corelm-pip-download.", install["executable"])
        self.assertTrue(install["executable"].endswith("/runtime/bin/python"))
        for call in (install, download):
            self.assertFalse(call["base"])
            self.assertEqual(call["pip_config"], "/dev/null")
            self.assertEqual(call["arguments"][:2], ["-I", "-B"])
            for option in (
                "--isolated", "--no-input", "--disable-pip-version-check",
                "--no-cache-dir", "--only-binary=:all:", "--require-hashes",
            ):
                self.assertIn(option, call["arguments"])
        arguments = install["arguments"]
        self.assertIn("--no-deps", arguments)
        self.assertEqual(
            arguments[arguments.index("--index-url") + 1], "https://pypi.org/simple"
        )
        self.assertEqual(arguments.count("-r"), 1)
        self.assertEqual(arguments[-1], str(ROOT / ".github/locks/pip-maintained.txt"))
        self.assertNotIn("https://mirror.example.invalid/simple", arguments)
        self.assertEqual(
            verify["arguments"][-2:],
            ["--lock", str(ROOT / ".github/locks/pip-maintained.txt")],
        )
        self.assertEqual(download["arguments"].count("-r"), 2)
        self.assertIn("https://mirror.example.invalid/simple", download["arguments"])
        self.assertIn(
            str(ROOT / ".github/locks/real-llm-portable-py312.txt"),
            download["arguments"],
        )

    def test_failures_remove_only_temporary_downloader_and_stop_the_pipeline(self):
        phases = ["preflight", "venv", "initialize", "install", "check", "verify", "download"]
        for index, phase in enumerate(phases):
            with self.subTest(phase=phase):
                completed, calls, downloaded = self._exercise(failure=phase)
                self.assertNotEqual(completed.returncode, 0)
                self.assertEqual([call["phase"] for call in calls], phases[: index + 1])
                self.assertFalse(downloaded)

    def test_existing_temporary_runtime_fails_before_creation_or_installation(self):
        completed, calls, downloaded = self._exercise(preflight="existing")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("temporary downloader must be fresh", completed.stderr)
        self.assertEqual([call["phase"] for call in calls], ["preflight"])
        self.assertFalse(downloaded)

    def test_shell_parses_and_downloader_follows_wheelhouse_validation(self):
        completed = subprocess.run(
            ["/bin/sh", "-n", str(SCRIPT)], capture_output=True, text=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertLess(
            source.index('physical_wheelhouse=$(CDPATH= cd -- "$WHEELHOUSE" && pwd -P)'),
            source.index("\nprepare_wheelhouse\n"),
        )
        self.assertIn('"$WHEELHOUSE"/.corelm-pip-download.*)', source)
        self.assertIn('trap stop_downloader HUP INT TERM', source)
        self.assertNotIn('"$bootstrap_path" -I -B -m pip', source)


if __name__ == "__main__":
    unittest.main()
