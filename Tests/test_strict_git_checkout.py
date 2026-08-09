from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from security.verify_git_checkout import (
    StrictCheckoutError,
    inspect_checkout,
    verify_clean_checkout,
)


GIT = "/usr/bin/git"
ORIGIN = "https://example.invalid/strict-checkout"


class StrictGitCheckoutTests(unittest.TestCase):
    def _git(self, root: Path, *arguments: str) -> str:
        completed = subprocess.run(
            (
                GIT,
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                str(root),
                *arguments,
            ),
            env={
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "HOME": "/nonexistent-test-home",
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        return completed.stdout.decode("utf-8").strip()

    def _repository(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name).resolve(strict=True)
        self._git(root, "init")
        self._git(root, "branch", "-m", "main")
        self._git(root, "config", "user.name", "Checkout Test")
        self._git(root, "config", "user.email", "checkout@example.invalid")
        self._git(root, "remote", "add", "origin", ORIGIN)
        (root / "nested").mkdir()
        (root / "tracked.txt").write_text("signed bytes\n", encoding="utf-8")
        script = root / "nested" / "tool.sh"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
        self._git(root, "add", "tracked.txt", "nested/tool.sh")
        self._git(root, "commit", "-m", "fixture")
        return temporary, root

    def test_exact_clean_checkout_passes(self) -> None:
        temporary, root = self._repository()
        self.addCleanup(temporary.cleanup)
        identity = verify_clean_checkout(
            root,
            expected_origins={ORIGIN},
            expected_branch="main",
        )
        self.assertFalse(identity.dirty)
        self.assertEqual(identity.origin, ORIGIN)
        self.assertEqual(identity.commit, self._git(root, "rev-parse", "HEAD"))
        self.assertEqual(identity.tree, self._git(root, "rev-parse", "HEAD^{tree}"))

    def test_visible_change_and_untracked_file_are_dirty(self) -> None:
        temporary, root = self._repository()
        self.addCleanup(temporary.cleanup)
        (root / "tracked.txt").write_text("changed\n", encoding="utf-8")
        (root / "untracked.txt").write_text("extra\n", encoding="utf-8")
        self.assertTrue(inspect_checkout(root, require_clean=False).dirty)
        with self.assertRaisesRegex(StrictCheckoutError, "signed HEAD tree"):
            verify_clean_checkout(root)

    def test_skip_worktree_cannot_hide_modified_bytes(self) -> None:
        temporary, root = self._repository()
        self.addCleanup(temporary.cleanup)
        self._git(root, "update-index", "--skip-worktree", "tracked.txt")
        (root / "tracked.txt").write_text("hidden replacement\n", encoding="utf-8")
        self.assertEqual(
            self._git(root, "status", "--porcelain=v1", "--untracked-files=all"),
            "",
        )
        self.assertTrue(inspect_checkout(root, require_clean=False).dirty)
        with self.assertRaisesRegex(StrictCheckoutError, "signed HEAD tree"):
            verify_clean_checkout(root)

    def test_assume_unchanged_cannot_hide_modified_bytes(self) -> None:
        temporary, root = self._repository()
        self.addCleanup(temporary.cleanup)
        self._git(root, "update-index", "--assume-unchanged", "tracked.txt")
        (root / "tracked.txt").write_text("hidden replacement\n", encoding="utf-8")
        self.assertEqual(
            self._git(root, "status", "--porcelain=v1", "--untracked-files=all"),
            "",
        )
        self.assertTrue(inspect_checkout(root, require_clean=False).dirty)
        with self.assertRaisesRegex(StrictCheckoutError, "signed HEAD tree"):
            verify_clean_checkout(root)

    def test_staged_index_and_mode_changes_are_rejected(self) -> None:
        temporary, root = self._repository()
        self.addCleanup(temporary.cleanup)
        (root / "tracked.txt").write_text("staged replacement\n", encoding="utf-8")
        self._git(root, "add", "tracked.txt")
        self.assertTrue(inspect_checkout(root, require_clean=False).dirty)
        with self.assertRaises(StrictCheckoutError):
            verify_clean_checkout(root)

        self._git(root, "reset", "--hard", "HEAD")
        (root / "tracked.txt").chmod(0o755)
        self.assertTrue(inspect_checkout(root, require_clean=False).dirty)
        with self.assertRaises(StrictCheckoutError):
            verify_clean_checkout(root)

    def test_replacement_refs_and_grafts_are_forbidden(self) -> None:
        temporary, root = self._repository()
        self.addCleanup(temporary.cleanup)
        (root / "second.txt").write_text("second\n", encoding="utf-8")
        self._git(root, "add", "second.txt")
        self._git(root, "commit", "-m", "second")
        self._git(root, "replace", "HEAD", "HEAD^")
        with self.assertRaisesRegex(StrictCheckoutError, "replacement refs"):
            verify_clean_checkout(root)

        self._git(root, "replace", "-d", "HEAD")
        common = Path(self._git(root, "rev-parse", "--git-common-dir"))
        if not common.is_absolute():
            common = root / common
        grafts = common.resolve(strict=True) / "info" / "grafts"
        grafts.write_text("", encoding="utf-8")
        with self.assertRaisesRegex(StrictCheckoutError, "legacy grafts"):
            verify_clean_checkout(root)

    def test_sparse_checkout_configuration_is_forbidden(self) -> None:
        temporary, root = self._repository()
        self.addCleanup(temporary.cleanup)
        self._git(root, "config", "core.sparseCheckout", "true")
        with self.assertRaisesRegex(StrictCheckoutError, "sparse checkout"):
            verify_clean_checkout(root)

    def test_expected_identity_origin_branch_and_upstream_are_exact(self) -> None:
        temporary, root = self._repository()
        self.addCleanup(temporary.cleanup)
        with self.assertRaisesRegex(StrictCheckoutError, "expected commit"):
            verify_clean_checkout(root, expected_commit="0" * 40)
        with self.assertRaisesRegex(StrictCheckoutError, "canonical remote"):
            verify_clean_checkout(root, expected_origins={"https://example.invalid/other"})
        with self.assertRaisesRegex(StrictCheckoutError, "expected branch"):
            verify_clean_checkout(root, expected_branch="other")
        with self.assertRaisesRegex(StrictCheckoutError, "expected upstream"):
            verify_clean_checkout(root, expected_upstream="origin/main")


if __name__ == "__main__":
    unittest.main()
