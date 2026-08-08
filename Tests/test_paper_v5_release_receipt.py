import base64
import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from publication import verify_paper_v5_release as verifier


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _asset_fixture(root: Path, receipt: dict) -> None:
    payloads = {
        "corelm_reproducibility.tar.gz": b"local reproducibility archive\n",
        "corelm_voidtoken_v5.pdf": b"%PDF-1.7\nlocal paper\n",
        "corelm_voidtoken_v5_arxiv_source.tar.gz": b"local arxiv source\n",
    }
    records = {item["name"]: item for item in receipt["assets"]}
    for name, payload in payloads.items():
        (root / name).write_bytes(payload)
        records[name]["size_bytes"] = len(payload)
        records[name]["sha256"] = _sha256(payload)
    checksums = b"".join(
        f"{records[name]['sha256']}  {name}\n".encode("ascii")
        for name in verifier.CHECKSUM_ORDER
    )
    (root / "SHA256SUMS").write_bytes(checksums)
    records["SHA256SUMS"]["size_bytes"] = len(checksums)
    records["SHA256SUMS"]["sha256"] = _sha256(checksums)


class PaperV5ReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = verifier.load_pinned_receipt()

    def test_tracked_receipt_and_public_attestation_are_exact(self):
        receipt_bytes = verifier.RECEIPT_PATH.read_bytes()
        self.assertEqual(_sha256(receipt_bytes), verifier.PINNED_RECEIPT_SHA256)
        self.assertEqual(receipt_bytes, verifier._canonical_json(self.receipt))
        statement = verifier.verify_attestation(self.receipt)
        self.assertEqual(statement["predicate"]["databaseId"], "363130646")
        self.assertEqual(statement["predicate"]["tag"], verifier.PINNED_TAG)
        self.assertEqual(
            statement["subject"][0]["digest"], {"sha1": verifier.PINNED_COMMIT}
        )

    def test_receipt_tamper_is_rejected_before_parsing_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            raw = bytearray(verifier.RECEIPT_PATH.read_bytes())
            raw[0] ^= 1
            path.write_bytes(raw)
            with self.assertRaisesRegex(
                verifier.PaperV5VerificationError, "receipt SHA-256 is not pinned"
            ):
                verifier.load_pinned_receipt(path)

    def test_receipt_sections_require_strict_keys_types_and_values(self):
        mutations = {
            "release title": lambda value: value["release"].__setitem__("name", "edited"),
            "release bool type": lambda value: value["release"].__setitem__(
                "immutable", 1
            ),
            "source extra key": lambda value: value["source"].__setitem__(
                "operator", "self"
            ),
            "attestation path": lambda value: value["attestation"].__setitem__(
                "path", "another.json"
            ),
            "scope overclaim": lambda value: value["verification_scope"].__setitem__(
                "release_metadata", "LIVE_VERIFIED"
            ),
            "asset id": lambda value: value["assets"][0].__setitem__("id", 1),
            "asset content type": lambda value: value["assets"][1].__setitem__(
                "content_type", "application/octet-stream"
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                value = copy.deepcopy(self.receipt)
                mutate(value)
                raw = verifier._canonical_json(value)
                path = Path(temporary) / "receipt.json"
                path.write_bytes(raw)
                with mock.patch.object(
                    verifier, "PINNED_RECEIPT_SHA256", _sha256(raw)
                ):
                    with self.assertRaisesRegex(
                        verifier.PaperV5VerificationError,
                        "release receipt",
                    ):
                        verifier.load_pinned_receipt(path)

    def test_attestation_byte_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bundle.json"
            raw = bytearray(verifier.ATTESTATION_PATH.read_bytes())
            raw[100] ^= 1
            path.write_bytes(raw)
            with self.assertRaisesRegex(
                verifier.PaperV5VerificationError,
                "public attestation SHA-256 differs from receipt",
            ):
                verifier.verify_attestation(self.receipt, path)

    def test_attestation_subject_must_equal_receipt_even_when_rehashed(self):
        receipt = copy.deepcopy(self.receipt)
        raw = verifier.ATTESTATION_PATH.read_bytes()[:-1]
        bundle = json.loads(raw)
        statement = json.loads(base64.b64decode(bundle["dsseEnvelope"]["payload"]))
        statement["subject"][1]["digest"]["sha256"] = "0" * 64
        statement_raw = json.dumps(
            statement, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        bundle["dsseEnvelope"]["payload"] = base64.b64encode(statement_raw).decode(
            "ascii"
        )
        public_bytes = json.dumps(
            bundle, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        tracked = public_bytes + b"\n"
        receipt["attestation"]["public_size_bytes"] = len(public_bytes)
        receipt["attestation"]["tracked_size_bytes"] = len(tracked)
        receipt["attestation"]["public_bytes_sha256"] = _sha256(public_bytes)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bundle.json"
            path.write_bytes(tracked)
            with self.assertRaisesRegex(
                verifier.PaperV5VerificationError,
                "in-toto asset subjects differ from receipt",
            ):
                verifier.verify_attestation(receipt, path)

    def test_caller_supplied_assets_match_direct_receipt_hashes(self):
        receipt = copy.deepcopy(self.receipt)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "assets"
            root.mkdir()
            _asset_fixture(root, receipt)
            verified = verifier.verify_assets(root, receipt)
            self.assertEqual(
                {item["name"] for item in verified}, set(verifier.PINNED_ASSET_NAMES)
            )

    def test_asset_mutation_fails_even_if_sha256sums_is_self_consistent(self):
        receipt = copy.deepcopy(self.receipt)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _asset_fixture(root, receipt)
            name = "corelm_voidtoken_v5.pdf"
            mutated = (root / name).read_bytes() + b"operator adjustment\n"
            (root / name).write_bytes(mutated)
            records = {item["name"]: item for item in receipt["assets"]}
            self_generated = b"".join(
                (
                    f"{_sha256(mutated) if item == name else records[item]['sha256']}"
                    f"  {item}\n"
                ).encode("ascii")
                for item in verifier.CHECKSUM_ORDER
            )
            (root / "SHA256SUMS").write_bytes(self_generated)
            records["SHA256SUMS"]["size_bytes"] = len(self_generated)
            records["SHA256SUMS"]["sha256"] = _sha256(self_generated)
            with self.assertRaisesRegex(
                verifier.PaperV5VerificationError, "seal or size differs from receipt"
            ):
                verifier.verify_assets(root, receipt)

    def test_extra_symlink_and_hardlink_assets_are_rejected(self):
        receipt = copy.deepcopy(self.receipt)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "assets"
            root.mkdir()
            _asset_fixture(root, receipt)
            (root / "unexpected.txt").write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.PaperV5VerificationError, "exactly four release assets"
            ):
                verifier.verify_assets(root, receipt)
            (root / "unexpected.txt").unlink()

            pdf = root / "corelm_voidtoken_v5.pdf"
            original = root.parent / "pdf-original"
            pdf.rename(original)
            pdf.symlink_to(original)
            with self.assertRaisesRegex(
                verifier.PaperV5VerificationError, "regular and single-linked"
            ):
                verifier.verify_assets(root, receipt)
            pdf.unlink()
            original.rename(pdf)

            outside = root.parent / f"{root.name}-hardlink"
            try:
                os.link(pdf, outside)
                with self.assertRaisesRegex(
                    verifier.PaperV5VerificationError, "regular and single-linked"
                ):
                    verifier.verify_assets(root, receipt)
            finally:
                outside.unlink(missing_ok=True)

    def test_unified_asset_snapshot_rejects_added_file_during_reads(self):
        receipt = copy.deepcopy(self.receipt)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _asset_fixture(root, receipt)
            original = verifier._read_sealed_asset
            injected = False

            def mutate(directory_fd, name, seal, expected_size):
                nonlocal injected
                raw = original(directory_fd, name, seal, expected_size)
                if not injected:
                    injected = True
                    (root / "late-extra").write_bytes(b"not in initial snapshot")
                return raw

            with mock.patch.object(verifier, "_read_sealed_asset", side_effect=mutate):
                with self.assertRaisesRegex(
                    verifier.PaperV5VerificationError, "snapshot changed"
                ):
                    verifier.verify_assets(root, receipt)

    def test_unified_asset_snapshot_rejects_identical_inode_replacement(self):
        receipt = copy.deepcopy(self.receipt)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _asset_fixture(root, receipt)
            original = verifier._read_sealed_asset
            replaced = False

            def mutate(directory_fd, name, seal, expected_size):
                nonlocal replaced
                raw = original(directory_fd, name, seal, expected_size)
                if not replaced:
                    replaced = True
                    target = root / name
                    target.unlink()
                    target.write_bytes(raw)
                return raw

            with mock.patch.object(verifier, "_read_sealed_asset", side_effect=mutate):
                with self.assertRaisesRegex(
                    verifier.PaperV5VerificationError, "snapshot changed"
                ):
                    verifier.verify_assets(root, receipt)

    def test_machine_result_states_only_caller_supplied_equivalence(self):
        statement = {
            "predicateType": "https://in-toto.io/attestation/release/v0.2"
        }
        with (
            mock.patch.object(verifier, "load_pinned_receipt", return_value=self.receipt),
            mock.patch.object(verifier, "verify_attestation", return_value=statement),
            mock.patch.object(
                verifier,
                "verify_source",
                return_value={
                    "commit": verifier.PINNED_COMMIT,
                    "tree": verifier.PINNED_TREE,
                    "tag": verifier.PINNED_TAG,
                },
            ),
            mock.patch.object(verifier, "verify_assets", return_value=[]),
        ):
            report = verifier.verify(Path("source"), Path("assets"))
        expected = (
            "CALLER_SUPPLIED_BYTE_EQUIVALENCE_TO_AUTHOR_PINNED_PUBLIC_RELEASE"
        )
        self.assertEqual(report["status"], expected)
        self.assertEqual(report["claim_scope"], expected)
        self.assertEqual(
            report["release_metadata_scope"],
            "AUTHOR_PINNED_SAVED_GITHUB_METADATA_NOT_LIVE_VERIFIED",
        )
        serialized = json.dumps(report, sort_keys=True).lower()
        self.assertNotIn("rebuilt", serialized)
        self.assertNotIn('"status": "pass"', serialized)

    def _source_results(self, root: Path):
        (root / ".git" / "info").mkdir(parents=True)
        payload = b"tracked source bytes\n"
        (root / "tracked.txt").write_bytes(payload)
        object_id = verifier._git_blob_sha1(payload)
        tag_ref = f"refs/tags/{verifier.PINNED_TAG}"
        text = {
            ("rev-parse", "--is-inside-work-tree"): (0, "true"),
            ("rev-parse", "--show-toplevel"): (0, str(root)),
            ("rev-parse", "--show-object-format"): (0, "sha1"),
            ("config", "--bool", "core.sparseCheckout"): (1, ""),
            ("config", "--bool", "core.sparseCheckoutCone"): (1, ""),
            ("config", "--bool", "index.sparse"): (1, ""),
            ("rev-parse", "--git-path", "info/sparse-checkout"): (
                0,
                ".git/info/sparse-checkout",
            ),
            ("symbolic-ref", "--quiet", "HEAD"): (1, ""),
            (
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignored=matching",
                "--ignore-submodules=none",
            ): (0, ""),
            ("for-each-ref", "--format=%(refname)", "refs/replace"): (0, ""),
            ("rev-parse", "--git-path", "info/grafts"): (0, ".git/info/grafts"),
            ("cat-file", "-t", tag_ref): (0, "commit"),
            ("rev-parse", f"{tag_ref}^{{commit}}"): (0, verifier.PINNED_COMMIT),
            ("rev-parse", f"{tag_ref}^{{tree}}"): (0, verifier.PINNED_TREE),
            ("rev-parse", "HEAD^{commit}"): (0, verifier.PINNED_COMMIT),
            ("rev-parse", "HEAD^{tree}"): (0, verifier.PINNED_TREE),
            ("config", "--local", "--get-all", "remote.origin.url"): (
                0,
                verifier.PINNED_REPOSITORY,
            ),
        }
        raw = {
            ("ls-tree", "-rz", "--full-tree", "HEAD"): (
                0,
                f"100644 blob {object_id}\ttracked.txt\0".encode("ascii"),
            ),
            ("ls-files", "-z", "--stage"): (
                0,
                f"100644 {object_id} 0\ttracked.txt\0".encode("ascii"),
            ),
            ("ls-files", "-z", "-t"): (0, b"H tracked.txt\0"),
            ("ls-files", "-z", "-v"): (0, b"H tracked.txt\0"),
            ("ls-files", "-z", "-f"): (0, b"H tracked.txt\0"),
        }
        return text, raw, payload

    def _source_mocks(self, text, raw):
        def fake_git(_repository, arguments, *, allowed=(0,)):
            code, output = text[tuple(arguments)]
            if code not in allowed:
                raise AssertionError(f"unexpected mocked Git status: {arguments} -> {code}")
            return code, output

        def fake_git_raw(_repository, arguments, *, allowed=(0,)):
            code, output = raw[tuple(arguments)]
            if code not in allowed:
                raise AssertionError(f"unexpected mocked Git status: {arguments} -> {code}")
            return code, output

        return (
            mock.patch.object(verifier, "_git", side_effect=fake_git),
            mock.patch.object(verifier, "_git_raw", side_effect=fake_git_raw),
        )

    def test_source_requires_clean_detached_lightweight_exact_tag(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            text, raw, _payload = self._source_results(root)
            text_patch, raw_patch = self._source_mocks(text, raw)
            with text_patch, raw_patch:
                observed = verifier.verify_source(root, self.receipt)
            self.assertEqual(observed["commit"], verifier.PINNED_COMMIT)

            text[("symbolic-ref", "--quiet", "HEAD")] = (0, "refs/heads/main")
            text_patch, raw_patch = self._source_mocks(text, raw)
            with text_patch, raw_patch:
                with self.assertRaisesRegex(
                    verifier.PaperV5VerificationError, "HEAD must be detached"
                ):
                    verifier.verify_source(root, self.receipt)

    def test_source_rejects_wrong_commit_and_dirty_worktree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            text, raw, _payload = self._source_results(root)
            text[("rev-parse", "HEAD^{commit}")] = (0, "0" * 40)
            text_patch, raw_patch = self._source_mocks(text, raw)
            with text_patch, raw_patch:
                with self.assertRaisesRegex(
                    verifier.PaperV5VerificationError, "commit/tree identity"
                ):
                    verifier.verify_source(root, self.receipt)

            text[("rev-parse", "HEAD^{commit}")] = (0, verifier.PINNED_COMMIT)
            status_key = (
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignored=matching",
                "--ignore-submodules=none",
            )
            text[status_key] = (0, "?? operator-note.txt")
            text_patch, raw_patch = self._source_mocks(text, raw)
            with text_patch, raw_patch:
                with self.assertRaisesRegex(
                    verifier.PaperV5VerificationError, "worktree must be clean"
                ):
                    verifier.verify_source(root, self.receipt)

    def test_source_rejects_sparse_skip_assume_and_fsmonitor_index_flags(self):
        scenarios = {
            "sparse checkout": ("text", ("config", "--bool", "core.sparseCheckout"), (0, "true")),
            "sparse index": ("text", ("config", "--bool", "index.sparse"), (0, "true")),
            "staged index": (
                "raw",
                ("ls-files", "-z", "--stage"),
                (0, f"100644 {'0' * 40} 0\ttracked.txt\0".encode("ascii")),
            ),
            "skip worktree": ("raw", ("ls-files", "-z", "-t"), (0, b"S tracked.txt\0")),
            "assume unchanged": ("raw", ("ls-files", "-z", "-v"), (0, b"h tracked.txt\0")),
            "fsmonitor valid": ("raw", ("ls-files", "-z", "-f"), (0, b"h tracked.txt\0")),
        }
        for label, (kind, key, replacement) in scenarios.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                text, raw, _payload = self._source_results(root)
                (text if kind == "text" else raw)[key] = replacement
                text_patch, raw_patch = self._source_mocks(text, raw)
                with text_patch, raw_patch:
                    with self.assertRaises(verifier.PaperV5VerificationError):
                        verifier.verify_source(root, self.receipt)

    def test_source_independently_rejects_blob_and_mode_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            text, raw, payload = self._source_results(root)
            tracked = root / "tracked.txt"

            tracked.write_bytes(b"operator-adjusted bytes\n")
            text_patch, raw_patch = self._source_mocks(text, raw)
            with text_patch, raw_patch:
                with self.assertRaisesRegex(
                    verifier.PaperV5VerificationError, "bytes differ from HEAD blob"
                ):
                    verifier.verify_source(root, self.receipt)

            tracked.write_bytes(payload)
            tracked.chmod(0o755)
            text_patch, raw_patch = self._source_mocks(text, raw)
            with text_patch, raw_patch:
                with self.assertRaisesRegex(
                    verifier.PaperV5VerificationError, "executable mode differs"
                ):
                    verifier.verify_source(root, self.receipt)

            tracked.chmod(0o644)
            (root / "ignored-empty-directory").mkdir()
            text_patch, raw_patch = self._source_mocks(text, raw)
            with text_patch, raw_patch:
                with self.assertRaisesRegex(
                    verifier.PaperV5VerificationError, "untracked directory"
                ):
                    verifier.verify_source(root, self.receipt)

    def test_git_invocation_forcibly_disables_fsmonitor(self):
        completed = __import__("subprocess").CompletedProcess(
            args=[], returncode=0, stdout=b"ok\n", stderr=b""
        )
        with mock.patch.object(verifier.subprocess, "run", return_value=completed) as run:
            self.assertEqual(verifier._git(Path("/tmp"), ("status",))[1], "ok")
        command = run.call_args.args[0]
        self.assertIn("core.fsmonitor=false", command)
        self.assertIn("core.untrackedCache=false", command)
        self.assertEqual(run.call_args.kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")


if __name__ == "__main__":
    unittest.main()
