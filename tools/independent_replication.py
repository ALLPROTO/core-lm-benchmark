#!/usr/bin/env python3
"""Record or verify a privacy-safe independent Core LM replication bundle.

This tool uses only the Python standard library.  ``record`` launches one of
the two public real-model regression commands; ``verify`` checks the resulting
small public bundle without running a model.  Software can validate bytes and
declared fields, but it cannot establish that the declarant is a human or is
independent from the project author.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import platform
import re
import secrets
import shutil
import signal
import socket
import stat
import tempfile
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_SCHEMA = "corelm-independent-replication-bundle-v1"
ATTESTATION_SCHEMA = "corelm-independent-human-attestation-v1"
ENVIRONMENT_SCHEMA = "corelm-independent-replication-environment-v1"
RUN_FILES_SCHEMA = "corelm-independent-replication-run-files-v1"
EXPECTED_PYTHON = (3, 12, 13)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SAFE_RELATIVE_RE = re.compile(r"^[A-Za-z0-9._/+@=-]+$")
TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PORTFOLIO_TAG_RE = re.compile(r"^corelm-portfolio-v[1-9][0-9]*$")
PROFILE_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/?$"
)
ABSOLUTE_PRIVATE_PATHS = (
    re.compile(rb"/Users/[A-Za-z0-9._-]+(?:/|\b)"),
    re.compile(rb"/home/[A-Za-z0-9._-]+(?:/|\b)"),
    re.compile(rb"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+(?:\\|\b)"),
)
PRIVATE_KEY_RE = re.compile(
    rb"-{5}BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-{5}"
)
SECRET_PATTERNS = (
    re.compile(rb"gh" + rb"[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"hf_[A-Za-z0-9]{20,}"),
    re.compile(rb"sk-" + rb"(?:proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    re.compile(rb"xox[baprs]-[A-Za-z0-9-]{20,}"),
    re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(rb"https?://[^/@\s:]+:[^/@\s]+@"),
    re.compile(
        rb"(?i)(?:authorization\s*:\s*)?bearer\s+[A-Za-z0-9._~+/=-]{12,}"
    ),
    re.compile(
        rb"(?i)(?:[?&](?:access_token|token|api_key|key|signature|sig)=)"
        rb"[^&#\s]{8,}"
    ),
)
ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
MAX_PUBLIC_FILE_BYTES = 64 * 1024 * 1024
MAX_RUN_FILES = 10_000
MAX_CHECKSUM_BYTES = MAX_RUN_FILES * 256
COMMANDS = {
    "macos": ("./corelm", "macos", "proof"),
    "linux": ("./corelm", "linux", "run"),
}
CANONICAL_REMOTE = "https://github.com/ALLPROTO/core-lm-benchmark.git"
GIT_BINARY = Path("/usr/bin/git")
EXPECTED_SIGNING_POLICY_SHA256 = (
    "36fb4a170eee7664be32f2a5d562db209fa4f6f1f24667cf6a3ef0166d155c16"
)
EXPECTED_SIGNING_PRINCIPAL = "ivantyschenko777@gmail.com"
EXPECTED_SIGNING_PUBLIC_KEY_SHA256 = (
    "9d299ff032927caef3f1355fb55c01f206ebf27ef35bcb5da547f962168b1274"
)
CRITICAL_TRACKED_FILES = frozenset(
    {
        "corelm",
        "tools/independent_replication.py",
        "signing/allowed_signers",
        "signing/corelm-codec-signing.pub",
        "platforms/linux/scripts/build-runtime.sh",
        "platforms/linux/scripts/doctor.sh",
        "platforms/linux/scripts/find-python312.sh",
        "platforms/linux/scripts/run-regression.sh",
        "platforms/linux/scripts/runtime_safety.py",
        "platforms/macos/scripts/build-app.sh",
        "platforms/macos/scripts/doctor.sh",
        "platforms/macos/scripts/package-app.sh",
        "platforms/macos/scripts/run-proof.sh",
        "RealLLM/app_proof_core.py",
        "RealLLM/app_proof_runner.py",
        "RealLLM/codecs.py",
        "RealLLM/develop_voidtoken_v5.py",
        "RealLLM/verify_voidtoken_v5_development.py",
        "RealLLM/voidtoken_v5.py",
        "security/find_python312.sh",
        "security/generate_app_proof_core.py",
        "security/generate_build_provenance.py",
        "security/generate_python_runtime_manifest.py",
        "security/proof_process_groups.sh",
        "security/run_process_group_tests.sh",
        "security/run_swift_security_tests.sh",
        "security/validate_proof_challenge.sh",
        "security/verify_app_bundle.sh",
        "security/verify_app_run_evidence.py",
        "security/verify_local_app_run.py",
        "security/verify_locked_environment.py",
        "security/verify_primary_evidence.py",
        "security/verify_primary_replay.py",
        "scripts/verify-python.sh",
    }
)
EXPECTED_HOSTS = {
    "macos": ("Darwin", "arm64"),
    "linux": ("Linux", "x86_64"),
}
BUNDLE_TOP_ENTRIES = {
    "environment.json",
    "human-attestation.json",
    "replication.json",
    "run-files.json",
    "run-evidence",
    "terminal.sanitized.log",
    "verifier.sanitized.log",
    "SHA256SUMS",
}
DECLARATION = (
    "I am a human independent of the Core LM author and AI agents. I ran the "
    "documented command on the declared machine from a fresh public clone, "
    "made no source changes before execution, and report this completed "
    "attempt without selecting or altering its metric outcome."
)


class ReplicationError(ValueError):
    """A fail-closed replication contract error."""


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReplicationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ReplicationError(f"non-finite JSON constant is forbidden: {value}")


def _read_json(path: Path, maximum: int = 4 * 1024 * 1024) -> dict[str, Any]:
    _require_regular_file(path, maximum)
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReplicationError(f"invalid JSON in {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise ReplicationError(f"{path.name} must contain a JSON object")
    return value


def _require_regular_file(path: Path, maximum: int = MAX_PUBLIC_FILE_BYTES) -> None:
    try:
        status = path.lstat()
    except FileNotFoundError as error:
        raise ReplicationError(f"missing file: {path.name}") from error
    if not stat.S_ISREG(status.st_mode) or stat.S_ISLNK(status.st_mode):
        raise ReplicationError(f"not a regular file: {path.name}")
    if status.st_size < 0 or status.st_size > maximum:
        raise ReplicationError(f"file exceeds bound: {path.name}")


def _sha256(path: Path) -> str:
    _require_regular_file(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ReplicationError(f"{label} is not a lowercase SHA-256")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReplicationError(f"{label} is not numeric")
    observed = float(value)
    if not math.isfinite(observed):
        raise ReplicationError(f"{label} is not finite")
    return observed


def _same_number(left: Any, right: Any, label: str) -> None:
    first = _finite_number(left, label)
    second = _finite_number(right, label)
    if not math.isclose(first, second, rel_tol=1e-12, abs_tol=1e-12):
        raise ReplicationError(f"{label} differs between result and receipt")


def _exact_object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ReplicationError(f"{label} fields are not exact")
    return value


def _timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ReplicationError(f"{label} must be a UTC ISO-8601 timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ReplicationError(f"{label} is not ISO-8601") from error
    return parsed


def _privacy_error(data: bytes) -> str | None:
    if PRIVATE_KEY_RE.search(data):
        return "private key material"
    for pattern in SECRET_PATTERNS:
        if pattern.search(data):
            return "credential-like value"
    for pattern in ABSOLUTE_PRIVATE_PATHS:
        if pattern.search(data):
            return "private home path"
    for variable in ("CORELM_PYPI_INDEX_URL", "CORELM_HF_ENDPOINT"):
        endpoint = os.environ.get(variable, "").encode("utf-8")
        if len(endpoint) >= 8 and endpoint in data:
            return f"configured endpoint value ({variable})"
    # Absolute paths under /private/var and /tmp are not identities, but a
    # published bundle should never contain the collector's actual home.
    home = str(Path.home()).encode("utf-8")
    if home and home in data:
        return "collector home path"
    return None


def _assert_public_bytes(data: bytes, label: str) -> None:
    error = _privacy_error(data)
    if error is not None:
        raise ReplicationError(f"{label} contains {error}")


def _validate_attestation(value: Any) -> dict[str, Any]:
    document = _exact_object(
        value,
        {
            "schemaVersion",
            "publicProfileURL",
            "attestedAt",
            "declaration",
            "statements",
        },
        "human attestation",
    )
    if document["schemaVersion"] != ATTESTATION_SCHEMA:
        raise ReplicationError("human attestation schema is unsupported")
    match = PROFILE_RE.fullmatch(document["publicProfileURL"] or "")
    if match is None:
        raise ReplicationError("publicProfileURL must identify a GitHub account")
    if match.group(1).casefold() == "allproto":
        raise ReplicationError("the project author's account is not independent")
    if "replace" in match.group(1).casefold():
        raise ReplicationError("the profile placeholder must be replaced")
    _timestamp(document["attestedAt"], "attestedAt")
    if document["declaration"] != DECLARATION:
        raise ReplicationError("the human declaration is not exact")
    statements = _exact_object(
        document["statements"],
        {
            "humanOperated",
            "notProjectAuthor",
            "notAIAgent",
            "freshPublicClone",
            "differentIndependentlyControlledMachine",
            "sourceUnmodifiedBeforeRun",
            "reportedWithoutOutcomeSelection",
        },
        "human attestation statements",
    )
    if any(value is not True for value in statements.values()):
        raise ReplicationError("every human attestation statement must be true")
    _assert_public_bytes(_canonical_json(document), "human attestation")
    return document


def _git_environment(*, remote: bool = False) -> dict[str, str]:
    environment = {
        "HOME": "/",
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_COUNT": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_GRAFT_FILE": "/dev/null",
    }
    if remote:
        # Remote identity checks must not discover the caller's repository or
        # its local URL rewrite/configuration rules.
        environment["GIT_CEILING_DIRECTORIES"] = "/"
    return environment


def _git_process_at(
    repository: Path,
    *arguments: str,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    _require_regular_file(GIT_BINARY, 256 * 1024 * 1024)
    resolved = repository.resolve(strict=True)
    return subprocess.run(
        (str(GIT_BINARY), "-C", str(resolved), *arguments),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=timeout,
        env=_git_environment(),
        cwd=resolved,
    )


def _git_process(*arguments: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return _git_process_at(ROOT, *arguments, timeout=timeout)


def _remote_git(*arguments: str) -> str:
    _require_regular_file(GIT_BINARY, 256 * 1024 * 1024)
    completed = subprocess.run(
        (
            str(GIT_BINARY),
            "-c",
            "protocol.file.allow=never",
            "-c",
            "http.followRedirects=false",
            *arguments,
        ),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
        env=_git_environment(remote=True),
        cwd="/",
    )
    if completed.returncode != 0:
        raise ReplicationError(
            f"canonical remote inspection failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _git(*arguments: str) -> str:
    completed = _git_process(*arguments)
    if completed.returncode != 0:
        raise ReplicationError(f"Git inspection failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _git_at(repository: Path, *arguments: str) -> str:
    completed = _git_process_at(repository, *arguments)
    if completed.returncode != 0:
        raise ReplicationError(f"Git inspection failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _canonicalize_origin(value: Any) -> str:
    if not isinstance(value, str):
        raise ReplicationError("origin must be a GitHub repository URL")
    accepted = (
        r"https://github\.com/ALLPROTO/core-lm-benchmark(?:\.git)?/?",
        r"git@github\.com:ALLPROTO/core-lm-benchmark(?:\.git)?",
        r"ssh://git@github\.com/ALLPROTO/core-lm-benchmark(?:\.git)?/?",
    )
    if not any(re.fullmatch(pattern, value) for pattern in accepted):
        raise ReplicationError("origin must be the canonical public repository")
    return CANONICAL_REMOTE


def _parse_annotated_tag_header(
    payload: str, requested_tag: str, expected_commit: str
) -> None:
    try:
        header, _body = payload.split("\n\n", 1)
    except ValueError as error:
        raise ReplicationError("annotated tag header is malformed") from error
    rows = header.splitlines()
    if len(rows) != 4 or not rows[3].startswith("tagger "):
        raise ReplicationError("annotated tag header is not exact")
    if rows[:3] != [
        f"object {expected_commit}",
        "type commit",
        f"tag {requested_tag}",
    ]:
        raise ReplicationError("annotated tag header identity is inconsistent")
    if any(
        sum(row.startswith(prefix) for row in rows) != 1
        for prefix in ("object ", "type ", "tag ", "tagger ")
    ):
        raise ReplicationError("annotated tag header contains duplicate identity fields")


def _verify_release_tag(
    tag: str,
    expected_commit: str | None = None,
    expected_tree: str | None = None,
    expected_tag_object: str | None = None,
) -> dict[str, str]:
    if TAG_RE.fullmatch(tag) is None:
        raise ReplicationError("expected release tag name is unsafe")
    reference = f"refs/tags/{tag}"
    if _git("for-each-ref", "--format=%(refname)", "refs/replace"):
        raise ReplicationError("Git replacement refs are forbidden")
    git_directory = Path(_git("rev-parse", "--git-dir"))
    if not git_directory.is_absolute():
        git_directory = ROOT / git_directory
    if (git_directory / "info/grafts").exists():
        raise ReplicationError("Git grafts are forbidden")
    if _git("cat-file", "-t", reference) != "tag":
        raise ReplicationError("release tag must be annotated, not lightweight")
    tag_object = _git("rev-parse", reference)
    commit = _git("rev-parse", f"{reference}^{{commit}}")
    tree = _git("rev-parse", f"{reference}^{{tree}}")
    for value, label in (
        (tag_object, "tag object"),
        (commit, "tag commit"),
        (tree, "tag tree"),
    ):
        if COMMIT_RE.fullmatch(value) is None:
            raise ReplicationError(f"{label} is malformed")
    if expected_commit is not None and commit != expected_commit:
        raise ReplicationError("release tag does not resolve to recorded commit")
    if expected_tree is not None and tree != expected_tree:
        raise ReplicationError("release tag does not resolve to recorded tree")
    if expected_tag_object is not None and tag_object != expected_tag_object:
        raise ReplicationError("release tag object differs from the bundle")
    policy = ROOT / "signing" / "allowed_signers"
    public_key = ROOT / "signing" / "corelm-codec-signing.pub"
    _require_regular_file(policy, 16 * 1024)
    _require_regular_file(public_key, 16 * 1024)
    policy_digest = _sha256(policy)
    public_key_digest = _sha256(public_key)
    if policy_digest != EXPECTED_SIGNING_POLICY_SHA256:
        raise ReplicationError("tracked signing policy is not the hard-pinned policy")
    if public_key_digest != EXPECTED_SIGNING_PUBLIC_KEY_SHA256:
        raise ReplicationError("tracked signing public key is not hard-pinned")
    public_key_fields = public_key.read_text(encoding="ascii").split()
    public_key_identity = " ".join(public_key_fields[:2])
    if (
        len(public_key_fields) < 2
        or public_key_identity not in policy.read_text(encoding="ascii")
    ):
        raise ReplicationError("allowed-signers policy does not contain the public key")
    tag_payload = _git("cat-file", "-p", reference)
    _parse_annotated_tag_header(tag_payload, tag, commit)
    if (
        tag_payload.count("-----BEGIN SSH SIGNATURE-----") != 1
        or tag_payload.count("-----END SSH SIGNATURE-----") != 1
        or "-----BEGIN PGP SIGNATURE-----" in tag_payload
    ):
        raise ReplicationError("release tag does not contain one SSH signature")
    verified = _git_process(
        "-c",
        "gpg.format=ssh",
        "-c",
        "gpg.ssh.program=/usr/bin/ssh-keygen",
        "-c",
        f"gpg.ssh.allowedSignersFile={policy}",
        "verify-tag",
        "--raw",
        tag,
    )
    verification_text = verified.stdout + verified.stderr
    if (
        verified.returncode != 0
        or "Good \"git\" signature for " + EXPECTED_SIGNING_PRINCIPAL
        not in verification_text
    ):
        raise ReplicationError("release tag SSH signature/principal is invalid")
    remote_rows = _remote_git(
        "ls-remote",
        "--tags",
        CANONICAL_REMOTE,
        reference,
        f"{reference}^{{}}",
    ).splitlines()
    remote: dict[str, str] = {}
    for row in remote_rows:
        parts = row.split("\t")
        if len(parts) != 2 or COMMIT_RE.fullmatch(parts[0]) is None:
            raise ReplicationError("canonical remote tag receipt is malformed")
        if parts[1] in remote:
            raise ReplicationError("canonical remote tag receipt is duplicated")
        remote[parts[1]] = parts[0]
    if remote != {reference: tag_object, f"{reference}^{{}}": commit}:
        raise ReplicationError(
            "local release tag object/commit differs from canonical origin"
        )
    return {
        "releaseTag": tag,
        "releaseTagObject": tag_object,
        "signingPolicySHA256": policy_digest,
        "signingPublicKeySHA256": public_key_digest,
        "signatureVerification": "SSH_ALLOWED_SIGNER_VERIFIED",
    }


def _verify_tracked_worktree(
    repository: Path = ROOT,
) -> dict[str, tuple[str, str]]:
    root = repository.resolve(strict=True)
    if _git_at(root, "rev-parse", "--show-object-format") != "sha1":
        raise ReplicationError("unsupported Git object format")
    completed = _git_process_at(
        root, "ls-tree", "-rz", "--full-tree", "HEAD"
    )
    if completed.returncode != 0:
        raise ReplicationError("cannot enumerate tracked release files")
    records = completed.stdout.split("\0")
    if records and records[-1] == "":
        records.pop()
    if not records:
        raise ReplicationError("release tree has no tracked files")
    entries: dict[str, tuple[str, str]] = {}
    for record in records:
        try:
            metadata, relative = record.split("\t", 1)
            mode, object_type, expected = metadata.split(" ", 2)
        except ValueError as error:
            raise ReplicationError("Git tree entry is malformed") from error
        if (
            object_type != "blob"
            or COMMIT_RE.fullmatch(expected) is None
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise ReplicationError("Git tree contains an unsupported entry")
        if relative in entries:
            raise ReplicationError("Git tree contains a duplicate path")
        path = root / relative
        try:
            status = path.lstat()
        except FileNotFoundError as error:
            raise ReplicationError(f"tracked file is missing: {relative}") from error
        if mode in {"100644", "100755"}:
            if not stat.S_ISREG(status.st_mode) or stat.S_ISLNK(status.st_mode):
                raise ReplicationError(f"tracked file type differs: {relative}")
            executable = bool(status.st_mode & 0o111)
            if executable != (mode == "100755"):
                raise ReplicationError(
                    f"tracked executable mode differs: {relative}"
                )
            data = path.read_bytes()
        else:
            raise ReplicationError(
                f"tracked tree must contain regular blobs only: {relative} ({mode})"
            )
        digest = hashlib.sha1(
            f"blob {len(data)}\0".encode("ascii") + data,
            usedforsecurity=False,
        ).hexdigest()
        if digest != expected:
            raise ReplicationError(f"tracked bytes differ from HEAD: {relative}")
        entries[relative] = (mode, expected)
    return entries


def _require_critical_tracked_files(
    entries: dict[str, tuple[str, str]],
) -> None:
    missing = sorted(CRITICAL_TRACKED_FILES - entries.keys())
    if missing:
        raise ReplicationError(
            "critical execution/policy file is not tracked: " + missing[0]
        )
    for relative in sorted(CRITICAL_TRACKED_FILES):
        mode, _object_id = entries[relative]
        if mode not in {"100644", "100755"}:
            raise ReplicationError(
                f"critical execution/policy file is not a regular blob: {relative}"
            )


def _reject_untracked_artifacts(
    repository: Path,
    entries: dict[str, tuple[str, str]],
    *,
    allowed_generated_prefixes: tuple[str, ...] = (),
) -> None:
    """Reject ignored and untracked filesystem entries, including valid pyc.

    A fresh clone is required to have an exact worktree topology.  After a
    macOS run, only the explicitly generated ``dist`` tree may remain; all
    other ignored/untracked files and every symlink still fail closed.
    """

    root = repository.resolve(strict=True)
    tracked = set(entries)

    def allowed(relative: str) -> bool:
        return any(
            relative == prefix or relative.startswith(prefix + "/")
            for prefix in allowed_generated_prefixes
        )

    for directory, names, files in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        kept: list[str] = []
        for name in names:
            path = current / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise ReplicationError(f"worktree symlink is forbidden: {relative}")
            if relative == ".git":
                continue
            kept.append(name)
        names[:] = kept
        for name in files:
            path = current / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise ReplicationError(f"worktree symlink is forbidden: {relative}")
            if relative == ".git" or relative in tracked or allowed(relative):
                continue
            # This deliberately rejects every extra file, not just suffixes.
            # Therefore a valid ignored __pycache__/*.pyc cannot be imported.
            raise ReplicationError(
                f"ignored/untracked worktree file is forbidden: {relative}"
            )


def _verify_exact_checkout(
    repository: Path,
    *,
    allowed_generated_prefixes: tuple[str, ...] = (),
) -> dict[str, tuple[str, str]]:
    root = repository.resolve(strict=True)
    git_directory = root / ".git"
    try:
        git_status = git_directory.lstat()
    except FileNotFoundError as error:
        raise ReplicationError("checkout has no private Git metadata directory") from error
    if not stat.S_ISDIR(git_status.st_mode) or stat.S_ISLNK(git_status.st_mode):
        raise ReplicationError(
            "checkout Git metadata must be a real directory, not a worktree link"
        )
    entries = _verify_tracked_worktree(root)
    _require_critical_tracked_files(entries)
    _reject_untracked_artifacts(
        root,
        entries,
        allowed_generated_prefixes=allowed_generated_prefixes,
    )
    return entries


def _worktree_seal(
    repository: Path, entries: dict[str, tuple[str, str]]
) -> dict[str, tuple[int, int, int, int, int]]:
    """Seal inode/ctime metadata to detect ordinary in-run source mutation."""

    root = repository.resolve(strict=True)
    paths = {root}
    for relative in entries:
        candidate = root / relative
        paths.add(candidate)
        parent = candidate.parent
        while parent != root:
            paths.add(parent)
            parent = parent.parent
    seal: dict[str, tuple[int, int, int, int, int]] = {}
    for candidate in sorted(paths, key=lambda item: item.as_posix()):
        status = candidate.lstat()
        relative = "." if candidate == root else candidate.relative_to(root).as_posix()
        seal[relative] = (
            status.st_dev,
            status.st_ino,
            status.st_ctime_ns,
            stat.S_IFMT(status.st_mode) | stat.S_IMODE(status.st_mode),
            status.st_size,
        )
    return seal


def _assert_worktree_seal(
    repository: Path,
    entries: dict[str, tuple[str, str]],
    expected: dict[str, tuple[int, int, int, int, int]],
) -> None:
    observed = _worktree_seal(repository, entries)
    if observed != expected:
        changed = sorted(set(observed) ^ set(expected))
        if not changed:
            changed = sorted(
                relative
                for relative in expected
                if observed.get(relative) != expected[relative]
            )
        detail = changed[0] if changed else "unknown path"
        raise ReplicationError(
            "execution checkout changed during the run (inode/ctime seal): "
            + detail
        )


def _fresh_execution_checkout(source: dict[str, Any], parent: Path) -> Path:
    """Clone the exact public signed tag into an isolated execution checkout."""

    target = parent / "exact-public-tree"
    if target.exists() or target.is_symlink():
        raise ReplicationError("fresh execution checkout path already exists")
    completed = subprocess.run(
        (
            str(GIT_BINARY),
            "-c",
            "protocol.file.allow=never",
            "-c",
            "http.followRedirects=false",
            "clone",
            "--no-local",
            "--depth=1",
            "--single-branch",
            "--branch",
            source["releaseTag"],
            "--config",
            "core.hooksPath=/dev/null",
            CANONICAL_REMOTE,
            str(target),
        ),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=600,
        env=_git_environment(remote=True),
        cwd="/",
    )
    if completed.returncode != 0:
        raise ReplicationError(
            "fresh canonical clone failed: " + completed.stderr.strip()
        )
    if (
        _git_at(target, "rev-parse", "HEAD") != source["commit"]
        or _git_at(target, "rev-parse", "HEAD^{tree}") != source["tree"]
        or _git_at(
            target, "rev-parse", f"refs/tags/{source['releaseTag']}"
        )
        != source["releaseTagObject"]
        or _canonicalize_origin(_git_at(target, "remote", "get-url", "origin"))
        != source["origin"]
    ):
        raise ReplicationError("fresh canonical clone differs from signed source")
    if _git_at(target, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ReplicationError("fresh canonical clone is not clean")
    _verify_exact_checkout(target)
    return target


def _source_identity(expected_tag: str) -> dict[str, Any]:
    if PORTFOLIO_TAG_RE.fullmatch(expected_tag) is None:
        raise ReplicationError(
            "expected tag must use the canonical corelm-portfolio-vN identity"
        )
    if _git("rev-parse", "--is-inside-work-tree") != "true":
        raise ReplicationError("record must run from a Git clone")
    dirty = _git("status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        raise ReplicationError("the clone must be completely clean before record")
    _verify_exact_checkout(ROOT)
    commit = _git("rev-parse", "HEAD")
    tree = _git("rev-parse", "HEAD^{tree}")
    if COMMIT_RE.fullmatch(commit) is None or COMMIT_RE.fullmatch(tree) is None:
        raise ReplicationError("Git commit or tree identity is malformed")
    remote = _canonicalize_origin(_git("remote", "get-url", "origin"))
    tag = _verify_release_tag(expected_tag, commit, tree)
    return {
        "commit": commit,
        "tree": tree,
        "origin": remote,
        "cleanBeforeRun": True,
        **tag,
    }


def _verify_checkout_matches_source(source: dict[str, Any]) -> None:
    if _git("status", "--porcelain=v1", "--untracked-files=all"):
        raise ReplicationError("bundle verifier checkout must be completely clean")
    _verify_exact_checkout(ROOT)
    if (
        _git("rev-parse", "HEAD") != source["commit"]
        or _git("rev-parse", "HEAD^{tree}") != source["tree"]
        or _canonicalize_origin(_git("remote", "get-url", "origin"))
        != source["origin"]
    ):
        raise ReplicationError("bundle verifier checkout differs from source")


def _command_version(command: Iterable[str]) -> str | None:
    try:
        completed = subprocess.run(
            tuple(command),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    line = completed.stdout.strip().splitlines()
    return line[0][:512] if completed.returncode == 0 and line else None


def _memory_bytes(system: str) -> int | None:
    if system == "Darwin":
        try:
            completed = subprocess.run(
                ("/usr/sbin/sysctl", "-n", "hw.memsize"),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
            )
            return int(completed.stdout.strip())
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
    if system == "Linux":
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return None
    return None


def _environment(platform_name: str) -> dict[str, Any]:
    system = platform.system()
    architecture = platform.machine()
    expected = EXPECTED_HOSTS[platform_name]
    if (system, architecture) != expected:
        raise ReplicationError(
            f"{platform_name} record requires {expected[0]} {expected[1]}; "
            f"found {system} {architecture}"
        )
    return {
        "schemaVersion": ENVIRONMENT_SCHEMA,
        "system": system,
        "osRelease": platform.release(),
        "architecture": architecture,
        "pythonVersion": platform.python_version(),
        "cpuCount": os.cpu_count(),
        "memoryBytes": _memory_bytes(system),
        "tools": {
            "git": _command_version((str(GIT_BINARY), "--version")),
            "swift": (
                _command_version(("swift", "--version"))
                if platform_name == "macos"
                else None
            ),
        },
        "privacy": {
            "hostnameCollected": False,
            "localUsernameCollected": False,
            "environmentDumped": False,
        },
    }


def _safe_child_environment(extra: dict[str, str]) -> dict[str, str]:
    allowed = {
        "HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "TERM",
        "CORELM_OFFLINE",
        "CORELM_WHEELHOUSE",
        "CORELM_PYPI_INDEX_URL",
        "CORELM_HF_ENDPOINT",
        "CORELM_LINUX_RUNTIME",
        "CORELM_LINUX_HF_HOME",
    }
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    environment.setdefault("LANG", "C")
    environment.setdefault("LC_ALL", "C")
    environment.update(extra)
    return environment


def _redaction_values(
    additional: Iterable[tuple[str, str]] = (),
) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    candidates = (
        (str(ROOT), "$REPOSITORY"),
        (str(Path.home()), "$HOME"),
        (os.environ.get("USER", ""), "$USER"),
        (os.environ.get("LOGNAME", ""), "$USER"),
        (socket.gethostname(), "$HOST"),
        (os.environ.get("TMPDIR", ""), "$TMPDIR"),
        (os.environ.get("CORELM_WHEELHOUSE", ""), "$WHEELHOUSE"),
        (os.environ.get("CORELM_LINUX_RUNTIME", ""), "$RUNTIME"),
        (os.environ.get("CORELM_LINUX_HF_HOME", ""), "$MODEL_CACHE"),
        (os.environ.get("CORELM_PYPI_INDEX_URL", ""), "$PYPI_ENDPOINT"),
        (os.environ.get("CORELM_HF_ENDPOINT", ""), "$HF_ENDPOINT"),
        *tuple(additional),
    )
    for original, replacement in candidates:
        if original and len(original) >= 2:
            values.append((original, replacement))
    return sorted(set(values), key=lambda item: len(item[0]), reverse=True)


def _sanitize_text(
    text: str,
    additional_redactions: Iterable[tuple[str, str]] = (),
) -> tuple[str, int]:
    sanitized = ANSI_ESCAPE.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    replacements = 0
    for original, replacement in _redaction_values(additional_redactions):
        count = sanitized.count(original)
        if count:
            sanitized = sanitized.replace(original, replacement)
            replacements += count
    raw = sanitized.encode("utf-8", errors="replace")
    for pattern in SECRET_PATTERNS:
        raw, count = pattern.subn(b"[REDACTED_CREDENTIAL]", raw)
        replacements += count
    sanitized = raw.decode("utf-8", errors="replace")
    return sanitized, replacements


def _capture(
    command: tuple[str, ...],
    environment: dict[str, str],
    destination: Path,
    *,
    cwd: Path = ROOT,
) -> tuple[int, int]:
    resolved_cwd = cwd.resolve(strict=True)
    redaction_values = ((str(resolved_cwd), "$EXECUTION_CHECKOUT"),)
    process = subprocess.Popen(
        command,
        cwd=resolved_cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        start_new_session=True,
    )
    assert process.stdout is not None
    redactions = 0
    written = 0
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            for chunk in process.stdout:
                sanitized, count = _sanitize_text(chunk, redaction_values)
                if "[REDACTED_CREDENTIAL]" in sanitized:
                    raise ReplicationError(
                        "terminal emitted a credential-like value"
                    )
                redactions += count
                written += len(sanitized.encode("utf-8"))
                if written > MAX_PUBLIC_FILE_BYTES:
                    raise ReplicationError(
                        "terminal log exceeded the public bound"
                    )
                handle.write(sanitized)
                handle.flush()
                sys.stdout.write(sanitized)
                sys.stdout.flush()
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=15)
        raise
    finally:
        process.stdout.close()
    return process.wait(), redactions


def _capture_verifier(
    command: tuple[str, ...], *, cwd: Path = ROOT
) -> tuple[str, int]:
    resolved_cwd = cwd.resolve(strict=True)
    completed = subprocess.run(
        command,
        cwd=resolved_cwd,
        env=_safe_child_environment({}),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    sanitized, redactions = _sanitize_text(
        completed.stdout,
        ((str(resolved_cwd), "$EXECUTION_CHECKOUT"),),
    )
    if "[REDACTED_CREDENTIAL]" in sanitized:
        raise ReplicationError("verifier emitted a credential-like value")
    if completed.returncode != 0:
        raise ReplicationError(f"independent verifier failed:\n{sanitized}")
    return sanitized, redactions


def _macos_results_root() -> Path:
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "CoreLMBenchmark"
        / "real-llm-results"
    )


def _complete_macos_runs() -> set[Path]:
    root = _macos_results_root()
    if not root.is_dir() or root.is_symlink():
        return set()
    result: set[Path] = set()
    for candidate in root.iterdir():
        if candidate.is_symlink() or not candidate.is_dir():
            continue
        if (candidate / "app-run-receipt.json").is_file() and (
            candidate / "validation-064-071.json"
        ).is_file():
            result.add(candidate.resolve())
    return result


def _run_file_manifest(run_directory: Path) -> dict[str, Any]:
    if run_directory.is_symlink() or not run_directory.is_dir():
        raise ReplicationError("run directory is missing or symlinked")
    files: list[dict[str, Any]] = []
    for path in sorted(run_directory.rglob("*"), key=lambda item: item.as_posix()):
        status = path.lstat()
        if stat.S_ISDIR(status.st_mode) and not stat.S_ISLNK(status.st_mode):
            continue
        if not stat.S_ISREG(status.st_mode) or stat.S_ISLNK(status.st_mode):
            raise ReplicationError("run evidence contains a non-regular entry")
        relative = path.relative_to(run_directory).as_posix()
        if SAFE_RELATIVE_RE.fullmatch(relative) is None or ".." in Path(relative).parts:
            raise ReplicationError("run evidence contains an unsafe path")
        files.append({"path": relative, "bytes": status.st_size, "sha256": _sha256(path)})
        if len(files) > MAX_RUN_FILES:
            raise ReplicationError("run evidence contains too many files")
    if not files:
        raise ReplicationError("run evidence is empty")
    return {
        "schemaVersion": RUN_FILES_SCHEMA,
        "rawEvidenceIncludedInPublicBundle": True,
        "files": files,
    }


def _copy_public_file(source: Path, destination: Path) -> None:
    _require_regular_file(source, 8 * 1024 * 1024)
    data = source.read_bytes()
    _assert_public_bytes(data, source.name)
    destination.write_bytes(data)


def _copy_run_evidence(
    platform_name: str, run_directory: Path, destination: Path
) -> None:
    destination.mkdir(mode=0o700)
    receipt_name = (
        "app-run-receipt.json"
        if platform_name == "macos"
        else "run-manifest.json"
    )
    names = [receipt_name, "validation-064-071.json"]
    if platform_name == "linux":
        names.append("pre-run-contract.json")
    total = 0
    for name in names:
        source = run_directory / name
        _require_regular_file(source, 8 * 1024 * 1024)
        data = source.read_bytes()
        _assert_public_bytes(data, name)
        total += len(data)
        (destination / name).write_bytes(data)
    primary = run_directory / "primary-evidence"
    if primary.is_symlink() or not primary.is_dir():
        raise ReplicationError("primary evidence directory is missing or unsafe")
    for source in sorted(primary.rglob("*"), key=lambda item: item.as_posix()):
        status = source.lstat()
        relative = source.relative_to(run_directory)
        target = destination / relative
        if stat.S_ISDIR(status.st_mode) and not stat.S_ISLNK(status.st_mode):
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
            continue
        if not stat.S_ISREG(status.st_mode) or stat.S_ISLNK(status.st_mode):
            raise ReplicationError(
                "primary evidence contains a non-regular entry"
            )
        total += status.st_size
        if total > MAX_PUBLIC_FILE_BYTES:
            raise ReplicationError("raw public evidence exceeds the bundle bound")
        # Containers are binary, but high-confidence key/path/credential
        # markers are still forbidden.  Binary evidence is not a privacy-scan
        # exemption.
        _assert_public_bytes(source.read_bytes(), relative.as_posix())
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _extract_run_contract(
    platform_name: str,
    run_directory: Path,
    source: dict[str, Any],
    challenge: str | None,
) -> tuple[Path, Path, str, str]:
    if platform_name == "macos":
        receipt_path = run_directory / "app-run-receipt.json"
        receipt = _read_json(receipt_path)
        if receipt.get("challengeNonce") != challenge:
            raise ReplicationError("macOS receipt does not bind the fresh challenge")
        provenance = receipt.get("buildProvenance", {}).get("document", {}).get("source", {})
        if provenance.get("commit") != source["commit"] or provenance.get("tree") != source["tree"]:
            raise ReplicationError("macOS receipt source differs from the clone")
        result_entry = receipt.get("result")
        if not isinstance(result_entry, dict):
            raise ReplicationError("macOS receipt has no result binding")
        relative = result_entry.get("path")
        expected_file_digest = result_entry.get("resultFileSHA256")
        canonical_digest = result_entry.get("resultSHA256")
    else:
        receipt_path = run_directory / "run-manifest.json"
        receipt = _read_json(receipt_path)
        contract = _read_json(run_directory / "pre-run-contract.json")
        if receipt.get("sourceCommit") != source["commit"]:
            raise ReplicationError("Linux receipt source differs from the clone")
        if contract.get("sourceCommit") != source["commit"] or contract.get("sourceTree") != source["tree"]:
            raise ReplicationError("Linux pre-run source differs from the clone")
        relative = "validation-064-071.json"
        expected_file_digest = None
        canonical_digest = receipt.get("resultSHA256")
    if not isinstance(relative, str) or Path(relative).is_absolute() or relative != Path(relative).name:
        raise ReplicationError("result path is not a safe relative filename")
    result_path = run_directory / relative
    file_digest = _sha256(result_path)
    if expected_file_digest is not None and _digest(expected_file_digest, "receipt result file") != file_digest:
        raise ReplicationError("receipt result file digest is inconsistent")
    result = _read_json(result_path)
    canonical = _digest(canonical_digest, "receipt canonical result")
    if result.get("resultSHA256") != canonical:
        raise ReplicationError("receipt and result canonical digests differ")
    return receipt_path, result_path, file_digest, canonical


def _metric_verdict_from_result(result_path: Path) -> str:
    result = _read_json(result_path)
    aggregates = result.get("aggregates")
    if not isinstance(aggregates, list) or len(aggregates) != 1:
        raise ReplicationError("canonical result must contain one aggregate")
    aggregate = aggregates[0]
    if not isinstance(aggregate, dict) or not isinstance(
        aggregate.get("pass"), bool
    ):
        raise ReplicationError("canonical result aggregate is malformed")
    return "PASS" if aggregate["pass"] else "FAIL"


def _write_checksums(directory: Path) -> None:
    names = sorted(
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.name != "SHA256SUMS"
    )
    rows = [f"{_sha256(directory / name)}  {name}\n" for name in names]
    (directory / "SHA256SUMS").write_text("".join(rows), encoding="ascii")


def _assemble_bundle(
    output: Path,
    platform_name: str,
    source: dict[str, Any],
    environment: dict[str, Any],
    attestation_path: Path,
    run_directory: Path,
    terminal_log: Path,
    verifier_text: str,
    challenge: str | None,
    started_at: str,
    completed_at: str,
    redactions: int,
    exit_code: int = 0,
    terminal_outcome: str = "COMPLETED",
) -> None:
    attestation = _validate_attestation(_read_json(attestation_path, 64 * 1024))
    receipt, result, result_file_digest, result_digest = _extract_run_contract(
        platform_name, run_directory, source, challenge
    )
    metric_verdict = _metric_verdict_from_result(result)
    public_evidence = output / "run-evidence"
    _copy_run_evidence(platform_name, run_directory, public_evidence)
    run_files = _run_file_manifest(public_evidence)
    _copy_public_file(attestation_path, output / "human-attestation.json")
    _copy_public_file(terminal_log, output / "terminal.sanitized.log")
    (output / "verifier.sanitized.log").write_text(verifier_text, encoding="utf-8")
    (output / "environment.json").write_bytes(_canonical_json(environment))
    (output / "run-files.json").write_bytes(_canonical_json(run_files))
    receipt_copy = public_evidence / receipt.name
    terminal_copy = output / "terminal.sanitized.log"
    verifier_copy = output / "verifier.sanitized.log"
    document = {
        "schemaVersion": BUNDLE_SCHEMA,
        "evidenceClass": "PUBLIC_VALIDATION_REGRESSION",
        "countsTowardScientificVerdict": False,
        "metricVerdict": metric_verdict,
        "source": source,
        "execution": {
            "platform": platform_name,
            "command": list(COMMANDS[platform_name]),
            "startedAt": started_at,
            "completedAt": completed_at,
            "exitCode": exit_code,
            "terminalOutcome": terminal_outcome,
            "freshChallenge": challenge,
        },
        "environment": {
            "path": "environment.json",
            "sha256": _sha256(output / "environment.json"),
        },
        "runEvidence": {
            "receipt": {
                "path": f"run-evidence/{receipt.name}",
                "sha256": _sha256(receipt_copy),
            },
            "resultFileSHA256": result_file_digest,
            "canonicalResultSHA256": result_digest,
            "runFileManifest": {
                "path": "run-files.json",
                "sha256": _sha256(output / "run-files.json"),
                "fileCount": len(run_files["files"]),
            },
            "rawEvidenceIncludedInPublicBundle": True,
        },
        "reports": {
            "terminal": {
                "path": "terminal.sanitized.log",
                "sha256": _sha256(terminal_copy),
                "privacyRedactions": redactions,
            },
            "productVerifier": {
                "path": "verifier.sanitized.log",
                "sha256": _sha256(verifier_copy),
                "exitCode": 0,
            },
        },
        "humanAttestation": {
            "path": "human-attestation.json",
            "sha256": _sha256(output / "human-attestation.json"),
            "softwareAssessment": "DECLARED_ONLY_NOT_VERIFIED_BY_SOFTWARE",
            "publicProfileURL": attestation["publicProfileURL"],
        },
        "claimBoundary": {
            "automatedIntegrity": "PASS",
            "humanIdentity": "REQUIRES_PUBLIC_ACCOUNT_REVIEW",
            "independence": "REQUIRES_HUMAN_REVIEW",
            "scientificGeneralization": "NOT_CLAIMED",
        },
    }
    (output / "replication.json").write_bytes(_canonical_json(document))
    _write_checksums(output)


def _parse_checksums(path: Path) -> dict[str, str]:
    _require_regular_file(path, MAX_CHECKSUM_BYTES)
    result: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(
            r"([0-9a-f]{64})  ([A-Za-z0-9._/+@=-]+)", line
        )
        if match is None or match.group(2) in result:
            raise ReplicationError("SHA256SUMS is malformed")
        result[match.group(2)] = match.group(1)
    return result


def _run_portable_macos_verifier(
    result_path: Path, receipt_path: Path, challenge: str
) -> None:
    """Run the canonical full receipt verifier in an isolated interpreter."""

    _require_regular_file(result_path)
    _require_regular_file(receipt_path)
    _digest(challenge, "fresh challenge")
    code = """
import sys
sys.path.insert(0, sys.argv[1])
from security.verify_app_run_evidence import _verify_result_and_receipt
_verify_result_and_receipt(
    __import__('pathlib').Path(sys.argv[2]),
    __import__('pathlib').Path(sys.argv[3]),
    None,
    portable_macos_environment=True,
    expected_challenge_nonce=sys.argv[4],
    require_metric_pass=False,
)
print('PORTABLE MACOS RECEIPT/APPLICATION/WORKER/PROVENANCE PASS')
"""
    with tempfile.TemporaryDirectory(prefix="corelm-portable-pycache-") as cache:
        environment = _safe_child_environment(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPYCACHEPREFIX": cache,
            }
        )
        completed = subprocess.run(
            (
                sys.executable,
                "-I",
                "-B",
                "-c",
                code,
                str(ROOT),
                str(result_path),
                str(receipt_path),
                challenge,
            ),
            cwd="/",
            env=environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
    if (
        completed.returncode != 0
        or "PORTABLE MACOS RECEIPT/APPLICATION/WORKER/PROVENANCE PASS"
        not in completed.stdout
    ):
        sanitized, _redactions = _sanitize_text(completed.stdout)
        raise ReplicationError(
            "full portable macOS evidence verifier failed: " + sanitized.strip()
        )


def verify_bundle(directory: Path) -> dict[str, Any]:
    root = directory.resolve(strict=True)
    if directory.is_symlink() or not root.is_dir():
        raise ReplicationError("bundle must be a real directory")
    observed = {path.name for path in root.iterdir()}
    if observed != BUNDLE_TOP_ENTRIES:
        raise ReplicationError("bundle file set is not exact")
    for path in root.rglob("*"):
        status = path.lstat()
        if not (stat.S_ISREG(status.st_mode) or stat.S_ISDIR(status.st_mode)):
            raise ReplicationError("bundle contains a non-regular entry")
    checksums = _parse_checksums(root / "SHA256SUMS")
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.name != "SHA256SUMS"
    }
    if set(checksums) != actual_files:
        raise ReplicationError("SHA256SUMS does not cover the exact bundle")
    for name, digest in checksums.items():
        if _sha256(root / name) != digest:
            raise ReplicationError(f"checksum mismatch: {name}")
    public_files = set(actual_files)
    public_files.add("SHA256SUMS")
    for name in public_files:
        data = (root / name).read_bytes()
        _assert_public_bytes(data, name)
    document = _exact_object(
        _read_json(root / "replication.json"),
        {
            "schemaVersion",
            "evidenceClass",
            "countsTowardScientificVerdict",
            "metricVerdict",
            "source",
            "execution",
            "environment",
            "runEvidence",
            "reports",
            "humanAttestation",
            "claimBoundary",
        },
        "replication document",
    )
    if document["schemaVersion"] != BUNDLE_SCHEMA:
        raise ReplicationError("bundle schema is unsupported")
    if document["evidenceClass"] != "PUBLIC_VALIDATION_REGRESSION" or document["countsTowardScientificVerdict"] is not False:
        raise ReplicationError("bundle misclassifies a regression")
    source = _exact_object(
        document["source"],
        {
            "commit",
            "tree",
            "origin",
            "cleanBeforeRun",
            "releaseTag",
            "releaseTagObject",
            "signingPolicySHA256",
            "signingPublicKeySHA256",
            "signatureVerification",
        },
        "source",
    )
    if COMMIT_RE.fullmatch(source["commit"] or "") is None or COMMIT_RE.fullmatch(source["tree"] or "") is None:
        raise ReplicationError("source identity is malformed")
    if source["cleanBeforeRun"] is not True:
        raise ReplicationError("source was not clean before run")
    if source["origin"] != CANONICAL_REMOTE:
        raise ReplicationError("source origin is not the canonical repository")
    if source["signatureVerification"] != "SSH_ALLOWED_SIGNER_VERIFIED":
        raise ReplicationError("release tag signature is not verified")
    _digest(source["signingPolicySHA256"], "signing policy")
    _digest(source["signingPublicKeySHA256"], "signing public key")
    if source["signingPublicKeySHA256"] != EXPECTED_SIGNING_PUBLIC_KEY_SHA256:
        raise ReplicationError("signing public key differs from the hard pin")
    if COMMIT_RE.fullmatch(source["releaseTagObject"] or "") is None:
        raise ReplicationError("release tag object is malformed")
    if PORTFOLIO_TAG_RE.fullmatch(source["releaseTag"] or "") is None:
        raise ReplicationError("release tag is not a canonical portfolio tag")
    _verify_checkout_matches_source(source)
    execution = _exact_object(
        document["execution"],
        {
            "platform",
            "command",
            "startedAt",
            "completedAt",
            "exitCode",
            "terminalOutcome",
            "freshChallenge",
        },
        "execution",
    )
    platform_name = execution["platform"]
    normal_completion = (
        execution["exitCode"] == 0
        and execution["terminalOutcome"] == "COMPLETED"
    )
    preserved_macos_fail = (
        platform_name == "macos"
        and execution["exitCode"] == 0
        and execution["terminalOutcome"] == "METRIC_FAIL_PRESERVED"
    )
    if (
        platform_name not in COMMANDS
        or execution["command"] != list(COMMANDS[platform_name])
        or not (normal_completion or preserved_macos_fail)
    ):
        raise ReplicationError("execution contract is inconsistent")
    started = _timestamp(execution["startedAt"], "startedAt")
    completed = _timestamp(execution["completedAt"], "completedAt")
    if completed < started:
        raise ReplicationError("execution timestamps are reversed")
    challenge = execution["freshChallenge"]
    if platform_name == "macos":
        _digest(challenge, "fresh challenge")
    elif challenge is not None:
        raise ReplicationError("Linux execution must not claim a macOS challenge")
    environment = _exact_object(
        _read_json(root / "environment.json"),
        {
            "schemaVersion",
            "system",
            "osRelease",
            "architecture",
            "pythonVersion",
            "cpuCount",
            "memoryBytes",
            "tools",
            "privacy",
        },
        "environment",
    )
    if environment["schemaVersion"] != ENVIRONMENT_SCHEMA:
        raise ReplicationError("environment schema is unsupported")
    if (environment.get("system"), environment.get("architecture")) != EXPECTED_HOSTS[platform_name]:
        raise ReplicationError("environment and platform differ")
    if environment.get("privacy") != {
        "hostnameCollected": False,
        "localUsernameCollected": False,
        "environmentDumped": False,
    }:
        raise ReplicationError("environment privacy contract is inconsistent")
    if (
        environment["pythonVersion"] != "3.12.13"
        or not isinstance(environment["osRelease"], str)
        or not environment["osRelease"]
        or len(environment["osRelease"]) > 256
        or not isinstance(environment["cpuCount"], int)
        or isinstance(environment["cpuCount"], bool)
        or environment["cpuCount"] <= 0
        or not isinstance(environment["memoryBytes"], int)
        or isinstance(environment["memoryBytes"], bool)
        or environment["memoryBytes"] <= 0
    ):
        raise ReplicationError("environment values are malformed")
    tools = _exact_object(environment["tools"], {"git", "swift"}, "tools")
    if not isinstance(tools["git"], str) or not tools["git"].startswith("git version "):
        raise ReplicationError("Git environment identity is malformed")
    if platform_name == "macos":
        if not isinstance(tools["swift"], str) or "Swift version" not in tools["swift"]:
            raise ReplicationError("Swift environment identity is malformed")
    elif tools["swift"] is not None:
        raise ReplicationError("Linux environment must not claim Swift identity")
    environment_ref = _exact_object(
        document["environment"], {"path", "sha256"}, "environment reference"
    )
    run_evidence = _exact_object(
        document["runEvidence"],
        {
            "receipt",
            "resultFileSHA256",
            "canonicalResultSHA256",
            "runFileManifest",
            "rawEvidenceIncludedInPublicBundle",
        },
        "run evidence reference",
    )
    receipt_ref = _exact_object(
        run_evidence["receipt"], {"path", "sha256"}, "receipt reference"
    )
    run_manifest_ref = _exact_object(
        run_evidence["runFileManifest"],
        {"path", "sha256", "fileCount"},
        "run-file manifest reference",
    )
    if run_evidence["rawEvidenceIncludedInPublicBundle"] is not True:
        raise ReplicationError("raw evidence inclusion flag is false")
    reports = _exact_object(
        document["reports"], {"terminal", "productVerifier"}, "reports"
    )
    terminal_ref = _exact_object(
        reports["terminal"],
        {"path", "sha256", "privacyRedactions"},
        "terminal report",
    )
    verifier_ref = _exact_object(
        reports["productVerifier"],
        {"path", "sha256", "exitCode"},
        "product-verifier report",
    )
    human_ref = _exact_object(
        document["humanAttestation"],
        {"path", "sha256", "softwareAssessment", "publicProfileURL"},
        "human attestation reference",
    )
    if (
        not isinstance(terminal_ref["privacyRedactions"], int)
        or isinstance(terminal_ref["privacyRedactions"], bool)
        or terminal_ref["privacyRedactions"] < 0
        or verifier_ref["exitCode"] != 0
    ):
        raise ReplicationError("report status fields are malformed")
    for section, filename in (
        (environment_ref, "environment.json"),
        (
            receipt_ref,
            (
                "run-evidence/app-run-receipt.json"
                if platform_name == "macos"
                else "run-evidence/run-manifest.json"
            ),
        ),
        (run_manifest_ref, "run-files.json"),
        (terminal_ref, "terminal.sanitized.log"),
        (verifier_ref, "verifier.sanitized.log"),
        (human_ref, "human-attestation.json"),
    ):
        if section.get("path") != filename or _digest(section.get("sha256"), filename) != _sha256(root / filename):
            raise ReplicationError(f"replication binding differs for {filename}")
    attestation = _validate_attestation(_read_json(root / "human-attestation.json"))
    if _timestamp(attestation["attestedAt"], "attestedAt") > started:
        raise ReplicationError("human attestation postdates execution start")
    if human_ref["publicProfileURL"] != attestation["publicProfileURL"]:
        raise ReplicationError("attestation profile binding differs")
    if human_ref["softwareAssessment"] != "DECLARED_ONLY_NOT_VERIFIED_BY_SOFTWARE":
        raise ReplicationError("software overclaims human identity")
    run_files = _exact_object(
        _read_json(root / "run-files.json", 16 * 1024 * 1024),
        {"schemaVersion", "rawEvidenceIncludedInPublicBundle", "files"},
        "run-file manifest",
    )
    if (
        run_files.get("schemaVersion") != RUN_FILES_SCHEMA
        or run_files.get("rawEvidenceIncludedInPublicBundle") is not True
    ):
        raise ReplicationError("run-file manifest is inconsistent")
    files = run_files.get("files")
    if (
        not isinstance(files, list)
        or not files
        or len(files) > MAX_RUN_FILES
        or len(files)
        != run_manifest_ref["fileCount"]
    ):
        raise ReplicationError("run-file count is inconsistent")
    indexed: dict[str, dict[str, Any]] = {}
    for entry in files:
        item = _exact_object(entry, {"path", "bytes", "sha256"}, "run file")
        path_value = item["path"]
        if (
            not isinstance(path_value, str)
            or SAFE_RELATIVE_RE.fullmatch(path_value) is None
            or ".." in Path(path_value).parts
            or path_value in indexed
            or not isinstance(item["bytes"], int)
            or isinstance(item["bytes"], bool)
            or item["bytes"] < 0
        ):
            raise ReplicationError("run-file entry is malformed")
        _digest(item["sha256"], "run file")
        indexed[path_value] = item
    if list(indexed) != sorted(indexed):
        raise ReplicationError("run-file entries are not canonically ordered")
    evidence_root = root / "run-evidence"
    evidence_files = {
        path.relative_to(evidence_root).as_posix()
        for path in evidence_root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if set(indexed) != evidence_files:
        raise ReplicationError("run-file manifest does not cover exact raw evidence")
    for relative, item in indexed.items():
        candidate = evidence_root / relative
        _require_regular_file(candidate)
        if candidate.stat().st_size != item["bytes"] or _sha256(candidate) != item["sha256"]:
            raise ReplicationError(f"raw evidence differs: {relative}")
    result_file_digest = _digest(
        run_evidence["resultFileSHA256"], "result file"
    )
    canonical_result = _digest(
        run_evidence["canonicalResultSHA256"],
        "canonical result",
    )
    result_entry = indexed.get("validation-064-071.json")
    if result_entry is None or result_entry["sha256"] != result_file_digest:
        raise ReplicationError("result digest is absent from the run-file manifest")
    receipt = _read_json(
        root
        / (
            "run-evidence/app-run-receipt.json"
            if platform_name == "macos"
            else "run-evidence/run-manifest.json"
        )
    )
    result_document = _read_json(evidence_root / "validation-064-071.json")
    aggregates = result_document.get("aggregates")
    if not isinstance(aggregates, list) or len(aggregates) != 1:
        raise ReplicationError("canonical result must contain one aggregate")
    aggregate = aggregates[0]
    if not isinstance(aggregate, dict) or not isinstance(
        aggregate.get("pass"), bool
    ):
        raise ReplicationError("canonical result aggregate is malformed")
    derived_verdict = "PASS" if aggregate["pass"] else "FAIL"
    if document["metricVerdict"] != derived_verdict:
        raise ReplicationError(
            "top-level metricVerdict differs from the canonical result"
        )
    receipt_original = (
        "app-run-receipt.json" if platform_name == "macos" else "run-manifest.json"
    )
    if (
        receipt_original not in indexed
        or indexed[receipt_original]["sha256"]
        != receipt_ref["sha256"]
    ):
        raise ReplicationError("receipt digest is absent from the run-file manifest")
    if platform_name == "macos":
        _exact_object(
            receipt,
            {
                "application",
                "buildProvenance",
                "challengeNonce",
                "createdAt",
                "error",
                "primaryEvidence",
                "protocol",
                "result",
                "schemaVersion",
                "startedAt",
                "worker",
            },
            "macOS receipt",
        )
        receipt_result = receipt.get("result")
        provenance = (
            receipt.get("buildProvenance", {})
            .get("document", {})
            .get("source", {})
        )
        if (
            not isinstance(receipt_result, dict)
            or receipt_result.get("resultFileSHA256") != result_file_digest
            or receipt_result.get("resultSHA256") != canonical_result
            or receipt.get("challengeNonce") != challenge
            or provenance.get("commit") != source["commit"]
            or provenance.get("tree") != source["tree"]
        ):
            raise ReplicationError("macOS receipt binding is inconsistent")
        if (
            receipt.get("schemaVersion")
            != "corelm-macos-app-real-llm-run-v5"
            or receipt.get("error") is not None
            or receipt_result.get("resultRole")
            != "PUBLIC_VALIDATION_REGRESSION"
            or receipt_result.get("metricVerdict") not in {"PASS", "FAIL"}
            or receipt_result.get("swiftStructuralVerification") != "PASS"
            or receipt.get("primaryEvidence", {}).get("containerCount") != 192
            or receipt.get("primaryEvidence", {}).get("predictionTokens")
            != 1024
        ):
            raise ReplicationError("macOS receipt contract is inconsistent")
        _exact_object(
            receipt_result,
            {
                "compressionRatioVsBF16",
                "deltaNLLNatPerToken",
                "path",
                "resultFileSHA256",
                "resultSHA256",
                "resultRole",
                "metricVerdict",
                "swiftStructuralVerification",
                "top1Agreement",
            },
            "macOS result receipt",
        )
        protocol = _exact_object(
            receipt["protocol"],
            {
                "candidateIndex",
                "device",
                "hfHome",
                "offlineRequested",
                "sanitizedChildEnvironment",
                "validationBlocks",
                "validationStartBlock",
            },
            "macOS protocol receipt",
        )
        if protocol != {
            "candidateIndex": 32,
            "device": "mps",
            "hfHome": "configured",
            "offlineRequested": True,
            "sanitizedChildEnvironment": True,
            "validationBlocks": 8,
            "validationStartBlock": 64,
        }:
            raise ReplicationError("macOS protocol receipt is inconsistent")
        started_receipt = _timestamp(receipt["startedAt"], "receipt startedAt")
        result_created = _timestamp(
            result_document.get("createdAt"), "result createdAt"
        )
        receipt_created = _timestamp(receipt["createdAt"], "receipt createdAt")
        if not started_receipt <= result_created <= receipt_created:
            raise ReplicationError("macOS receipt timestamps are inconsistent")
        if receipt.get("primaryEvidence") != result_document.get(
            "primaryEvidence"
        ):
            raise ReplicationError("macOS receipt primary evidence differs")
        build_source = (
            receipt.get("buildProvenance", {})
            .get("document", {})
            .get("source", {})
        )
        worker = receipt.get("worker")
        if (
            not isinstance(worker, dict)
            or worker.get("script")
            != "Resources/RealLLM/app_proof_runner.py"
            or worker.get("scriptSHA256")
            != _sha256(ROOT / "RealLLM/app_proof_runner.py")
            or worker.get("terminationStatus") != 0
            or build_source.get("mode") != "git"
            or build_source.get("dirty") is not False
            or build_source.get("commit") != source["commit"]
            or build_source.get("tree") != source["tree"]
            or _canonicalize_origin(build_source.get("remote"))
            != source["origin"]
        ):
            raise ReplicationError("macOS runner/build provenance is inconsistent")
        if receipt_result.get("metricVerdict") != derived_verdict:
            raise ReplicationError("macOS metric verdict differs from result")
        _same_number(
            receipt_result.get("compressionRatioVsBF16"),
            aggregate.get("compressionRatioVsBF16"),
            "compression ratio",
        )
        _same_number(
            receipt_result.get("deltaNLLNatPerToken"),
            aggregate.get("deltaNLLNatPerToken"),
            "delta NLL",
        )
        _same_number(
            receipt_result.get("top1Agreement"),
            aggregate.get("top1Agreement"),
            "top-1 agreement",
        )
        if (
            preserved_macos_fail
            and receipt_result.get("metricVerdict") != "FAIL"
        ) or (
            normal_completion
            and receipt_result.get("metricVerdict") != "PASS"
        ):
            raise ReplicationError("macOS terminal outcome and metric differ")
    else:
        _exact_object(
            receipt,
            {
                "schemaVersion",
                "evidenceClass",
                "countsTowardScientificVerdict",
                "modelExecuted",
                "testDataOpened",
                "beaconExecuted",
                "sourceCommit",
                "resultSHA256",
                "selectedTokenIdsSHA256",
                "containerCount",
                "predictionTokens",
                "compressionRatioVsBF16",
                "deltaNLLNatPerToken",
                "top1Agreement",
                "metricVerdict",
            },
            "Linux receipt",
        )
        if (
            receipt["schemaVersion"]
            != "corelm-real-qwen-linux-regression-run-v1"
            or receipt["evidenceClass"] != "regression-only"
            or receipt["countsTowardScientificVerdict"] is not False
            or receipt["modelExecuted"] is not True
            or receipt["testDataOpened"] is not False
            or receipt["beaconExecuted"] is not False
            or receipt["sourceCommit"] != source["commit"]
            or receipt["resultSHA256"] != canonical_result
            or receipt["containerCount"] != 192
            or receipt["predictionTokens"] != 1024
            or receipt["metricVerdict"] not in {"PASS", "FAIL"}
        ):
            raise ReplicationError("Linux receipt binding is inconsistent")
        contract = _exact_object(
            _read_json(evidence_root / "pre-run-contract.json"),
            {
                "schemaVersion",
                "evidenceClass",
                "countsTowardScientificVerdict",
                "dataClass",
                "modelExecutionRequested",
                "modelRepository",
                "modelRevision",
                "datasetRepository",
                "datasetSplit",
                "validationStartBlock",
                "validationBlocks",
                "candidateIndex",
                "device",
                "testDataAccessAllowed",
                "beaconExecutionAllowed",
                "sourceCommit",
                "sourceTree",
            },
            "Linux pre-run contract",
        )
        if contract != {
            "schemaVersion": "corelm-real-qwen-linux-regression-contract-v1",
            "evidenceClass": "regression-only",
            "countsTowardScientificVerdict": False,
            "dataClass": "real-public-validation",
            "modelExecutionRequested": True,
            "modelRepository": "Qwen/Qwen2.5-0.5B",
            "modelRevision": "060db6499f32faf8b98477b0a26969ef7d8b9987",
            "datasetRepository": "Salesforce/wikitext",
            "datasetSplit": "validation",
            "validationStartBlock": 64,
            "validationBlocks": 8,
            "candidateIndex": 32,
            "device": "cpu",
            "testDataAccessAllowed": False,
            "beaconExecutionAllowed": False,
            "sourceCommit": source["commit"],
            "sourceTree": source["tree"],
        }:
            raise ReplicationError("Linux pre-run contract is inconsistent")
        if (
            receipt["selectedTokenIdsSHA256"]
            != result_document.get("selectedTokenIdsSHA256")
            or receipt["metricVerdict"] != derived_verdict
        ):
            raise ReplicationError("Linux receipt differs from canonical result")
        _same_number(
            receipt["compressionRatioVsBF16"],
            aggregate.get("compressionRatioVsBF16"),
            "compression ratio",
        )
        _same_number(
            receipt["deltaNLLNatPerToken"],
            aggregate.get("deltaNLLNatPerToken"),
            "delta NLL",
        )
        _same_number(
            receipt["top1Agreement"],
            aggregate.get("top1Agreement"),
            "top-1 agreement",
        )
    terminal_text = (root / "terminal.sanitized.log").read_text(encoding="utf-8")
    verifier = (root / "verifier.sanitized.log").read_text(encoding="utf-8")
    if platform_name == "macos":
        if derived_verdict == "PASS":
            expected_terminal_marker = "END-TO-END PROOF PASS:"
            expected_marker = "FRESH LOCAL APP PROOF PASS"
        else:
            expected_terminal_marker = (
                "END-TO-END PROOF VERIFIED — METRIC FAIL:"
            )
            expected_marker = "FRESH LOCAL APP PROOF VERIFIED — METRIC FAIL"
        if expected_terminal_marker not in terminal_text:
            raise ReplicationError(
                "full macOS verifier/heavy-replay terminal marker is missing"
            )
    else:
        expected_marker = "PRIMARY EVIDENCE PASS"
    if expected_marker not in verifier:
        raise ReplicationError("product verifier PASS marker is missing")
    if platform_name == "macos":
        _run_portable_macos_verifier(
            evidence_root / "validation-064-071.json",
            evidence_root / "app-run-receipt.json",
            challenge,
        )
    else:
        completed_verifier = subprocess.run(
            (
                sys.executable,
                "-I",
                "-B",
                str(ROOT / "security" / "verify_primary_evidence.py"),
                str(root / "run-evidence"),
            ),
            cwd=ROOT,
            env=_safe_child_environment({}),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
        if (
            completed_verifier.returncode != 0
            or "PRIMARY EVIDENCE PASS" not in completed_verifier.stdout
        ):
            raise ReplicationError("bundled raw primary evidence does not reverify")
    claims = document["claimBoundary"]
    if claims != {
        "automatedIntegrity": "PASS",
        "humanIdentity": "REQUIRES_PUBLIC_ACCOUNT_REVIEW",
        "independence": "REQUIRES_HUMAN_REVIEW",
        "scientificGeneralization": "NOT_CLAIMED",
    }:
        raise ReplicationError("claim boundary is inconsistent")
    _verify_release_tag(
        source["releaseTag"],
        source["commit"],
        source["tree"],
        source["releaseTagObject"],
    )
    if _sha256(ROOT / "signing" / "allowed_signers") != source["signingPolicySHA256"]:
        raise ReplicationError("signing policy differs from the bundle")
    if (
        _sha256(ROOT / "signing" / "corelm-codec-signing.pub")
        != source["signingPublicKeySHA256"]
    ):
        raise ReplicationError("signing public key differs from the bundle")
    return document


def _macos_completed_outcome(
    exit_code: int, receipt: dict[str, Any], terminal_text: str
) -> str:
    """Accept only a fully completed proof, including its heavy replay."""

    if exit_code != 0:
        raise ReplicationError(
            f"macOS proof exited with {exit_code}; post-receipt failures are fatal"
        )
    result = receipt.get("result")
    if (
        receipt.get("error") is not None
        or not isinstance(result, dict)
        or result.get("swiftStructuralVerification") != "PASS"
        or result.get("metricVerdict") not in {"PASS", "FAIL"}
    ):
        raise ReplicationError("macOS receipt is not a completed structural proof")
    if result["metricVerdict"] == "PASS":
        marker = "END-TO-END PROOF PASS:"
        outcome = "COMPLETED"
    else:
        marker = "END-TO-END PROOF VERIFIED — METRIC FAIL:"
        outcome = "METRIC_FAIL_PRESERVED"
    if marker not in terminal_text:
        raise ReplicationError(
            "macOS proof did not reach the full verifier/heavy-replay marker"
        )
    return outcome


def record(arguments: argparse.Namespace) -> int:
    if sys.version_info[:3] != EXPECTED_PYTHON:
        raise ReplicationError("record requires the pinned Python 3.12.13 runtime")
    source = _source_identity(arguments.expected_tag)
    environment = _environment(arguments.platform)
    output = arguments.output.expanduser().resolve()
    if output == ROOT or ROOT in output.parents:
        raise ReplicationError("public bundle output must be outside the clone")
    if output.exists() or output.is_symlink():
        raise ReplicationError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.partial-{secrets.token_hex(8)}")
    temporary.mkdir(mode=0o700)
    attestation_snapshot = temporary / "attestation.snapshot.json"
    try:
        _copy_public_file(arguments.attestation, attestation_snapshot)
        attestation = _validate_attestation(
            _read_json(attestation_snapshot, 64 * 1024)
        )
        execution_root = _fresh_execution_checkout(source, temporary)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    terminal = temporary / "terminal.capture"
    challenge: str | None = None
    run_directory: Path
    before: set[Path] = set()
    extra: dict[str, str] = {}
    allowed_generated = ("dist",) if arguments.platform == "macos" else ()
    if arguments.platform == "macos":
        (execution_root / "dist").mkdir(mode=0o700)
    execution_entries = _verify_exact_checkout(
        execution_root, allowed_generated_prefixes=allowed_generated
    )
    execution_seal = _worktree_seal(execution_root, execution_entries)
    pycache = temporary / "fresh-pycache"
    pycache.mkdir(mode=0o700)
    extra.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(pycache),
        }
    )
    if arguments.platform == "macos":
        before = _complete_macos_runs()
        challenge = secrets.token_hex(32)
        extra["CORELM_PROOF_CHALLENGE"] = challenge
    else:
        run_root = Path.home() / ".cache" / "corelm" / "linux" / "independent-replication-runs"
        run_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        run_directory = run_root / secrets.token_hex(16)
        extra["CORELM_RUN_DIR"] = str(run_directory)
    started_at = _utc_now()
    if _timestamp(attestation["attestedAt"], "attestedAt") > _timestamp(
        started_at, "startedAt"
    ):
        shutil.rmtree(temporary, ignore_errors=True)
        raise ReplicationError("human attestation must be signed before execution")
    try:
        exit_code, terminal_redactions = _capture(
            COMMANDS[arguments.platform],
            _safe_child_environment(extra),
            terminal,
            cwd=execution_root,
        )
        completed_at = _utc_now()
        _assert_worktree_seal(
            execution_root, execution_entries, execution_seal
        )
        _verify_exact_checkout(
            execution_root,
            allowed_generated_prefixes=allowed_generated,
        )
        if exit_code != 0:
            raise ReplicationError(f"public command exited with {exit_code}")
        terminal_outcome = "COMPLETED"
        if arguments.platform == "macos":
            created = _complete_macos_runs() - before
            if len(created) != 1:
                raise ReplicationError(
                    f"expected one fresh macOS run directory; found {len(created)}"
                )
            run_directory = created.pop()
            receipt = _read_json(run_directory / "app-run-receipt.json")
            terminal_text = terminal.read_text(encoding="utf-8")
            terminal_outcome = _macos_completed_outcome(
                exit_code, receipt, terminal_text
            )
            verifier_command = (
                sys.executable,
                "-I",
                "-B",
                str(execution_root / "security" / "verify_local_app_run.py"),
                "--run-directory",
                str(run_directory),
                "--app",
                str(execution_root / "dist" / "CoreLMBenchmark.app"),
                "--challenge",
                challenge,
            )
        else:
            verifier_command = (
                sys.executable,
                "-I",
                "-B",
                str(execution_root / "security" / "verify_primary_evidence.py"),
                str(run_directory),
            )
        verifier_text, verifier_redactions = _capture_verifier(
            verifier_command, cwd=execution_root
        )
        _assert_worktree_seal(
            execution_root, execution_entries, execution_seal
        )
        _verify_exact_checkout(
            execution_root,
            allowed_generated_prefixes=allowed_generated,
        )
        _assert_public_bytes(verifier_text.encode("utf-8"), "verifier output")
        bundle_stage = temporary / "bundle"
        bundle_stage.mkdir(mode=0o700)
        _assemble_bundle(
            bundle_stage,
            arguments.platform,
            source,
            environment,
            attestation_snapshot,
            run_directory,
            terminal,
            verifier_text,
            challenge,
            started_at,
            completed_at,
            terminal_redactions + verifier_redactions,
            exit_code,
            terminal_outcome,
        )
        verified_document = verify_bundle(bundle_stage)
        bundle_stage.rename(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    shutil.rmtree(temporary, ignore_errors=True)
    print(f"REPLICATION BUNDLE RECORDED: {output}")
    print(f"METRIC VERDICT: {verified_document['metricVerdict']}")
    print("Human identity/independence remains DECLARED ONLY until public review.")
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    recorder = subparsers.add_parser("record", help="run and record one real-model regression")
    recorder.add_argument("--platform", choices=sorted(COMMANDS), required=True)
    recorder.add_argument(
        "--expected-tag",
        required=True,
        help="exact SSH-signed annotated portfolio release tag",
    )
    recorder.add_argument("--attestation", type=Path, required=True)
    recorder.add_argument("--output", type=Path, required=True)
    verifier = subparsers.add_parser("verify", help="verify a published bundle without model execution")
    verifier.add_argument("bundle", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    try:
        if arguments.operation == "record":
            return record(arguments)
        document = verify_bundle(arguments.bundle)
    except (OSError, ReplicationError, subprocess.SubprocessError) as error:
        print(f"INDEPENDENT REPLICATION BUNDLE FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "INDEPENDENT REPLICATION BUNDLE INTEGRITY PASS; "
        f"METRIC VERDICT {document['metricVerdict']}: checksums, source "
        "identity, environment, receipt/result bindings, terminal record, "
        "and product-verifier report agree. Integrity PASS is not metric PASS."
    )
    print(
        "Human identity and independence: DECLARED_ONLY_NOT_VERIFIED_BY_SOFTWARE; "
        "compare the attested profile with the public submission account."
    )
    print(
        "Claim scope: PUBLIC_VALIDATION_REGRESSION; does not count toward a "
        "blind or scientific-generalization verdict."
    )
    print(f"Exact commit: {document['source']['commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
