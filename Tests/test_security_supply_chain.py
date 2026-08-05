import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import security.verify_supply_chain as supply_chain

from security.verify_supply_chain import (
    dependabot_text_errors,
    matching_secret,
    reachable_message_errors,
    workflow_text_errors,
)


ROOT = Path(__file__).resolve().parents[1]


class SupplyChainPolicyTests(unittest.TestCase):
    def test_secret_matcher_rejects_private_material_and_tokens(self):
        private_key = b"-----BEGIN " + b"OPENSSH PRIVATE KEY-----"
        github_token = b"gh" + b"p_" + (b"A" * 30)
        openai_key = b"s" + b"k-proj-" + (b"A" * 24)
        self.assertEqual(matching_secret(private_key), "private key")
        self.assertEqual(matching_secret(github_token), "GitHub token")
        self.assertEqual(matching_secret(openai_key), "OpenAI key")

    def test_secret_matcher_allows_the_registered_public_key(self):
        public_key = (ROOT / "signing/corelm-codec-signing.pub").read_bytes()
        allowed_signers = (ROOT / "signing/allowed_signers").read_bytes()
        self.assertIsNone(matching_secret(public_key))
        self.assertIsNone(matching_secret(allowed_signers))
        self.assertEqual(
            public_key,
            b"ssh-ed25519 "
            b"AAAAC3NzaC1lZDI1NTE5AAAAIKpsQwHhryVsgGIgNON9uTJzu4/Il5pj1vTFK7LCZuaB "
            b"Ivan Tyshchenko core-lm-cross-model-v4 signing\n",
        )

    def test_reachable_commit_and_annotated_tag_messages_are_scanned(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(
                ("git", "init", "-q"), cwd=repository, check=True
            )
            subprocess.run(
                ("git", "config", "user.name", "Unit Test"),
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ("git", "config", "user.email", "unit@example.invalid"),
                cwd=repository,
                check=True,
            )
            (repository / "public.txt").write_text(
                "public fixture\n", encoding="utf-8"
            )
            subprocess.run(
                ("git", "add", "public.txt"), cwd=repository, check=True
            )
            token = "gh" + "p_" + ("A" * 30)
            subprocess.run(
                ("git", "commit", "-q", "-m", f"commit {token}"),
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ("git", "tag", "-a", "fixture", "-m", f"tag {token}"),
                cwd=repository,
                check=True,
            )
            with mock.patch.object(supply_chain, "ROOT", repository):
                errors = reachable_message_errors()
            self.assertEqual(len(errors), 2)
            self.assertTrue(
                any("reachable Git commit" in error for error in errors)
            )
            self.assertTrue(
                any("reachable Git tag" in error for error in errors)
            )

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

    def test_beacon_evidence_audit_is_manual_fixed_and_non_executing(self):
        path = ROOT / ".github/workflows/audit-beacon-evidence.yml"
        workflow = path.read_text(encoding="utf-8")
        self.assertEqual(workflow_text_errors(path.name, workflow), [])
        for required in (
            "workflow_dispatch:",
            "ref: corelm-beacon-heldout-v1-evidence",
            "audit_beacon_evidence_ref.py",
            "preflight --repository evidence",
            "extract-lock",
            "--repository evidence",
            "Audit without NIST network access or a new scientific attempt",
        ):
            self.assertIn(required, workflow)
        for forbidden in (
            "run_beacon_one_shot",
            "run_beacon_regression",
            "prepare_beacon_assets",
            "beacon.nist.gov",
            "actions/upload-artifact",
            "torch==",
            "transformers==",
        ):
            self.assertNotIn(forbidden, workflow)
        preflight = workflow.index("preflight --repository evidence")
        extraction = workflow.index("extract-lock")
        installation = workflow.index("-m pip install")
        control_environment_check = workflow.index(
            "control/security/verify_locked_environment.py"
        )
        self.assertLess(preflight, extraction)
        self.assertLess(extraction, installation)
        self.assertLess(installation, control_environment_check)
        self.assertNotIn("evidence/security/", workflow)
