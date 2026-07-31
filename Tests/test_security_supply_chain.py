import unittest

from security.verify_supply_chain import workflow_text_errors


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
