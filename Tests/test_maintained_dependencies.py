"""Test-only checks separating historical replay inputs from supported runtime locks."""

import hashlib
import unittest
from pathlib import Path
from unittest import mock

from security import audit_beacon_evidence_ref as historical
from security import generate_direct_sbom as sbom
from security import verify_supply_chain as policy

ROOT = Path(__file__).resolve().parents[1]
MAINTAINED = {
    '.github/locks/pip-maintained.txt',
    'requirements.lock',
    '.github/locks/core-linux-py312.txt',
    '.github/locks/core-macos-arm64-py312.txt',
    '.github/locks/real-llm-portable-py312.txt',
    '.github/locks/real-llm-linux-cpu-py312.txt',
    '.github/locks/torch-linux-cpu-py312.txt',
}


class MaintainedDependencyTests(unittest.TestCase):
    def test_frozen_audit_inputs_remain_byte_identical(self):
        for relative, expected in historical.FROZEN_AUDIT_FILE_SHA256.items():
            with self.subTest(path=relative):
                self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected)

    def test_maintained_closures_satisfy_policy(self):
        self.assertEqual(policy.dependency_errors(), [])

    def test_linux_closure_must_follow_maintained_not_historical_pins(self):
        original = policy.manifest_pins
        def historical_linux(path):
            if path.name == 'real-llm-linux-cpu-py312.txt':
                return {n: v for n, v in original(ROOT / 'RealLLM/requirements.lock').items() if n != 'torch'}
            return original(path)
        with mock.patch.object(policy, 'manifest_pins', side_effect=historical_linux):
            self.assertIn('Linux CPU maintained RealLLM lock must match the portable lock except torch', policy.dependency_errors())

    def test_live_osv_gate_covers_every_maintained_closure(self):
        workflow = (ROOT / '.github/workflows/verify-linux.yml').read_text()
        command = workflow.split('python security/osv_direct_audit.py', 1)[1].split('\n\n', 1)[0]
        self.assertEqual(set(command.split()), MAINTAINED)
        self.assertNotIn('continue-on-error', workflow)
        self.assertNotIn('|| true', command)

    def test_historical_osv_findings_are_not_suppressed(self):
        workflow = (ROOT / '.github/workflows/audit-historical-dependencies.yml').read_text()
        self.assertIn('RealLLM/requirements.lock', workflow)
        self.assertIn('.github/locks/pip-bootstrap.txt', workflow)
        self.assertNotIn('continue-on-error', workflow)
        self.assertNotIn('|| true', workflow)
        self.assertNotIn('pip install', workflow)

    def test_sbom_uses_maintained_direct_manifest(self):
        paths = {str(path.relative_to(ROOT)) for path in sbom.MANIFESTS}
        self.assertEqual(paths, {'requirements.txt', '.github/locks/real-llm-maintained.txt'})


if __name__ == '__main__':
    unittest.main()
