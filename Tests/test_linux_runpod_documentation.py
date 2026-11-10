import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "platforms/linux/RUNPOD.md"
RECORDED_RUN = ROOT / "platforms/linux/RECORDED_RUN_2026-08-11_RUNPOD.md"


class LinuxRunPodDocumentationTests(unittest.TestCase):
    def test_runbook_preserves_the_real_cpu_qwen_boundary(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        commands = (
            "./corelm linux bootstrap",
            "./corelm linux doctor",
            "./corelm linux build",
            "CORELM_OFFLINE=1 ./corelm linux run",
            'security/verify_primary_evidence.py "$CORELM_RUN_DIR"',
            "sha256sum -c SHA256SUMS",
        )
        offsets = [text.index(command) for command in commands]
        self.assertEqual(offsets, sorted(offsets))
        for phrase in (
            "complete Linux CPU contour",
            "Qwen/Qwen2.5-0.5B",
            "the runner fixes `--device cpu`",
            "A RunPod pod is also a container",
            "does not run every metadata adapter",
            "not a new blind result, independent replication, GPU result, or VM-portability result",
            "pod volume can survive a stop/restart of the same pod",
        ):
            self.assertIn(phrase, normalized)
        self.assertIn('test ! -e "$CORELM_E2E_ROOT"', text)
        self.assertIn('install -d -m 700 "$CORELM_E2E_ROOT"', text)

    def test_recorded_run_is_exact_and_discloses_the_failed_full_gate(self):
        text = RECORDED_RUN.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        exact_values = (
            "9b68055502e81efe6c9aa164632d2fa6de780c4b",
            "e07617638be98c95a158f8241a4ca095f6c70858",
            "2.052389237121773",
            "2.2321861713692215e-05",
            "0.99609375",
            "70dd06e8b7c7c4c53b4c86f0ba393fc667577563f146a23652f7c0ec9c29842f",
            "3c44a2adc4b2c19c1ceb7e854fdeb3748b36ec9bc39542ca581c7cdd4a5bd110",
            "28a1605a74e9f967d6e54cc96cca991d6e0ceaa050a211228839b7110e7c609c",
            "d5390403b10b8ca1584d5cdfcebebce2f13fa5173de403d1f2b2ed76cf965621",
            "c14e165c80a1ab4aa1b5c17cb984f22838617cf23884f580a99ff5b787fecb88",
        )
        for value in exact_values:
            self.assertIn(value, text)
        for phrase in (
            "`modelExecuted`: `true`",
            "192 containers and 1,024 token decisions",
            "Metric verdict: `PASS`",
            "passed 463 of 464 tests",
            "test_inode_ctime_seal_detects_modify_execute_restore_attack",
            "does not claim that a reader can independently retrieve or reverify that tar",
            "The pod was terminated after evidence retrieval and its access key was removed",
        ):
            self.assertIn(phrase, normalized)
        self.assertIn(
            "disclosed rather than relabelled as a full-suite PASS", normalized
        )

    def test_docs_link_the_runbook_without_publishing_access_material(self):
        linux_readme = (ROOT / "platforms/linux/README.md").read_text(
            encoding="utf-8"
        )
        docs_index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
        self.assertIn("[RunPod guide](RUNPOD.md)", linux_readme)
        self.assertIn(
            "[recorded 2026-08-11 RunPod run](RECORDED_RUN_2026-08-11_RUNPOD.md)",
            linux_readme,
        )
        self.assertIn("../platforms/linux/RUNPOD.md", docs_index)
        self.assertIn(
            "../platforms/linux/RECORDED_RUN_2026-08-11_RUNPOD.md", docs_index
        )
        combined = RUNBOOK.read_text(encoding="utf-8") + RECORDED_RUN.read_text(
            encoding="utf-8"
        )
        for private_value in (
            "corelm_runpod_session_",
            "RUNPOD_API_KEY",
            "ssh-ed25519 AAAA",
            "IdentityFile",
            ".ssh/",
        ):
            self.assertNotIn(private_value, combined)
        self.assertNotRegex(combined, r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        self.assertNotRegex(combined, r"(?im)\b(?:pod|instance)\s+id\s*[:=]")


if __name__ == "__main__":
    unittest.main()
