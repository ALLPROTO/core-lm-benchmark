#!/usr/bin/env python3
"""Offline verifier for author-pinned ``voidtoken-v5-paper-v5`` metadata.

The tracked receipt is the trust input.  Asset hashes are compared directly
with that receipt; the release's own SHA256SUMS is checked only as a secondary
consistency file.  The GitHub Sigstore bundle is byte-pinned and its DSSE /
in-toto payload is validated with the Python standard library.  This module
does *not* perform cryptographic Sigstore signature or certificate validation.

No function in this module contacts a network or mutates Git state.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = (
    ROOT
    / "publication"
    / "receipts"
    / "voidtoken-v5-paper-v5.release-receipt.json"
)
ATTESTATION_PATH = (
    ROOT
    / "publication"
    / "receipts"
    / "voidtoken-v5-paper-v5.github-release-attestation.json"
)

PINNED_RECEIPT_SHA256 = (
    "bb6b3ca347d0040e64f6bad03fa067ab374d79e6fed574ff6530b82191a45cf2"
)
PINNED_REPOSITORY = "https://github.com/ALLPROTO/core-lm-benchmark"
PINNED_REPOSITORY_SLUG = "ALLPROTO/core-lm-benchmark"
PINNED_TAG = "voidtoken-v5-paper-v5"
PINNED_COMMIT = "e77175759dde47dfb7b56f4013c04686ffb7ddc9"
PINNED_TREE = "0ef3e0367268ce0815d0e408ec2c062f1b64d7c9"
PINNED_RELEASE_ID = 363130646
PINNED_OWNER_ID = 246591744
PINNED_REPOSITORY_ID = 1314990457
PINNED_PURL = f"pkg:github/{PINNED_REPOSITORY_SLUG}@{PINNED_TAG}"
PINNED_ASSET_NAMES = (
    "SHA256SUMS",
    "corelm_reproducibility.tar.gz",
    "corelm_voidtoken_v5.pdf",
    "corelm_voidtoken_v5_arxiv_source.tar.gz",
)
PINNED_RELEASE = {
    "api_url": "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/tags/voidtoken-v5-paper-v5",
    "created_at": "2026-07-31T12:34:05Z",
    "draft": False,
    "html_url": f"{PINNED_REPOSITORY}/releases/tag/{PINNED_TAG}",
    "id": PINNED_RELEASE_ID,
    "immutable": True,
    "name": "VoidToken v5 paper v5 — self-built macOS compression proof",
    "owner_id": PINNED_OWNER_ID,
    "package_id": PINNED_REPOSITORY_ID,
    "prerelease": False,
    "published_at": "2026-07-31T14:34:52Z",
    "repository_id": PINNED_REPOSITORY_ID,
    "tag": PINNED_TAG,
    "target_commitish": "main",
}
PINNED_SOURCE = {
    "commit": PINNED_COMMIT,
    "commit_signature": "UNSIGNED_GITHUB_API",
    "purl": PINNED_PURL,
    "repository": PINNED_REPOSITORY,
    "tag_kind": "lightweight",
    "tree": PINNED_TREE,
}
PINNED_ATTESTATION = {
    "download_url": (
        "https://github.com/ALLPROTO/core-lm-benchmark/attestations/38318869/download"
    ),
    "id": 38318869,
    "media_type": "application/vnd.dev.sigstore.bundle.v0.3+json",
    "path": (
        "publication/receipts/"
        "voidtoken-v5-paper-v5.github-release-attestation.json"
    ),
    "payload_type": "application/vnd.in-toto+json",
    "predicate_type": "https://in-toto.io/attestation/release/v0.2",
    "public_bytes_sha256": (
        "dc90ad74d2b76dfd2ea38582506d94f3c9bd5d3ce4a546fded491490b4f77762"
    ),
    "public_size_bytes": 3605,
    "signature_count": 1,
    "signature_verification": "NOT_PERFORMED_STDLIB_ONLY_PINNED_BUNDLE",
    "tracked_representation": "PUBLIC_BYTES_PLUS_SINGLE_LF",
    "tracked_size_bytes": 3606,
}
PINNED_VERIFICATION_SCOPE = {
    "attestation_bundle": (
        "BYTES_AND_SIGNED_PAYLOAD_PINNED_SIGNATURE_NOT_CRYPTOGRAPHICALLY_VERIFIED"
    ),
    "caller_supplied_assets": (
        "CALLER_SUPPLIED_BYTE_EQUIVALENCE_TO_AUTHOR_PINNED_PUBLIC_RELEASE"
    ),
    "release_metadata": "AUTHOR_PINNED_SAVED_GITHUB_METADATA_NOT_LIVE_VERIFIED",
    "remote_api": "NOT_CONTACTED_BY_OFFLINE_VERIFIER",
    "source_identity": (
        "CALLER_SUPPLIED_CLEAN_DETACHED_WORKTREE_EQUIVALENCE_TO_AUTHOR_PINNED_TAG"
    ),
}
PINNED_ASSETS = {
    "SHA256SUMS": {
        "content_type": "application/octet-stream",
        "created_at": "2026-07-31T14:34:37Z",
        "download_url": f"{PINNED_REPOSITORY}/releases/download/{PINNED_TAG}/SHA256SUMS",
        "id": 496790595,
        "name": "SHA256SUMS",
        "sha256": "3eb9a4afc5fbbaa86d11bd1a5412981eb81c58eadfffcff8ea8eb02a1a3265a2",
        "size_bytes": 292,
        "state": "uploaded",
        "updated_at": "2026-07-31T14:34:37Z",
    },
    "corelm_reproducibility.tar.gz": {
        "content_type": "application/x-gzip",
        "created_at": "2026-07-31T14:34:35Z",
        "download_url": (
            f"{PINNED_REPOSITORY}/releases/download/{PINNED_TAG}/"
            "corelm_reproducibility.tar.gz"
        ),
        "id": 496790563,
        "name": "corelm_reproducibility.tar.gz",
        "sha256": "faeaf75adbfd1056f09d1a2674ad930e093352d556cce4fa7301268f25bb3e61",
        "size_bytes": 2012121,
        "state": "uploaded",
        "updated_at": "2026-07-31T14:34:36Z",
    },
    "corelm_voidtoken_v5.pdf": {
        "content_type": "application/pdf",
        "created_at": "2026-07-31T14:34:36Z",
        "download_url": (
            f"{PINNED_REPOSITORY}/releases/download/{PINNED_TAG}/"
            "corelm_voidtoken_v5.pdf"
        ),
        "id": 496790577,
        "name": "corelm_voidtoken_v5.pdf",
        "sha256": "f3d79254a576f5824fa014519d075332be4ed2301fab50cb6bd173d7b5c95fee",
        "size_bytes": 129322,
        "state": "uploaded",
        "updated_at": "2026-07-31T14:34:37Z",
    },
    "corelm_voidtoken_v5_arxiv_source.tar.gz": {
        "content_type": "application/x-gzip",
        "created_at": "2026-07-31T14:34:35Z",
        "download_url": (
            f"{PINNED_REPOSITORY}/releases/download/{PINNED_TAG}/"
            "corelm_voidtoken_v5_arxiv_source.tar.gz"
        ),
        "id": 496790551,
        "name": "corelm_voidtoken_v5_arxiv_source.tar.gz",
        "sha256": "aee9d759844224edbaf5bd63864ab0666cbead4db6cc3a94b44869857685400a",
        "size_bytes": 31197,
        "state": "uploaded",
        "updated_at": "2026-07-31T14:34:35Z",
    },
}
CHECKSUM_ORDER = (
    "corelm_voidtoken_v5_arxiv_source.tar.gz",
    "corelm_reproducibility.tar.gz",
    "corelm_voidtoken_v5.pdf",
)
GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_METADATA_BYTES = 128 * 1024
MAX_ASSET_BYTES = 32 * 1024 * 1024
MAX_TRACKED_FILE_BYTES = 128 * 1024 * 1024
MAX_TRACKED_TOTAL_BYTES = 512 * 1024 * 1024
MAX_TRACKED_FILES = 10_000
GIT = Path("/usr/bin/git")


class PaperV5VerificationError(ValueError):
    """The historical release does not satisfy its pinned receipt."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PaperV5VerificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise PaperV5VerificationError(f"non-finite JSON value is forbidden: {value}")


def _json_bytes(raw: bytes, label: str) -> Any:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise PaperV5VerificationError(f"{label} must not contain a UTF-8 BOM")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_without_duplicates,
            parse_constant=_reject_constant,
        )
    except PaperV5VerificationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PaperV5VerificationError(f"{label} is not valid UTF-8 JSON") from error


def _identity(status: os.stat_result) -> tuple[int, ...]:
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_nlink,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def _stable_bytes(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
    expected_size: int | None = None,
) -> bytes:
    """Read one regular, single-link inode without following replacements."""

    try:
        before = path.lstat()
    except OSError as error:
        raise PaperV5VerificationError(f"{label} is unavailable: {path}") from error
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise PaperV5VerificationError(f"{label} must be a regular non-symlink file")
    if before.st_nlink != 1:
        raise PaperV5VerificationError(f"{label} must not be hard-linked")
    if before.st_size < 0 or before.st_size > maximum_bytes:
        raise PaperV5VerificationError(f"{label} exceeds its size bound")
    if expected_size is not None and before.st_size != expected_size:
        raise PaperV5VerificationError(
            f"{label} size differs from receipt: {before.st_size} != {expected_size}"
        )

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise PaperV5VerificationError(f"{label} cannot be opened safely") from error
    try:
        opened = os.fstat(descriptor)
        expected_identity = _identity(before)
        if _identity(opened) != expected_identity:
            raise PaperV5VerificationError(f"{label} changed before reading")
        chunks: list[bytes] = []
        observed = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - observed))
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
            if observed > maximum_bytes:
                raise PaperV5VerificationError(f"{label} exceeds its size bound")
        if _identity(os.fstat(descriptor)) != expected_identity:
            raise PaperV5VerificationError(f"{label} changed while reading")
    finally:
        os.close(descriptor)
    try:
        after = path.lstat()
    except OSError as error:
        raise PaperV5VerificationError(f"{label} disappeared after reading") from error
    if _identity(after) != expected_identity:
        raise PaperV5VerificationError(f"{label} path changed while reading")
    return b"".join(chunks)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PaperV5VerificationError(f"{label} must be a JSON object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise PaperV5VerificationError(f"{label} fields are not exact")


def _require_exact(value: Any, expected: Any, label: str) -> None:
    """Require recursive JSON equality without Python's bool/int coercion."""

    if type(value) is not type(expected):
        raise PaperV5VerificationError(f"{label} type is not exact")
    if isinstance(expected, dict):
        if set(value) != set(expected):
            raise PaperV5VerificationError(f"{label} fields are not exact")
        for key in expected:
            _require_exact(value[key], expected[key], f"{label}.{key}")
        return
    if isinstance(expected, list):
        if len(value) != len(expected):
            raise PaperV5VerificationError(f"{label} length is not exact")
        for index, (observed, wanted) in enumerate(zip(value, expected, strict=True)):
            _require_exact(observed, wanted, f"{label}[{index}]")
        return
    if value != expected:
        raise PaperV5VerificationError(f"{label} value is not exact")


def _decode_base64(value: Any, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise PaperV5VerificationError(f"{label} must be nonempty base64")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise PaperV5VerificationError(f"{label} is not valid base64") from error
    if not decoded:
        raise PaperV5VerificationError(f"{label} decodes to empty bytes")
    return decoded


def load_pinned_receipt(path: Path = RECEIPT_PATH) -> Mapping[str, Any]:
    raw = _stable_bytes(
        path,
        label="paper-v5 release receipt",
        maximum_bytes=MAX_METADATA_BYTES,
    )
    observed = hashlib.sha256(raw).hexdigest()
    if observed != PINNED_RECEIPT_SHA256:
        raise PaperV5VerificationError("paper-v5 release receipt SHA-256 is not pinned")
    value = _mapping(_json_bytes(raw, "paper-v5 release receipt"), "release receipt")
    if raw != _canonical_json(value):
        raise PaperV5VerificationError("paper-v5 release receipt is not canonical JSON")
    _exact_keys(
        value,
        {
            "artifact_kind",
            "assets",
            "attestation",
            "release",
            "schema_version",
            "source",
            "verification_scope",
        },
        "release receipt",
    )
    _require_exact(
        value["artifact_kind"],
        "corelm_historical_paper_release_receipt",
        "release receipt artifact kind",
    )
    _require_exact(value["schema_version"], 1, "release receipt schema version")
    _require_exact(value["release"], PINNED_RELEASE, "release receipt release")
    _require_exact(value["source"], PINNED_SOURCE, "release receipt source")
    _require_exact(
        value["attestation"], PINNED_ATTESTATION, "release receipt attestation"
    )
    _require_exact(
        value["verification_scope"],
        PINNED_VERIFICATION_SCOPE,
        "release receipt verification scope",
    )
    _require_exact(
        value["assets"],
        [PINNED_ASSETS[name] for name in PINNED_ASSET_NAMES],
        "release receipt assets",
    )
    return value


def verify_attestation(
    receipt: Mapping[str, Any], path: Path = ATTESTATION_PATH
) -> Mapping[str, Any]:
    contract = _mapping(receipt["attestation"], "release receipt attestation")
    raw = _stable_bytes(
        path,
        label="tracked GitHub release attestation",
        maximum_bytes=MAX_METADATA_BYTES,
        expected_size=contract["tracked_size_bytes"],
    )
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise PaperV5VerificationError(
            "tracked attestation must be public bytes plus exactly one LF"
        )
    public_bytes = raw[:-1]
    if len(public_bytes) != contract["public_size_bytes"]:
        raise PaperV5VerificationError("public attestation size differs from receipt")
    if hashlib.sha256(public_bytes).hexdigest() != contract["public_bytes_sha256"]:
        raise PaperV5VerificationError("public attestation SHA-256 differs from receipt")

    bundle = _mapping(_json_bytes(public_bytes, "GitHub release attestation"), "bundle")
    _exact_keys(bundle, {"dsseEnvelope", "mediaType", "verificationMaterial"}, "bundle")
    if bundle["mediaType"] != contract["media_type"]:
        raise PaperV5VerificationError("attestation media type differs from receipt")
    envelope = _mapping(bundle["dsseEnvelope"], "DSSE envelope")
    _exact_keys(envelope, {"payload", "payloadType", "signatures"}, "DSSE envelope")
    if envelope["payloadType"] != contract["payload_type"]:
        raise PaperV5VerificationError("DSSE payload type differs from receipt")
    signatures = envelope["signatures"]
    if not isinstance(signatures, list) or len(signatures) != contract["signature_count"]:
        raise PaperV5VerificationError("DSSE signature count differs from receipt")
    signature = _mapping(signatures[0], "DSSE signature")
    _exact_keys(signature, {"sig"}, "DSSE signature")
    _decode_base64(signature["sig"], "DSSE signature")

    material = _mapping(bundle["verificationMaterial"], "verification material")
    _exact_keys(material, {"certificate", "timestampVerificationData"}, "verification material")
    certificate = _mapping(material["certificate"], "verification certificate")
    _exact_keys(certificate, {"rawBytes"}, "verification certificate")
    _decode_base64(certificate["rawBytes"], "verification certificate")
    timestamp_data = _mapping(
        material["timestampVerificationData"], "timestamp verification data"
    )
    _exact_keys(timestamp_data, {"rfc3161Timestamps"}, "timestamp verification data")
    timestamps = timestamp_data["rfc3161Timestamps"]
    if not isinstance(timestamps, list) or len(timestamps) != 1:
        raise PaperV5VerificationError("attestation must contain one RFC3161 timestamp")
    timestamp = _mapping(timestamps[0], "RFC3161 timestamp")
    _exact_keys(timestamp, {"signedTimestamp"}, "RFC3161 timestamp")
    _decode_base64(timestamp["signedTimestamp"], "RFC3161 timestamp")

    statement_raw = _decode_base64(envelope["payload"], "DSSE payload")
    statement = _mapping(_json_bytes(statement_raw, "in-toto statement"), "statement")
    _exact_keys(statement, {"_type", "predicate", "predicateType", "subject"}, "statement")
    if statement["_type"] != "https://in-toto.io/Statement/v1":
        raise PaperV5VerificationError("in-toto statement type is not exact")
    if statement["predicateType"] != contract["predicate_type"]:
        raise PaperV5VerificationError("in-toto predicate type differs from receipt")

    release = _mapping(receipt["release"], "release receipt release")
    predicate = _mapping(statement["predicate"], "in-toto predicate")
    expected_predicate = {
        "databaseId": str(release["id"]),
        "ownerId": str(release["owner_id"]),
        "packageId": str(release["package_id"]),
        "purl": PINNED_PURL,
        "repository": PINNED_REPOSITORY_SLUG,
        "repositoryId": str(release["repository_id"]),
        "tag": PINNED_TAG,
    }
    if predicate != expected_predicate:
        raise PaperV5VerificationError("in-toto release predicate differs from receipt")

    subjects = statement["subject"]
    if not isinstance(subjects, list) or len(subjects) != 5:
        raise PaperV5VerificationError("in-toto statement must contain five subjects")
    observed_source: Mapping[str, Any] | None = None
    observed_assets: dict[str, str] = {}
    for item in subjects:
        subject = _mapping(item, "in-toto subject")
        digest = _mapping(subject.get("digest"), "in-toto subject digest")
        if "uri" in subject:
            _exact_keys(subject, {"digest", "uri"}, "source subject")
            if observed_source is not None:
                raise PaperV5VerificationError("in-toto source subject is duplicated")
            observed_source = subject
        else:
            _exact_keys(subject, {"digest", "name"}, "asset subject")
            name = subject.get("name")
            if not isinstance(name, str) or name in observed_assets:
                raise PaperV5VerificationError("in-toto asset subject is invalid or duplicated")
            if set(digest) != {"sha256"} or not isinstance(digest["sha256"], str):
                raise PaperV5VerificationError("in-toto asset subject digest is invalid")
            observed_assets[name] = digest["sha256"]
    if observed_source is None:
        raise PaperV5VerificationError("in-toto source subject is missing")
    source_digest = _mapping(observed_source["digest"], "source subject digest")
    if (
        observed_source["uri"] != PINNED_PURL
        or source_digest != {"sha1": PINNED_COMMIT}
    ):
        raise PaperV5VerificationError("in-toto source subject differs from receipt")
    expected_assets = {
        item["name"]: item["sha256"] for item in receipt["assets"]
    }
    if observed_assets != expected_assets:
        raise PaperV5VerificationError("in-toto asset subjects differ from receipt")
    return statement


def _run_git(
    repository: Path, arguments: Sequence[str], *, allowed: tuple[int, ...] = (0,)
) -> subprocess.CompletedProcess[bytes]:
    if not GIT.is_file() or not os.access(GIT, os.X_OK):
        raise PaperV5VerificationError("/usr/bin/git is required")
    environment = {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": "/nonexistent-corelm-verifier-home",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }
    try:
        completed = subprocess.run(
            [
                str(GIT),
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "-C",
                str(repository),
                *arguments,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise PaperV5VerificationError("local Git inspection failed") from error
    if completed.returncode not in allowed:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise PaperV5VerificationError(
            f"local Git inspection failed ({' '.join(arguments)}): "
            f"{detail or 'no diagnostic'}"
        )
    return completed


def _git(
    repository: Path, arguments: Sequence[str], *, allowed: tuple[int, ...] = (0,)
) -> tuple[int, str]:
    completed = _run_git(repository, arguments, allowed=allowed)
    try:
        output = completed.stdout.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise PaperV5VerificationError("local Git text output is not UTF-8") from error
    return completed.returncode, output


def _git_raw(
    repository: Path, arguments: Sequence[str], *, allowed: tuple[int, ...] = (0,)
) -> tuple[int, bytes]:
    completed = _run_git(repository, arguments, allowed=allowed)
    return completed.returncode, completed.stdout


def _safe_git_path(raw: bytes, label: str) -> str:
    try:
        value = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PaperV5VerificationError(f"{label} path is not UTF-8") from error
    parts = value.split("/")
    if (
        not value
        or value.startswith("/")
        or any(part in {"", ".", ".."} for part in parts)
        or parts[0] == ".git"
    ):
        raise PaperV5VerificationError(f"{label} path is unsafe")
    return value


def _nul_records(raw: bytes, label: str) -> list[bytes]:
    if not raw or not raw.endswith(b"\0"):
        raise PaperV5VerificationError(f"{label} is empty or not NUL-terminated")
    records = raw[:-1].split(b"\0")
    if any(not record for record in records):
        raise PaperV5VerificationError(f"{label} contains an empty record")
    return records


def _head_tree(repository: Path) -> dict[str, tuple[str, str]]:
    raw = _git_raw(repository, ("ls-tree", "-rz", "--full-tree", "HEAD"))[1]
    records = _nul_records(raw, "HEAD tree listing")
    if len(records) > MAX_TRACKED_FILES:
        raise PaperV5VerificationError("HEAD tree contains too many tracked files")
    tree: dict[str, tuple[str, str]] = {}
    for record in records:
        header, separator, raw_path = record.partition(b"\t")
        fields = header.split(b" ")
        if not separator or len(fields) != 3:
            raise PaperV5VerificationError("HEAD tree record is malformed")
        try:
            mode, object_type, object_id = (
                field.decode("ascii", errors="strict") for field in fields
            )
        except UnicodeDecodeError as error:
            raise PaperV5VerificationError("HEAD tree header is not ASCII") from error
        path = _safe_git_path(raw_path, "HEAD tree")
        if object_type != "blob" or mode not in {"100644", "100755", "120000"}:
            raise PaperV5VerificationError(
                "HEAD tree contains an unsupported mode, object, or gitlink"
            )
        if GIT_OBJECT_RE.fullmatch(object_id) is None or path in tree:
            raise PaperV5VerificationError("HEAD tree object or path is invalid")
        tree[path] = (mode, object_id)
    return tree


def _index_entries(repository: Path) -> dict[str, tuple[str, str]]:
    raw = _git_raw(repository, ("ls-files", "-z", "--stage"))[1]
    records = _nul_records(raw, "Git index listing")
    entries: dict[str, tuple[str, str]] = {}
    for record in records:
        header, separator, raw_path = record.partition(b"\t")
        fields = header.split(b" ")
        if not separator or len(fields) != 3:
            raise PaperV5VerificationError("Git index record is malformed")
        try:
            mode, object_id, stage = (
                field.decode("ascii", errors="strict") for field in fields
            )
        except UnicodeDecodeError as error:
            raise PaperV5VerificationError("Git index header is not ASCII") from error
        path = _safe_git_path(raw_path, "Git index")
        if (
            stage != "0"
            or mode not in {"100644", "100755", "120000"}
            or GIT_OBJECT_RE.fullmatch(object_id) is None
            or path in entries
        ):
            raise PaperV5VerificationError("Git index is staged, sparse, or malformed")
        entries[path] = (mode, object_id)
    return entries


def _verify_index_flags(repository: Path, expected_paths: set[str]) -> None:
    for option, label in (("-t", "status"), ("-v", "assume-unchanged"), ("-f", "fsmonitor")):
        raw = _git_raw(repository, ("ls-files", "-z", option))[1]
        records = _nul_records(raw, f"Git index {label} flags")
        observed: list[str] = []
        for record in records:
            if not record.startswith(b"H "):
                raise PaperV5VerificationError(
                    f"Git index {label} flags are not all ordinary tracked entries"
                )
            observed.append(_safe_git_path(record[2:], f"Git index {label}"))
        if len(observed) != len(set(observed)) or set(observed) != expected_paths:
            raise PaperV5VerificationError(f"Git index {label} paths differ from HEAD")


def _walk_worktree(root: Path, expected_paths: set[str]) -> tuple[dict[str, tuple[int, ...]], dict[str, tuple[int, ...]]]:
    expected_directories: set[str] = set()
    for tracked in expected_paths:
        parts = tracked.split("/")
        expected_directories.update("/".join(parts[:index]) for index in range(1, len(parts)))
    files: dict[str, tuple[int, ...]] = {}
    directories: dict[str, tuple[int, ...]] = {"": _identity(root.lstat())}

    def visit(directory: Path, relative: str) -> None:
        try:
            entries = list(os.scandir(directory))
        except OSError as error:
            raise PaperV5VerificationError("worktree cannot be enumerated safely") from error
        for entry in entries:
            child = entry.name if not relative else f"{relative}/{entry.name}"
            if not relative and entry.name == ".git":
                continue
            try:
                status = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise PaperV5VerificationError("worktree entry cannot be inspected") from error
            if stat.S_ISDIR(status.st_mode):
                if child not in expected_directories:
                    raise PaperV5VerificationError(
                        f"worktree contains an untracked directory: {child}"
                    )
                directories[child] = _identity(status)
                visit(Path(entry.path), child)
            elif stat.S_ISREG(status.st_mode) or stat.S_ISLNK(status.st_mode):
                if child in files:
                    raise PaperV5VerificationError("worktree path is duplicated")
                files[child] = _identity(status)
            else:
                raise PaperV5VerificationError(
                    f"worktree contains an unsupported filesystem entry: {child}"
                )

    visit(root, "")
    return files, directories


def _git_blob_sha1(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw, usedforsecurity=False).hexdigest()


def _verify_worktree_against_head(repository: Path) -> None:
    tree = _head_tree(repository)
    index = _index_entries(repository)
    if index != tree:
        raise PaperV5VerificationError("Git index entries differ from the exact HEAD tree")
    _verify_index_flags(repository, set(tree))

    initial_files, initial_directories = _walk_worktree(repository, set(tree))
    if set(initial_files) != set(tree):
        raise PaperV5VerificationError("worktree file set differs from the exact HEAD tree")
    seals: dict[str, tuple[int, ...]] = {}
    total_bytes = 0
    for path, (mode, expected_object) in tree.items():
        target = repository / path
        try:
            before = target.lstat()
        except OSError as error:
            raise PaperV5VerificationError(f"tracked path is unavailable: {path}") from error
        if _identity(before) != initial_files[path]:
            raise PaperV5VerificationError(f"tracked path changed before reading: {path}")
        if mode == "120000":
            if not stat.S_ISLNK(before.st_mode) or before.st_nlink != 1:
                raise PaperV5VerificationError(f"tracked symlink mode differs from HEAD: {path}")
            try:
                raw = os.fsencode(os.readlink(target))
                after = target.lstat()
            except OSError as error:
                raise PaperV5VerificationError(f"tracked symlink cannot be read: {path}") from error
            if _identity(after) != _identity(before):
                raise PaperV5VerificationError(f"tracked symlink changed while reading: {path}")
        else:
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise PaperV5VerificationError(f"tracked file mode differs from HEAD: {path}")
            executable = stat.S_IMODE(before.st_mode) & 0o111
            expected_executable = 0o111 if mode == "100755" else 0
            if executable != expected_executable:
                raise PaperV5VerificationError(f"tracked executable mode differs from HEAD: {path}")
            raw = _stable_bytes(
                target,
                label=f"tracked file {path}",
                maximum_bytes=MAX_TRACKED_FILE_BYTES,
            )
            after = target.lstat()
        total_bytes += len(raw)
        if total_bytes > MAX_TRACKED_TOTAL_BYTES:
            raise PaperV5VerificationError("tracked worktree exceeds its byte bound")
        if _git_blob_sha1(raw) != expected_object:
            raise PaperV5VerificationError(f"tracked bytes differ from HEAD blob: {path}")
        seals[path] = _identity(after)

    final_files, final_directories = _walk_worktree(repository, set(tree))
    if final_files != seals or final_directories != initial_directories:
        raise PaperV5VerificationError("worktree changed during independent tree verification")


def verify_source(repository: Path, receipt: Mapping[str, Any]) -> Mapping[str, str]:
    try:
        supplied = repository.absolute()
        supplied_status = supplied.lstat()
        resolved = supplied.resolve(strict=True)
    except OSError as error:
        raise PaperV5VerificationError("historical source repository is unavailable") from error
    if (
        supplied != resolved
        or stat.S_ISLNK(supplied_status.st_mode)
        or not resolved.is_dir()
    ):
        raise PaperV5VerificationError("historical source repository must be a real directory")
    if _git(resolved, ("rev-parse", "--is-inside-work-tree"))[1] != "true":
        raise PaperV5VerificationError("historical source is not a Git worktree")
    if Path(_git(resolved, ("rev-parse", "--show-toplevel"))[1]).resolve() != resolved:
        raise PaperV5VerificationError("historical source path is not the Git worktree root")
    if _git(resolved, ("rev-parse", "--show-object-format"))[1] != "sha1":
        raise PaperV5VerificationError("historical source does not use SHA-1 Git objects")
    for key in ("core.sparseCheckout", "core.sparseCheckoutCone", "index.sparse"):
        code, value = _git(
            resolved, ("config", "--bool", key), allowed=(0, 1)
        )
        if code == 0 and value != "false":
            raise PaperV5VerificationError("sparse checkout and sparse index are forbidden")
    sparse_path = Path(
        _git(resolved, ("rev-parse", "--git-path", "info/sparse-checkout"))[1]
    )
    if not sparse_path.is_absolute():
        sparse_path = resolved / sparse_path
    try:
        sparse_path.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise PaperV5VerificationError("sparse checkout state cannot be inspected") from error
    else:
        raise PaperV5VerificationError("sparse checkout metadata is forbidden")
    branch_code, branch = _git(
        resolved, ("symbolic-ref", "--quiet", "HEAD"), allowed=(0, 1)
    )
    if branch_code != 1 or branch:
        raise PaperV5VerificationError("historical source HEAD must be detached")
    if _git(
        resolved,
        (
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored=matching",
            "--ignore-submodules=none",
        ),
    )[1]:
        raise PaperV5VerificationError("historical source worktree must be clean")
    if _git(resolved, ("for-each-ref", "--format=%(refname)", "refs/replace"))[1]:
        raise PaperV5VerificationError("Git replacement refs are forbidden")
    graft_path = Path(_git(resolved, ("rev-parse", "--git-path", "info/grafts"))[1])
    if not graft_path.is_absolute():
        graft_path = resolved / graft_path
    try:
        graft_status = graft_path.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise PaperV5VerificationError("Git graft state cannot be inspected") from error
    else:
        if not stat.S_ISREG(graft_status.st_mode) or graft_status.st_size:
            raise PaperV5VerificationError("Git grafts are forbidden")

    source = _mapping(receipt["source"], "release receipt source")
    tag_kind = source["tag_kind"]
    if tag_kind != "lightweight":
        raise PaperV5VerificationError("historical tag contract is not lightweight")
    tag_ref = f"refs/tags/{PINNED_TAG}"
    checks = {
        "tag_type": _git(resolved, ("cat-file", "-t", tag_ref))[1],
        "tag_commit": _git(resolved, ("rev-parse", f"{tag_ref}^{{commit}}"))[1],
        "tag_tree": _git(resolved, ("rev-parse", f"{tag_ref}^{{tree}}"))[1],
        "head_commit": _git(resolved, ("rev-parse", "HEAD^{commit}"))[1],
        "head_tree": _git(resolved, ("rev-parse", "HEAD^{tree}"))[1],
    }
    if checks != {
        "tag_type": "commit",
        "tag_commit": PINNED_COMMIT,
        "tag_tree": PINNED_TREE,
        "head_commit": PINNED_COMMIT,
        "head_tree": PINNED_TREE,
    }:
        raise PaperV5VerificationError("detached tag commit/tree identity differs from receipt")

    origins = _git(
        resolved, ("config", "--local", "--get-all", "remote.origin.url")
    )[1].splitlines()
    allowed_origins = {
        PINNED_REPOSITORY,
        f"{PINNED_REPOSITORY}.git",
        f"git@github.com:{PINNED_REPOSITORY_SLUG}.git",
        f"ssh://git@github.com/{PINNED_REPOSITORY_SLUG}.git",
    }
    if len(origins) != 1 or origins[0] not in allowed_origins:
        raise PaperV5VerificationError("origin is not the canonical GitHub repository")
    _verify_worktree_against_head(resolved)
    if _git(
        resolved,
        (
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored=matching",
            "--ignore-submodules=none",
        ),
    )[1]:
        raise PaperV5VerificationError("historical source changed during verification")
    return {
        "commit": PINNED_COMMIT,
        "tree": PINNED_TREE,
        "tag": PINNED_TAG,
    }


def _read_sealed_asset(
    directory_fd: int,
    name: str,
    seal: tuple[int, ...],
    expected_size: int,
) -> bytes:
    try:
        before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as error:
        raise PaperV5VerificationError(
            f"caller-supplied asset is unavailable: {name}"
        ) from error
    if (
        _identity(before) != seal
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size != expected_size
        or before.st_size > MAX_ASSET_BYTES
    ):
        raise PaperV5VerificationError(
            f"caller-supplied asset seal or size differs from receipt: {name}"
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as error:
        raise PaperV5VerificationError(
            f"caller-supplied asset cannot be opened safely: {name}"
        ) from error
    try:
        if _identity(os.fstat(descriptor)) != seal:
            raise PaperV5VerificationError(
                f"caller-supplied asset changed before reading: {name}"
            )
        chunks: list[bytes] = []
        observed = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_ASSET_BYTES + 1 - observed))
            if not chunk:
                break
            observed += len(chunk)
            if observed > MAX_ASSET_BYTES:
                raise PaperV5VerificationError(
                    f"caller-supplied asset exceeds its byte bound: {name}"
                )
            chunks.append(chunk)
        if _identity(os.fstat(descriptor)) != seal:
            raise PaperV5VerificationError(
                f"caller-supplied asset changed while reading: {name}"
            )
    finally:
        os.close(descriptor)
    try:
        after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as error:
        raise PaperV5VerificationError(
            f"caller-supplied asset disappeared after reading: {name}"
        ) from error
    if _identity(after) != seal:
        raise PaperV5VerificationError(
            f"caller-supplied asset path changed while reading: {name}"
        )
    return b"".join(chunks)


def verify_assets(directory: Path, receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    try:
        supplied = directory.absolute()
        supplied_status = supplied.lstat()
        root = supplied.resolve(strict=True)
    except OSError as error:
        raise PaperV5VerificationError("caller-supplied asset directory is unavailable") from error
    if (
        stat.S_ISLNK(supplied_status.st_mode)
        or not stat.S_ISDIR(supplied_status.st_mode)
    ):
        raise PaperV5VerificationError(
            "caller-supplied asset directory must be a canonical real directory"
        )
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        directory_fd = os.open(root, directory_flags)
    except OSError as error:
        raise PaperV5VerificationError(
            "caller-supplied asset directory cannot be opened safely"
        ) from error
    try:
        directory_seal = _identity(os.fstat(directory_fd))
        if directory_seal != _identity(supplied_status):
            raise PaperV5VerificationError(
                "caller-supplied asset directory changed before verification"
            )
        try:
            initial_names = os.listdir(directory_fd)
        except OSError as error:
            raise PaperV5VerificationError(
                "caller-supplied asset directory cannot be enumerated"
            ) from error
        if (
            len(initial_names) != len(PINNED_ASSET_NAMES)
            or set(initial_names) != set(PINNED_ASSET_NAMES)
        ):
            raise PaperV5VerificationError(
                "caller-supplied directory must contain exactly four release assets"
            )
        seals: dict[str, tuple[int, ...]] = {}
        for name in PINNED_ASSET_NAMES:
            try:
                status = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as error:
                raise PaperV5VerificationError(
                    f"caller-supplied asset cannot be inspected: {name}"
                ) from error
            if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                raise PaperV5VerificationError(
                    f"caller-supplied asset must be regular and single-linked: {name}"
                )
            seals[name] = _identity(status)

        by_name = {item["name"]: item for item in receipt["assets"]}
        verified: list[dict[str, Any]] = []
        observed_bytes: dict[str, bytes] = {}
        for name in PINNED_ASSET_NAMES:
            expected = by_name[name]
            raw = _read_sealed_asset(
                directory_fd, name, seals[name], expected["size_bytes"]
            )
            digest = hashlib.sha256(raw).hexdigest()
            if digest != expected["sha256"]:
                raise PaperV5VerificationError(
                    f"caller-supplied asset SHA-256 differs from receipt: {name}"
                )
            observed_bytes[name] = raw
            verified.append({"name": name, "sha256": digest, "size_bytes": len(raw)})

        try:
            final_names = os.listdir(directory_fd)
            final_seals = {
                name: _identity(
                    os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                )
                for name in PINNED_ASSET_NAMES
            }
            final_directory_seal = _identity(os.fstat(directory_fd))
            final_path_seal = _identity(root.lstat())
        except OSError as error:
            raise PaperV5VerificationError(
                "caller-supplied asset snapshot changed during verification"
            ) from error
        if (
            len(final_names) != len(PINNED_ASSET_NAMES)
            or set(final_names) != set(PINNED_ASSET_NAMES)
            or final_seals != seals
            or final_directory_seal != directory_seal
            or final_path_seal != directory_seal
        ):
            raise PaperV5VerificationError(
                "caller-supplied asset snapshot changed during verification"
            )
    finally:
        os.close(directory_fd)

    expected_sums = b"".join(
        f"{by_name[name]['sha256']}  {name}\n".encode("ascii")
        for name in CHECKSUM_ORDER
    )
    if observed_bytes["SHA256SUMS"] != expected_sums:
        raise PaperV5VerificationError(
            "SHA256SUMS is inconsistent with the independently pinned receipt"
        )
    return verified


def verify(repository: Path, asset_directory: Path) -> Mapping[str, Any]:
    receipt = load_pinned_receipt()
    statement = verify_attestation(receipt)
    source = verify_source(repository, receipt)
    assets = verify_assets(asset_directory, receipt)
    return {
        "artifact_kind": "corelm_paper_v5_caller_supplied_equivalence_verification",
        "attestation": {
            "bundle_public_bytes_sha256": receipt["attestation"]["public_bytes_sha256"],
            "payload_predicate_type": statement["predicateType"],
            "signature_verification": "NOT_PERFORMED_STDLIB_ONLY_PINNED_BUNDLE",
        },
        "caller_supplied_assets": assets,
        "claim_scope": (
            "CALLER_SUPPLIED_BYTE_EQUIVALENCE_TO_AUTHOR_PINNED_PUBLIC_RELEASE"
        ),
        "receipt_sha256": PINNED_RECEIPT_SHA256,
        "release_metadata_scope": (
            "AUTHOR_PINNED_SAVED_GITHUB_METADATA_NOT_LIVE_VERIFIED"
        ),
        "source": source,
        "status": "CALLER_SUPPLIED_BYTE_EQUIVALENCE_TO_AUTHOR_PINNED_PUBLIC_RELEASE",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        required=True,
        type=Path,
        help="clean local worktree detached at voidtoken-v5-paper-v5",
    )
    parser.add_argument(
        "--asset-directory",
        required=True,
        type=Path,
        help="directory containing exactly four caller-supplied release-asset bytes",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    try:
        report = verify(options.repository, options.asset_directory)
    except PaperV5VerificationError as error:
        print(f"PAPER V5 PINNED BYTE EQUIVALENCE FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    print(
        "NOTICE: Sigstore bundle bytes and signed payload are pinned; "
        "cryptographic signature verification is NOT performed by this stdlib-only verifier.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
