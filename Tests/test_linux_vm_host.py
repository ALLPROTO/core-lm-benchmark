import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "platforms/linux/scripts/verify-vm-host.sh"
WORKFLOW = ROOT / ".github/workflows/verify-linux-vm.yml"
TAG_WORKFLOW = ROOT / ".github/workflows/verify-linux.yml"


class LinuxVMHostContractTests(unittest.TestCase):
    def test_host_gate_requires_real_x86_64_ubuntu_vm_not_container(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('EXPECTED_VERSION=$1', source)
        self.assertIn('22.04|24.04', source)
        self.assertIn('"$(/usr/bin/uname -s)" = Linux', source)
        self.assertIn('"$(/usr/bin/uname -m)" = x86_64', source)
        self.assertIn('/usr/bin/systemd-detect-virt --vm', source)
        self.assertIn('/usr/bin/systemd-detect-virt --container', source)
        self.assertIn('CONTAINER_STATUS=$?', source)
        self.assertIn('[ "$CONTAINER_STATUS" -eq 1 ]', source)
        self.assertNotIn('--container 2>/dev/null || true', source)
        for forbidden in (
            "docker",
            "podman",
            "lxc",
            "systemd-nspawn",
            "container-other",
        ):
            self.assertIn(forbidden, source)
        self.assertIn('fields.get("ID") != "ubuntu"', source)
        self.assertIn(
            'fields.get("VERSION_ID") != expected_version', source
        )
        self.assertIn(
            "BOOTED_VM_PORTABILITY_CHECK_NOT_HERMETIC_IMAGE", source
        )
        self.assertIn('"modelExecuted": False', source)
        self.assertNotIn("qemu", source.lower())
        self.assertNotIn("docker run", source.lower())

    def test_embedded_report_program_is_canonical_and_non_evidentiary(self):
        source = SCRIPT.read_text(encoding="utf-8")
        program = source.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        fixture = ROOT / "Tests/fixtures/linux-vm-os-release.fixture"
        # The program only reads this path.  Use an existing tracked UTF-8 file
        # through stdin-independent synthetic arguments by replacing that one
        # file read with a deterministic in-memory Ubuntu os-release string.
        program = program.replace(
            'path.read_text(encoding="utf-8")',
            '"ID=ubuntu\\nVERSION_ID=24.04\\n"',
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                program,
                str(fixture),
                "24.04",
                "kvm",
            ],
            check=False,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertEqual(completed.stderr, b"")
        report = json.loads(completed.stdout)
        self.assertEqual(
            completed.stdout,
            json.dumps(
                report,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            + b"\n",
        )
        self.assertFalse(report["modelExecuted"])
        self.assertFalse(report["acceptedAsModelEvidence"])
        self.assertFalse(report["container"])

    def test_push_and_pr_use_two_booted_ubuntu_vm_images(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        tag_workflow = TAG_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: Verify Linux VMs", workflow)
        self.assertIn('      - "**"', workflow)
        self.assertIn('refs/pull/*/merge', workflow)
        self.assertIn("linux-cli-vm-smoke:", workflow)
        self.assertIn("runner: ubuntu-22.04", workflow)
        self.assertIn('version: "22.04"', workflow)
        self.assertIn("runner: ubuntu-24.04", workflow)
        self.assertIn('version: "24.04"', workflow)
        self.assertIn("runs-on: ${{ matrix.runner }}", workflow)
        self.assertIn("timeout-minutes: 40", workflow)
        self.assertIn("verify-vm-host.sh '${{ matrix.version }}'", workflow)
        self.assertIn("./corelm linux bootstrap", workflow)
        self.assertIn("./corelm linux doctor", workflow)
        self.assertIn("Tests.test_linux_vm_host", workflow)
        self.assertIn("Tests.test_linux_runtime_hardening", workflow)
        self.assertIn("Tests.test_platform_boundaries", workflow)
        self.assertNotIn("ubuntu-24.04-arm", workflow)
        self.assertNotIn("linux-cli-vm-smoke:", tag_workflow)


if __name__ == "__main__":
    unittest.main()
