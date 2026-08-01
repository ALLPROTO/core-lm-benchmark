import unittest
from pathlib import Path

from security.verify_supply_chain import (
    dependabot_text_errors,
    workflow_text_errors,
)


ROOT = Path(__file__).resolve().parents[1]


class SupplyChainPolicyTests(unittest.TestCase):
    def _workflow(self, permissions: str) -> str:
        return f"""\
name: test
on: [push]
permissions:
  contents: read
jobs:
  verify:
    {permissions}
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5.1.0
        with:
          persist-credentials: false
"""

    def test_safe_read_only_workflow_passes(self):
        self.assertEqual(
            workflow_text_errors("safe.yml", self._workflow("timeout-minutes: 1")),
            [],
        )

    def test_write_all_and_inline_write_permissions_are_rejected(self):
        unsafe_permissions = (
            "permissions: write-all",
            "permissions : write-all",
            '"permissions": write-all',
            "'permissions': {contents: read, id-token: write}",
        )
        for index, declaration in enumerate(unsafe_permissions):
            with self.subTest(declaration=declaration):
                self.assertTrue(
                    workflow_text_errors(
                        f"unsafe-{index}.yml",
                        self._workflow(declaration),
                    )
                )

    def test_quoted_or_spaced_unpinned_actions_are_rejected(self):
        safe = self._workflow("timeout-minutes: 1")
        for unsafe in (
            safe.replace(
                "uses: actions/checkout@"
                "fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09",
                "uses : actions/checkout@v5",
            ),
            safe.replace(
                "uses: actions/checkout@"
                "fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09",
                '"uses": evil/action@main',
            ),
        ):
            with self.subTest(workflow=unsafe):
                self.assertTrue(workflow_text_errors("unsafe.yml", unsafe))

    def test_duplicate_yaml_keys_are_rejected(self):
        duplicated = self._workflow("permissions: read-all").replace(
            "permissions: read-all",
            "permissions: read-all\n    permissions: {}",
        )
        self.assertTrue(workflow_text_errors("duplicate.yml", duplicated))

    def test_dependabot_cannot_rewrite_the_frozen_real_llm_manifest(self):
        config = (ROOT / ".github" / "dependabot.yml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(dependabot_text_errors("dependabot.yml", config), [])
        self.assertTrue(
            dependabot_text_errors(
                "dependabot.yml",
                config.replace('      - "RealLLM/**"', '      - "other/**"'),
            )
        )
        self.assertTrue(
            dependabot_text_errors(
                "dependabot.yml",
                config.replace(
                    "    open-pull-requests-limit: 0\n"
                    "    groups:\n"
                    "      core-python:",
                    "    open-pull-requests-limit: 5\n"
                    "    groups:\n"
                    "      core-python:",
                ),
            )
        )
        self.assertTrue(
            dependabot_text_errors(
                "dependabot.yml",
                config.replace(
                    "    open-pull-requests-limit: 0\n"
                    "    groups:\n"
                    "      real-llm-python:",
                    "    open-pull-requests-limit: 5\n"
                    "    groups:\n"
                    "      real-llm-python:",
                ),
            )
        )
