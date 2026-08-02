from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCH_RUNBOOK = PROJECT_ROOT / "docs" / "BEACON_LAUNCH_RUNBOOK.md"


class BeaconLaunchRunbookTests(unittest.TestCase):
    def test_preparation_uses_the_immutable_tag_interface(self):
        document = LAUNCH_RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("CORELM_SKIP_SMOKE_TEST=1 ./build_local_app.sh", document)

    def test_scientific_launch_block_is_fail_fast_and_propagates_status(self):
        document = LAUNCH_RUNBOOK.read_text(encoding="utf-8")
        marker = "BEACON_TAG_SHA=0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44"
        marker_offset = document.rindex(marker)
        fence_start = document.rindex("```sh\n", 0, marker_offset) + len("```sh\n")
        fence_end = document.index("```", marker_offset)
        block = document[fence_start:fence_end]
        self.assertTrue(block.startswith("(\nset -eu\n"))
        self.assertTrue(block.rstrip().endswith('exit "$BEACON_EXIT"\n)'))
        self.assertEqual(block.count("RealLLM/run_beacon_one_shot.py"), 1)
        self.assertIn("BEACON_OPERATOR_NOT_BEFORE=1785694500", block)
        self.assertIn("BEACON_OPERATOR_DEADLINE=1785866400", block)
        self.assertNotIn("/pulse/last", block)
        self.assertNotIn("beacon.nist.gov", block)
        runner_offset = block.index("RealLLM/run_beacon_one_shot.py")
        sync_offset = block.index("/bin/sync")
        self.assertLess(runner_offset, sync_offset)
        self.assertLess(sync_offset, block.index("Beacon runner exit code"))
        self.assertLess(
            block.index("BEACON_GIT_OR_LOADER_ENV"),
            block.index("/usr/bin/git rev-parse"),
        )
        self.assertLess(
            block.index("system proxy/PAC/SOCKS configuration is a NO-GO"),
            block.index("/usr/bin/git ls-remote"),
        )
        for required_gate in (
            'test "$HOME" = "$BEACON_ACCOUNT_HOME"',
            'test "$(pwd -P)" = "$(cd "$BEACON_ROOT" && pwd -P)"',
            'test "$(/usr/bin/git rev-parse HEAD)" = "$BEACON_TAG_SHA"',
            'test -z "$(/usr/bin/git symbolic-ref -q --short HEAD || true)"',
            'refs/tags/$BEACON_TAG^{commit}',
            'test -z "$(/usr/bin/git status --porcelain=v1 --untracked-files=all --ignored=no)"',
            'test "$(/bin/date -u +%s)" -ge "$BEACON_OPERATOR_NOT_BEFORE"',
            'test "$(/bin/date -u +%s)" -le "$BEACON_OPERATOR_DEADLINE"',
            "test ! -e real-llm-beacon-results/attempt.json",
            "test ! -L real-llm-beacon-results/attempt.json",
            "test ! -e real-llm-beacon-results/resolution.json",
            "test ! -L real-llm-beacon-results/resolution.json",
            "test ! -e real-llm-beacon-results/outcome.json",
            "test ! -L real-llm-beacon-results/outcome.json",
            "test ! -e real-llm-beacon-results/primary-evidence",
            "test ! -L real-llm-beacon-results/primary-evidence",
            'test ! -e "$HOME/.cache/corelm-proof-runtimes/.proof-run.lock"',
            'test ! -L "$HOME/.cache/corelm-proof-runtimes/.proof-run.lock"',
            '/usr/bin/git ls-remote --heads origin "$BEACON_EVIDENCE_BRANCH"',
            '/usr/bin/git ls-remote --tags origin "$BEACON_EVIDENCE_TAG"',
            "./security/verify_app_bundle.sh dist/CoreLMBenchmark.app",
            "validate_manifest_files(manifest)",
            "security/verify_locked_environment.py",
            "--offline-only",
            "from RealLLM.beacon_evaluation import prepare_runtime",
            "torch.mps.device_count()",
            "result directory ownership or mode is unsafe",
            ".beacon-preflight-write-probe",
            'test "$BEACON_FREE_KIB" -ge "$BEACON_MIN_FREE_KIB"',
            'test "$BEACON_FREE_MEMORY_PERCENT" -ge',
            "/usr/bin/sntp -d time.apple.com",
            "system clock offset exceeds the operator limit",
            "Scheduled shutdown, restart, or sleep is a NO-GO.",
            '"AppleClamshellState" = No',
            "Now drawing from 'AC Power'",
        ):
            self.assertLess(block.index(required_gate), runner_offset)

    def test_scientific_build_boundary_is_explicit(self):
        document = LAUNCH_RUNBOOK.read_text(encoding="utf-8")
        self.assertIn(
            "Only one build is allowed to create the scientific record",
            document,
        )
        self.assertIn("Current macOS application build", document)
        self.assertIn("Current Linux CPU build", document)
        self.assertIn(
            "No; the frozen experiment requires Apple MPS",
            document,
        )

    def test_launch_rejects_environment_redirection(self):
        document = LAUNCH_RUNBOOK.read_text(encoding="utf-8")
        marker = "BEACON_TAG_SHA=0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44"
        marker_offset = document.rindex(marker)
        fence_start = document.rindex("```sh\n", 0, marker_offset) + len("```sh\n")
        fence_end = document.index("```", marker_offset)
        block = document[fence_start:fence_end]
        for variable in (
            "HF_HUB_CACHE",
            "HTTPS_PROXY",
            "SSL_CERT_FILE",
            "PYTHONPATH",
            "DYLD_INSERT_LIBRARIES",
        ):
            self.assertIn(variable, block)

    def test_publication_block_is_fail_fast_and_additions_only(self):
        document = LAUNCH_RUNBOOK.read_text(encoding="utf-8")
        marker = "/usr/bin/git switch -c evidence/corelm-beacon-heldout-v1-outcome"
        marker_offset = document.index(marker)
        fence_start = document.rindex("```sh\n", 0, marker_offset) + len("```sh\n")
        fence_end = document.index("```", marker_offset)
        block = document[fence_start:fence_end]
        self.assertTrue(block.startswith("(\nset -eu\n"))
        self.assertTrue(block.rstrip().endswith(")"))
        self.assertEqual(block.count("diff --cached --name-status"), 1)
        self.assertEqual(block.count("diff-tree --no-commit-id --name-status"), 1)
        self.assertEqual(block.count('test "$BEACON_STATUS" = A'), 2)
        self.assertIn('test "$BEACON_INDEX_MODE" = 100644', block)
        self.assertIn("real-llm-beacon-results/attempt.json", block)
        self.assertIn("primary-evidence/containers/block-[0-9]", block)
        self.assertNotIn("real-llm-beacon-results/README.md", block)
        self.assertNotIn("real-llm-beacon-results/regressions", block)


if __name__ == "__main__":
    unittest.main()
