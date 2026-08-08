#!/usr/bin/env python3
"""Build or publicly verify the exact Core LM portfolio release bundle.

Build mode is intentionally offline and fail closed.  It accepts only a clean
canonical ``main`` worktree at an already-created SSH-signed annotated
``corelm-portfolio-vN`` tag.  It never creates a tag and never contacts
GitHub.  The operator must perform the documented GitHub Actions API preflight
immediately before build mode and acknowledge that step explicitly.

The private key is read only from ``CORELM_PORTFOLIO_SIGNING_KEY``.  Its path
and bytes are never emitted, copied, or included in an output manifest.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import zlib
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterable, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
# ``python -I`` deliberately omits the checkout root.  Pin the resolved root
# containing this tracked tool at index zero even when an API caller already
# placed it later in ``sys.path``; product verifiers must not resolve through
# an earlier ambient package.
sys.path[:] = [entry for entry in sys.path if entry != str(ROOT)]
sys.path.insert(0, str(ROOT))
INPUT_SCHEMA = ROOT / "schemas" / "portfolio-release-input.schema.json"
IDENTITY_SCHEMA = ROOT / "schemas" / "portfolio-source-identity.schema.json"
CANONICAL_REMOTE = "https://github.com/ALLPROTO/core-lm-benchmark.git"
CANONICAL_REPOSITORY = "https://github.com/ALLPROTO/core-lm-benchmark"
LAB_REPOSITORY = "https://github.com/ALLPROTO/core-lm-cross-model-lab"
BLIND_PULL_REQUEST = f"{LAB_REPOSITORY}/pull/5"
EXPECTED_AUTHOR = "Ivan Tyshchenko"
EXPECTED_ORCID = "https://orcid.org/0009-0000-7935-6090"
EXPECTED_LICENSE = "MIT"
EXPECTED_PUBLIC_KEY_SHA256 = (
    "9d299ff032927caef3f1355fb55c01f206ebf27ef35bcb5da547f962168b1274"
)
EXPECTED_ALLOWED_SIGNERS_SHA256 = (
    "36fb4a170eee7664be32f2a5d562db209fa4f6f1f24667cf6a3ef0166d155c16"
)
EXPECTED_FINGERPRINT = "SHA256:8A4y/GkoFglweSfg3rP21BtWWqIBOeQAUoAJDQM8sMM"
EXPECTED_SIGNING_PRINCIPAL = "ivantyschenko777@gmail.com"
EXPECTED_MODEL = "Qwen/Qwen2.5-0.5B"
EXPECTED_MODEL_REVISION = "060db6499f32faf8b98477b0a26969ef7d8b9987"
EXPECTED_CORPUS = "Salesforce/wikitext"
EXPECTED_CORPUS_REVISION = "b08601e04326c79dfdd32d625aee71d232d685c3"
TAG_RE = re.compile(r"^corelm-portfolio-v([1-9][0-9]*)$")
GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_RELATIVE_RE = re.compile(r"^[A-Za-z0-9._+@=-]+(?:/[A-Za-z0-9._+@=-]+)*$")
PLACEHOLDER_RE = re.compile(r"@[A-Z][A-Z0-9_]*@")
ACTION_URL_RE = re.compile(
    r"^https://github\.com/ALLPROTO/core-lm-benchmark/actions/runs/([1-9][0-9]*)$"
)
PRIVATE_KEY_RE = re.compile(rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
ABSOLUTE_PRIVATE_PATHS = (
    re.compile(rb"/Users/[A-Za-z0-9._-]+(?:/|\b)"),
    re.compile(rb"/home/[A-Za-z0-9._-]+(?:/|\b)"),
    re.compile(rb"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+(?:\\|\b)"),
)
SECRET_PATTERNS = (
    re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"hf_[A-Za-z0-9]{20,}"),
    re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    re.compile(rb"xox[baprs]-[A-Za-z0-9-]{20,}"),
)
STRICT_METADATA_SECRET_PATTERNS = (
    re.compile(
        rb"authorization[ \t]*:[ \t]*bearer[ \t]+[A-Za-z0-9._~+/=-]{8,}",
        re.IGNORECASE,
    ),
    re.compile(rb"https?://[^/@\s:]+:[^/@\s]+@", re.IGNORECASE),
)
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_TEXT_BYTES = 16 * 1024 * 1024
MAX_POSTER_BYTES = 64 * 1024 * 1024
MAX_VIDEO_BYTES = 256 * 1024 * 1024
MAX_EVIDENCE_BYTES = 256 * 1024 * 1024
MAX_SOURCE_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_TAR_MEMBERS = 20_000
MAX_TAR_EXPANDED_BYTES = 256 * 1024 * 1024
LOCKFILE_PATHS = (
    "RealLLM/requirements.lock",
    "RealLLM/requirements.txt",
    "requirements.txt",
)
VERIFIER_PATHS = (
    "BenchmarkCore/corelm_benchmark.py",
    "RealLLM/__init__.py",
    "RealLLM/app_proof_core.py",
    "RealLLM/app_proof_runner.py",
    "RealLLM/benchmark_real_llm.py",
    "RealLLM/codecs.py",
    "RealLLM/develop_voidtoken_v5.py",
    "RealLLM/legacy_voidtoken_adapter.py",
    "RealLLM/run_voidtoken_v5_frozen.py",
    "RealLLM/verify_voidtoken_v5_development.py",
    "RealLLM/voidtoken_v5.py",
    "publication/build_portfolio_release.py",
    "schemas/portfolio-release-input.schema.json",
    "schemas/portfolio-source-identity.schema.json",
    "security/generate_app_proof_core.py",
    "security/generate_build_provenance.py",
    "security/generate_direct_sbom.py",
    "security/generate_python_runtime_manifest.py",
    "security/verify_app_bundle.sh",
    "security/verify_app_run_evidence.py",
    "security/verify_local_app_run.py",
    "security/verify_primary_evidence.py",
    "security/verify_primary_replay.py",
)
LEGACY_PRIVATE_PATH_ALLOWLIST = {
    "RealLLM/verify_voidtoken_v5_development.py": "9645dd4a456a9c7e35c0f91dc613ea4cbad97bea8b0e6d3f6090c9604cd7308b",
    "Tests/test_app_real_llm_evidence.py": "ff0419672b46fea6a77f48ec89c7b60ebab5b71362b52593534391219a100a97",
    "Tests/test_build_provenance.py": "fcc66c13b9c23fb5d4770f1439088abee260de8c94243b4b0c757be6cec2c69b",
    "Tests/test_independent_replication.py": "54283ec6d76e56c626d7f1e16aa55d9d98d15825e7a19549b9b46f05d15e1608",
    "Tests/test_local_app_build.py": "ff7c1a4e6b114b68ff59d9032cf27e5cf895f4466c6c75572e73d56dde8d3e05",
    "platforms/macos/Tests/SecurityValidationTests.swift": "953c6a7165c62a77baa1bfc714a6da23d67bda6e8986d0ac758c65c562647050",
    "real-llm-results/aggregate.json": "ebf3bb9558282bf23265989df82a9b18c599654b5bb05d82c4e4d400f1f62265",
    "real-llm-v5-development/validation-000-007.json": "f8c900246c8dafe50ffea309ce86793822cf6fb93e438e3f16b7450bd1f9f224",
    "real-llm-v5-development/validation-008-015.json": "04ef609cf32f0828de70e6adc47eefc717b6c7c67240035d856f047450860d34",
    "real-llm-v5-development/validation-016-023.json": "65ac4c9bbb1e3d3821d08c9a2f11aa970b0390582388f6ffdbb8ff6f235ad827",
    "real-llm-v5-development/validation-024-031.json": "ab3a981349e5d2bfcda51d5c32235499fc35af396e827b2f916ed64af769ce1e",
    "real-llm-v5-results/holdout.json": "499c067d6ccff4bf1ac4a9f98436a52fa6c414ccced495719532347b89b46167",
    "real-llm-v5-results/selection.json": "72bd149903ac84edb4d56ac7e066fa5640278845bbb5961264ae1b34854dd247",
}


class PortfolioReleaseError(ValueError):
    """A fail-closed portfolio release contract violation."""


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


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PortfolioReleaseError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise PortfolioReleaseError(f"non-finite JSON number is forbidden: {value}")


def _require_regular_file(path: Path, maximum_bytes: int | None = None) -> os.stat_result:
    try:
        status = path.lstat()
    except OSError as error:
        raise PortfolioReleaseError(f"required file is unavailable: {path.name}") from error
    if not stat.S_ISREG(status.st_mode):
        raise PortfolioReleaseError(f"file must be regular and not a symlink: {path.name}")
    if status.st_nlink != 1:
        raise PortfolioReleaseError(f"file must not be hard-linked: {path.name}")
    if maximum_bytes is not None and status.st_size > maximum_bytes:
        raise PortfolioReleaseError(f"file is too large: {path.name}")
    return status


def _sha256(path: Path) -> str:
    _require_regular_file(path)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, maximum_bytes: int = MAX_JSON_BYTES) -> Any:
    status = _require_regular_file(path, maximum_bytes)
    data = path.read_bytes()
    if len(data) != status.st_size or data.startswith(b"\xef\xbb\xbf"):
        raise PortfolioReleaseError(f"JSON bytes are unstable or have a BOM: {path.name}")
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PortfolioReleaseError(f"invalid JSON: {path.name}") from error


def _read_canonical_json(path: Path) -> Any:
    value = _read_json(path)
    if path.read_bytes() != _canonical_json(value):
        raise PortfolioReleaseError(
            f"JSON must be canonical compact UTF-8 with one final newline: {path.name}"
        )
    _reject_placeholders(value, path.name)
    return value


def _reject_placeholders(value: Any, label: str) -> None:
    if isinstance(value, str) and PLACEHOLDER_RE.search(value):
        raise PortfolioReleaseError(f"unresolved release placeholder in {label}")
    if isinstance(value, dict):
        for key, nested in value.items():
            _reject_placeholders(key, label)
            _reject_placeholders(nested, label)
    elif isinstance(value, list):
        for nested in value:
            _reject_placeholders(nested, label)


def _validate_schema(value: Any, schema_path: Path, label: str) -> None:
    try:
        import jsonschema
    except ImportError as error:
        raise PortfolioReleaseError("jsonschema is required by the locked runtime") from error
    schema = _read_json(schema_path)
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
        errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    except jsonschema.SchemaError as error:
        raise PortfolioReleaseError(f"invalid tracked schema: {schema_path.name}") from error
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "<root>"
        raise PortfolioReleaseError(f"{label} schema failure at {location}: {first.message}")


def _exact_object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PortfolioReleaseError(f"{label} has missing or unknown keys")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise PortfolioReleaseError(f"{label} must be lowercase SHA-256")
    return value


def _git_object(value: Any, label: str) -> str:
    if not isinstance(value, str) or GIT_OBJECT_RE.fullmatch(value) is None:
        raise PortfolioReleaseError(f"{label} must be lowercase 40-hex")
    return value


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or SAFE_RELATIVE_RE.fullmatch(value) is None:
        raise PortfolioReleaseError(f"{label} is not a safe relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise PortfolioReleaseError(f"{label} is not normalized")
    return value


def _exact_tag(value: Any) -> tuple[str, int]:
    if not isinstance(value, str):
        raise PortfolioReleaseError("portfolio tag must be a string")
    match = TAG_RE.fullmatch(value)
    if match is None:
        raise PortfolioReleaseError("portfolio tag must be exact corelm-portfolio-vN")
    return value, int(match.group(1))


def asset_names(tag: str) -> tuple[str, ...]:
    exact, _version = _exact_tag(tag)
    return (
        f"REPRODUCE-{exact}.md",
        "allowed_signers",
        "corelm-portfolio-signing.pub",
        f"{exact}-demo-evidence.tar.gz",
        f"{exact}-demo-poster.png",
        f"{exact}-demo-provenance.json",
        f"{exact}-demo.mp4",
        f"{exact}-direct-dependencies.cdx.json",
        f"{exact}-runtime-assets.json",
        f"{exact}-source-identity.json",
        f"{exact}-source-identity.json.sig",
        f"{exact}-source.tar.gz",
        "SHA256SUMS",
        "SHA256SUMS.sig",
    )


def covered_asset_names(tag: str) -> tuple[str, ...]:
    return asset_names(tag)[:12]


def asset_size_caps(tag: str) -> dict[str, int]:
    exact, _version = _exact_tag(tag)
    return {
        f"REPRODUCE-{exact}.md": MAX_TEXT_BYTES,
        "allowed_signers": 64 * 1024,
        "corelm-portfolio-signing.pub": 64 * 1024,
        f"{exact}-demo-evidence.tar.gz": MAX_EVIDENCE_BYTES,
        f"{exact}-demo-poster.png": MAX_POSTER_BYTES,
        f"{exact}-demo-provenance.json": MAX_JSON_BYTES,
        f"{exact}-demo.mp4": MAX_VIDEO_BYTES,
        f"{exact}-direct-dependencies.cdx.json": MAX_JSON_BYTES,
        f"{exact}-runtime-assets.json": MAX_JSON_BYTES,
        f"{exact}-source-identity.json": MAX_JSON_BYTES,
        f"{exact}-source-identity.json.sig": 1024 * 1024,
        f"{exact}-source.tar.gz": MAX_SOURCE_ARCHIVE_BYTES,
        "SHA256SUMS": 64 * 1024,
        "SHA256SUMS.sig": 1024 * 1024,
    }


def _safe_environment() -> dict[str, str]:
    return {
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    }


def _run(
    arguments: Sequence[str],
    *,
    cwd: Path,
    input_bytes: bytes | None = None,
    timeout: int = 120,
    private_operation: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            list(arguments),
            cwd=cwd,
            env=_safe_environment(),
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        if private_operation:
            raise PortfolioReleaseError("private-key operation failed") from None
        raise PortfolioReleaseError(f"command failed to execute: {Path(arguments[0]).name}") from error
    return completed


def _git(repository: Path, *arguments: str, timeout: int = 120) -> str:
    completed = _run(("/usr/bin/git", *arguments), cwd=repository, timeout=timeout)
    if completed.returncode != 0:
        raise PortfolioReleaseError(f"Git command failed: {' '.join(arguments[:2])}")
    try:
        return completed.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise PortfolioReleaseError("Git returned non-UTF-8 output") from error


def _resolve_exact_root(repository: Path) -> Path:
    if repository.is_symlink():
        raise PortfolioReleaseError("repository root must not be a symlink")
    try:
        resolved = repository.resolve(strict=True)
    except OSError as error:
        raise PortfolioReleaseError("repository root is unavailable") from error
    if not resolved.is_dir():
        raise PortfolioReleaseError("repository root must be a directory")
    top = Path(_git(resolved, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if top != resolved:
        raise PortfolioReleaseError("path must be the exact Git worktree root")
    return resolved


def _require_builder_repository(repository: Path) -> Path:
    resolved = _resolve_exact_root(repository)
    if resolved != ROOT.resolve(strict=True):
        raise PortfolioReleaseError(
            "build repository must be the exact source tree containing this builder"
        )
    return resolved


def _validate_git_object(repository: Path, commit: str, tree: str, label: str) -> None:
    _git_object(commit, f"{label} commit")
    _git_object(tree, f"{label} tree")
    if _git(repository, "cat-file", "-t", commit) != "commit":
        raise PortfolioReleaseError(f"{label} commit object is unavailable")
    observed = _git(repository, "rev-parse", f"{commit}^{{tree}}")
    if observed != tree:
        raise PortfolioReleaseError(f"{label} commit/tree binding is inconsistent")


def _parse_annotated_tag_header(payload: str, tag: str, commit: str) -> None:
    try:
        header, _body = payload.split("\n\n", 1)
    except ValueError as error:
        raise PortfolioReleaseError("annotated tag header is malformed") from error
    rows = header.splitlines()
    if len(rows) != 4 or not rows[3].startswith("tagger "):
        raise PortfolioReleaseError("annotated tag header is not exact")
    if rows[:3] != [f"object {commit}", "type commit", f"tag {tag}"]:
        raise PortfolioReleaseError("annotated tag identity is inconsistent")
    for prefix in ("object ", "type ", "tag ", "tagger "):
        if sum(row.startswith(prefix) for row in rows) != 1:
            raise PortfolioReleaseError("annotated tag has duplicate identity fields")


def _public_key_identity(path: Path) -> str:
    _require_regular_file(path, 16 * 1024)
    try:
        fields = path.read_text(encoding="ascii").split()
    except UnicodeDecodeError as error:
        raise PortfolioReleaseError("public key is not ASCII") from error
    if len(fields) < 2 or fields[0] != "ssh-ed25519":
        raise PortfolioReleaseError("public key must be ssh-ed25519")
    return " ".join(fields[:2])


def _signer_principal(allowed_signers: Path, public_key: Path) -> str:
    _require_regular_file(allowed_signers, 16 * 1024)
    try:
        rows = allowed_signers.read_text(encoding="ascii").splitlines()
    except UnicodeDecodeError as error:
        raise PortfolioReleaseError("allowed_signers is not ASCII") from error
    if len(rows) != 1 or not rows[0] or any(character in rows[0] for character in "\r\x00"):
        raise PortfolioReleaseError("allowed_signers must contain exactly one policy row")
    fields = rows[0].split()
    if len(fields) != 3 or fields[1] != "ssh-ed25519":
        raise PortfolioReleaseError("allowed_signers policy row is not exact")
    if " ".join(fields[1:3]) != _public_key_identity(public_key):
        raise PortfolioReleaseError("allowed_signers does not contain the public key")
    return fields[0]


def _validate_trust(public_key: Path, allowed_signers: Path) -> str:
    if _sha256(public_key) != EXPECTED_PUBLIC_KEY_SHA256:
        raise PortfolioReleaseError("signing public key does not match the hard pin")
    if _sha256(allowed_signers) != EXPECTED_ALLOWED_SIGNERS_SHA256:
        raise PortfolioReleaseError("allowed_signers does not match the hard pin")
    principal = _signer_principal(allowed_signers, public_key)
    if principal != EXPECTED_SIGNING_PRINCIPAL:
        raise PortfolioReleaseError("allowed_signers principal is not the hard-pinned author")
    completed = _run(
        ("/usr/bin/ssh-keygen", "-E", "sha256", "-lf", str(public_key)),
        cwd=public_key.parent,
    )
    if completed.returncode != 0 or EXPECTED_FINGERPRINT.encode("ascii") not in completed.stdout:
        raise PortfolioReleaseError("public-key fingerprint does not match the hard pin")
    return principal


def _verify_signed_tag(repository: Path, tag: str, commit: str, tree: str) -> None:
    reference = f"refs/tags/{tag}"
    if _git(repository, "for-each-ref", "--format=%(refname)", "refs/replace"):
        raise PortfolioReleaseError("Git replacement refs are forbidden")
    git_dir = Path(_git(repository, "rev-parse", "--git-dir"))
    if not git_dir.is_absolute():
        git_dir = repository / git_dir
    if (git_dir / "info" / "grafts").exists():
        raise PortfolioReleaseError("Git grafts are forbidden")
    if _git(repository, "cat-file", "-t", reference) != "tag":
        raise PortfolioReleaseError("portfolio tag must be annotated, not lightweight")
    if _git(repository, "rev-parse", f"{reference}^{{commit}}") != commit:
        raise PortfolioReleaseError("portfolio tag does not target exact HEAD")
    if _git(repository, "rev-parse", f"{reference}^{{tree}}") != tree:
        raise PortfolioReleaseError("portfolio tag tree differs from exact HEAD tree")
    payload = _git(repository, "cat-file", "-p", reference)
    _parse_annotated_tag_header(payload, tag, commit)
    if (
        payload.count("-----BEGIN SSH SIGNATURE-----") != 1
        or payload.count("-----END SSH SIGNATURE-----") != 1
        or "-----BEGIN PGP SIGNATURE-----" in payload
    ):
        raise PortfolioReleaseError("portfolio tag must contain exactly one SSH signature")
    policy = repository / "signing" / "allowed_signers"
    public_key = repository / "signing" / "corelm-codec-signing.pub"
    principal = _validate_trust(public_key, policy)
    completed = _run(
        (
            "/usr/bin/git",
            "-c",
            "gpg.format=ssh",
            "-c",
            "gpg.ssh.program=/usr/bin/ssh-keygen",
            "-c",
            f"gpg.ssh.allowedSignersFile={policy}",
            "verify-tag",
            "--raw",
            tag,
        ),
        cwd=repository,
    )
    verification = completed.stdout + completed.stderr
    if completed.returncode != 0 or f'Good "git" signature for {principal}'.encode("utf-8") not in verification:
        raise PortfolioReleaseError("portfolio tag SSH signature is invalid")


def _validate_source(repository: Path, release_input: Mapping[str, Any]) -> tuple[str, str]:
    root = _resolve_exact_root(repository)
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all", "--ignored=no", "--ignore-submodules=none"):
        raise PortfolioReleaseError("portfolio build requires a completely clean worktree")
    if _git(root, "branch", "--show-current") != "main":
        raise PortfolioReleaseError("portfolio build requires the exact main branch")
    if _git(root, "remote", "get-url", "origin") != CANONICAL_REMOTE:
        raise PortfolioReleaseError("origin is not the canonical HTTPS remote")
    commit = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
    tree = _git(root, "rev-parse", "--verify", "HEAD^{tree}")
    if _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}") != "origin/main":
        raise PortfolioReleaseError("local main must track exact origin/main")
    if _git(root, "rev-parse", "--verify", "refs/remotes/origin/main^{commit}") != commit:
        raise PortfolioReleaseError("origin/main does not equal clean local HEAD")
    if _git(root, "rev-parse", "--verify", "refs/remotes/origin/main^{tree}") != tree:
        raise PortfolioReleaseError("origin/main tree does not equal clean local HEAD tree")
    source = release_input["source"]
    tag_object = _git(root, "rev-parse", f"refs/tags/{release_input['tag']}")
    if (
        commit != source["commit"]
        or tree != source["tree"]
        or tag_object != source["tag_object"]
    ):
        raise PortfolioReleaseError("release input does not bind exact main HEAD/tree")
    _validate_git_object(root, commit, tree, "portfolio source")
    _verify_signed_tag(root, release_input["tag"], commit, tree)
    return commit, tree


def _validate_related_sources(lab: Path, release_input: Mapping[str, Any]) -> None:
    repository = _resolve_exact_root(lab)
    if _git(repository, "remote", "get-url", "origin") != f"{LAB_REPOSITORY}.git":
        raise PortfolioReleaseError("cross-model lab origin is not canonical")
    related = release_input["related_sources"]
    references = {
        "cross_model_lab": "refs/remotes/origin/main",
        "blind_v1_draft": "refs/remotes/origin/pull/5/head",
    }
    for key, label in (("cross_model_lab", "lab main"), ("blind_v1_draft", "Blind V1 draft")):
        identity = related[key]
        _validate_git_object(repository, identity["commit"], identity["tree"], label)
        reference = references[key]
        if _git(repository, "rev-parse", "--verify", f"{reference}^{{commit}}") != identity["commit"]:
            raise PortfolioReleaseError(f"{label} does not equal exact local {reference}")
        if _git(repository, "rev-parse", "--verify", f"{reference}^{{tree}}") != identity["tree"]:
            raise PortfolioReleaseError(f"{label} tree does not equal exact local {reference} tree")


def _validate_citation(repository: Path, tag: str, release_date: str) -> None:
    path = repository / "CITATION.cff"
    _require_regular_file(path, 256 * 1024)
    try:
        import yaml

        class UniqueKeySafeLoader(yaml.SafeLoader):
            pass

        def construct_unique_mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
            result: dict[Any, Any] = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node, deep=deep)
                if key in result:
                    raise PortfolioReleaseError(f"CITATION.cff has duplicate key: {key}")
                result[key] = loader.construct_object(value_node, deep=deep)
            return result

        UniqueKeySafeLoader.add_constructor(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            construct_unique_mapping,
        )
        value = yaml.load(
            path.read_text(encoding="utf-8"), Loader=UniqueKeySafeLoader
        )
    except (ImportError, UnicodeDecodeError, ValueError) as error:
        raise PortfolioReleaseError("CITATION.cff cannot be parsed by the locked runtime") from error
    if not isinstance(value, dict):
        raise PortfolioReleaseError("CITATION.cff root is malformed")
    observed_date = value.get("date-released")
    if isinstance(observed_date, dt.date):
        observed_date = observed_date.isoformat()
    expected = {
        "version": tag,
        "date-released": release_date,
        "license": EXPECTED_LICENSE,
        "repository-code": CANONICAL_REPOSITORY,
        "url": CANONICAL_REPOSITORY,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted if key != "date-released" else observed_date != wanted:
            raise PortfolioReleaseError(f"CITATION.cff {key} is not release-exact")
    authors = value.get("authors")
    if not isinstance(authors, list) or not any(
        isinstance(author, dict)
        and author.get("given-names") == "Ivan"
        and author.get("family-names") == "Tyshchenko"
        and author.get("orcid") == EXPECTED_ORCID
        for author in authors
    ):
        raise PortfolioReleaseError("CITATION.cff author/ORCID identity is not exact")
    _reject_placeholders(value, "CITATION.cff")


def _copy_regular(source: Path, destination: Path, maximum_bytes: int) -> None:
    _require_regular_file(source, maximum_bytes)
    if destination.exists() or destination.is_symlink():
        raise PortfolioReleaseError(f"destination already exists: {destination.name}")
    with source.open("rb") as reader, destination.open("xb") as writer:
        shutil.copyfileobj(reader, writer, length=1024 * 1024)
    destination.chmod(0o644)
    if _sha256(source) != _sha256(destination):
        raise PortfolioReleaseError(f"copy verification failed: {destination.name}")


def _assert_public_bytes(
    data: bytes,
    label: str,
    *,
    reject_absolute_paths: bool = True,
    strict_credentials: bool = False,
) -> None:
    if PRIVATE_KEY_RE.search(data):
        raise PortfolioReleaseError(f"private key material detected in {label}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(data):
            raise PortfolioReleaseError(f"credential-like bytes detected in {label}")
    if strict_credentials:
        for pattern in STRICT_METADATA_SECRET_PATTERNS:
            if pattern.search(data):
                raise PortfolioReleaseError(
                    f"authorization credential bytes detected in {label}"
                )
    if reject_absolute_paths:
        for pattern in ABSOLUTE_PRIVATE_PATHS:
            if pattern.search(data):
                raise PortfolioReleaseError(f"author-only absolute path detected in {label}")


def _assert_public_stream(
    source: Any,
    label: str,
    *,
    reject_absolute_paths: bool,
    strict_credentials: bool = False,
) -> tuple[bool, str]:
    overlap = b""
    digest = hashlib.sha256()
    contains_private_path = False
    while True:
        chunk = source.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        data = overlap + chunk
        contains_private_path = contains_private_path or any(
            pattern.search(data) is not None for pattern in ABSOLUTE_PRIVATE_PATHS
        )
        _assert_public_bytes(
            data,
            label,
            reject_absolute_paths=reject_absolute_paths,
            strict_credentials=strict_credentials,
        )
        overlap = data[-1024:]
    return contains_private_path, digest.hexdigest()


def _validate_demo_provenance(
    path: Path,
    *,
    tag: str,
    commit: str,
    tree: str,
    video: Path,
    poster: Path,
    evidence: Path,
    captured_evidence_sha256: str | None = None,
) -> dict[str, Any]:
    value = _exact_object(
        _read_canonical_json(path),
        {
            "schema_version",
            "tag",
            "source",
            "video",
            "poster",
            "capture",
            "application_executable_sha256",
            "result_sha256",
            "receipt_sha256",
            "evidence_sha256",
            "workload_classification",
            "synthetic_data",
        },
        "demo provenance",
    )
    if value["schema_version"] != 1 or value["tag"] != tag:
        raise PortfolioReleaseError("demo provenance version/tag is inconsistent")
    source = _exact_object(value["source"], {"commit", "tree"}, "demo source")
    if source != {"commit": commit, "tree": tree}:
        raise PortfolioReleaseError("demo provenance does not bind source commit/tree")
    video_identity = _exact_object(
        value["video"],
        {
            "sha256",
            "duration_seconds",
            "width",
            "height",
            "codec",
            "audio_codec",
        },
        "demo video identity",
    )
    poster_identity = _exact_object(
        value["poster"],
        {"sha256", "width", "height", "frame_timestamp_seconds"},
        "demo poster identity",
    )
    capture = _exact_object(
        value["capture"], {"platform", "architecture"}, "demo capture"
    )
    if capture != {"platform": "macOS", "architecture": "arm64"}:
        raise PortfolioReleaseError("demo capture must be macOS arm64")
    if video_identity["codec"] != "h264" or video_identity["audio_codec"] not in {
        "aac",
        "silent",
    }:
        raise PortfolioReleaseError("demo must be H.264 with AAC or no audio")
    duration = video_identity["duration_seconds"]
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(float(duration))
        or not (0 < float(duration) <= 90)
    ):
        raise PortfolioReleaseError("demo duration must be in (0, 90] seconds")
    for identity, label in (
        (video_identity, "video"),
        (poster_identity, "poster"),
    ):
        for key in ("width", "height"):
            if isinstance(identity[key], bool) or not isinstance(identity[key], int) or identity[key] <= 0:
                raise PortfolioReleaseError(f"demo {label} {key} is invalid")
    timestamp = poster_identity["frame_timestamp_seconds"]
    if (
        isinstance(timestamp, bool)
        or not isinstance(timestamp, (int, float))
        or not math.isfinite(float(timestamp))
        or not (0 <= float(timestamp) <= float(duration))
    ):
        raise PortfolioReleaseError("poster frame timestamp is outside the video")
    expected_hashes = {
        "video": (video_identity["sha256"], _sha256(video)),
        "poster": (poster_identity["sha256"], _sha256(poster)),
        "evidence": (
            value["evidence_sha256"],
            _sha256(evidence)
            if captured_evidence_sha256 is None
            else _digest(
                captured_evidence_sha256, "captured demo evidence SHA-256"
            ),
        ),
    }
    for label, (recorded, observed) in expected_hashes.items():
        if _digest(recorded, f"demo {label}") != observed:
            raise PortfolioReleaseError(f"demo {label} hash does not match the file")
    for key in (
        "application_executable_sha256",
        "result_sha256",
        "receipt_sha256",
    ):
        _digest(value[key], f"demo {key}")
    if (
        value["workload_classification"] != "PUBLIC_VALIDATION_REGRESSION"
        or value["synthetic_data"] is not False
    ):
        raise PortfolioReleaseError("demo must be a non-synthetic public regression")
    return value


def _validate_manifest_rows(
    rows: Any,
    *,
    exact_paths: Sequence[str] | None,
    label: str,
    repository: Path | None,
    include_size: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        raise PortfolioReleaseError(f"{label} must be a non-empty list")
    result: list[dict[str, Any]] = []
    expected_keys = {"path", "sha256", "size_bytes"} if include_size else {"path", "sha256"}
    for index, raw in enumerate(rows):
        row = _exact_object(raw, expected_keys, f"{label}[{index}]")
        relative = _safe_relative(row["path"], f"{label}[{index}].path")
        digest = _digest(row["sha256"], f"{label}[{index}].sha256")
        if include_size:
            size = row["size_bytes"]
            if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
                raise PortfolioReleaseError(f"{label}[{index}].size_bytes is invalid")
        if repository is not None:
            tracked = repository / relative
            _require_regular_file(tracked, MAX_TEXT_BYTES)
            if _sha256(tracked) != digest:
                raise PortfolioReleaseError(f"{label} hash differs from the clean source: {relative}")
        result.append(row)
    paths = [row["path"] for row in result]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise PortfolioReleaseError(f"{label} paths must be unique and bytewise sorted")
    if exact_paths is not None and tuple(paths) != tuple(exact_paths):
        raise PortfolioReleaseError(f"{label} path set is not exact")
    return result


def _validate_runtime_assets(
    path: Path,
    *,
    tag: str,
    commit: str,
    tree: str,
    provenance: Mapping[str, Any],
    repository: Path | None,
) -> dict[str, Any]:
    value = _exact_object(
        _read_canonical_json(path),
        {
            "schema_version",
            "tag",
            "source",
            "platform",
            "python",
            "toolchain",
            "ffprobe",
            "lockfiles",
            "model",
            "corpus",
            "application",
            "proof",
            "verifiers",
        },
        "runtime-assets manifest",
    )
    if value["schema_version"] != 1 or value["tag"] != tag:
        raise PortfolioReleaseError("runtime-assets version/tag is inconsistent")
    source = _exact_object(value["source"], {"commit", "tree"}, "runtime source")
    if source != {"commit": commit, "tree": tree}:
        raise PortfolioReleaseError("runtime-assets source commit/tree is inconsistent")
    platform = _exact_object(value["platform"], {"system", "architecture"}, "runtime platform")
    if platform != {"system": "macOS", "architecture": "arm64"}:
        raise PortfolioReleaseError("recorded demo runtime must be macOS arm64")
    python = _exact_object(value["python"], {"version", "executable_sha256"}, "Python identity")
    if python["version"] != "3.12.13":
        raise PortfolioReleaseError("recorded demo Python must be exactly 3.12.13")
    _digest(python["executable_sha256"], "Python executable")
    toolchain = _exact_object(
        value["toolchain"], {"macos_version", "swift_version", "xcode_version"}, "toolchain identity"
    )
    if not all(isinstance(item, str) and item.strip() and not PLACEHOLDER_RE.search(item) for item in toolchain.values()):
        raise PortfolioReleaseError("toolchain versions must be literal non-empty strings")
    ffprobe_identity = _exact_object(
        value["ffprobe"], {"executable_sha256", "version"}, "ffprobe identity"
    )
    _digest(ffprobe_identity["executable_sha256"], "ffprobe executable")
    if (
        not isinstance(ffprobe_identity["version"], str)
        or not ffprobe_identity["version"].startswith("ffprobe version ")
        or "\n" in ffprobe_identity["version"]
        or "\r" in ffprobe_identity["version"]
        or len(ffprobe_identity["version"].encode("utf-8")) > 1024
    ):
        raise PortfolioReleaseError("ffprobe version identity is not exact")
    _validate_manifest_rows(
        value["lockfiles"], exact_paths=LOCKFILE_PATHS, label="lockfiles", repository=repository
    )
    _validate_manifest_rows(
        value["verifiers"], exact_paths=VERIFIER_PATHS, label="verifiers", repository=repository
    )
    model = _exact_object(
        value["model"], {"repository", "revision", "license", "files"}, "model identity"
    )
    if (
        model["repository"] != EXPECTED_MODEL
        or model["revision"] != EXPECTED_MODEL_REVISION
        or model["license"] != "Apache-2.0"
    ):
        raise PortfolioReleaseError("model repository/revision/license is not pinned")
    _validate_manifest_rows(
        model["files"], exact_paths=None, label="model files", repository=None, include_size=True
    )
    corpus = _exact_object(
        value["corpus"],
        {"repository", "revision", "path", "sha256", "license", "source_url"},
        "corpus identity",
    )
    if corpus["repository"] != EXPECTED_CORPUS or corpus["revision"] != EXPECTED_CORPUS_REVISION:
        raise PortfolioReleaseError("corpus repository/revision is not pinned")
    _safe_relative(corpus["path"], "corpus path")
    _digest(corpus["sha256"], "corpus file")
    if not isinstance(corpus["license"], str) or not corpus["license"].strip():
        raise PortfolioReleaseError("corpus license must be explicit")
    if not isinstance(corpus["source_url"], str) or not corpus["source_url"].startswith("https://"):
        raise PortfolioReleaseError("corpus source URL must be HTTPS")
    application = _exact_object(value["application"], {"executable_sha256"}, "application identity")
    if _digest(application["executable_sha256"], "application executable") != provenance["application_executable_sha256"]:
        raise PortfolioReleaseError("runtime and demo application hashes differ")
    proof = _exact_object(
        value["proof"], {"receipt_sha256", "result_sha256", "evidence_sha256"}, "proof identity"
    )
    for key in proof:
        if _digest(proof[key], f"proof {key}") != provenance[key]:
            raise PortfolioReleaseError(f"runtime and demo {key} differ")
    return value


def _png_dimensions(path: Path) -> tuple[int, int]:
    _require_regular_file(path, 64 * 1024 * 1024)
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise PortfolioReleaseError("demo poster has no PNG signature")
    offset = 8
    chunks: list[bytes] = []
    width = height = 0
    while offset < len(data):
        if offset + 12 > len(data):
            raise PortfolioReleaseError("demo poster has a truncated PNG chunk")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(data):
            raise PortfolioReleaseError("demo poster has a truncated PNG payload")
        payload = data[offset + 8 : offset + 8 + length]
        recorded_crc = struct.unpack(">I", data[offset + 8 + length : end])[0]
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != recorded_crc:
            raise PortfolioReleaseError("demo poster PNG CRC is invalid")
        chunks.append(chunk_type)
        if len(chunks) == 1:
            if chunk_type != b"IHDR" or length != 13:
                raise PortfolioReleaseError("demo poster PNG IHDR is not exact")
            width, height = struct.unpack(">II", payload[:8])
            if width <= 0 or height <= 0:
                raise PortfolioReleaseError("demo poster has invalid dimensions")
        if chunk_type == b"IEND":
            if length != 0 or end != len(data):
                raise PortfolioReleaseError("demo poster PNG has an invalid IEND/trailing bytes")
            break
        offset = end
    if not chunks or b"IDAT" not in chunks or chunks[-1] != b"IEND":
        raise PortfolioReleaseError("demo poster PNG is missing IDAT or IEND")
    return width, height


def _mp4_boxes(
    source: Any,
    start: int,
    end: int,
    counter: list[int],
) -> list[tuple[bytes, int, int]]:
    boxes: list[tuple[bytes, int, int]] = []
    offset = start
    while offset < end:
        if end - offset < 8:
            raise PortfolioReleaseError("demo MP4 has a truncated atom header")
        source.seek(offset)
        header = source.read(8)
        if len(header) != 8:
            raise PortfolioReleaseError("demo MP4 has a truncated atom header")
        size, atom_type = struct.unpack(">I4s", header)
        header_bytes = 8
        if size == 1:
            extended = source.read(8)
            if len(extended) != 8:
                raise PortfolioReleaseError("demo MP4 has a truncated extended atom")
            size = struct.unpack(">Q", extended)[0]
            header_bytes = 16
        elif size == 0:
            size = end - offset
        if size < header_bytes or offset + size > end:
            raise PortfolioReleaseError("demo MP4 atom size is invalid")
        counter[0] += 1
        if counter[0] > 10_000:
            raise PortfolioReleaseError("demo MP4 has too many atoms")
        boxes.append((atom_type, offset + header_bytes, offset + size))
        offset += size
    return boxes


def _validate_mp4_atoms(path: Path) -> None:
    status = _require_regular_file(path, MAX_VIDEO_BYTES)
    if status.st_size < 1024:
        raise PortfolioReleaseError("demo MP4 is implausibly small")
    counter = [0]
    with path.open("rb") as source:
        top = _mp4_boxes(source, 0, status.st_size, counter)
        if not top or top[0][0] != b"ftyp":
            raise PortfolioReleaseError("demo MP4 does not start with ftyp")
        moov_boxes = [box for box in top if box[0] == b"moov"]
        mdat_boxes = [box for box in top if box[0] == b"mdat"]
        if len(moov_boxes) != 1 or not mdat_boxes or not all(
            end > start for _kind, start, end in mdat_boxes
        ):
            raise PortfolioReleaseError("demo MP4 lacks one moov and nonempty mdat")
        found_avc1 = False
        for _kind, moov_start, moov_end in moov_boxes:
            for kind, trak_start, trak_end in _mp4_boxes(
                source, moov_start, moov_end, counter
            ):
                if kind != b"trak":
                    continue
                for kind, mdia_start, mdia_end in _mp4_boxes(
                    source, trak_start, trak_end, counter
                ):
                    if kind != b"mdia":
                        continue
                    for kind, minf_start, minf_end in _mp4_boxes(
                        source, mdia_start, mdia_end, counter
                    ):
                        if kind != b"minf":
                            continue
                        for kind, stbl_start, stbl_end in _mp4_boxes(
                            source, minf_start, minf_end, counter
                        ):
                            if kind != b"stbl":
                                continue
                            for kind, stsd_start, stsd_end in _mp4_boxes(
                                source, stbl_start, stbl_end, counter
                            ):
                                if kind != b"stsd" or stsd_end - stsd_start < 8:
                                    continue
                                source.seek(stsd_start)
                                header = source.read(8)
                                entry_count = struct.unpack(">I", header[4:])[0]
                                entries = _mp4_boxes(
                                    source, stsd_start + 8, stsd_end, counter
                                )
                                if entry_count != len(entries) or entry_count == 0:
                                    raise PortfolioReleaseError(
                                        "demo MP4 stsd entry count is inconsistent"
                                    )
                                for entry_kind, entry_start, entry_end in entries:
                                    if entry_kind != b"avc1":
                                        continue
                                    if entry_end - entry_start < 78:
                                        raise PortfolioReleaseError(
                                            "demo MP4 avc1 sample entry is truncated"
                                        )
                                    children = _mp4_boxes(
                                        source, entry_start + 78, entry_end, counter
                                    )
                                    avcc = [
                                        box
                                        for box in children
                                        if box[0] == b"avcC" and box[2] - box[1] >= 7
                                    ]
                                    if len(avcc) != 1:
                                        raise PortfolioReleaseError(
                                            "demo MP4 avc1 entry lacks one nonempty avcC"
                                        )
                                    source.seek(avcc[0][1])
                                    if source.read(1) != b"\x01":
                                        raise PortfolioReleaseError(
                                            "demo MP4 avcC configuration is malformed"
                                        )
                                    found_avc1 = True
        if not found_avc1:
            raise PortfolioReleaseError(
                "demo MP4 has no H.264 avc1/avcC sample description"
            )


def _resolve_executable(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise PortfolioReleaseError(f"{label} path must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise PortfolioReleaseError(f"{label} is unavailable") from error
    status = _require_regular_file(resolved, 64 * 1024 * 1024)
    if not status.st_mode & stat.S_IXUSR:
        raise PortfolioReleaseError(f"{label} is not executable")
    return resolved


def _ffprobe_version(executable: Path) -> str:
    completed = _run((str(executable), "-version"), cwd=executable.parent, timeout=30)
    if completed.returncode != 0:
        raise PortfolioReleaseError("ffprobe version query failed")
    try:
        lines = completed.stdout.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise PortfolioReleaseError("ffprobe version is not UTF-8") from error
    if not lines or not lines[0].startswith("ffprobe version ") or len(lines[0]) > 1024:
        raise PortfolioReleaseError("ffprobe version output is malformed")
    return lines[0]


def _validate_video(
    path: Path,
    provenance: Mapping[str, Any],
    ffprobe: Path | None,
    runtime: Mapping[str, Any],
    *,
    require_recorded_ffprobe: bool,
) -> None:
    _validate_mp4_atoms(path)
    if ffprobe is None:
        raise PortfolioReleaseError("ffprobe is required for a full public verification PASS")
    executable = _resolve_executable(ffprobe, "ffprobe")
    local_version = _ffprobe_version(executable)
    if require_recorded_ffprobe:
        recorded = runtime["ffprobe"]
        if (
            _sha256(executable) != recorded["executable_sha256"]
            or local_version != recorded["version"]
        ):
            raise PortfolioReleaseError(
                "build ffprobe executable/version differs from runtime assets"
            )
    completed = _run(
        (
            str(executable),
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_name,codec_type,width,height",
            "-of",
            "json",
            str(path),
        ),
        cwd=path.parent,
        timeout=60,
    )
    if completed.returncode != 0:
        raise PortfolioReleaseError("ffprobe rejected the demo video")
    try:
        report = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PortfolioReleaseError("ffprobe returned malformed JSON") from error
    if not isinstance(report, dict) or not isinstance(report.get("streams"), list):
        raise PortfolioReleaseError("ffprobe report is incomplete")
    streams = report["streams"]
    videos = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"]
    expected = provenance["video"]
    if len(videos) != 1 or videos[0].get("codec_name") != "h264":
        raise PortfolioReleaseError("demo must have exactly one H.264 video stream")
    if videos[0].get("width") != expected["width"] or videos[0].get("height") != expected["height"]:
        raise PortfolioReleaseError("ffprobe dimensions differ from demo provenance")
    audio_codec = "silent" if not audios else "aac"
    if audios and (len(audios) != 1 or audios[0].get("codec_name") != "aac"):
        raise PortfolioReleaseError("demo audio must be absent or one AAC stream")
    if audio_codec != expected["audio_codec"]:
        raise PortfolioReleaseError("ffprobe audio identity differs from demo provenance")
    try:
        duration = float(report["format"]["duration"])
    except (KeyError, TypeError, ValueError) as error:
        raise PortfolioReleaseError("ffprobe duration is unavailable") from error
    if not math.isfinite(duration) or not (0 < duration <= 90):
        raise PortfolioReleaseError("ffprobe duration is outside the release limit")
    if abs(duration - float(expected["duration_seconds"])) > 0.05:
        raise PortfolioReleaseError("ffprobe duration differs from demo provenance")


def _safe_tar_name(name: str, label: str) -> PurePosixPath:
    if not name or "\x00" in name or "\\" in name:
        raise PortfolioReleaseError(f"{label} contains an unsafe member name")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise PortfolioReleaseError(f"{label} contains a non-normalized member")
    return path


def _decompress_bounded_gzip_stream(
    source: BinaryIO, maximum_bytes: int, label: str
) -> BinaryIO:
    expanded = 0
    destination = tempfile.TemporaryFile(mode="w+b")
    try:
        source.seek(0)
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        ended = False
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            if ended:
                raise PortfolioReleaseError(
                    f"{label} has trailing or concatenated gzip data"
                )
            pending = chunk
            while pending:
                output = decoder.decompress(
                    pending,
                    min(1024 * 1024, maximum_bytes - expanded + 1),
                )
                expanded += len(output)
                if expanded > maximum_bytes:
                    raise PortfolioReleaseError(
                        f"{label} compressed stream expands beyond the safety limit"
                    )
                destination.write(output)
                pending = decoder.unconsumed_tail
                if decoder.eof:
                    if decoder.unused_data or pending or source.read(1):
                        raise PortfolioReleaseError(
                            f"{label} has trailing or concatenated gzip data"
                        )
                    ended = True
                    break
        if not ended:
            raise PortfolioReleaseError(f"{label} gzip stream is truncated")
        destination.flush()
        destination.seek(0)
        return destination
    except (PortfolioReleaseError, zlib.error, OSError) as error:
        destination.close()
        if isinstance(error, PortfolioReleaseError):
            raise
        raise PortfolioReleaseError(f"{label} is not one bounded gzip stream") from error


def _decompress_bounded_gzip(
    path: Path, maximum_bytes: int, label: str
) -> BinaryIO:
    with path.open("rb") as source:
        return _decompress_bounded_gzip_stream(source, maximum_bytes, label)


def _validate_bounded_gzip(path: Path, maximum_bytes: int, label: str) -> None:
    with _decompress_bounded_gzip(path, maximum_bytes, label):
        pass


def _validate_tar_end(
    payload: BinaryIO, members: Sequence[tarfile.TarInfo], label: str
) -> None:
    if not members:
        raise PortfolioReleaseError(f"{label} member count is invalid")
    logical_end = max(
        member.offset_data + ((member.size + 511) // 512) * 512
        for member in members
    )
    payload.seek(0, os.SEEK_END)
    payload_size = payload.tell()
    if payload_size < logical_end + 1024:
        raise PortfolioReleaseError(f"{label} has no exact two-block tar end marker")
    payload.seek(logical_end)
    remaining = payload_size - logical_end
    while remaining:
        chunk = payload.read(min(1024 * 1024, remaining))
        if not chunk or any(chunk):
            raise PortfolioReleaseError(
                f"{label} has non-zero data after the tar end marker"
            )
        remaining -= len(chunk)
    payload.seek(0)


@contextmanager
def _open_bounded_tar_stream(
    source: BinaryIO, *, label: str
) -> Iterator[tarfile.TarFile]:
    payload = _decompress_bounded_gzip_stream(
        source, MAX_TAR_EXPANDED_BYTES, label
    )
    try:
        try:
            archive = tarfile.open(fileobj=payload, mode="r:")
            members = archive.getmembers()
            _validate_tar_end(payload, members, label)
        except (tarfile.TarError, OSError) as error:
            raise PortfolioReleaseError(f"{label} is not a valid gzip tar archive") from error
        try:
            yield archive
        finally:
            archive.close()
    finally:
        payload.close()


@contextmanager
def _open_bounded_tar(
    path: Path,
    *,
    label: str,
    compressed_limit: int,
) -> Iterator[tarfile.TarFile]:
    _require_regular_file(path, compressed_limit)
    with path.open("rb") as source:
        with _open_bounded_tar_stream(source, label=label) as archive:
            yield archive


def _validate_tar_members(
    archive: tarfile.TarFile,
    *,
    label: str,
    source_commit: str | None,
    source_prefix: str | None,
    reject_absolute_paths: bool = True,
) -> set[str]:
    if source_commit is not None and archive.pax_headers.get("comment") != source_commit:
        raise PortfolioReleaseError("source archive does not record the exact Git commit")
    members = archive.getmembers()
    if not members or len(members) > MAX_TAR_MEMBERS:
        raise PortfolioReleaseError(f"{label} member count is invalid")
    names: set[str] = set()
    expanded = 0
    for member in members:
        pure = _safe_tar_name(member.name, label)
        normalized = pure.as_posix().rstrip("/")
        if normalized in names:
            raise PortfolioReleaseError(f"{label} contains duplicate members")
        names.add(normalized)
        if source_prefix is not None and not (
            normalized == source_prefix.rstrip("/")
            or normalized.startswith(source_prefix)
        ):
            raise PortfolioReleaseError("source archive has an entry outside its prefix")
        if not (member.isfile() or member.isdir()):
            raise PortfolioReleaseError(f"{label} contains a link or special entry")
        expanded += member.size
        if expanded > MAX_TAR_EXPANDED_BYTES:
            raise PortfolioReleaseError(f"{label} expands beyond the safety limit")
        lowered = {part.lower() for part in pure.parts}
        if lowered & {".git", ".ssh", "__pycache__", ".cache", "node_modules"}:
            raise PortfolioReleaseError(f"{label} contains a forbidden directory")
        lower_name = pure.name.lower()
        if (
            lower_name in {"id_rsa", "id_ed25519"}
            or lower_name.endswith((".safetensors", ".gguf", ".ckpt", ".pth", ".pt"))
            or lower_name.startswith("pytorch_model")
        ):
            raise PortfolioReleaseError(f"{label} contains a key or model weight")
        if member.isfile():
            extracted = archive.extractfile(member)
            if extracted is None:
                raise PortfolioReleaseError(f"{label} member cannot be read")
            contains_private_path, member_digest = _assert_public_stream(
                extracted,
                f"{label}:{member.name}",
                reject_absolute_paths=reject_absolute_paths,
                strict_credentials=source_commit is None,
            )
            if contains_private_path and not reject_absolute_paths:
                if source_prefix is None or not normalized.startswith(source_prefix):
                    raise PortfolioReleaseError(
                        "private-path exception is allowed only in the exact source archive"
                    )
                relative = normalized[len(source_prefix) :]
                if LEGACY_PRIVATE_PATH_ALLOWLIST.get(relative) != member_digest:
                    raise PortfolioReleaseError(
                        f"source private-path file is not hard-allowlisted: {relative}"
                    )
    return names


def _validate_tar(
    path: Path,
    *,
    label: str,
    source_commit: str | None,
    source_prefix: str | None,
    reject_absolute_paths: bool = True,
    captured_source: BinaryIO | None = None,
) -> set[str]:
    compressed_limit = (
        MAX_SOURCE_ARCHIVE_BYTES if source_commit is not None else MAX_EVIDENCE_BYTES
    )
    opener = (
        _open_bounded_tar_stream(captured_source, label=label)
        if captured_source is not None
        else _open_bounded_tar(path, label=label, compressed_limit=compressed_limit)
    )
    with opener as archive:
        return _validate_tar_members(
            archive,
            label=label,
            source_commit=source_commit,
            source_prefix=source_prefix,
            reject_absolute_paths=reject_absolute_paths,
        )


EVIDENCE_REQUIRED_FILES = frozenset(
    {
        "run/app-run-receipt.json",
        "run/validation-064-071.json",
        "run/build-provenance.json",
        "run/runtime-provenance.json",
        "reports/structural-verifier.json",
        "reports/fresh-model-replay.json",
        "logs/terminal.log",
    }
)
EVIDENCE_ALLOWED_DIRECTORIES = frozenset(
    {"run", "run/primary-evidence", "reports", "logs"}
)


def _evidence_directory_allowed(name: str) -> bool:
    return name in EVIDENCE_ALLOWED_DIRECTORIES or name.startswith(
        "run/primary-evidence/"
    )


def _read_tar_member(
    archive: tarfile.TarFile, name: str, maximum_bytes: int
) -> bytes:
    try:
        member = archive.getmember(name)
    except KeyError as error:
        raise PortfolioReleaseError(f"demo evidence is missing exact member: {name}") from error
    if not member.isfile() or member.size > maximum_bytes:
        raise PortfolioReleaseError(f"demo evidence member is not a bounded regular file: {name}")
    extracted = archive.extractfile(member)
    if extracted is None:
        raise PortfolioReleaseError(f"demo evidence member cannot be read: {name}")
    data = extracted.read(maximum_bytes + 1)
    if len(data) != member.size:
        raise PortfolioReleaseError(f"demo evidence member size is unstable: {name}")
    return data


def _json_from_bytes(data: bytes, label: str, *, canonical: bool) -> Any:
    if data.startswith(b"\xef\xbb\xbf"):
        raise PortfolioReleaseError(f"{label} has a forbidden UTF-8 BOM")
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PortfolioReleaseError(f"{label} is not valid strict JSON") from error
    if canonical and data != _canonical_json(value):
        raise PortfolioReleaseError(f"{label} is not canonical JSON")
    _reject_placeholders(value, label)
    return value


def _validate_evidence_report(
    value: Any,
    *,
    kind: str,
    source: Mapping[str, str],
    receipt_sha256: str,
    result_sha256: str,
    metric_verdict: str,
) -> None:
    keys = {
        "schema_version",
        "report_kind",
        "verdict",
        "metric_verdict",
        "source",
        "receipt_sha256",
        "result_sha256",
        "workload_classification",
        "synthetic_data",
    }
    if kind == "fresh_model_replay":
        keys.update({"fresh", "model"})
    report = _exact_object(value, keys, f"{kind} report")
    if (
        report["schema_version"] != 1
        or report["report_kind"] != kind
        or report["verdict"] != "PASS"
        or report["metric_verdict"] != metric_verdict
        or report["source"] != source
        or report["receipt_sha256"] != receipt_sha256
        or report["result_sha256"] != result_sha256
        or report["workload_classification"] != "PUBLIC_VALIDATION_REGRESSION"
        or report["synthetic_data"] is not False
    ):
        raise PortfolioReleaseError(f"{kind} report does not bind the demo proof")
    if kind == "fresh_model_replay":
        model = _exact_object(
            report["model"], {"repository", "revision"}, "model replay identity"
        )
        if (
            report["fresh"] is not True
            or model["repository"] != EXPECTED_MODEL
            or model["revision"] != EXPECTED_MODEL_REVISION
        ):
            raise PortfolioReleaseError("fresh model replay identity is not exact")


def _load_product_evidence_verifiers() -> tuple[Any, Any, Any]:
    try:
        from security.generate_build_provenance import (
            canonical_json_bytes as canonical_provenance_bytes,
            validate_build_manifest,
        )
        from security.verify_app_run_evidence import _verify_result_and_receipt
    except ImportError as error:
        raise PortfolioReleaseError("tracked product evidence verifier is unavailable") from error
    return canonical_provenance_bytes, validate_build_manifest, _verify_result_and_receipt


def _extract_and_verify_product_evidence(
    archive: tarfile.TarFile, source: Mapping[str, str]
) -> dict[str, Any]:
    (
        canonical_provenance_bytes,
        validate_build_manifest,
        _verify_result_and_receipt,
    ) = _load_product_evidence_verifiers()
    with tempfile.TemporaryDirectory(prefix="corelm-portfolio-evidence-") as temporary:
        root = Path(temporary)
        try:
            for member in archive.getmembers():
                pure = _safe_tar_name(member.name, "demo evidence archive")
                destination = root.joinpath(*pure.parts)
                if member.isdir():
                    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise PortfolioReleaseError("demo evidence member cannot be extracted")
                with destination.open("xb") as target:
                    for chunk in iter(lambda: extracted.read(1024 * 1024), b""):
                        target.write(chunk)
                destination.chmod(0o600)
        except (OSError, tarfile.TarError) as error:
            raise PortfolioReleaseError("demo evidence cannot be safely materialized") from error
        receipt_path = root / "run" / "app-run-receipt.json"
        result_path = root / "run" / "validation-064-071.json"
        receipt = _read_json(receipt_path)
        if not isinstance(receipt, dict):
            raise PortfolioReleaseError("demo receipt is malformed")
        challenge = _digest(receipt.get("challengeNonce"), "demo proof challenge")
        try:
            verified_result = _verify_result_and_receipt(
                result_path,
                receipt_path,
                None,
                portable_macos_environment=True,
                expected_challenge_nonce=challenge,
                require_metric_pass=False,
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            raise PortfolioReleaseError("tracked product verifier rejected demo evidence") from error
        build_receipt = receipt.get("buildProvenance")
        if not isinstance(build_receipt, dict):
            raise PortfolioReleaseError("demo receipt has no build provenance")
        build_document = build_receipt.get("document")
        try:
            validate_build_manifest(build_document)
            expected_build_bytes = canonical_provenance_bytes(build_document)
        except (TypeError, ValueError) as error:
            raise PortfolioReleaseError("demo build provenance is invalid") from error
        build_path = root / "run" / "build-provenance.json"
        if build_path.read_bytes() != expected_build_bytes:
            raise PortfolioReleaseError("standalone build provenance differs from the receipt")
        build_source = build_document["source"]
        if build_source.get("commit") != source["commit"] or build_source.get("tree") != source["tree"]:
            raise PortfolioReleaseError("demo build provenance does not bind release source")
        runtime_path = root / "run" / "runtime-provenance.json"
        runtime_value = _read_json(runtime_path)
        _reject_placeholders(runtime_value, "runtime provenance")
        worker = receipt.get("worker")
        if not isinstance(worker, dict) or _sha256(runtime_path) != worker.get("runtimeManifestSHA256"):
            raise PortfolioReleaseError("runtime provenance differs from the receipt")
        return verified_result


def _validate_evidence_archive(
    path: Path,
    *,
    provenance: Mapping[str, Any],
    source: Mapping[str, str],
    captured_source: BinaryIO | None = None,
) -> None:
    try:
        opener = (
            _open_bounded_tar_stream(
                captured_source, label="demo evidence archive"
            )
            if captured_source is not None
            else _open_bounded_tar(
                path,
                label="demo evidence archive",
                compressed_limit=MAX_EVIDENCE_BYTES,
            )
        )
        with opener as archive:
            _validate_tar_members(
                archive,
                label="demo evidence archive",
                source_commit=None,
                source_prefix=None,
            )
            regular = {member.name for member in archive.getmembers() if member.isfile()}
            directories = {member.name.rstrip("/") for member in archive.getmembers() if member.isdir()}
            if not EVIDENCE_REQUIRED_FILES.issubset(regular):
                missing = sorted(EVIDENCE_REQUIRED_FILES - regular)
                raise PortfolioReleaseError(f"demo evidence is missing exact members: {missing}")
            if not any(name.startswith("run/primary-evidence/") for name in regular):
                raise PortfolioReleaseError("demo evidence has no primary raw evidence files")
            allowed_regular = EVIDENCE_REQUIRED_FILES | {
                name for name in regular if name.startswith("run/primary-evidence/")
            }
            if regular != allowed_regular or not all(
                _evidence_directory_allowed(name) for name in directories
            ):
                raise PortfolioReleaseError("demo evidence member topology is not exact")
            receipt_bytes = _read_tar_member(
                archive, "run/app-run-receipt.json", MAX_JSON_BYTES
            )
            result_bytes = _read_tar_member(
                archive, "run/validation-064-071.json", MAX_JSON_BYTES
            )
            receipt = _json_from_bytes(receipt_bytes, "demo receipt", canonical=False)
            result = _json_from_bytes(result_bytes, "demo result", canonical=False)
            if not isinstance(receipt, dict) or not isinstance(result, dict):
                raise PortfolioReleaseError("demo receipt/result roots are malformed")
            receipt_digest = hashlib.sha256(receipt_bytes).hexdigest()
            result_digest = hashlib.sha256(result_bytes).hexdigest()
            if (
                receipt_digest != provenance["receipt_sha256"]
                or result_digest != provenance["result_sha256"]
            ):
                raise PortfolioReleaseError("demo provenance does not bind receipt/result bytes")
            result_receipt = receipt.get("result")
            if (
                receipt.get("schemaVersion") != "corelm-macos-app-real-llm-run-v5"
                or not isinstance(result_receipt, dict)
                or result_receipt.get("path") != "validation-064-071.json"
                or result_receipt.get("resultFileSHA256") != result_digest
                or result_receipt.get("resultSHA256") != result.get("resultSHA256")
                or result_receipt.get("resultRole") != "PUBLIC_VALIDATION_REGRESSION"
                or result_receipt.get("swiftStructuralVerification") != "PASS"
                or result_receipt.get("metricVerdict") not in {"PASS", "FAIL"}
                or receipt.get("error") is not None
                or receipt.get("application", {}).get("executableSHA256")
                != provenance["application_executable_sha256"]
                or result.get("schemaVersion")
                != "corelm-voidtoken-v5-validation-development-v3"
            ):
                raise PortfolioReleaseError("demo receipt/result contract is not exact")
            metric_verdict = result_receipt["metricVerdict"]
            report_source = {"commit": source["commit"], "tree": source["tree"]}
            for member_name, kind in (
                ("reports/structural-verifier.json", "structural_verifier"),
                ("reports/fresh-model-replay.json", "fresh_model_replay"),
            ):
                report = _json_from_bytes(
                    _read_tar_member(archive, member_name, MAX_JSON_BYTES),
                    kind,
                    canonical=True,
                )
                _validate_evidence_report(
                    report,
                    kind=kind,
                    source=report_source,
                    receipt_sha256=receipt_digest,
                    result_sha256=result_digest,
                    metric_verdict=metric_verdict,
                )
            log = _read_tar_member(archive, "logs/terminal.log", MAX_TEXT_BYTES)
            try:
                terminal = log.decode("utf-8")
            except UnicodeDecodeError as error:
                raise PortfolioReleaseError("demo terminal log is not UTF-8") from error
            expected_outcome = (
                "END-TO-END PROOF PASS"
                if metric_verdict == "PASS"
                else "END-TO-END PROOF VERIFIED — METRIC FAIL"
            )
            if terminal.count(expected_outcome) != 1 or "rerun-to-pass" in terminal.lower():
                raise PortfolioReleaseError("demo terminal outcome is missing or selection-tainted")
            _extract_and_verify_product_evidence(archive, source)
    except (OSError, tarfile.TarError) as error:
        raise PortfolioReleaseError("demo evidence archive cannot be inspected") from error


def _deterministic_gzip(payload: bytes) -> bytes:
    import io

    target = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=target, mtime=0) as compressed:
        compressed.write(payload)
    return target.getvalue()


def _git_sha1(payload: bytes) -> bytes:
    try:
        return hashlib.sha1(payload, usedforsecurity=False).digest()
    except TypeError:  # pragma: no cover - compatibility with non-OpenSSL builds
        return hashlib.sha1(payload).digest()


def _git_tree_oid(files: Mapping[str, tuple[str, bytes]]) -> str:
    root: dict[bytes, Any] = {}
    for relative, (mode, object_id) in files.items():
        safe = _safe_relative(relative, "source archive Git path")
        if mode not in {"100644", "100755"} or len(object_id) != 20:
            raise PortfolioReleaseError("source archive Git entry is malformed")
        parts = [part.encode("ascii") for part in PurePosixPath(safe).parts]
        node = root
        for part in parts[:-1]:
            existing = node.get(part)
            if existing is None:
                child: dict[bytes, Any] = {}
                node[part] = child
                node = child
            elif isinstance(existing, dict):
                node = existing
            else:
                raise PortfolioReleaseError("source archive has a file/directory collision")
        leaf = parts[-1]
        if leaf in node:
            raise PortfolioReleaseError("source archive has a duplicate Git path")
        node[leaf] = (mode, object_id)

    def digest_tree(node: Mapping[bytes, Any]) -> bytes:
        entries: list[tuple[bytes, bool, bytes]] = []
        for name, value in node.items():
            if isinstance(value, dict):
                entry = b"40000 " + name + b"\0" + digest_tree(value)
                entries.append((name, True, entry))
            else:
                mode, object_id = value
                entry = mode.encode("ascii") + b" " + name + b"\0" + object_id
                entries.append((name, False, entry))
        entries.sort(key=lambda item: item[0] + (b"/" if item[1] else b"\0"))
        body = b"".join(item[2] for item in entries)
        return _git_sha1(b"tree " + str(len(body)).encode("ascii") + b"\0" + body)

    return digest_tree(root).hex()


def _validate_source_archive_tree(
    path: Path,
    expected_tree: str,
    expected_commit: str,
    *,
    captured_source: BinaryIO | None = None,
) -> None:
    _git_object(expected_tree, "source archive expected tree")
    _git_object(expected_commit, "source archive expected commit")
    prefix = "core-lm-benchmark/"
    files: dict[str, tuple[str, bytes]] = {}
    directories: set[str] = set()
    try:
        opener = (
            _open_bounded_tar_stream(captured_source, label="source archive")
            if captured_source is not None
            else _open_bounded_tar(
                path,
                label="source archive",
                compressed_limit=MAX_SOURCE_ARCHIVE_BYTES,
            )
        )
        with opener as archive:
            _validate_tar_members(
                archive,
                label="source archive",
                source_commit=expected_commit,
                source_prefix=prefix,
                reject_absolute_paths=False,
            )
            for member in archive.getmembers():
                pure = _safe_tar_name(member.name, "source archive")
                normalized = pure.as_posix().rstrip("/")
                if normalized == prefix.rstrip("/"):
                    if not member.isdir() or member.mode & 0o777 != 0o775:
                        raise PortfolioReleaseError("source archive root entry is not exact")
                    directories.add("")
                    continue
                if not normalized.startswith(prefix):
                    raise PortfolioReleaseError("source archive entry is outside exact prefix")
                relative = normalized[len(prefix) :]
                _safe_relative(relative, "source archive path")
                if member.isdir():
                    if member.mode & 0o777 != 0o775:
                        raise PortfolioReleaseError("source archive directory mode is not exact")
                    directories.add(relative)
                    continue
                if not member.isfile() or getattr(member, "sparse", None):
                    raise PortfolioReleaseError("source archive Git entry is not a plain file")
                permissions = member.mode & 0o777
                if permissions not in {0o664, 0o775}:
                    raise PortfolioReleaseError("source archive file mode is not exact")
                mode = "100755" if permissions == 0o775 else "100644"
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise PortfolioReleaseError("source archive Git blob cannot be read")
                digest = hashlib.sha1(usedforsecurity=False)
                digest.update(b"blob " + str(member.size).encode("ascii") + b"\0")
                observed_size = 0
                for chunk in iter(lambda: extracted.read(1024 * 1024), b""):
                    observed_size += len(chunk)
                    digest.update(chunk)
                if observed_size != member.size:
                    raise PortfolioReleaseError("source archive Git blob size is unstable")
                if relative in files:
                    raise PortfolioReleaseError("source archive has a duplicate Git file")
                files[relative] = (mode, digest.digest())
    except (OSError, tarfile.TarError, UnicodeEncodeError) as error:
        raise PortfolioReleaseError("source archive Git tree cannot be reconstructed") from error
    if not files:
        raise PortfolioReleaseError("source archive Git tree is empty")
    expected_directories = {""}
    for relative in files:
        parts = PurePosixPath(relative).parts
        expected_directories.update(
            PurePosixPath(*parts[:index]).as_posix()
            for index in range(1, len(parts))
        )
    if directories != expected_directories:
        raise PortfolioReleaseError("source archive directory set is not exact")
    observed_tree = _git_tree_oid(files)
    if observed_tree != expected_tree:
        raise PortfolioReleaseError(
            "source archive content/modes do not reconstruct the signed source tree"
        )


def _build_source_archive(repository: Path, commit: str, destination: Path) -> None:
    command = (
        "/usr/bin/git",
        "-c",
        "tar.umask=0002",
        "archive",
        "--format=tar",
        "--prefix=core-lm-benchmark/",
        commit,
    )
    archives = [
        _run(command, cwd=repository, timeout=300),
        _run(command, cwd=repository, timeout=300),
    ]
    if any(completed.returncode != 0 for completed in archives):
        raise PortfolioReleaseError("git archive failed")
    if archives[0].stdout != archives[1].stdout:
        raise PortfolioReleaseError("git archive is not byte-deterministic")
    first = _deterministic_gzip(archives[0].stdout)
    second = _deterministic_gzip(archives[1].stdout)
    if first != second:
        raise PortfolioReleaseError("gzip source archive is not deterministic")
    destination.write_bytes(first)
    destination.chmod(0o644)
    _validate_tar(
        destination,
        label="source archive",
        source_commit=commit,
        source_prefix="core-lm-benchmark/",
        reject_absolute_paths=False,
    )
    _validate_source_archive_tree(
        destination,
        _git(repository, "rev-parse", f"{commit}^{{tree}}"),
        commit,
    )


def _validate_source_manifest_bindings(
    archive_path: Path,
    runtime: Mapping[str, Any],
    expected_commit: str,
    *,
    captured_source: BinaryIO | None = None,
) -> None:
    expected = {
        row["path"]: row["sha256"]
        for row in (*runtime["lockfiles"], *runtime["verifiers"])
    }
    try:
        opener = (
            _open_bounded_tar_stream(captured_source, label="source archive")
            if captured_source is not None
            else _open_bounded_tar(
                archive_path,
                label="source archive",
                compressed_limit=MAX_SOURCE_ARCHIVE_BYTES,
            )
        )
        with opener as archive:
            _validate_tar_members(
                archive,
                label="source archive",
                source_commit=expected_commit,
                source_prefix="core-lm-benchmark/",
                reject_absolute_paths=False,
            )
            for relative, digest in expected.items():
                member_name = f"core-lm-benchmark/{relative}"
                try:
                    member = archive.getmember(member_name)
                except KeyError as error:
                    raise PortfolioReleaseError(
                        f"source archive is missing runtime-bound file: {relative}"
                    ) from error
                if not member.isfile():
                    raise PortfolioReleaseError(
                        f"runtime-bound source entry is not regular: {relative}"
                    )
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise PortfolioReleaseError(
                        f"runtime-bound source entry cannot be read: {relative}"
                    )
                observed = hashlib.sha256()
                for chunk in iter(lambda: extracted.read(1024 * 1024), b""):
                    observed.update(chunk)
                if observed.hexdigest() != digest:
                    raise PortfolioReleaseError(
                        f"runtime manifest differs from source archive: {relative}"
                    )
    except (OSError, tarfile.TarError) as error:
        raise PortfolioReleaseError("source archive cannot be checked against runtime identities") from error


def _validate_sbom(path: Path, tag: str) -> dict[str, Any]:
    value = _read_json(path)
    if not isinstance(value, dict):
        raise PortfolioReleaseError("direct SBOM root is malformed")
    if value.get("bomFormat") != "CycloneDX" or value.get("specVersion") != "1.5" or value.get("version") != 1:
        raise PortfolioReleaseError("direct SBOM must be CycloneDX 1.5")
    metadata = value.get("metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("component"), dict):
        raise PortfolioReleaseError("direct SBOM metadata is incomplete")
    if metadata["component"].get("version") != tag:
        raise PortfolioReleaseError("direct SBOM version does not match the portfolio tag")
    properties = metadata.get("properties")
    if properties != [{"name": "corelm:sbom-scope", "value": "direct-python-dependencies-only"}]:
        raise PortfolioReleaseError("direct SBOM scope is not exact")
    if not isinstance(value.get("components"), list) or not value["components"]:
        raise PortfolioReleaseError("direct SBOM has no dependency components")
    _reject_placeholders(value, "direct SBOM")
    return value


def _build_sbom(repository: Path, destination: Path, tag: str) -> None:
    script = repository / "security" / "generate_direct_sbom.py"
    _require_regular_file(script, MAX_TEXT_BYTES)
    with tempfile.TemporaryDirectory(prefix="corelm-portfolio-sbom-") as temporary:
        first = Path(temporary) / "first.json"
        second = Path(temporary) / "second.json"
        for target in (first, second):
            completed = _run(
                (sys.executable, "-I", "-B", str(script), "--output", str(target)),
                cwd=repository,
            )
            if completed.returncode != 0:
                raise PortfolioReleaseError("direct SBOM generator failed")
            _require_regular_file(target, MAX_JSON_BYTES)
        if first.read_bytes() != second.read_bytes():
            raise PortfolioReleaseError("direct SBOM generation is not deterministic")
        _validate_sbom(first, tag)
        _copy_regular(first, destination, MAX_JSON_BYTES)


def _source_identity(
    release_input: Mapping[str, Any], provenance: Mapping[str, Any]
) -> dict[str, Any]:
    tag = release_input["tag"]
    source = release_input["source"]
    related = release_input["related_sources"]
    ci = release_input["continuous_integration"]
    identity = {
        "artifact_kind": "corelm_portfolio_release",
        "author": {"name": EXPECTED_AUTHOR, "orcid": EXPECTED_ORCID},
        "claims": {
            "excluded": [
                "model_weight_compression",
                "universal_llm_generalization",
                "state_of_the_art",
                "production_serving_readiness",
                "independent_human_replication",
            ],
            "supported": "Built and reproducibly evaluated complete-container KV-cache compression on pinned real-model workloads.",
        },
        "continuous_integration": {
            "commit": source["commit"],
            "linux_x86_64": {
                "conclusion": "success",
                "required": True,
                "url": ci["linux_x86_64"]["url"],
            },
            "macos_arm64": {
                "conclusion": "success",
                "required": True,
                "url": ci["macos_arm64"]["url"],
            },
            "validation": "SIGNED_OPERATOR_ASSERTION_REQUIRES_LIVE_API_RECHECK",
        },
        "demo": {
            "evidence_sha256": provenance["evidence_sha256"],
            "result_sha256": provenance["result_sha256"],
            "synthetic_data": False,
            "video_sha256": provenance["video"]["sha256"],
            "workload_classification": "PUBLIC_VALIDATION_REGRESSION",
        },
        "related_sources": {
            "blind_v1_draft": {
                "commit": related["blind_v1_draft"]["commit"],
                "lifecycle_state": "DRAFT_NOT_PREREGISTERED",
                "pull_request": BLIND_PULL_REQUEST,
                "tree": related["blind_v1_draft"]["tree"],
            },
            "cross_model_lab": {
                "commit": related["cross_model_lab"]["commit"],
                "repository": LAB_REPOSITORY,
                "tree": related["cross_model_lab"]["tree"],
            },
        },
        "release": {
            "prerelease": False,
            "scientific_status": "NOT_A_BLIND_OR_GENERALIZATION_RESULT",
            "tag": tag,
            "url": f"{CANONICAL_REPOSITORY}/releases/tag/{tag}",
        },
        "reproduction": {
            "linux": [
                "./corelm linux bootstrap",
                "./corelm linux doctor",
                "./corelm linux build",
                "./corelm linux run",
            ],
            "macos": ["./corelm macos doctor", "./corelm macos proof"],
            "repository_gate": "./corelm verify",
        },
        "schema_version": 1,
        "signing": {
            "allowed_signers_sha256": EXPECTED_ALLOWED_SIGNERS_SHA256,
            "algorithm": "ssh-ed25519",
            "fingerprint": EXPECTED_FINGERPRINT,
            "public_key_sha256": EXPECTED_PUBLIC_KEY_SHA256,
        },
        "source": {
            "commit": source["commit"],
            "default_branch": "main",
            "repository": CANONICAL_REPOSITORY,
            "tag_object": source["tag_object"],
            "tree": source["tree"],
            "worktree_state": "clean",
        },
    }
    _reject_placeholders(identity, "source identity")
    _validate_schema(identity, IDENTITY_SCHEMA, "source identity")
    return identity


def _validate_identity_bindings(identity: Mapping[str, Any], tag: str) -> None:
    _validate_schema(identity, IDENTITY_SCHEMA, "source identity")
    _reject_placeholders(identity, "source identity")
    if identity["release"]["tag"] != tag:
        raise PortfolioReleaseError("source identity tag is inconsistent")
    if identity["release"]["url"] != f"{CANONICAL_REPOSITORY}/releases/tag/{tag}":
        raise PortfolioReleaseError("source identity release URL is inconsistent")
    commit = identity["source"]["commit"]
    tree = identity["source"]["tree"]
    if identity["continuous_integration"]["commit"] != commit:
        raise PortfolioReleaseError("CI identity is not bound to the source commit")
    if identity["continuous_integration"]["validation"] != (
        "SIGNED_OPERATOR_ASSERTION_REQUIRES_LIVE_API_RECHECK"
    ):
        raise PortfolioReleaseError("CI identity overstates offline verification")
    for platform in ("linux_x86_64", "macos_arm64"):
        run = identity["continuous_integration"][platform]
        if ACTION_URL_RE.fullmatch(run["url"]) is None:
            raise PortfolioReleaseError(f"{platform} CI URL is not canonical")
    for source in (
        identity["source"],
        identity["related_sources"]["cross_model_lab"],
        identity["related_sources"]["blind_v1_draft"],
    ):
        _git_object(source["commit"], "source identity commit")
        _git_object(source["tree"], "source identity tree")
    _git_object(identity["source"]["tag_object"], "source identity tag object")
    if not commit or not tree:
        raise PortfolioReleaseError("source identity is incomplete")


def reproduce_document(tag: str, commit: str, tree: str, tag_object: str) -> bytes:
    exact, version = _exact_tag(tag)
    _git_object(commit, "reproduction commit")
    _git_object(tree, "reproduction tree")
    _git_object(tag_object, "reproduction tag object")
    text = f"""# Reproduce Core LM Portfolio v{version}

This is a source-built engineering regression on pinned real-model workloads.
It is not model-weight compression and not a Blind V1 generalization result.

## Verify downloaded release assets

Download all assets from:

`https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/{exact}`

From the download directory:

```sh
set -eu
sha256_path() {{
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{{print $1}}'
  else
    shasum -a 256 "$1" | awk '{{print $1}}'
  fi
}}
test "$(sha256_path corelm-portfolio-signing.pub)" = \\
  {EXPECTED_PUBLIC_KEY_SHA256}
test "$(sha256_path allowed_signers)" = \\
  {EXPECTED_ALLOWED_SIGNERS_SHA256}
ssh-keygen -E sha256 -lf corelm-portfolio-signing.pub | \\
  grep -Fq '{EXPECTED_FINGERPRINT}'
signer_identity=$(awk 'NR == 1 {{print $1}}' allowed_signers)
ssh-keygen -Y verify -f allowed_signers -I "$signer_identity" -n file \\
  -s SHA256SUMS.sig < SHA256SUMS
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum -c SHA256SUMS
else
  shasum -a 256 -c SHA256SUMS
fi
ssh-keygen -Y verify -f allowed_signers -I "$signer_identity" -n file \\
  -s {exact}-source-identity.json.sig \\
  < {exact}-source-identity.json
```

## Verify and check out the signed source tag

```sh
set -eu
asset_directory=$(pwd -P)
checkout_root=$(mktemp -d)
git clone https://github.com/ALLPROTO/core-lm-benchmark.git \
  "$checkout_root/core-lm-benchmark"
cd "$checkout_root/core-lm-benchmark"
git fetch origin tag {exact}
git -c gpg.format=ssh \\
  -c gpg.ssh.program=/usr/bin/ssh-keygen \\
  -c gpg.ssh.allowedSignersFile="$asset_directory/allowed_signers" \\
  verify-tag {exact}
test "$(git rev-parse 'refs/tags/{exact}')" = "{tag_object}"
git checkout --detach "$(git rev-list -n 1 {exact})"
test "$(git rev-parse HEAD)" = "{commit}"
test "$(git rev-parse 'HEAD^{{tree}}')" = "{tree}"
case "$(uname -s):$(uname -m)" in
  Darwin:arm64)
    ./corelm macos bootstrap
    ./corelm macos build
    locked_python="$HOME/.cache/corelm/macos/runtime/bin/python"
    ;;
  Linux:x86_64)
    ./corelm linux bootstrap
    ./corelm linux build
    locked_python="$HOME/.cache/corelm/linux/runtime/bin/python"
    ;;
  *)
    echo "Unsupported reproduction platform: $(uname -s):$(uname -m)" >&2
    exit 2
    ;;
esac
test -x "$locked_python"
test "$("$locked_python" -I -B -c \\
  'import platform; print(platform.python_version())')" = "3.12.13"
ffprobe_path=$(command -v ffprobe || true)
test -n "$ffprobe_path"
# This is a caller-side decoder check, not a release signing or CI trust root.
"$locked_python" -I -B publication/build_portfolio_release.py \
  --verify "$asset_directory" --ffprobe "$ffprobe_path"
PYTHON_BIN="$locked_python" ./corelm verify
```

## macOS Apple Silicon

Requirements: macOS 14+, Swift 6, 8 GB unified memory, 6 GiB free disk, an
active desktop session, and Python 3.12.13. If the exact Python is absent, run
the hash-checked bootstrap first.

```sh
./corelm macos bootstrap
./corelm macos doctor
./corelm macos proof
```

The command builds and opens the native SwiftUI app, runs pinned real Qwen on
Apple MPS, retains fresh evidence, and requires the separate verifier and model
replay to pass before reporting the end-to-end verdict.

## Ubuntu 24.04 x86-64

Requirements: 8 GiB available memory and 6 GiB free disk.

```sh
./corelm linux bootstrap
./corelm linux doctor
./corelm linux build
./corelm linux run
```

The Linux path is a real-Qwen CPU regression. CPU and Apple MPS metrics need
not be bit-identical.

## Claim boundary

Successful reproduction establishes execution of the exact public source,
pinned assets, complete-container accounting, retained evidence, and verifier
agreement on the recorded narrow workload. It does not establish model-weight
compression, arbitrary-model generalization, production latency/memory gains,
state of the art, or independent human validation.
"""
    if PLACEHOLDER_RE.search(text):
        raise PortfolioReleaseError("generated reproduction document has a placeholder")
    return text.encode("utf-8")


def _private_key_from_environment(public_key: Path) -> Path:
    raw = os.environ.get("CORELM_PORTFOLIO_SIGNING_KEY")
    if not raw or "\x00" in raw or "\n" in raw or "\r" in raw:
        raise PortfolioReleaseError("CORELM_PORTFOLIO_SIGNING_KEY is required")
    candidate = Path(raw)
    if not candidate.is_absolute() or candidate.is_symlink():
        raise PortfolioReleaseError("signing key must be an absolute regular file")
    try:
        key = candidate.resolve(strict=True)
    except OSError:
        raise PortfolioReleaseError("signing key is unavailable") from None
    status = _require_regular_file(key, 64 * 1024)
    if status.st_mode & 0o077:
        raise PortfolioReleaseError("signing key permissions must exclude group/other access")
    completed = _run(
        ("/usr/bin/ssh-keygen", "-y", "-f", str(key)),
        cwd=public_key.parent,
        private_operation=True,
    )
    if completed.returncode != 0:
        raise PortfolioReleaseError("private-key operation failed")
    try:
        fields = completed.stdout.decode("ascii").split()
    except UnicodeDecodeError:
        raise PortfolioReleaseError("private-key operation failed") from None
    if len(fields) < 2 or " ".join(fields[:2]) != _public_key_identity(public_key):
        raise PortfolioReleaseError("private signing key does not match the tracked public key")
    return key


def _verify_detached_signature(
    payload: Path, signature: Path, allowed_signers: Path, public_key: Path
) -> None:
    _require_regular_file(payload)
    _require_regular_file(signature, 64 * 1024)
    principal = _signer_principal(allowed_signers, public_key)
    completed = _run(
        (
            "/usr/bin/ssh-keygen",
            "-Y",
            "verify",
            "-f",
            str(allowed_signers),
            "-I",
            principal,
            "-n",
            "file",
            "-s",
            str(signature),
        ),
        cwd=payload.parent,
        input_bytes=payload.read_bytes(),
    )
    if completed.returncode != 0:
        raise PortfolioReleaseError(f"detached SSH signature failed: {signature.name}")


def _sign_file(payload: Path, key: Path, allowed_signers: Path, public_key: Path) -> Path:
    signature = Path(str(payload) + ".sig")
    if signature.exists() or signature.is_symlink():
        raise PortfolioReleaseError(f"signature destination already exists: {signature.name}")
    completed = _run(
        (
            "/usr/bin/ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            "file",
            str(payload),
        ),
        cwd=payload.parent,
        private_operation=True,
    )
    if completed.returncode != 0:
        raise PortfolioReleaseError("private-key operation failed")
    _require_regular_file(signature, 64 * 1024)
    signature.chmod(0o644)
    _verify_detached_signature(payload, signature, allowed_signers, public_key)
    return signature


def _write_checksums(directory: Path, tag: str) -> None:
    rows = []
    for name in sorted(covered_asset_names(tag), key=lambda item: item.encode("ascii")):
        rows.append(f"{_sha256(directory / name)}  {name}\n")
    target = directory / "SHA256SUMS"
    target.write_text("".join(rows), encoding="ascii")
    target.chmod(0o644)


def _parse_checksums(path: Path) -> dict[str, str]:
    _require_regular_file(path, MAX_TEXT_BYTES)
    try:
        text = path.read_text(encoding="ascii")
    except UnicodeDecodeError as error:
        raise PortfolioReleaseError("SHA256SUMS is not ASCII") from error
    if not text.endswith("\n") or "\r" in text:
        raise PortfolioReleaseError("SHA256SUMS must use exact LF lines")
    result: dict[str, str] = {}
    rows = text.splitlines()
    for row in rows:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._+-]+)", row)
        if match is None or match.group(2) in result:
            raise PortfolioReleaseError("SHA256SUMS is malformed")
        result[match.group(2)] = match.group(1)
    if list(result) != sorted(result, key=lambda item: item.encode("ascii")):
        raise PortfolioReleaseError("SHA256SUMS rows are not bytewise sorted")
    return result


def _validate_ci_bindings(release_input: Mapping[str, Any]) -> None:
    commit = release_input["source"]["commit"]
    for platform in ("linux_x86_64", "macos_arm64"):
        run = release_input["continuous_integration"][platform]
        if run["commit"] != commit:
            raise PortfolioReleaseError(f"{platform} CI run is not bound to source HEAD")
        if ACTION_URL_RE.fullmatch(run["url"]) is None:
            raise PortfolioReleaseError(f"{platform} CI URL is not an exact run URL")
    urls = [release_input["continuous_integration"][key]["url"] for key in ("linux_x86_64", "macos_arm64")]
    if len(set(urls)) != 2:
        raise PortfolioReleaseError("Linux and macOS must bind distinct CI runs")


def _asset_paths(release_input: Mapping[str, Any]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    file_identities: set[tuple[int, int]] = set()
    for key, value in release_input["local_assets"].items():
        path = Path(value)
        if not path.is_absolute() or path.is_symlink():
            raise PortfolioReleaseError(f"local asset must be an absolute regular path: {key}")
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise PortfolioReleaseError(f"local asset is unavailable: {key}") from error
        maximum = (
            MAX_EVIDENCE_BYTES
            if key == "demo_evidence"
            else MAX_VIDEO_BYTES
            if key == "demo_video"
            else MAX_POSTER_BYTES
            if key == "demo_poster"
            else MAX_JSON_BYTES
        )
        status = _require_regular_file(resolved, maximum)
        identity = (status.st_dev, status.st_ino)
        if identity in file_identities:
            raise PortfolioReleaseError("local release assets must not alias one inode")
        file_identities.add(identity)
        result[key] = resolved
    if len(set(result.values())) != len(result):
        raise PortfolioReleaseError("local release assets must be distinct files")
    return result


def _stable_stat_identity(status: os.stat_result) -> tuple[int, ...]:
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_nlink,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def _capture_checksum_bound_file(
    path: Path,
    *,
    expected_sha256: str,
    maximum_bytes: int,
    label: str,
) -> BinaryIO:
    """Return a pathless read-only copy bound to one signed checksum row."""
    expected = _digest(expected_sha256, f"{label} expected SHA-256")
    before = _require_regular_file(path, maximum_bytes)
    source_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    source_flags |= getattr(os, "O_NOFOLLOW", 0)
    source_fd = -1
    write_fd = -1
    read_fd = -1
    private_directory = Path(
        tempfile.mkdtemp(prefix="corelm-checksum-bound-capture-")
    )
    capture_path = private_directory / "payload"
    try:
        source_fd = os.open(path, source_flags)
        opened = os.fstat(source_fd)
        if _stable_stat_identity(opened) != _stable_stat_identity(before):
            raise PortfolioReleaseError(f"{label} changed while it was opened")
        write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        write_flags |= getattr(os, "O_CLOEXEC", 0)
        write_fd = os.open(capture_path, write_flags, 0o600)
        digest = hashlib.sha256()
        copied = 0
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            copied += len(chunk)
            if copied > maximum_bytes:
                raise PortfolioReleaseError(f"{label} grew beyond its safety limit")
            digest.update(chunk)
            pending = memoryview(chunk)
            while pending:
                written = os.write(write_fd, pending)
                if written <= 0:
                    raise PortfolioReleaseError(f"{label} capture write was incomplete")
                pending = pending[written:]
        after = os.fstat(source_fd)
        if (
            copied != opened.st_size
            or _stable_stat_identity(after) != _stable_stat_identity(opened)
        ):
            raise PortfolioReleaseError(f"{label} changed while it was captured")
        observed = digest.hexdigest()
        if observed != expected:
            raise PortfolioReleaseError(f"checksum mismatch: {path.name}")
        os.fsync(write_fd)
        written_status = os.fstat(write_fd)
        if written_status.st_size != copied:
            raise PortfolioReleaseError(f"{label} capture size is unstable")
        os.close(write_fd)
        write_fd = -1
        capture_path.chmod(0o400)
        read_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        read_flags |= getattr(os, "O_NOFOLLOW", 0)
        read_fd = os.open(capture_path, read_flags)
        read_status = os.fstat(read_fd)
        if (
            not stat.S_ISREG(read_status.st_mode)
            or read_status.st_nlink != 1
            or (read_status.st_dev, read_status.st_ino, read_status.st_size)
            != (written_status.st_dev, written_status.st_ino, written_status.st_size)
        ):
            raise PortfolioReleaseError(f"{label} capture cannot be sealed")
        capture_path.unlink()
        private_directory.rmdir()
        captured = os.fdopen(read_fd, "rb", closefd=True)
        read_fd = -1
        return captured
    except OSError as error:
        raise PortfolioReleaseError(f"{label} cannot be captured safely") from error
    finally:
        if source_fd >= 0:
            os.close(source_fd)
        if write_fd >= 0:
            os.close(write_fd)
        if read_fd >= 0:
            os.close(read_fd)
        try:
            capture_path.unlink(missing_ok=True)
            private_directory.rmdir()
        except OSError:
            pass


def _open_checksum_bound_file(
    path: Path,
    *,
    expected_sha256: str,
    maximum_bytes: int,
    label: str,
) -> tuple[BinaryIO, tuple[int, ...]]:
    """Hash one stable inode and retain its read-only descriptor as a seal."""
    expected = _digest(expected_sha256, f"{label} expected SHA-256")
    before = _require_regular_file(path, maximum_bytes)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if _stable_stat_identity(opened) != _stable_stat_identity(before):
            raise PortfolioReleaseError(f"{label} changed while it was opened")
        digest = hashlib.sha256()
        observed_size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            observed_size += len(chunk)
            if observed_size > maximum_bytes:
                raise PortfolioReleaseError(f"{label} grew beyond its safety limit")
            digest.update(chunk)
        after = os.fstat(descriptor)
        sealed = _stable_stat_identity(after)
        if observed_size != opened.st_size or sealed != _stable_stat_identity(opened):
            raise PortfolioReleaseError(f"{label} changed while it was hashed")
        if digest.hexdigest() != expected:
            raise PortfolioReleaseError(f"checksum mismatch: {path.name}")
        os.lseek(descriptor, 0, os.SEEK_SET)
        source = os.fdopen(descriptor, "rb", closefd=True)
        descriptor = -1
        return source, sealed
    except OSError as error:
        raise PortfolioReleaseError(f"{label} cannot be opened safely") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@contextmanager
def _checksum_bound_asset_snapshots(
    root: Path,
    *,
    tag: str,
    checksums: Mapping[str, str],
    caps: Mapping[str, int],
) -> Iterator[Mapping[str, BinaryIO]]:
    archive_names = {
        f"{tag}-demo-evidence.tar.gz",
        f"{tag}-source.tar.gz",
    }
    captured: dict[str, BinaryIO] = {}
    held: dict[str, BinaryIO] = {}
    sealed_file_identities: dict[str, tuple[int, ...]] = {}
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    directory_fd = -1
    try:
        directory_fd = os.open(root, directory_flags)
        sealed_directory_identity = _stable_stat_identity(os.fstat(directory_fd))
        expected_entries = set(asset_names(tag))
        if set(os.listdir(directory_fd)) != expected_entries:
            raise PortfolioReleaseError("checksum-bound release file set is not exact")
        for name, digest in checksums.items():
            path = root / name
            if name in archive_names:
                captured[name] = _capture_checksum_bound_file(
                    path,
                    expected_sha256=digest,
                    maximum_bytes=caps[name],
                    label=name,
                )
            else:
                source, identity = _open_checksum_bound_file(
                    path,
                    expected_sha256=digest,
                    maximum_bytes=caps[name],
                    label=name,
                )
                held[name] = source
                sealed_file_identities[name] = identity
        if set(captured) != archive_names:
            raise PortfolioReleaseError("checksum-bound archive set is not exact")
        if set(held) != set(checksums) - archive_names:
            raise PortfolioReleaseError("checksum-bound non-archive set is not exact")

        def assert_stable() -> None:
            if set(os.listdir(directory_fd)) != expected_entries or (
                _stable_stat_identity(os.fstat(directory_fd))
                != sealed_directory_identity
            ):
                raise PortfolioReleaseError(
                    "checksum-bound release snapshot changed during verification"
                )
            try:
                current_root = os.stat(root, follow_symlinks=False)
            except OSError as error:
                raise PortfolioReleaseError(
                    "checksum-bound release snapshot changed during verification"
                ) from error
            directory_status = os.fstat(directory_fd)
            if (current_root.st_dev, current_root.st_ino) != (
                directory_status.st_dev,
                directory_status.st_ino,
            ):
                raise PortfolioReleaseError(
                    "checksum-bound release snapshot changed during verification"
                )
            for name, source in held.items():
                try:
                    current_fd = os.fstat(source.fileno())
                    current_path = os.stat(
                        name, dir_fd=directory_fd, follow_symlinks=False
                    )
                except OSError as error:
                    raise PortfolioReleaseError(
                        f"checksum-bound asset changed during verification: {name}"
                    ) from error
                sealed = sealed_file_identities[name]
                if (
                    _stable_stat_identity(current_fd) != sealed
                    or _stable_stat_identity(current_path) != sealed
                ):
                    raise PortfolioReleaseError(
                        f"checksum-bound asset changed during verification: {name}"
                    )

        assert_stable()
        try:
            yield captured
        except BaseException:
            raise
        else:
            assert_stable()
    finally:
        for source in captured.values():
            source.close()
        for source in held.values():
            source.close()
        if directory_fd >= 0:
            os.close(directory_fd)


@contextmanager
def _release_snapshot(directory: Path) -> Iterator[Path]:
    if directory.is_symlink():
        raise PortfolioReleaseError("release directory must not be a symlink")
    try:
        root = directory.resolve(strict=True)
    except OSError as error:
        raise PortfolioReleaseError("release directory is unavailable") from error
    if not root.is_dir():
        raise PortfolioReleaseError("release path must be a directory")
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(root, directory_flags)
    except OSError as error:
        raise PortfolioReleaseError("release directory cannot be opened safely") from error
    source_fds: dict[str, int] = {}
    sealed_file_identities: dict[str, tuple[int, ...]] = {}
    try:
        initial_directory_status = os.fstat(directory_fd)
        observed = set(os.listdir(directory_fd))
        identity_candidates = [
            name
            for name in observed
            if re.fullmatch(
                r"corelm-portfolio-v[1-9][0-9]*-source-identity\.json", name
            )
        ]
        if len(identity_candidates) != 1:
            raise PortfolioReleaseError(
                "release must contain exactly one portfolio source identity"
            )
        tag = identity_candidates[0][: -len("-source-identity.json")]
        expected = set(asset_names(tag))
        if observed != expected:
            missing = sorted(expected - observed)
            extra = sorted(observed - expected)
            raise PortfolioReleaseError(
                f"release file set is not exact; missing={missing}, extra={extra}"
            )
        caps = asset_size_caps(tag)
        identities: set[tuple[int, int]] = set()
        with tempfile.TemporaryDirectory(
            prefix="corelm-portfolio-release-snapshot-"
        ) as temporary:
            snapshot = Path(temporary)
            for name in asset_names(tag):
                try:
                    before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError as error:
                    raise PortfolioReleaseError(
                        f"required file is unavailable: {name}"
                    ) from error
                if not stat.S_ISREG(before.st_mode):
                    raise PortfolioReleaseError(
                        f"file must be regular and not a symlink: {name}"
                    )
                if before.st_nlink != 1:
                    raise PortfolioReleaseError(f"file must not be hard-linked: {name}")
                if before.st_size > caps[name]:
                    raise PortfolioReleaseError(f"file is too large: {name}")
                flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                flags |= getattr(os, "O_NOFOLLOW", 0)
                try:
                    source_fd = os.open(name, flags, dir_fd=directory_fd)
                except OSError as error:
                    raise PortfolioReleaseError(
                        f"release asset cannot be opened safely: {name}"
                    ) from error
                source_fds[name] = source_fd
                opened = os.fstat(source_fd)
                if _stable_stat_identity(opened) != _stable_stat_identity(before):
                    raise PortfolioReleaseError(
                        f"release asset changed while it was opened: {name}"
                    )
                identity = (opened.st_dev, opened.st_ino)
                if identity in identities:
                    raise PortfolioReleaseError("release assets must not alias one inode")
                identities.add(identity)
                destination = snapshot / name
                copied = 0
                with destination.open("xb") as target:
                    while True:
                        chunk = os.read(source_fd, 1024 * 1024)
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > caps[name]:
                            raise PortfolioReleaseError(
                                f"release asset grew beyond its limit: {name}"
                            )
                        target.write(chunk)
                destination.chmod(0o600)
                after_copy = os.fstat(source_fd)
                if (
                    copied != opened.st_size
                    or _stable_stat_identity(after_copy)
                    != _stable_stat_identity(opened)
                ):
                    raise PortfolioReleaseError(
                        f"release asset changed while it was copied: {name}"
                    )
                sealed_file_identities[name] = _stable_stat_identity(after_copy)
            sealed_directory_status = os.fstat(directory_fd)
            if (
                set(os.listdir(directory_fd)) != expected
                or _stable_stat_identity(sealed_directory_status)
                != _stable_stat_identity(initial_directory_status)
            ):
                raise PortfolioReleaseError("release directory changed while it was copied")
            try:
                yield snapshot
            except BaseException:
                raise
            else:
                if set(os.listdir(directory_fd)) != expected:
                    raise PortfolioReleaseError("release file set changed during verification")
                if (
                    _stable_stat_identity(os.fstat(directory_fd))
                    != _stable_stat_identity(sealed_directory_status)
                ):
                    raise PortfolioReleaseError("release directory changed during verification")
                try:
                    current_root = os.stat(root, follow_symlinks=False)
                except OSError as error:
                    raise PortfolioReleaseError(
                        "release directory changed during verification"
                    ) from error
                if (current_root.st_dev, current_root.st_ino) != (
                    sealed_directory_status.st_dev,
                    sealed_directory_status.st_ino,
                ):
                    raise PortfolioReleaseError("release directory was replaced during verification")
                for name, source_fd in source_fds.items():
                    current_fd = os.fstat(source_fd)
                    try:
                        current_path = os.stat(
                            name, dir_fd=directory_fd, follow_symlinks=False
                        )
                    except OSError as error:
                        raise PortfolioReleaseError(
                            f"release asset changed during verification: {name}"
                        ) from error
                    if (
                        _stable_stat_identity(current_fd)
                        != _stable_stat_identity(current_path)
                        or _stable_stat_identity(current_fd)
                        != sealed_file_identities[name]
                    ):
                        raise PortfolioReleaseError(
                            f"release asset changed during verification: {name}"
                        )
    finally:
        for source_fd in source_fds.values():
            os.close(source_fd)
        os.close(directory_fd)


def verify_release(directory: Path, ffprobe: Path | None = None) -> dict[str, Any]:
    with _release_snapshot(directory) as snapshot:
        return _verify_release_snapshot(snapshot, ffprobe=ffprobe)


def _verify_release_snapshot(
    directory: Path, ffprobe: Path | None = None
) -> dict[str, Any]:
    root = directory.resolve(strict=True)
    observed = {entry.name for entry in root.iterdir()}
    identity_candidates = [name for name in observed if re.fullmatch(r"corelm-portfolio-v[1-9][0-9]*-source-identity\.json", name)]
    if len(identity_candidates) != 1:
        raise PortfolioReleaseError("release must contain exactly one portfolio source identity")
    tag = identity_candidates[0][: -len("-source-identity.json")]
    expected = set(asset_names(tag))
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise PortfolioReleaseError(f"release file set is not exact; missing={missing}, extra={extra}")
    caps = asset_size_caps(tag)
    identities: set[tuple[int, int]] = set()
    for name in asset_names(tag):
        status = _require_regular_file(root / name, caps[name])
        identity = (status.st_dev, status.st_ino)
        if identity in identities:
            raise PortfolioReleaseError("release assets must not alias one inode")
        identities.add(identity)
    public_key = root / "corelm-portfolio-signing.pub"
    allowed_signers = root / "allowed_signers"
    _validate_trust(public_key, allowed_signers)
    checksums = _parse_checksums(root / "SHA256SUMS")
    if tuple(checksums) != tuple(sorted(covered_asset_names(tag), key=lambda item: item.encode("ascii"))):
        raise PortfolioReleaseError("SHA256SUMS does not cover the exact twelve assets")
    _verify_detached_signature(root / "SHA256SUMS", root / "SHA256SUMS.sig", allowed_signers, public_key)
    with _checksum_bound_asset_snapshots(
        root, tag=tag, checksums=checksums, caps=caps
    ) as captured_archives:
        identity_path = root / f"{tag}-source-identity.json"
        identity = _read_canonical_json(identity_path)
        _validate_identity_bindings(identity, tag)
        _verify_detached_signature(
            identity_path,
            root / f"{tag}-source-identity.json.sig",
            allowed_signers,
            public_key,
        )
        provenance_path = root / f"{tag}-demo-provenance.json"
        runtime_path = root / f"{tag}-runtime-assets.json"
        video_path = root / f"{tag}-demo.mp4"
        poster_path = root / f"{tag}-demo-poster.png"
        evidence_name = f"{tag}-demo-evidence.tar.gz"
        evidence_path = root / evidence_name
        provenance = _validate_demo_provenance(
            provenance_path,
            tag=tag,
            commit=identity["source"]["commit"],
            tree=identity["source"]["tree"],
            video=video_path,
            poster=poster_path,
            evidence=evidence_path,
            captured_evidence_sha256=checksums[evidence_name],
        )
        runtime = _validate_runtime_assets(
            runtime_path,
            tag=tag,
            commit=identity["source"]["commit"],
            tree=identity["source"]["tree"],
            provenance=provenance,
            repository=None,
        )
        if identity["demo"] != {
            "evidence_sha256": provenance["evidence_sha256"],
            "result_sha256": provenance["result_sha256"],
            "synthetic_data": False,
            "video_sha256": provenance["video"]["sha256"],
            "workload_classification": "PUBLIC_VALIDATION_REGRESSION",
        }:
            raise PortfolioReleaseError("source identity and demo provenance differ")
        width, height = _png_dimensions(poster_path)
        if (width, height) != (
            provenance["poster"]["width"],
            provenance["poster"]["height"],
        ):
            raise PortfolioReleaseError("PNG dimensions differ from demo provenance")
        _validate_video(
            video_path,
            provenance,
            ffprobe,
            runtime,
            require_recorded_ffprobe=False,
        )
        _validate_evidence_archive(
            evidence_path,
            provenance=provenance,
            source=identity["source"],
            captured_source=captured_archives[evidence_name],
        )
        source_name = f"{tag}-source.tar.gz"
        source_archive = root / source_name
        source_capture = captured_archives[source_name]
        _validate_tar(
            source_archive,
            label="source archive",
            source_commit=identity["source"]["commit"],
            source_prefix="core-lm-benchmark/",
            reject_absolute_paths=False,
            captured_source=source_capture,
        )
        _validate_source_archive_tree(
            source_archive,
            identity["source"]["tree"],
            identity["source"]["commit"],
            captured_source=source_capture,
        )
        _validate_source_manifest_bindings(
            source_archive,
            runtime,
            identity["source"]["commit"],
            captured_source=source_capture,
        )
        _validate_sbom(root / f"{tag}-direct-dependencies.cdx.json", tag)
        reproduce_path = root / f"REPRODUCE-{tag}.md"
        expected_reproduce = reproduce_document(
            tag,
            identity["source"]["commit"],
            identity["source"]["tree"],
            identity["source"]["tag_object"],
        )
        if reproduce_path.read_bytes() != expected_reproduce:
            raise PortfolioReleaseError(
                "REPRODUCE document is not the exact generated contract"
            )
        archive_names = {
            f"{tag}-demo-evidence.tar.gz",
            f"{tag}-source.tar.gz",
        }
        for name in covered_asset_names(tag):
            if name in archive_names:
                continue
            with (root / name).open("rb") as source:
                _assert_public_stream(
                    source,
                    name,
                    reject_absolute_paths=True,
                    strict_credentials=True,
                )
        return {
            "status": "OFFLINE_ARTIFACT_PASS",
            "tag": tag,
            "commit": identity["source"]["commit"],
            "tree": identity["source"]["tree"],
            "asset_count": 14,
            "covered_asset_count": 12,
            "model_file_count": len(runtime["model"]["files"]),
            "ci_status": "SIGNED_OPERATOR_ASSERTION_REQUIRES_LIVE_API_RECHECK",
            "decoder_check": "CALLER_SIDE_FFPROBE_NOT_A_RELEASE_TRUST_ROOT",
        }


def build_release(
    *,
    repository: Path,
    lab_repository: Path,
    input_path: Path,
    output: Path,
    ffprobe: Path,
    ci_api_preflight_confirmed: bool,
) -> dict[str, Any]:
    if not ci_api_preflight_confirmed:
        raise PortfolioReleaseError(
            "release-time GitHub Actions API preflight was not acknowledged"
        )
    release_input = _read_canonical_json(input_path)
    _validate_schema(release_input, INPUT_SCHEMA, "release input")
    tag, _version = _exact_tag(release_input["tag"])
    _validate_ci_bindings(release_input)
    root = _require_builder_repository(repository)
    commit, tree = _validate_source(root, release_input)
    _validate_related_sources(lab_repository, release_input)
    _validate_citation(root, tag, release_input["release_date"])
    assets = _asset_paths(release_input)
    provenance = _validate_demo_provenance(
        assets["demo_provenance"],
        tag=tag,
        commit=commit,
        tree=tree,
        video=assets["demo_video"],
        poster=assets["demo_poster"],
        evidence=assets["demo_evidence"],
    )
    runtime = _validate_runtime_assets(
        assets["runtime_assets"],
        tag=tag,
        commit=commit,
        tree=tree,
        provenance=provenance,
        repository=root,
    )
    width, height = _png_dimensions(assets["demo_poster"])
    if (width, height) != (provenance["poster"]["width"], provenance["poster"]["height"]):
        raise PortfolioReleaseError("poster dimensions differ from provenance")
    _validate_video(
        assets["demo_video"],
        provenance,
        ffprobe,
        runtime,
        require_recorded_ffprobe=True,
    )
    _validate_evidence_archive(
        assets["demo_evidence"],
        provenance=provenance,
        source={"commit": commit, "tree": tree},
    )
    if not output.is_absolute():
        raise PortfolioReleaseError("output directory path must be absolute")
    if output.parent.is_symlink():
        raise PortfolioReleaseError("output parent must not be a symlink")
    parent = output.parent.resolve(strict=True)
    if output.parent != parent:
        raise PortfolioReleaseError("output parent must be normalized and contain no symlink")
    if output.exists() or output.is_symlink():
        raise PortfolioReleaseError("output directory must not already exist")
    if output.parent.resolve(strict=True) != parent:
        raise PortfolioReleaseError("output parent is ambiguous")
    public_key_source = root / "signing" / "corelm-codec-signing.pub"
    policy_source = root / "signing" / "allowed_signers"
    _validate_trust(public_key_source, policy_source)
    key = _private_key_from_environment(public_key_source)
    staging = Path(tempfile.mkdtemp(prefix=f".{tag}-", dir=parent))
    try:
        if staging.is_symlink():
            raise PortfolioReleaseError("temporary output directory is unsafe")
        copy_map = {
            assets["demo_video"]: staging / f"{tag}-demo.mp4",
            assets["demo_poster"]: staging / f"{tag}-demo-poster.png",
            assets["demo_provenance"]: staging / f"{tag}-demo-provenance.json",
            assets["demo_evidence"]: staging / f"{tag}-demo-evidence.tar.gz",
            assets["runtime_assets"]: staging / f"{tag}-runtime-assets.json",
            public_key_source: staging / "corelm-portfolio-signing.pub",
            policy_source: staging / "allowed_signers",
        }
        caps = asset_size_caps(tag)
        for source, destination in copy_map.items():
            _copy_regular(source, destination, caps[destination.name])
        _build_source_archive(root, commit, staging / f"{tag}-source.tar.gz")
        _build_sbom(root, staging / f"{tag}-direct-dependencies.cdx.json", tag)
        identity = _source_identity(release_input, provenance)
        identity_path = staging / f"{tag}-source-identity.json"
        identity_path.write_bytes(_canonical_json(identity))
        identity_path.chmod(0o644)
        reproduce_path = staging / f"REPRODUCE-{tag}.md"
        reproduce_path.write_bytes(
            reproduce_document(tag, commit, tree, release_input["source"]["tag_object"])
        )
        reproduce_path.chmod(0o644)
        for path in staging.iterdir():
            if path.suffix in {".json", ".md", ".pub"} or path.name == "allowed_signers":
                _assert_public_bytes(path.read_bytes(), path.name)
        _sign_file(
            identity_path,
            key,
            staging / "allowed_signers",
            staging / "corelm-portfolio-signing.pub",
        )
        _write_checksums(staging, tag)
        _sign_file(
            staging / "SHA256SUMS",
            key,
            staging / "allowed_signers",
            staging / "corelm-portfolio-signing.pub",
        )
        result = verify_release(staging, ffprobe=ffprobe)
        staging.rename(output)
        return result
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--input", type=Path, help="canonical release input JSON")
    mode.add_argument("--verify", type=Path, metavar="RELEASE_DIRECTORY")
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--cross-model-lab", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ffprobe", type=Path)
    parser.add_argument(
        "--ci-api-preflight-confirmed",
        action="store_true",
        help="acknowledge the mandatory same-commit GitHub Actions API preflight",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    try:
        if options.verify is not None:
            if options.input is not None or options.output is not None or options.cross_model_lab is not None or options.ci_api_preflight_confirmed:
                raise PortfolioReleaseError("build-only options are forbidden in verify mode")
            if options.ffprobe is None:
                raise PortfolioReleaseError("verify mode requires --ffprobe for a full PASS")
            result = verify_release(options.verify, ffprobe=options.ffprobe)
        else:
            if options.output is None or options.cross_model_lab is None or options.ffprobe is None:
                raise PortfolioReleaseError(
                    "build mode requires --output, --cross-model-lab, and --ffprobe"
                )
            result = build_release(
                repository=options.repository,
                lab_repository=options.cross_model_lab,
                input_path=options.input,
                output=options.output,
                ffprobe=options.ffprobe,
                ci_api_preflight_confirmed=options.ci_api_preflight_confirmed,
            )
    except (OSError, PortfolioReleaseError) as error:
        print(f"PORTFOLIO RELEASE FAIL: {error}", file=sys.stderr)
        return 2
    print(
        "PORTFOLIO RELEASE OFFLINE SIGNED-ARTIFACT PASS — "
        "CALLER-SIDE FFPROBE DECODER CHECK ONLY — LIVE CI API RECHECK REQUIRED: "
        f"{result['tag']} commit={result['commit']} tree={result['tree']} "
        f"assets={result['asset_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
