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
        self.assertNotIn("/pulse/last", block)
        runner_offset = block.index("RealLLM/run_beacon_one_shot.py")
        for required_gate in (
            'test "$(git rev-parse HEAD)" = "$BEACON_TAG_SHA"',
            'test -z "$(git status --porcelain=v1 --untracked-files=all --ignored=no)"',
            'test "$(/bin/date -u +%s)" -ge "$BEACON_OPERATOR_NOT_BEFORE"',
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
            "Now drawing from 'AC Power'",
        ):
            self.assertLess(block.index(required_gate), runner_offset)


if __name__ == "__main__":
    unittest.main()
