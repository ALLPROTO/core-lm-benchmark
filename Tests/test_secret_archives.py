"""Isolated security fixtures only; never benchmark/model evidence."""
import gzip
import io
import stat
import struct
import zlib
import subprocess
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

import security.verify_supply_chain as scanner


def archive(entries, compression=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(buffer, "w", compression=compression) as z:
            for name, data in entries:
                z.writestr(name, data)
    return buffer.getvalue()


class ArchiveSecretTests(unittest.TestCase):
    def scan(self, data, name="fixture.zip"):
        return scanner.scanned_content_errors(data, name, name)

    def test_compressed_secret_detected_without_leaking_value(self):
        secret = b"gh" + b"p_" + b"A" * 30
        payload = archive([("nested/code.txt", secret)])
        self.assertNotIn(secret, payload)
        errors = self.scan(payload)
        self.assertTrue(any("GitHub token" in e for e in errors))
        self.assertNotIn(secret.decode(), str(errors))

    def test_valid_archive_and_content_sniffing(self):
        payload = archive([("code.py", b"print('public')\n")])
        self.assertEqual(self.scan(payload), [])
        self.assertEqual(self.scan(payload, "not-a-zip.bin"), [])
        self.assertTrue(self.scan(b"prefix" + payload, "polyglot.bin"))

    def test_ordinary_blob_limit_not_relaxed(self):
        with mock.patch.object(scanner, "MAX_SCANNED_BLOB_BYTES", 20):
            self.assertTrue(self.scan(b"a" * 21, "plain.txt"))
            self.assertEqual(self.scan(archive([("public.txt", b"a" * 21)])), [])

    def test_archive_size_limit(self):
        payload = archive([("a", b"public")])
        with mock.patch.object(scanner, "MAX_ARCHIVE_BYTES", len(payload) - 1):
            self.assertTrue(self.scan(payload))

    def test_member_expansion_bomb_limit(self):
        payload = archive([("large.txt", b"a" * 10001)])
        with mock.patch.object(scanner, "MAX_ARCHIVE_MEMBER_BYTES", 10000):
            self.assertTrue(self.scan(payload))

    def test_total_expansion_and_count_limits(self):
        payload = archive([("a", b"aaaa"), ("b", b"bbbb")])
        with mock.patch.object(scanner, "MAX_ARCHIVE_EXPANDED_BYTES", 7):
            self.assertTrue(self.scan(payload))
        with mock.patch.object(scanner, "MAX_ARCHIVE_MEMBERS", 1):
            self.assertTrue(self.scan(payload))

    def test_nested_archive_rejected(self):
        nested = archive([("public", b"public")])
        for name in ("inner.zip", "inner.bin"):
            self.assertTrue(self.scan(archive([(name, nested)])))

    def test_concatenated_zip_and_trailing_bytes_rejected(self):
        secret = b"gh" + b"p_" + b"A" * 30
        hidden = archive([("hidden", secret)])
        public = archive([("public", b"public")])
        self.assertTrue(self.scan(hidden + public))
        self.assertTrue(self.scan(public + b"trailing"))

    def test_lzma_and_comment_features_fail_closed(self):
        self.assertTrue(self.scan(archive([("a", b"public")], zipfile.ZIP_LZMA)))
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as z:
            z.writestr("public", b"public")
            z.comment = b"comment"
        self.assertTrue(self.scan(payload.getvalue()))

    def test_data_descriptor_and_zip64_rejected(self):
        class NonSeekable(io.BytesIO):
            def seek(self, *args):
                raise OSError("not seekable")

        streamed = NonSeekable()
        with zipfile.ZipFile(streamed, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("public", b"public")
        self.assertTrue(self.scan(streamed.getvalue()))
        zip64 = io.BytesIO()
        with zipfile.ZipFile(zip64, "w") as z:
            with z.open("public", "w", force_zip64=True) as member:
                member.write(b"public")
        self.assertTrue(self.scan(zip64.getvalue()))

    def test_stored_payload_cannot_hide_uninspected_tail(self):
        public = b"public"
        secret = b"gh" + b"p_" + b"A" * 30
        payload = bytearray(archive([("a", public + gzip.compress(secret))], zipfile.ZIP_STORED))
        central = payload.index(b"PK\x01\x02")
        struct.pack_into("<I", payload, 22, len(public))
        struct.pack_into("<I", payload, central + 24, len(public))
        struct.pack_into("<I", payload, 14, zlib.crc32(public))
        struct.pack_into("<I", payload, central + 16, zlib.crc32(public))
        self.assertTrue(self.scan(bytes(payload)))

    def test_forged_local_header_rejected(self):
        payload = bytearray(archive([("a", b"public")]))
        payload[14] ^= 1  # Local CRC differs from the central-directory CRC.
        self.assertTrue(self.scan(bytes(payload)))

    def test_nested_other_compression_rejected(self):
        self.assertTrue(self.scan(archive([("opaque.bin", gzip.compress(b"public"))])))

    def test_malformed_archive_rejected(self):
        self.assertTrue(self.scan(b"not zip"))
        self.assertTrue(self.scan(b"PK\x03\x04bad", "bad.bin"))
        self.assertTrue(self.scan(archive([("a", b"public")])[:-12]))

    def test_unsafe_duplicate_and_nonregular_members_rejected(self):
        for name in ("../a", "/a", "a/../b", "a//b", "a\\b", "C:/a", "./a"):
            self.assertTrue(self.scan(archive([(name, b"public")])), name)
        self.assertTrue(self.scan(archive([("a", b"public"), ("a", b"public")])))
        nul_name = archive([("axb", b"public")]).replace(b"axb", b"a\x00b")
        self.assertTrue(self.scan(nul_name))
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.assertTrue(self.scan(archive([(link, b"target")])))

    def test_encrypted_member_rejected(self):
        payload = bytearray(archive([("a", b"public")]))
        central = payload.index(b"PK\x01\x02")
        payload[6] |= 1
        payload[central + 8] |= 1
        self.assertTrue(self.scan(bytes(payload)))

    def test_crc_corruption_rejected(self):
        payload = bytearray(archive([("a", b"public")], zipfile.ZIP_STORED))
        payload[payload.index(b"public")] ^= 1
        self.assertTrue(self.scan(bytes(payload)))

    def test_large_classic_archive_is_fully_inspected(self):
        public = b"a" * (scanner.MAX_SCANNED_BLOB_BYTES + 1)
        payload = archive([("public.txt", public)], zipfile.ZIP_STORED)
        self.assertGreater(len(payload), scanner.MAX_SCANNED_BLOB_BYTES)
        self.assertEqual(self.scan(payload), [])

    def test_full_fetch_scans_other_ref_and_deleted_historical_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            upstream, checkout = root / "upstream", root / "checkout"
            upstream.mkdir()

            def git(*args, cwd=upstream):
                return subprocess.check_output(["git", *args], cwd=cwd, stderr=subprocess.STDOUT)

            git("init", "-q", "-b", "main")
            git("config", "user.name", "Unit Test")
            git("config", "user.email", "unit@example.invalid")
            (upstream / "public.txt").write_text("public fixture\n")
            git("add", ".")
            git("commit", "-qm", "clean base")
            git("switch", "-qc", "delivery")
            secret = b"gh" + b"p_" + b"A" * 30
            (upstream / "old.zip").write_bytes(archive([("code.txt", secret)]))
            git("add", ".")
            git("commit", "-qm", "archive fixture")
            git("rm", "old.zip")
            git("commit", "-qm", "remove archive fixture")
            git("switch", "-q", "main")
            git("clone", "--no-local", str(upstream), str(checkout), cwd=root)
            self.assertEqual(git("rev-parse", "--is-shallow-repository", cwd=checkout).strip(), b"false")
            self.assertFalse((checkout / "old.zip").exists())
            self.assertIn(b"refs/remotes/origin/delivery", git("show-ref", cwd=checkout))
            with mock.patch.object(scanner, "ROOT", checkout):
                errors = scanner.secret_errors()
            self.assertTrue(any("reachable Git object" in e and "GitHub token" in e for e in errors), errors)
            self.assertNotIn(secret.decode(), str(errors))


if __name__ == "__main__":
    unittest.main()
