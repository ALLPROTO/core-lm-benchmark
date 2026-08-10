#!/usr/bin/env python3
"""Prepare and verify the bounded GitHub portfolio-release contract.

This tool is intentionally network-free.  ``verify-policy`` validates the
saved immutable-release policy before draft creation.  ``prepare-draft``
writes the exact JSON body for GitHub's create-release API.
``verify-empty-draft`` validates the saved empty draft before any upload.
``verify-draft`` validates the same authenticated draft after all fourteen
assets are uploaded, revalidates a fresh policy response, and emits the exact
publish PATCH body.  ``verify`` checks saved public API responses and the
exact fourteen downloaded assets, then writes a canonical receipt.  The tool
neither creates nor mutates a Git tag or GitHub release.

Draft gates require GitHub's ``immutable`` boolean to be false; the final
published gate requires it to be true.  Project preservation policy and
GitHub's platform-reported immutability remain deliberately separate facts.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]


def _require_isolated_product_python() -> None:
    """Reject a direct CLI before any checkout-local module can be imported."""

    prefix_value = sys.pycache_prefix
    if (
        sys.flags.isolated != 1
        or not sys.dont_write_bytecode
        or not isinstance(prefix_value, str)
        or not prefix_value
    ):
        raise SystemExit("portfolio tools require a tracked isolated Python launcher")
    prefix = Path(prefix_value)
    if not prefix.is_absolute():
        raise SystemExit("portfolio Python cache prefix must be absolute")
    try:
        resolved = prefix.resolve(strict=True)
    except OSError as error:
        raise SystemExit("portfolio Python cache prefix is unavailable") from error
    if resolved != prefix or resolved == ROOT or ROOT in resolved.parents:
        raise SystemExit(
            "portfolio Python cache prefix must be canonical and outside the checkout"
        )
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError as error:
        raise SystemExit("portfolio Python cache prefix is unsafe") from error
    try:
        status = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(status.st_mode)
            or status.st_uid != os.getuid()
            or stat.S_IMODE(status.st_mode) != 0o700
            or os.listdir(descriptor)
        ):
            raise SystemExit(
                "portfolio Python cache prefix must be an empty owner-only directory"
            )
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    _require_isolated_product_python()

sys.path[:] = [entry for entry in sys.path if entry != str(ROOT)]
sys.path.insert(0, str(ROOT))

from publication.build_portfolio_release import (  # noqa: E402
    CANONICAL_REPOSITORY,
    CI_VALIDATION_SCOPE,
    GIT_OBJECT_RE,
    PortfolioReleaseError,
    SHA256_RE,
    _canonical_json,
    _exact_tag,
    _read_canonical_json,
    _release_snapshot,
    asset_names,
    asset_size_caps,
    verify_release,
)
from security import automated_media  # noqa: E402


REPOSITORY_SLUG = "ALLPROTO/core-lm-benchmark"
CREATE_RELEASE_ENDPOINT = f"https://api.github.com/repos/{REPOSITORY_SLUG}/releases"
IMMUTABLE_RELEASES_ENDPOINT = (
    f"https://api.github.com/repos/{REPOSITORY_SLUG}/immutable-releases"
)
UPDATE_RELEASE_ENDPOINT_PREFIX = CREATE_RELEASE_ENDPOINT + "/"
UPLOAD_RELEASE_ENDPOINT_PREFIX = (
    f"https://uploads.github.com/repos/{REPOSITORY_SLUG}/releases/"
)
PROJECT_PRESERVATION_POLICY = "TAG_AND_ASSETS_MUST_NOT_BE_MOVED_OR_REPLACED"
IMMUTABILITY_SCOPE = (
    "GITHUB_DRAFT_FALSE_AND_PUBLISHED_TRUE_REQUIRED_SEPARATE_FROM_PROJECT_POLICY"
)
API_TIMESTAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
DRAFT_DOWNLOAD_SLUG_RE = re.compile(r"^untagged-[0-9a-f]{20}$")
IDENTITY_NAME_RE = re.compile(
    r"^(corelm-portfolio-v[1-9][0-9]*)-source-identity\.json$"
)
MAX_API_BYTES = 32 * 1024 * 1024
EXACT_SUCCESSOR_PATHS = (
    "README.md",
    "docs/media/corelm-result.png",
)
PRESENTATION_MARKER_START = "<!-- corelm-portfolio-presentation-v1:start -->"
PRESENTATION_MARKER_END = "<!-- corelm-portfolio-presentation-v1:end -->"
MAX_GIT_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_SUCCESSOR_TRACKED_BYTES = 1024 * 1024 * 1024


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PortfolioReleaseError(f"{label} must be a JSON object")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PortfolioReleaseError(f"{label} must be a nonempty string")
    return value


def _git_object(value: Any, label: str) -> str:
    if not isinstance(value, str) or GIT_OBJECT_RE.fullmatch(value) is None:
        raise PortfolioReleaseError(f"{label} must be lowercase 40-hex")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise PortfolioReleaseError(f"{label} must be lowercase SHA-256")
    return value


def _absolute(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise PortfolioReleaseError(f"{label} must be an absolute path")
    return path


def _stable_read(
    path: Path, maximum_bytes: int, *, capture: bool
) -> tuple[int, str, bytes | None]:
    """Read once through one no-follow FD and return a stable byte identity."""

    try:
        before = path.lstat()
    except OSError as error:
        raise PortfolioReleaseError(f"required file is unavailable: {path.name}") from error
    if not stat.S_ISREG(before.st_mode):
        raise PortfolioReleaseError(f"file must be regular and not a symlink: {path.name}")
    if before.st_nlink != 1:
        raise PortfolioReleaseError(f"file must not be hard-linked: {path.name}")
    if before.st_size <= 0 or before.st_size > maximum_bytes:
        raise PortfolioReleaseError(f"file size is outside its contract: {path.name}")

    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise PortfolioReleaseError(f"file cannot be opened safely: {path.name}") from error
    digest = hashlib.sha256()
    chunks: list[bytes] | None = [] if capture else None
    try:
        opened = os.fstat(descriptor)
        identity = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        observed = (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_nlink,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        )
        if observed != identity:
            raise PortfolioReleaseError(f"file changed before reading: {path.name}")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            if chunks is not None:
                chunks.append(chunk)
        after = os.fstat(descriptor)
        final = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if final != identity:
            raise PortfolioReleaseError(f"file changed while reading: {path.name}")
    finally:
        os.close(descriptor)
    return (
        before.st_size,
        digest.hexdigest(),
        b"".join(chunks) if chunks is not None else None,
    )


def _stable_file(path: Path, maximum_bytes: int) -> tuple[int, str]:
    size, digest, _data = _stable_read(path, maximum_bytes, capture=False)
    return size, digest


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, nested in pairs:
        if key in value:
            raise PortfolioReleaseError(f"duplicate JSON key: {key}")
        value[key] = nested
    return value


def _reject_json_constant(value: str) -> None:
    raise PortfolioReleaseError(f"non-finite JSON number is forbidden: {value}")


def _single_fd_json(path: Path, label: str) -> tuple[Any, str]:
    source = _absolute(path, label)
    _size, digest, data = _stable_read(source, MAX_API_BYTES, capture=True)
    assert data is not None
    if data.startswith(b"\xef\xbb\xbf"):
        raise PortfolioReleaseError(f"{label} must not have a BOM")
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PortfolioReleaseError(f"{label} is invalid JSON") from error
    return value, digest


def _identity(directory: Path) -> tuple[str, Mapping[str, Any]]:
    matches = []
    try:
        entries = list(directory.iterdir())
    except OSError as error:
        raise PortfolioReleaseError("asset directory cannot be enumerated") from error
    for entry in entries:
        match = IDENTITY_NAME_RE.fullmatch(entry.name)
        if match is not None:
            matches.append((match.group(1), entry))
    if len(matches) != 1:
        raise PortfolioReleaseError("assets must contain exactly one portfolio source identity")
    tag, path = matches[0]
    _exact, version = _exact_tag(tag)
    value = _mapping(_read_canonical_json(path), "source identity")
    if (
        version < 3
        or value.get("schema_version") != 2
        or value.get("artifact_kind") != "corelm_portfolio_release"
    ):
        raise PortfolioReleaseError("source identity artifact kind is not portfolio release")

    release = _mapping(value.get("release"), "source identity release")
    if release.get("tag") != tag or release.get("prerelease") is not False:
        raise PortfolioReleaseError("source identity release fields are inconsistent")
    if release.get("url") != f"{CANONICAL_REPOSITORY}/releases/tag/{tag}":
        raise PortfolioReleaseError("source identity release URL is inconsistent")
    if release.get("scientific_status") != "NOT_A_BLIND_OR_GENERALIZATION_RESULT":
        raise PortfolioReleaseError("source identity scientific status is inconsistent")

    source = _mapping(value.get("source"), "source identity source")
    if source.get("repository") != CANONICAL_REPOSITORY:
        raise PortfolioReleaseError("source identity repository is not canonical")
    if source.get("default_branch") != "main" or source.get("worktree_state") != "clean":
        raise PortfolioReleaseError("source identity branch/worktree state is inconsistent")
    _git_object(source.get("commit"), "source commit")
    _git_object(source.get("tree"), "source tree")
    _git_object(source.get("tag_object"), "source tag object")

    claims = _mapping(value.get("claims"), "source identity claims")
    if claims.get("supported") != (
        "Built and reproducibly evaluated complete-container KV-cache compression "
        "on pinned real-model workloads."
    ):
        raise PortfolioReleaseError("source identity supported claim is not exact")
    excluded = claims.get("excluded")
    if not isinstance(excluded, list) or "independent_human_replication" not in excluded:
        raise PortfolioReleaseError("source identity exclusions are incomplete")

    continuous = _mapping(
        value.get("continuous_integration"), "source identity continuous integration"
    )
    if continuous.get("commit") != source["commit"]:
        raise PortfolioReleaseError("source identity CI is not bound to the source commit")
    if continuous.get("validation") != CI_VALIDATION_SCOPE:
        raise PortfolioReleaseError("source identity CI scope is overstated")
    for platform in ("linux_x86_64", "macos_arm64"):
        run = _mapping(continuous.get(platform), f"source identity {platform} CI")
        if run.get("conclusion") != "success" or run.get("required") is not True:
            raise PortfolioReleaseError(f"source identity {platform} CI is not successful")
        url = _string(run.get("url"), f"source identity {platform} CI URL")
        if re.fullmatch(
            r"https://github\.com/ALLPROTO/core-lm-benchmark/actions/runs/[1-9][0-9]*",
            url,
        ) is None:
            raise PortfolioReleaseError(f"source identity {platform} CI URL is not canonical")

    demo = _mapping(value.get("demo"), "source identity demo")
    for key in (
        "video_sha256",
        "evidence_sha256",
        "result_sha256",
        "provenance_sha256",
    ):
        _digest(demo.get(key), f"source identity demo {key}")
    if demo.get("synthetic_data") is not False:
        raise PortfolioReleaseError("source identity demo must be non-synthetic")
    if (
        demo.get("workload_classification")
        != "AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION"
    ):
        raise PortfolioReleaseError("source identity demo classification is inconsistent")
    if {
        "media_classification": demo.get("media_classification"),
        "automation_contract": demo.get("automation_contract"),
        "automation_only": demo.get("automation_only"),
        "human_reviewed": demo.get("human_reviewed"),
        "manual_edits": demo.get("manual_edits"),
        "machine_evidence": demo.get("machine_evidence"),
        "pixel_semantics_verified": demo.get("pixel_semantics_verified"),
    } != {
        "media_classification": automated_media.MEDIA_CLASSIFICATION,
        "automation_contract": automated_media.AUTOMATION_CONTRACT,
        "automation_only": True,
        "human_reviewed": False,
        "manual_edits": False,
        "machine_evidence": False,
        "pixel_semantics_verified": False,
    }:
        raise PortfolioReleaseError("source identity automated presentation boundary is inconsistent")

    related = _mapping(value.get("related_sources"), "source identity related sources")
    blind = _mapping(related.get("blind_v1_draft"), "source identity Blind V1")
    if blind.get("lifecycle_state") != "CHECKPOINT_MISSED_TERMINAL_DRAFT":
        raise PortfolioReleaseError("Blind V1 lifecycle is not terminal draft")
    return tag, value


def _asset_records(directory: Path) -> tuple[str, Mapping[str, Any], list[dict[str, Any]]]:
    root = _absolute(directory, "asset directory")
    try:
        status = root.lstat()
    except OSError as error:
        raise PortfolioReleaseError("asset directory is unavailable") from error
    if not stat.S_ISDIR(status.st_mode):
        raise PortfolioReleaseError("asset directory must be a directory and not a symlink")
    tag, identity = _identity(root)
    expected = set(asset_names(tag))
    try:
        observed = {entry.name for entry in root.iterdir()}
    except OSError as error:
        raise PortfolioReleaseError("asset directory cannot be enumerated") from error
    if observed != expected:
        raise PortfolioReleaseError(
            f"release file set is not exact; missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )

    caps = asset_size_caps(tag)
    inodes: set[tuple[int, int]] = set()
    records: list[dict[str, Any]] = []
    for name in sorted(expected, key=lambda item: item.encode("utf-8")):
        path = root / name
        status = path.lstat()
        inode = (status.st_dev, status.st_ino)
        if inode in inodes:
            raise PortfolioReleaseError("release assets must not alias one inode")
        inodes.add(inode)
        size, digest = _stable_file(path, caps[name])
        records.append({"name": name, "sha256": digest, "size_bytes": size})

    identity_record = next(
        record for record in records if record["name"] == f"{tag}-source-identity.json"
    )
    if _canonical_json(identity) != (root / identity_record["name"]).read_bytes():
        raise PortfolioReleaseError("source identity changed during asset inspection")
    return tag, identity, records


def _ffprobe_identity(path: Path) -> tuple[Path, dict[str, str]]:
    candidate = _absolute(path, "ffprobe")
    try:
        executable = candidate.resolve(strict=True)
    except OSError as error:
        raise PortfolioReleaseError("ffprobe is unavailable") from error
    if not os.access(executable, os.X_OK):
        raise PortfolioReleaseError("ffprobe must be executable")
    _size, digest = _stable_file(executable, 128 * 1024 * 1024)
    try:
        completed = subprocess.run(
            (str(executable), "-version"),
            cwd=executable.parent,
            env={
                "HOME": "/nonexistent",
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise PortfolioReleaseError("ffprobe version query failed") from error
    try:
        lines = completed.stdout.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise PortfolioReleaseError("ffprobe version is not UTF-8") from error
    if (
        completed.returncode != 0
        or not lines
        or not lines[0].startswith("ffprobe version ")
        or len(lines[0].encode("utf-8")) > 1024
    ):
        raise PortfolioReleaseError("ffprobe version identity is malformed")
    return executable, {"executable_sha256": digest, "version": lines[0]}


@contextmanager
def _verified_asset_snapshot(
    directory: Path, ffprobe: Path
) -> Iterator[tuple[Path, str, Mapping[str, Any], list[dict[str, Any]], dict[str, str]]]:
    root = _absolute(directory, "asset directory")
    decoder, decoder_identity = _ffprobe_identity(ffprobe)
    with _release_snapshot(root) as snapshot:
        artifact = verify_release(snapshot, ffprobe=decoder)
        decoder_after, decoder_identity_after = _ffprobe_identity(decoder)
        if decoder_after != decoder or decoder_identity_after != decoder_identity:
            raise PortfolioReleaseError("caller-side ffprobe identity changed during verification")
        artifact = _mapping(artifact, "offline signed-artifact verifier result")
        tag, identity, records = _asset_records(snapshot)
        source = _mapping(identity.get("source"), "source identity source")
        expected_artifact = {
            "status": "OFFLINE_ARTIFACT_PASS",
            "tag": tag,
            "commit": source["commit"],
            "tree": source["tree"],
            "asset_count": 14,
        }
        for key, expected in expected_artifact.items():
            if artifact.get(key) != expected:
                raise PortfolioReleaseError(
                    f"offline signed-artifact verifier did not bind {key}"
                )
        yield snapshot, tag, identity, records, decoder_identity


def release_title(tag: str) -> str:
    exact, version = _exact_tag(tag)
    if exact != tag:
        raise PortfolioReleaseError("portfolio tag is not exact")
    return (
        f"Core LM Portfolio v{version} — reproducible real-model "
        "KV-cache benchmark"
    )


def release_body(identity: Mapping[str, Any], sha256sums_sha256: str) -> str:
    release = _mapping(identity.get("release"), "source identity release")
    tag = _string(release.get("tag"), "source identity tag")
    title = release_title(tag)
    source = _mapping(identity.get("source"), "source identity source")
    claims = _mapping(identity.get("claims"), "source identity claims")
    continuous = _mapping(
        identity.get("continuous_integration"), "source identity continuous integration"
    )
    demo = _mapping(identity.get("demo"), "source identity demo")
    checksum = _digest(sha256sums_sha256, "SHA256SUMS digest")
    return "\n".join(
        (
            f"# {title}",
            "",
            "Stable engineering release for complete-container KV-cache compression "
            "on pinned real-model workloads.",
            "",
            f"Supported engineering claim: {claims['supported']}",
            "",
            "Scientific status: `NOT_A_BLIND_OR_GENERALIZATION_RESULT`.",
            "Blind V1 remains `CHECKPOINT_MISSED_TERMINAL_DRAFT` and was not run.",
            "Independent human replication is not claimed by this release.",
            "Presentation classification: "
            f"`{automated_media.MEDIA_CLASSIFICATION}`.",
            "The single-window media was accepted by automated checks only; signed "
            "result/evidence files, not pixels, support the metrics. Semantic pixel "
            "privacy and independent review are not claimed.",
            "",
            f"Source commit: `{source['commit']}`",
            f"Source tree: `{source['tree']}`",
            f"Annotated tag object: `{source['tag_object']}`",
            f"Linux x86-64 CI: {continuous['linux_x86_64']['url']}",
            f"macOS arm64 CI: {continuous['macos_arm64']['url']}",
            f"Demo video SHA-256: `{demo['video_sha256']}`",
            f"Demo evidence SHA-256: `{demo['evidence_sha256']}`",
            f"Demo result SHA-256: `{demo['result_sha256']}`",
            f"SHA256SUMS SHA-256: `{checksum}`",
            "",
            "Download exactly all 14 attached assets and follow "
            f"`REPRODUCE-{tag}.md`. `SHA256SUMS` covers the twelve payload assets; "
            "its signature and the source-identity signature verify under the "
            "attached public key and `allowed_signers`.",
            "",
            "Public media verification uses a caller-selected `ffprobe` as a decoder "
            "check. Its observed identity belongs to that verification invocation and "
            "is not a release trust root.",
            "",
            "Project preservation policy: this tag and its uploaded assets will not be "
            "moved, replaced, or rewritten. This policy is not a claim that GitHub "
            "reports the release as immutable. Check the live GitHub API `immutable` "
            "field separately.",
        )
    )


def expected_create_request(
    identity: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    tag = _string(_mapping(identity.get("release"), "release").get("tag"), "tag")
    sums = next((record for record in records if record.get("name") == "SHA256SUMS"), None)
    if sums is None:
        raise PortfolioReleaseError("SHA256SUMS is absent from the asset records")
    return {
        "body": release_body(identity, _digest(sums.get("sha256"), "SHA256SUMS digest")),
        "draft": True,
        "make_latest": "false",
        "name": release_title(tag),
        "prerelease": False,
        "tag_name": tag,
        "target_commitish": "main",
    }


def expected_publish_request(
    identity: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    request = expected_create_request(identity, records)
    return {
        "body": request["body"],
        "draft": False,
        "make_latest": "true",
        "name": request["name"],
        "prerelease": False,
        "tag_name": request["tag_name"],
        "target_commitish": request["target_commitish"],
    }


def _validate_publish_request(
    value: Any,
    *,
    identity: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    request = _mapping(value, "publish PATCH request")
    expected = expected_publish_request(identity, records)
    if set(request) != set(expected) or request != expected:
        raise PortfolioReleaseError("publish PATCH request is not exact")
    return dict(request)


def _immutable_release_policy(value: Any) -> dict[str, bool]:
    policy = _mapping(value, "GitHub immutable-releases policy response")
    enabled = policy.get("enabled")
    enforced_by_owner = policy.get("enforced_by_owner")
    if (
        set(policy) != {"enabled", "enforced_by_owner"}
        or type(enabled) is not bool
        or type(enforced_by_owner) is not bool
        or enabled is not True
    ):
        raise PortfolioReleaseError(
            "GitHub immutable-releases policy response must contain exact boolean "
            "enabled:true and enforced_by_owner"
        )
    return {
        "enabled": enabled,
        "enforced_by_owner": enforced_by_owner,
    }


def _release_id(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise PortfolioReleaseError(f"{label} must be a positive integer")
    return value


def publish_release_endpoint(release_id: int) -> str:
    exact = _release_id(release_id, "GitHub release id")
    return f"{UPDATE_RELEASE_ENDPOINT_PREFIX}{exact}"


def _expected_upload_url(release_id: int) -> str:
    exact = _release_id(release_id, "GitHub release id")
    return (
        f"{UPLOAD_RELEASE_ENDPOINT_PREFIX}{exact}/assets"
        "{?name,label}"
    )


def _api_assets(
    value: Any,
    *,
    records: Sequence[Mapping[str, Any]],
    download_ref: str,
    label: str,
) -> tuple[tuple[str, int], ...]:
    observed_assets = value
    if not isinstance(observed_assets, list):
        raise PortfolioReleaseError(f"{label} assets must be an array")
    expected_by_name = {record["name"]: record for record in records}
    if len(expected_by_name) != len(records):
        raise PortfolioReleaseError("local release asset records are duplicated")
    seen: set[str] = set()
    asset_ids: set[int] = set()
    for asset_value in observed_assets:
        asset = _mapping(asset_value, f"{label} asset")
        asset_id = _release_id(asset.get("id"), f"{label} asset id")
        if asset_id in asset_ids:
            raise PortfolioReleaseError(f"duplicate {label} asset id")
        asset_ids.add(asset_id)
        name = _string(asset.get("name"), f"{label} asset name")
        if name in seen:
            raise PortfolioReleaseError(f"duplicate {label} asset: {name}")
        seen.add(name)
        expected = expected_by_name.get(name)
        if expected is None:
            raise PortfolioReleaseError(f"unexpected {label} asset: {name}")
        if asset.get("state") != "uploaded":
            raise PortfolioReleaseError(f"{label} asset is not uploaded: {name}")
        if type(asset.get("size")) is not int or asset["size"] != expected["size_bytes"]:
            raise PortfolioReleaseError(f"{label} asset size differs: {name}")
        expected_url = (
            f"{CANONICAL_REPOSITORY}/releases/download/{download_ref}/{name}"
        )
        if asset.get("browser_download_url") != expected_url:
            raise PortfolioReleaseError(f"{label} asset URL differs: {name}")
        if asset.get("digest") != f"sha256:{expected['sha256']}":
            raise PortfolioReleaseError(f"{label} asset digest differs: {name}")
    if seen != set(expected_by_name):
        missing = sorted(set(expected_by_name) - seen)
        raise PortfolioReleaseError(
            f"{label} asset set is incomplete; missing={missing}"
        )
    return tuple(
        sorted(
            (
                (_string(asset["name"], f"{label} asset name"), asset["id"])
                for asset in observed_assets
            ),
            key=lambda item: item[0].encode("utf-8"),
        )
    )


def _draft_download_slug(release: Mapping[str, Any], label: str) -> str:
    html_url = _string(release.get("html_url"), f"{label} html_url")
    prefix = f"{CANONICAL_REPOSITORY}/releases/tag/"
    if not html_url.startswith(prefix):
        raise PortfolioReleaseError(f"{label} html_url is not exact")
    slug = html_url[len(prefix) :]
    if (
        DRAFT_DOWNLOAD_SLUG_RE.fullmatch(slug) is None
        or html_url != f"{prefix}{slug}"
    ):
        raise PortfolioReleaseError(f"{label} html_url is not an exact draft URL")
    return slug


def _draft_release(
    value: Any,
    *,
    request: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]] | None,
    label: str,
    expected_release_id: int | None = None,
) -> dict[str, Any]:
    release = _mapping(value, label)
    expected_scalars = {
        "tag_name": request["tag_name"],
        "target_commitish": request["target_commitish"],
        "name": request["name"],
        "body": request["body"],
        "draft": True,
        "prerelease": False,
    }
    for key, expected in expected_scalars.items():
        if release.get(key) != expected:
            raise PortfolioReleaseError(f"{label} {key} is not exact")
    release_id = _release_id(release.get("id"), f"{label} id")
    if expected_release_id is not None and release_id != expected_release_id:
        raise PortfolioReleaseError(f"{label} release id differs from create response")
    if release.get("immutable") is not False:
        raise PortfolioReleaseError(f"{label} must report immutable false")
    if release.get("published_at") is not None:
        raise PortfolioReleaseError(f"{label} published_at must be null")
    upload_url = _expected_upload_url(release_id)
    release_url = publish_release_endpoint(release_id)
    assets_url = f"{release_url}/assets"
    if release.get("url") != release_url:
        raise PortfolioReleaseError(f"{label} url is not exact")
    if release.get("assets_url") != assets_url:
        raise PortfolioReleaseError(f"{label} assets_url is not exact")
    if release.get("upload_url") != upload_url:
        raise PortfolioReleaseError(f"{label} upload_url is not exact")
    download_slug = _draft_download_slug(release, label)
    if records is None:
        if release.get("assets") != []:
            raise PortfolioReleaseError("GitHub create response assets must be empty")
    else:
        _api_assets(
            release.get("assets"),
            records=records,
            download_ref=download_slug,
            label=label,
        )
    return {
        "assets_url": assets_url,
        "download_slug": download_slug,
        "id": release_id,
        "html_url": f"{CANONICAL_REPOSITORY}/releases/tag/{download_slug}",
        "release_url": release_url,
        "upload_url": upload_url,
    }


def _api_release(
    value: Any,
    *,
    request: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    release = _mapping(value, "GitHub release response")
    expected_scalars = {
        "tag_name": request["tag_name"],
        "target_commitish": request["target_commitish"],
        "name": request["name"],
        "body": request["body"],
        "draft": False,
        "prerelease": False,
        "html_url": f"{CANONICAL_REPOSITORY}/releases/tag/{request['tag_name']}",
    }
    for key, expected in expected_scalars.items():
        if release.get(key) != expected:
            raise PortfolioReleaseError(f"GitHub release {key} is not exact")
    release_id = _release_id(release.get("id"), "GitHub release id")
    published_at = release.get("published_at")
    if not isinstance(published_at, str) or API_TIMESTAMP_RE.fullmatch(published_at) is None:
        raise PortfolioReleaseError("GitHub release published_at is not exact UTC seconds")
    immutable = release.get("immutable")
    if immutable is not True:
        raise PortfolioReleaseError("GitHub published release must report immutable true")
    release_url = publish_release_endpoint(release_id)
    if release.get("url") != release_url:
        raise PortfolioReleaseError("GitHub release url is not exact")
    if release.get("assets_url") != f"{release_url}/assets":
        raise PortfolioReleaseError("GitHub release assets_url is not exact")

    asset_ids = _api_assets(
        release.get("assets"),
        records=records,
        download_ref=request["tag_name"],
        label="GitHub release",
    )
    return {
        "asset_ids": asset_ids,
        "id": release_id,
        "immutable": immutable,
        "published_at": published_at,
    }


def _tag_ref(value: Any, tag: str, tag_object: str) -> None:
    reference = _mapping(value, "GitHub tag-ref response")
    if reference.get("ref") != f"refs/tags/{tag}":
        raise PortfolioReleaseError("GitHub tag ref name is not exact")
    target = _mapping(reference.get("object"), "GitHub tag-ref object")
    if target.get("type") != "tag" or target.get("sha") != tag_object:
        raise PortfolioReleaseError("GitHub tag ref is not the signed annotated tag object")


def _verify_git_payload_signature(
    verification_value: Any, snapshot: Path, label: str
) -> dict[str, Any]:
    verification = _mapping(verification_value, f"{label} API verification")
    verified = verification.get("verified")
    if type(verified) is not bool:
        raise PortfolioReleaseError(f"{label} API verified field is not boolean")
    reason = verification.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise PortfolioReleaseError(f"{label} API verification reason is malformed")
    payload = _string(verification.get("payload"), f"{label} signed payload")
    signature = _string(verification.get("signature"), f"{label} SSH signature")
    try:
        payload_bytes = payload.encode("utf-8")
        signature_bytes = signature.encode("ascii")
    except UnicodeEncodeError as error:
        raise PortfolioReleaseError(f"{label} signature payload encoding is invalid") from error
    if (
        payload.count("\x00")
        or len(payload_bytes) > 4 * 1024 * 1024
        or signature.count("-----BEGIN SSH SIGNATURE-----") != 1
        or signature.count("-----END SSH SIGNATURE-----") != 1
        or len(signature_bytes) > 64 * 1024
    ):
        raise PortfolioReleaseError(f"{label} SSH signature payload is malformed")
    allowed_signers = snapshot / "allowed_signers"
    try:
        principal = allowed_signers.read_text(encoding="ascii").split()[0]
    except (OSError, UnicodeDecodeError, IndexError) as error:
        raise PortfolioReleaseError("allowed_signers cannot verify Git payload") from error
    with tempfile.TemporaryDirectory(prefix="corelm-github-git-signature-") as temporary:
        signature_path = Path(temporary) / "signature.ssh"
        signature_path.write_bytes(signature_bytes)
        signature_path.chmod(0o600)
        try:
            completed = subprocess.run(
                (
                    "/usr/bin/ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    str(allowed_signers),
                    "-I",
                    principal,
                    "-n",
                    "git",
                    "-s",
                    str(signature_path),
                ),
                cwd=snapshot,
                env={
                    "HOME": "/nonexistent",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                },
                input=payload_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise PortfolioReleaseError(f"{label} SSH verification failed") from error
    if completed.returncode != 0:
        raise PortfolioReleaseError(f"{label} SSH verification failed")
    return {
        "api_reason": reason,
        "api_verified": verified,
        "cryptographic_verification": "SSH_GIT_NAMESPACE_PASS",
        "scope": "API_VERDICT_INFORMATIONAL_LOCAL_SSH_VERIFICATION_REQUIRED",
    }


def _tag_object(
    value: Any, tag: str, tag_object: str, commit: str, snapshot: Path
) -> dict[str, Any]:
    annotation = _mapping(value, "GitHub annotated-tag response")
    if annotation.get("sha") != tag_object or annotation.get("tag") != tag:
        raise PortfolioReleaseError("GitHub annotated tag identity is not exact")
    target = _mapping(annotation.get("object"), "GitHub annotated-tag target")
    if target.get("type") != "commit" or target.get("sha") != commit:
        raise PortfolioReleaseError("GitHub annotated tag does not target the source commit")
    verification = _mapping(
        annotation.get("verification"), "GitHub annotated-tag verification"
    )
    payload = _string(verification.get("payload"), "annotated-tag signed payload")
    header = payload.split("\n\n", 1)[0].splitlines()
    if (
        len(header) != 4
        or header[:3] != [f"object {commit}", "type commit", f"tag {tag}"]
        or not header[3].startswith("tagger ")
    ):
        raise PortfolioReleaseError("annotated-tag signed payload header is not exact")
    return _verify_git_payload_signature(verification, snapshot, "annotated tag")


def _commit_object(value: Any, commit: str, tree: str) -> dict[str, Any]:
    document = _mapping(value, "GitHub commit-object response")
    if document.get("sha") != commit:
        raise PortfolioReleaseError("GitHub commit-object SHA is not the source commit")
    observed_tree = _mapping(document.get("tree"), "GitHub commit-object tree")
    if observed_tree.get("sha") != tree:
        raise PortfolioReleaseError("GitHub source commit does not bind the signed source tree")
    verification = document.get("verification")
    if verification is None:
        return {"present": False, "scope": "INFORMATIONAL_NOT_A_TRUST_ROOT"}
    verification = _mapping(verification, "GitHub commit-object verification")
    verified = verification.get("verified")
    if type(verified) is not bool:
        raise PortfolioReleaseError("GitHub commit-object verified field is not boolean")
    reason = verification.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise PortfolioReleaseError("GitHub commit-object verification reason is malformed")
    return {
        "api_reason": reason,
        "api_verified": verified,
        "scope": "INFORMATIONAL_NOT_A_TRUST_ROOT",
    }


def _snapshot(path: Path, label: str) -> tuple[Any, str]:
    return _single_fd_json(path, label)


def verify_immutable_policy_response(
    *, immutable_policy_json: Path
) -> dict[str, Any]:
    value, digest = _snapshot(
        immutable_policy_json, "precreate immutable-policy JSON"
    )
    policy = _immutable_release_policy(value)
    return {
        "api_snapshot": {
            "kind": "immutable_policy_precreate",
            "sha256": digest,
        },
        "artifact_kind": "corelm_portfolio_github_immutable_policy_receipt",
        "github_immutable_releases_policy": {
            "enabled": policy["enabled"],
            "enforced_by_owner": policy["enforced_by_owner"],
            "endpoint": IMMUTABLE_RELEASES_ENDPOINT,
        },
        "repository": CANONICAL_REPOSITORY,
        "schema_version": 2,
        "status": "PRECREATE_IMMUTABLE_POLICY_BOUNDARY_PASS",
        "verification_scope": {
            "api_transport_authentication": (
                "CALLER_MUST_RETAIN_AUTHENTICATED_POLICY_RESPONSE"
            ),
            "network": "NOT_PERFORMED_BY_VERIFIER",
        },
    }


def verify_empty_draft_response(
    *,
    assets: Path,
    ffprobe: Path,
    create_response_json: Path,
) -> dict[str, Any]:
    with _verified_asset_snapshot(assets, ffprobe) as (
        _snapshot_directory,
        tag,
        identity,
        records,
        decoder_identity,
    ):
        request = expected_create_request(identity, records)
        publish_request = expected_publish_request(identity, records)
        create_value, create_sha256 = _snapshot(
            create_response_json, "draft create-response JSON"
        )
        draft = _draft_release(
            create_value,
            request=request,
            records=None,
            label="GitHub draft create response",
        )
        source = _mapping(identity.get("source"), "source identity source")
        identity_record = next(
            record
            for record in records
            if record["name"] == f"{tag}-source-identity.json"
        )
        return {
            "api_snapshot": {
                "kind": "draft_create_response",
                "sha256": create_sha256,
            },
            "artifact_kind": "corelm_portfolio_github_empty_draft_receipt",
            "artifact_verification": {
                "caller_decoder": decoder_identity,
                "ssh_detached_signatures": "OFFLINE_ARTIFACT_VERIFIER_PASS",
                "status": "OFFLINE_ARTIFACT_PASS",
            },
            "assets": list(records),
            "create_request_sha256": hashlib.sha256(
                _canonical_json(request)
            ).hexdigest(),
            "publish_request_sha256": hashlib.sha256(
                _canonical_json(publish_request)
            ).hexdigest(),
            "github_draft": {
                "asset_count": 0,
                "draft": True,
                "id": draft["id"],
                "immutable": False,
                "prerelease": False,
                "published_at": None,
                "tag": tag,
                "upload_url": draft["upload_url"],
            },
            "repository": CANONICAL_REPOSITORY,
            "schema_version": 1,
            "source": {
                "commit": source["commit"],
                "source_identity_sha256": identity_record["sha256"],
                "tag_object": source["tag_object"],
                "tree": source["tree"],
            },
            "status": "EMPTY_DRAFT_UPLOAD_BOUNDARY_PASS",
            "verification_scope": {
                "api_transport_authentication": (
                    "CALLER_MUST_RETAIN_AUTHENTICATED_CREATE_RESPONSE"
                ),
                "network": "NOT_PERFORMED_BY_VERIFIER",
            },
        }


def verify_draft_saved_responses(
    *,
    assets: Path,
    ffprobe: Path,
    create_response_json: Path,
    draft_json: Path,
    immutable_policy_json: Path,
    tag_ref_json: Path,
    tag_object_json: Path,
    commit_object_json: Path,
) -> dict[str, Any]:
    with _verified_asset_snapshot(assets, ffprobe) as (
        snapshot,
        tag,
        identity,
        records,
        decoder_identity,
    ):
        create_request = expected_create_request(identity, records)
        publish_request = _validate_publish_request(
            expected_publish_request(identity, records),
            identity=identity,
            records=records,
        )
        snapshots: dict[str, tuple[Any, str]] = {}
        for kind, path in (
            ("create_response", create_response_json),
            ("draft", draft_json),
            ("immutable_policy_prepublish", immutable_policy_json),
            ("tag_ref", tag_ref_json),
            ("tag_object", tag_object_json),
            ("commit_object", commit_object_json),
        ):
            snapshots[kind] = _snapshot(path, f"{kind} JSON")

        immutable_policy = _immutable_release_policy(
            snapshots["immutable_policy_prepublish"][0]
        )

        empty = _draft_release(
            snapshots["create_response"][0],
            request=create_request,
            records=None,
            label="GitHub draft create response",
        )
        populated = _draft_release(
            snapshots["draft"][0],
            request=create_request,
            records=records,
            label="GitHub populated draft",
            expected_release_id=empty["id"],
        )
        if populated["upload_url"] != empty["upload_url"]:
            raise PortfolioReleaseError(
                "GitHub populated draft upload_url differs from create response"
            )
        if populated["download_slug"] != empty["download_slug"]:
            raise PortfolioReleaseError(
                "GitHub populated draft html_url differs from create response"
            )

        source = _mapping(identity.get("source"), "source identity source")
        _tag_ref(snapshots["tag_ref"][0], tag, source["tag_object"])
        tag_verification = _tag_object(
            snapshots["tag_object"][0],
            tag,
            source["tag_object"],
            source["commit"],
            snapshot,
        )
        commit_verification = _commit_object(
            snapshots["commit_object"][0], source["commit"], source["tree"]
        )
        identity_record = next(
            record
            for record in records
            if record["name"] == f"{tag}-source-identity.json"
        )
        return {
            "api_snapshots": [
                {"kind": kind, "sha256": snapshots[kind][1]}
                for kind in (
                    "commit_object",
                    "create_response",
                    "draft",
                    "immutable_policy_prepublish",
                    "tag_object",
                    "tag_ref",
                )
            ],
            "artifact_kind": "corelm_portfolio_github_populated_draft_receipt",
            "artifact_verification": {
                "caller_decoder": decoder_identity,
                "ssh_detached_signatures": "OFFLINE_ARTIFACT_VERIFIER_PASS",
                "status": "OFFLINE_ARTIFACT_PASS",
            },
            "assets": list(records),
            "create_request_sha256": hashlib.sha256(
                _canonical_json(create_request)
            ).hexdigest(),
            "github_draft": {
                "asset_count": len(records),
                "draft": True,
                "id": populated["id"],
                "immutable": False,
                "prerelease": False,
                "published_at": None,
                "tag": tag,
                "tag_api_verification": tag_verification,
                "upload_url": populated["upload_url"],
            },
            "github_immutable_releases_policy": {
                "enabled": immutable_policy["enabled"],
                "enforced_by_owner": immutable_policy["enforced_by_owner"],
                "endpoint": IMMUTABLE_RELEASES_ENDPOINT,
            },
            "publish_endpoint": publish_release_endpoint(populated["id"]),
            "publish_request": publish_request,
            "publish_request_sha256": hashlib.sha256(
                _canonical_json(publish_request)
            ).hexdigest(),
            "repository": CANONICAL_REPOSITORY,
            "schema_version": 2,
            "source": {
                "commit": source["commit"],
                "commit_api_verification": commit_verification,
                "source_identity_sha256": identity_record["sha256"],
                "tag_object": source["tag_object"],
                "tree": source["tree"],
            },
            "status": "POPULATED_DRAFT_PUBLISH_BOUNDARY_PASS",
            "verification_scope": {
                "api_transport_authentication": (
                    "CALLER_MUST_RETAIN_AUTHENTICATED_DRAFT_RESPONSES"
                ),
                "network": "NOT_PERFORMED_BY_VERIFIER",
            },
        }


def verify_saved_responses(
    *,
    assets: Path,
    ffprobe: Path,
    release_id_json: Path,
    release_tag_json: Path,
    latest_json: Path,
    tag_ref_json: Path,
    tag_object_json: Path,
    commit_object_json: Path,
) -> dict[str, Any]:
    with _verified_asset_snapshot(assets, ffprobe) as (
        snapshot,
        tag,
        identity,
        records,
        decoder_identity,
    ):
        request = expected_create_request(identity, records)
        publish_request = expected_publish_request(identity, records)
        snapshots: dict[str, tuple[Any, str]] = {}
        for kind, path in (
            ("release_id", release_id_json),
            ("release_tag", release_tag_json),
            ("latest", latest_json),
            ("tag_ref", tag_ref_json),
            ("tag_object", tag_object_json),
            ("commit_object", commit_object_json),
        ):
            snapshots[kind] = _snapshot(path, f"{kind} JSON")

        release_by_id = _api_release(
            snapshots["release_id"][0], request=request, records=records
        )
        release_by_tag = _api_release(
            snapshots["release_tag"][0], request=request, records=records
        )
        latest = _api_release(
            snapshots["latest"][0], request=request, records=records
        )
        if not (release_by_id == release_by_tag == latest):
            raise PortfolioReleaseError(
                "GitHub release by-id/by-tag/latest responses are not the same published release"
            )
        release = release_by_id
        source = _mapping(identity.get("source"), "source identity source")
        _tag_ref(snapshots["tag_ref"][0], tag, source["tag_object"])
        tag_verification = _tag_object(
            snapshots["tag_object"][0],
            tag,
            source["tag_object"],
            source["commit"],
            snapshot,
        )
        commit_verification = _commit_object(
            snapshots["commit_object"][0], source["commit"], source["tree"]
        )

        immutable_statement = "GITHUB_API_REPORTED_TRUE"
        identity_record = next(
            record
            for record in records
            if record["name"] == f"{tag}-source-identity.json"
        )
        return {
            "api_snapshots": [
                {"kind": kind, "sha256": snapshots[kind][1]}
                for kind in (
                    "commit_object",
                    "latest",
                    "release_id",
                    "release_tag",
                    "tag_object",
                    "tag_ref",
                )
            ],
            "artifact_kind": "corelm_portfolio_github_release_receipt",
            "artifact_verification": {
                "caller_decoder": decoder_identity,
                "ssh_detached_signatures": "OFFLINE_ARTIFACT_VERIFIER_PASS",
                "status": "OFFLINE_ARTIFACT_PASS",
            },
            "assets": list(records),
            "create_request_sha256": hashlib.sha256(
                _canonical_json(request)
            ).hexdigest(),
            "publish_request_sha256": hashlib.sha256(
                _canonical_json(publish_request)
            ).hexdigest(),
            "github_release": {
                "asset_count": len(records),
                "body_sha256": hashlib.sha256(
                    request["body"].encode("utf-8")
                ).hexdigest(),
                "draft": False,
                "html_url": f"{CANONICAL_REPOSITORY}/releases/tag/{tag}",
                "id": release["id"],
                "immutable": release["immutable"],
                "immutable_statement": immutable_statement,
                "latest": True,
                "prerelease": False,
                "published_at": release["published_at"],
                "tag": tag,
                "tag_api_verification": tag_verification,
                "target_commitish": "main",
                "title": release_title(tag),
            },
            "immutability_scope": IMMUTABILITY_SCOPE,
            "project_preservation_policy": PROJECT_PRESERVATION_POLICY,
            "repository": CANONICAL_REPOSITORY,
            "schema_version": 2,
            "source": {
                "commit": source["commit"],
                "commit_api_verification": commit_verification,
                "source_identity_sha256": identity_record["sha256"],
                "tag_object": source["tag_object"],
                "tree": source["tree"],
            },
            "status": "OFFLINE_ARTIFACT_AND_SAVED_PUBLIC_API_SNAPSHOT_PASS",
            "verification_scope": {
                "api_transport_authentication": "NOT_OBSERVABLE_FROM_SAVED_RESPONSES",
                "caller_decoder_identity": "RECORDED_INVOCATION_NOT_TRUST_ROOT",
                "github_state": "SAVED_RESPONSES_NOT_LIVE_STATE",
            },
        }


def _git_blob_sha1(data: bytes) -> str:
    prefix = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(prefix + data).hexdigest()


def _run_successor_git(
    root: Path,
    arguments: Sequence[str],
    *,
    allowed: tuple[int, ...] = (0,),
) -> tuple[int, bytes]:
    """Run one bounded, non-interactive Git query against the C1 checkout."""

    try:
        completed = subprocess.run(
            (
                "/usr/bin/git",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.quotepath=false",
                "-C",
                str(root),
                *arguments,
            ),
            env={
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "HOME": "/nonexistent",
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise PortfolioReleaseError("presentation successor Git query failed") from error
    if completed.returncode not in allowed:
        raise PortfolioReleaseError("presentation successor Git query was rejected")
    if len(completed.stdout) > MAX_GIT_OUTPUT_BYTES:
        raise PortfolioReleaseError("presentation successor Git output is oversized")
    return completed.returncode, completed.stdout


def _successor_git_text(root: Path, arguments: Sequence[str]) -> str:
    raw = _run_successor_git(root, arguments)[1]
    try:
        return raw.decode("utf-8", errors="strict").rstrip("\n")
    except UnicodeDecodeError as error:
        raise PortfolioReleaseError("presentation successor Git output is not UTF-8") from error


def _safe_git_path(raw: bytes, label: str) -> str:
    try:
        value = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PortfolioReleaseError(f"{label} path is not UTF-8") from error
    parts = value.split("/")
    if (
        not value
        or value.startswith("/")
        or any(part in {"", ".", ".."} for part in parts)
        or parts[0] == ".git"
    ):
        raise PortfolioReleaseError(f"{label} path is unsafe")
    return value


def _successor_tree(root: Path) -> dict[str, tuple[str, str]]:
    raw = _run_successor_git(root, ("ls-tree", "-rz", "--full-tree", "HEAD"))[1]
    if not raw or not raw.endswith(b"\0"):
        raise PortfolioReleaseError("presentation successor HEAD tree is malformed")
    tree: dict[str, tuple[str, str]] = {}
    for record in raw[:-1].split(b"\0"):
        header, separator, raw_path = record.partition(b"\t")
        fields = header.split(b" ")
        if not separator or len(fields) != 3:
            raise PortfolioReleaseError("presentation successor tree record is malformed")
        try:
            mode, object_type, object_id = (
                field.decode("ascii", errors="strict") for field in fields
            )
        except UnicodeDecodeError as error:
            raise PortfolioReleaseError("presentation successor tree header is invalid") from error
        path = _safe_git_path(raw_path, "presentation successor tree")
        if (
            object_type != "blob"
            or mode not in {"100644", "100755", "120000"}
            or GIT_OBJECT_RE.fullmatch(object_id) is None
            or path in tree
        ):
            raise PortfolioReleaseError("presentation successor tree is unsupported")
        tree[path] = (mode, object_id)
    return tree


def _successor_index(root: Path) -> dict[str, tuple[str, str]]:
    raw = _run_successor_git(root, ("ls-files", "-z", "--stage"))[1]
    if not raw or not raw.endswith(b"\0"):
        raise PortfolioReleaseError("presentation successor index is malformed")
    index: dict[str, tuple[str, str]] = {}
    for record in raw[:-1].split(b"\0"):
        header, separator, raw_path = record.partition(b"\t")
        fields = header.split(b" ")
        if not separator or len(fields) != 3:
            raise PortfolioReleaseError("presentation successor index record is malformed")
        try:
            mode, object_id, stage = (
                field.decode("ascii", errors="strict") for field in fields
            )
        except UnicodeDecodeError as error:
            raise PortfolioReleaseError("presentation successor index header is invalid") from error
        path = _safe_git_path(raw_path, "presentation successor index")
        if (
            stage != "0"
            or mode not in {"100644", "100755", "120000"}
            or GIT_OBJECT_RE.fullmatch(object_id) is None
            or path in index
        ):
            raise PortfolioReleaseError("presentation successor index is unsupported")
        index[path] = (mode, object_id)
    return index


def _verify_successor_index_flags(root: Path, expected_paths: set[str]) -> None:
    for option, label in (
        ("-t", "status"),
        ("-v", "assume-unchanged"),
        ("-f", "fsmonitor"),
    ):
        raw = _run_successor_git(root, ("ls-files", "-z", option))[1]
        if not raw or not raw.endswith(b"\0"):
            raise PortfolioReleaseError(f"presentation successor {label} flags are malformed")
        observed: list[str] = []
        for record in raw[:-1].split(b"\0"):
            if not record.startswith(b"H "):
                raise PortfolioReleaseError(
                    f"presentation successor {label} flags are not ordinary"
                )
            observed.append(_safe_git_path(record[2:], f"successor {label}"))
        if len(observed) != len(set(observed)) or set(observed) != expected_paths:
            raise PortfolioReleaseError(
                f"presentation successor {label} paths differ from HEAD"
            )


def _verify_successor_worktree(root: Path, tree: Mapping[str, tuple[str, str]]) -> None:
    total = 0
    for path, (mode, expected_object) in tree.items():
        target = root / path
        try:
            status = target.lstat()
        except OSError as error:
            raise PortfolioReleaseError(
                f"presentation successor tracked path is unavailable: {path}"
            ) from error
        if mode == "120000":
            if not stat.S_ISLNK(status.st_mode) or status.st_nlink != 1:
                raise PortfolioReleaseError("presentation successor symlink mode differs")
            try:
                raw = os.fsencode(os.readlink(target))
            except OSError as error:
                raise PortfolioReleaseError("presentation successor symlink is unreadable") from error
        else:
            if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                raise PortfolioReleaseError("presentation successor file mode differs")
            expected_executable = bool(mode == "100755")
            if bool(stat.S_IMODE(status.st_mode) & 0o111) != expected_executable:
                raise PortfolioReleaseError("presentation successor executable mode differs")
            _size, _digest, captured = _stable_read(
                target, 256 * 1024 * 1024, capture=True
            )
            assert captured is not None
            raw = captured
        total += len(raw)
        if total > MAX_SUCCESSOR_TRACKED_BYTES:
            raise PortfolioReleaseError("presentation successor worktree is oversized")
        if _git_blob_sha1(raw) != expected_object:
            raise PortfolioReleaseError(
                f"presentation successor bytes differ from signed HEAD: {path}"
            )


def _verify_raw_successor_commit(
    root: Path, *, c0_commit: str, c1_commit: str, c1_tree: str
) -> None:
    """Read the raw commit object so grafts cannot rewrite its parent view."""

    raw = _run_successor_git(root, ("cat-file", "commit", c1_commit))[1]
    if not raw or len(raw) > 16 * 1024 * 1024:
        raise PortfolioReleaseError("presentation successor raw commit is unavailable")
    object_id = hashlib.sha1(
        b"commit " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()
    if object_id != c1_commit:
        raise PortfolioReleaseError("presentation successor raw commit hash differs")
    header, separator, _message = raw.partition(b"\n\n")
    if not separator:
        raise PortfolioReleaseError("presentation successor raw commit is malformed")
    lines = header.splitlines()
    tree_lines = [line for line in lines if line.startswith(b"tree ")]
    parent_lines = [line for line in lines if line.startswith(b"parent ")]
    if tree_lines != [f"tree {c1_tree}".encode("ascii")]:
        raise PortfolioReleaseError("presentation successor raw tree is not exact")
    if parent_lines != [f"parent {c0_commit}".encode("ascii")]:
        raise PortfolioReleaseError("presentation successor raw parent is not exact C0")


def _verify_successor_checkout(
    root: Path,
    *,
    allowed_signers: Path,
    c0_commit: str,
    c1_commit: str,
    c1_tree: str,
) -> bytes:
    """Bind the supplied clean checkout to the exact signed C1 object chain."""

    root = root.resolve(strict=True)
    if _successor_git_text(root, ("rev-parse", "--is-inside-work-tree")) != "true":
        raise PortfolioReleaseError("presentation successor root is not a Git worktree")
    observed_root = Path(
        _successor_git_text(root, ("rev-parse", "--show-toplevel"))
    ).resolve(strict=True)
    if observed_root != root:
        raise PortfolioReleaseError("presentation successor root is not the worktree root")
    if _successor_git_text(root, ("rev-parse", "--show-object-format")) != "sha1":
        raise PortfolioReleaseError("presentation successor Git object format is not SHA-1")
    if _successor_git_text(root, ("remote", "get-url", "origin")) != CANONICAL_REPOSITORY:
        raise PortfolioReleaseError("presentation successor origin is not canonical")
    if _run_successor_git(
        root, ("for-each-ref", "--format=%(refname)", "refs/replace")
    )[1]:
        raise PortfolioReleaseError("presentation successor replacement refs are forbidden")
    common_raw = _successor_git_text(root, ("rev-parse", "--git-common-dir"))
    common_directory = Path(common_raw)
    if not common_directory.is_absolute():
        common_directory = root / common_directory
    try:
        common_directory = common_directory.resolve(strict=True)
    except OSError as error:
        raise PortfolioReleaseError("presentation successor Git directory is unavailable") from error
    try:
        (common_directory / "info" / "grafts").lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise PortfolioReleaseError("presentation successor graft state is unreadable") from error
    else:
        raise PortfolioReleaseError("presentation successor legacy grafts are forbidden")
    for key in ("core.sparseCheckout", "core.sparseCheckoutCone", "index.sparse"):
        code, value = _run_successor_git(
            root, ("config", "--bool", key), allowed=(0, 1)
        )
        if code == 0 and value.decode("ascii", errors="strict").strip() != "false":
            raise PortfolioReleaseError("presentation successor sparse modes are forbidden")
    if _successor_git_text(root, ("rev-parse", "HEAD")) != c1_commit:
        raise PortfolioReleaseError("presentation successor checkout is not exact C1")
    if _successor_git_text(root, ("rev-parse", "HEAD^{tree}")) != c1_tree:
        raise PortfolioReleaseError("presentation successor checkout tree differs from signed C1")
    _verify_raw_successor_commit(
        root,
        c0_commit=c0_commit,
        c1_commit=c1_commit,
        c1_tree=c1_tree,
    )
    _run_successor_git(
        root,
        (
            "-c",
            "gpg.format=ssh",
            "-c",
            "gpg.ssh.program=/usr/bin/ssh-keygen",
            "-c",
            f"gpg.ssh.allowedSignersFile={allowed_signers}",
            "verify-commit",
            c1_commit,
        ),
    )
    if _run_successor_git(
        root, ("status", "--porcelain=v1", "--untracked-files=all")
    )[1]:
        raise PortfolioReleaseError("presentation successor checkout is not clean")

    tree = _successor_tree(root)
    if _successor_index(root) != tree:
        raise PortfolioReleaseError("presentation successor index differs from signed HEAD")
    _verify_successor_index_flags(root, set(tree))
    _verify_successor_worktree(root, tree)
    if _successor_git_text(root, ("rev-parse", "HEAD")) != c1_commit:
        raise PortfolioReleaseError("presentation successor changed during verification")
    if _successor_git_text(root, ("rev-parse", "HEAD^{tree}")) != c1_tree:
        raise PortfolioReleaseError("presentation successor tree changed during verification")
    _verify_raw_successor_commit(
        root,
        c0_commit=c0_commit,
        c1_commit=c1_commit,
        c1_tree=c1_tree,
    )

    changed = _successor_git_text(
        root,
        (
            "diff-tree",
            "--no-commit-id",
            "--name-status",
            "--no-renames",
            "-r",
            c0_commit,
            c1_commit,
        ),
    ).splitlines()
    if set(changed) != {
        "M\tREADME.md",
        "A\tdocs/media/corelm-result.png",
    } or len(changed) != 2:
        raise PortfolioReleaseError("presentation successor local diff is not exact")
    base_readme = _run_successor_git(root, ("show", f"{c0_commit}:README.md"))[1]
    if not base_readme or len(base_readme) > 16 * 1024 * 1024:
        raise PortfolioReleaseError("C0 README is unavailable or oversized")
    return base_readme


def _expected_successor_readme(base: bytes, tag: str, source_commit: str) -> bytes:
    """Return the only README transformation permitted in presentation C1."""

    prefix = b"# Core LM Benchmark\n\n"
    if not base.startswith(prefix):
        raise PortfolioReleaseError("C0 README title/prefix is not canonical")
    if (
        PRESENTATION_MARKER_START.encode("ascii") in base
        or PRESENTATION_MARKER_END.encode("ascii") in base
    ):
        raise PortfolioReleaseError("C0 README already contains a presentation block")
    poster = (
        f"{CANONICAL_REPOSITORY}/releases/download/{tag}/{tag}-demo-poster.png"
    )
    video = f"{CANONICAL_REPOSITORY}/releases/download/{tag}/{tag}-demo.mp4"
    block = (
        f"{PRESENTATION_MARKER_START}\n"
        "## Verified real-model demo\n\n"
        f"![Core LM benchmark result]({poster})\n\n"
        f"[Watch the complete demo video]({video})\n\n"
        "This presentation was recorded from SSH-signed release source "
        f"[`{source_commit}`]({CANONICAL_REPOSITORY}/commit/{source_commit}) at "
        f"annotated tag [`{tag}`]({CANONICAL_REPOSITORY}/releases/tag/{tag}). "
        "It is an `AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION` on pinned "
        "public data, classified as "
        f"`{automated_media.MEDIA_CLASSIFICATION}`. Signed result and evidence "
        "files—not the pixels—support the metrics. Automated checks found no "
        "configured violation; semantic pixel privacy and independent review are "
        "not claimed. This presentation-only successor does not alter the "
        "released source or evidence and is **not** a blind/generalization "
        "result, model-weight-compression result, or independent human "
        "replication.\n"
        f"{PRESENTATION_MARKER_END}\n\n"
    ).encode("utf-8")
    return prefix + block + base[len(prefix) :]


def _successor_media_urls(readme: str, tag: str) -> tuple[str, str]:
    poster = (
        f"{CANONICAL_REPOSITORY}/releases/download/{tag}/"
        f"{tag}-demo-poster.png"
    )
    video = f"{CANONICAL_REPOSITORY}/releases/download/{tag}/{tag}-demo.mp4"
    observed = re.findall(
        r"https://github\.com/ALLPROTO/core-lm-benchmark/releases/"
        r"(?:download|latest/download)/[^\s)>'\"`]+",
        readme,
    )
    if sorted(observed) != sorted((poster, video)):
        raise PortfolioReleaseError(
            "presentation README must contain exactly the immutable poster/video URLs"
        )
    return poster, video


def verify_presentation_successor(
    *,
    assets: Path,
    ffprobe: Path,
    release_json: Path,
    latest_json: Path,
    tag_ref_json: Path,
    tag_object_json: Path,
    commit_object_json: Path,
    compare_json: Path,
    successor_commit_json: Path,
    successor_root: Path,
) -> dict[str, Any]:
    root = _absolute(successor_root, "successor root")
    try:
        root_status = root.lstat()
        resolved_root = root.resolve(strict=True)
    except OSError as error:
        raise PortfolioReleaseError("successor root is unavailable") from error
    if not stat.S_ISDIR(root_status.st_mode):
        raise PortfolioReleaseError("successor root must be a directory, not a symlink")
    root = resolved_root

    with _verified_asset_snapshot(assets, ffprobe) as (
        snapshot,
        tag,
        identity,
        records,
        decoder_identity,
    ):
        request = expected_create_request(identity, records)
        api_paths = {
            "release": release_json,
            "latest": latest_json,
            "tag_ref": tag_ref_json,
            "tag_object": tag_object_json,
            "commit_object": commit_object_json,
            "compare": compare_json,
            "successor_commit": successor_commit_json,
        }
        api = {
            kind: _snapshot(path, f"{kind} JSON")
            for kind, path in api_paths.items()
        }
        release = _api_release(api["release"][0], request=request, records=records)
        latest = _api_release(api["latest"][0], request=request, records=records)
        if latest != release:
            raise PortfolioReleaseError(
                "GitHub latest-release response is not the exact published release"
            )
        if release["immutable"] is not True:
            raise PortfolioReleaseError(
                "presentation successor requires GitHub API immutable:true for C0"
            )
        source = _mapping(identity.get("source"), "source identity source")
        _tag_ref(api["tag_ref"][0], tag, source["tag_object"])
        c0_tag_signature = _tag_object(
            api["tag_object"][0],
            tag,
            source["tag_object"],
            source["commit"],
            snapshot,
        )
        _commit_object(api["commit_object"][0], source["commit"], source["tree"])

        compare = _mapping(api["compare"][0], "GitHub compare response")
        if (
            compare.get("status") != "ahead"
            or compare.get("ahead_by") != 1
            or compare.get("behind_by") != 0
            or compare.get("total_commits") != 1
        ):
            raise PortfolioReleaseError("presentation successor must be exactly one C1 commit")
        base_commit = _mapping(compare.get("base_commit"), "compare base commit")
        merge_base = _mapping(
            compare.get("merge_base_commit"), "compare merge-base commit"
        )
        commits = compare.get("commits")
        if (
            base_commit.get("sha") != source["commit"]
            or merge_base.get("sha") != source["commit"]
            or not isinstance(commits, list)
            or len(commits) != 1
        ):
            raise PortfolioReleaseError("presentation successor is not directly based on C0")
        c1_commit = _mapping(api["successor_commit"][0], "successor commit response")
        c1_sha = _git_object(c1_commit.get("sha"), "C1 commit")
        compare_commit = _mapping(commits[0], "compare C1 commit")
        if compare_commit.get("sha") != c1_sha or c1_sha == source["commit"]:
            raise PortfolioReleaseError("compare response does not bind exact C1 commit")
        parents = c1_commit.get("parents")
        if (
            not isinstance(parents, list)
            or len(parents) != 1
            or not isinstance(parents[0], dict)
            or parents[0].get("sha") != source["commit"]
        ):
            raise PortfolioReleaseError("C1 must have exact C0 as its only parent")
        c1_inner = _mapping(c1_commit.get("commit"), "successor commit payload")
        c1_tree = _git_object(
            _mapping(c1_inner.get("tree"), "successor commit tree").get("sha"),
            "C1 tree",
        )
        if c1_tree == source["tree"]:
            raise PortfolioReleaseError("C1 tree must contain the presentation changes")
        compare_inner = _mapping(compare_commit.get("commit"), "compare C1 payload")
        if _mapping(compare_inner.get("tree"), "compare C1 tree").get("sha") != c1_tree:
            raise PortfolioReleaseError("compare response C1 tree differs from commit API")
        c1_verification_value = _mapping(
            c1_inner.get("verification"), "successor commit verification"
        )
        signed_payload = _string(
            c1_verification_value.get("payload"), "successor signed payload"
        )
        payload_header = signed_payload.split("\n\n", 1)[0].splitlines()
        if (
            not payload_header
            or payload_header[0] != f"tree {c1_tree}"
            or payload_header.count(f"parent {source['commit']}") != 1
            or sum(line.startswith("parent ") for line in payload_header) != 1
        ):
            raise PortfolioReleaseError("C1 signed payload does not bind tree and C0 parent")
        c1_signature = _verify_git_payload_signature(
            c1_verification_value, snapshot, "presentation successor commit"
        )
        base_readme = _verify_successor_checkout(
            root,
            allowed_signers=snapshot / "allowed_signers",
            c0_commit=source["commit"],
            c1_commit=c1_sha,
            c1_tree=c1_tree,
        )

        files = compare.get("files")
        if not isinstance(files, list) or len(files) != 2:
            raise PortfolioReleaseError("presentation successor diff must contain two files")
        by_name: dict[str, Mapping[str, Any]] = {}
        for value in files:
            item = _mapping(value, "presentation successor changed file")
            name = _string(item.get("filename"), "changed filename")
            if name in by_name or item.get("previous_filename") is not None:
                raise PortfolioReleaseError("presentation successor contains a rename/duplicate")
            by_name[name] = item
        if set(by_name) != set(EXACT_SUCCESSOR_PATHS):
            raise PortfolioReleaseError("presentation successor changed paths are not exact")
        if (
            by_name["README.md"].get("status") != "modified"
            or by_name["docs/media/corelm-result.png"].get("status") != "added"
        ):
            raise PortfolioReleaseError("presentation successor file statuses are not exact")

        _readme_size, readme_sha256, readme_bytes = _stable_read(
            root / "README.md", 16 * 1024 * 1024, capture=True
        )
        _poster_size, successor_poster_sha256, successor_poster = _stable_read(
            root / "docs" / "media" / "corelm-result.png",
            64 * 1024 * 1024,
            capture=True,
        )
        assert readme_bytes is not None and successor_poster is not None
        if by_name["README.md"].get("sha") != _git_blob_sha1(readme_bytes):
            raise PortfolioReleaseError("C1 README bytes differ from the public compare API")
        if by_name["docs/media/corelm-result.png"].get("sha") != _git_blob_sha1(
            successor_poster
        ):
            raise PortfolioReleaseError("C1 poster bytes differ from the public compare API")
        released_poster = next(
            record
            for record in records
            if record["name"] == f"{tag}-demo-poster.png"
        )
        if successor_poster_sha256 != released_poster["sha256"]:
            raise PortfolioReleaseError("C1 poster does not equal the released poster bytes")
        try:
            readme = readme_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise PortfolioReleaseError("C1 README is not UTF-8") from error
        expected_readme = _expected_successor_readme(
            base_readme, tag, source["commit"]
        )
        if readme_bytes != expected_readme:
            raise PortfolioReleaseError(
                "C1 README is not the exact presentation-only transformation of C0"
            )
        poster_url, video_url = _successor_media_urls(readme, tag)

        return {
            "api_snapshots": [
                {"kind": kind, "sha256": api[kind][1]}
                for kind in sorted(api)
            ],
            "artifact_kind": "corelm_portfolio_presentation_successor_receipt",
            "c0": {
                "commit": source["commit"],
                "github_immutable": True,
                "tag": tag,
                "tag_object": source["tag_object"],
                "tag_signature": c0_tag_signature,
                "tree": source["tree"],
            },
            "c1": {
                "allowed_paths": list(EXACT_SUCCESSOR_PATHS),
                "commit": c1_sha,
                "commit_signature": c1_signature,
                "parent": source["commit"],
                "poster_sha256": successor_poster_sha256,
                "readme_sha256": readme_sha256,
                "readme_policy": "EXACT_PRESENTATION_ONLY_TRANSFORMATION_OF_C0",
                "tree": c1_tree,
            },
            "caller_decoder": decoder_identity,
            "media_urls": {"poster": poster_url, "video": video_url},
            "project_preservation_policy": PROJECT_PRESERVATION_POLICY,
            "schema_version": 1,
            "status": "PRESENTATION_SUCCESSOR_PASS",
        }


def _reject_output_overlap(
    output: Path, *, protected_directories: Sequence[Path], label: str
) -> None:
    destination = _absolute(output, label).resolve(strict=False)
    for protected in protected_directories:
        root = _absolute(protected, "protected input directory").resolve(strict=True)
        if destination == root or destination in root.parents or root in destination.parents:
            raise PortfolioReleaseError(f"{label} overlaps an asset/input directory")


def _write_new(path: Path, payload: bytes, label: str) -> None:
    destination = _absolute(path, label)
    try:
        parent = destination.parent.lstat()
    except OSError as error:
        raise PortfolioReleaseError(f"{label} parent directory is unavailable") from error
    if not stat.S_ISDIR(parent.st_mode):
        raise PortfolioReleaseError(f"{label} parent must be a directory and not a symlink")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(destination, flags, 0o644)
    except OSError as error:
        raise PortfolioReleaseError(f"{label} must not already exist") from error
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise PortfolioReleaseError(f"{label} write failed")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_new_pair(
    first: tuple[Path, bytes, str],
    second: tuple[Path, bytes, str],
) -> None:
    created: list[tuple[Path, str]] = []
    try:
        for path, payload, label in (first, second):
            _write_new(path, payload, label)
            created.append((_absolute(path, label), label))
    except BaseException:
        for path, _label in reversed(created):
            try:
                os.unlink(path)
            except OSError:
                pass
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    policy = commands.add_parser(
        "verify-policy",
        help="verify the saved immutable-release policy before draft creation",
    )
    policy.add_argument("--immutable-policy-json", type=Path, required=True)
    policy.add_argument("--receipt", type=Path, required=True)

    prepare = commands.add_parser(
        "prepare-draft", help="write the exact create-draft API JSON"
    )
    prepare.add_argument("--assets", type=Path, required=True)
    prepare.add_argument("--ffprobe", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)

    empty_draft = commands.add_parser(
        "verify-empty-draft",
        help="verify the saved empty draft response before any asset upload",
    )
    empty_draft.add_argument("--assets", type=Path, required=True)
    empty_draft.add_argument("--ffprobe", type=Path, required=True)
    empty_draft.add_argument("--create-response-json", type=Path, required=True)
    empty_draft.add_argument("--receipt", type=Path, required=True)

    draft = commands.add_parser(
        "verify-draft",
        help="verify the populated authenticated draft and write its publish PATCH JSON",
    )
    draft.add_argument("--assets", type=Path, required=True)
    draft.add_argument("--ffprobe", type=Path, required=True)
    draft.add_argument("--create-response-json", type=Path, required=True)
    draft.add_argument("--draft-json", type=Path, required=True)
    draft.add_argument("--immutable-policy-json", type=Path, required=True)
    draft.add_argument("--tag-ref-json", type=Path, required=True)
    draft.add_argument("--tag-object-json", type=Path, required=True)
    draft.add_argument("--commit-object-json", type=Path, required=True)
    draft.add_argument("--publish-request", type=Path, required=True)
    draft.add_argument("--receipt", type=Path, required=True)

    verify = commands.add_parser("verify", help="verify saved public API JSON and assets")
    verify.add_argument("--assets", type=Path, required=True)
    verify.add_argument("--release-id-json", type=Path, required=True)
    verify.add_argument("--release-tag-json", type=Path, required=True)
    verify.add_argument("--latest-json", type=Path, required=True)
    verify.add_argument("--tag-ref-json", type=Path, required=True)
    verify.add_argument("--tag-object-json", type=Path, required=True)
    verify.add_argument("--commit-object-json", type=Path, required=True)
    verify.add_argument("--ffprobe", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)

    successor = commands.add_parser(
        "verify-successor",
        help="verify the exact signed documentation-only C1 successor",
    )
    successor.add_argument("--assets", type=Path, required=True)
    successor.add_argument("--ffprobe", type=Path, required=True)
    successor.add_argument("--release-json", type=Path, required=True)
    successor.add_argument("--latest-json", type=Path, required=True)
    successor.add_argument("--tag-ref-json", type=Path, required=True)
    successor.add_argument("--tag-object-json", type=Path, required=True)
    successor.add_argument("--commit-object-json", type=Path, required=True)
    successor.add_argument("--compare-json", type=Path, required=True)
    successor.add_argument("--successor-commit-json", type=Path, required=True)
    successor.add_argument("--successor-root", type=Path, required=True)
    successor.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    try:
        if options.command == "verify-policy":
            _reject_output_overlap(
                options.receipt,
                protected_directories=(options.immutable_policy_json.parent,),
                label="precreate policy receipt output",
            )
            receipt = verify_immutable_policy_response(
                immutable_policy_json=options.immutable_policy_json
            )
            _write_new(
                options.receipt,
                _canonical_json(receipt),
                "precreate policy receipt output",
            )
            print(
                "PORTFOLIO GITHUB IMMUTABLE POLICY PASS: "
                f"enabled={str(receipt['github_immutable_releases_policy']['enabled']).lower()} "
                "enforced_by_owner="
                f"{str(receipt['github_immutable_releases_policy']['enforced_by_owner']).lower()} "
                f"endpoint={IMMUTABLE_RELEASES_ENDPOINT}"
            )
        elif options.command == "prepare-draft":
            _reject_output_overlap(
                options.output,
                protected_directories=(options.assets,),
                label="create-request output",
            )
            with _verified_asset_snapshot(options.assets, options.ffprobe) as (
                _snapshot_directory,
                _tag,
                identity,
                records,
                _decoder_identity,
            ):
                request = expected_create_request(identity, records)
            _write_new(options.output, _canonical_json(request), "create-request output")
            print(
                "PORTFOLIO GITHUB DRAFT REQUEST PASS: "
                f"tag={request['tag_name']} assets={len(records)} "
                f"endpoint={CREATE_RELEASE_ENDPOINT}"
            )
        elif options.command == "verify-empty-draft":
            _reject_output_overlap(
                options.receipt,
                protected_directories=(
                    options.assets,
                    options.create_response_json.parent,
                ),
                label="empty-draft receipt output",
            )
            receipt = verify_empty_draft_response(
                assets=options.assets,
                ffprobe=options.ffprobe,
                create_response_json=options.create_response_json,
            )
            _write_new(
                options.receipt,
                _canonical_json(receipt),
                "empty-draft receipt output",
            )
            print(
                "PORTFOLIO GITHUB EMPTY DRAFT PASS: "
                f"tag={receipt['github_draft']['tag']} "
                f"id={receipt['github_draft']['id']} "
                f"upload_url={receipt['github_draft']['upload_url']}"
            )
        elif options.command == "verify-draft":
            api_paths = (
                options.create_response_json,
                options.draft_json,
                options.immutable_policy_json,
                options.tag_ref_json,
                options.tag_object_json,
                options.commit_object_json,
            )
            _reject_output_overlap(
                options.publish_request,
                protected_directories=(
                    options.assets,
                    *(path.parent for path in api_paths),
                    options.receipt.parent,
                ),
                label="publish-request output",
            )
            _reject_output_overlap(
                options.receipt,
                protected_directories=(
                    options.assets,
                    *(path.parent for path in api_paths),
                    options.publish_request.parent,
                ),
                label="populated-draft receipt output",
            )
            receipt = verify_draft_saved_responses(
                assets=options.assets,
                ffprobe=options.ffprobe,
                create_response_json=options.create_response_json,
                draft_json=options.draft_json,
                immutable_policy_json=options.immutable_policy_json,
                tag_ref_json=options.tag_ref_json,
                tag_object_json=options.tag_object_json,
                commit_object_json=options.commit_object_json,
            )
            _write_new_pair(
                (
                    options.publish_request,
                    _canonical_json(receipt["publish_request"]),
                    "publish-request output",
                ),
                (
                    options.receipt,
                    _canonical_json(receipt),
                    "populated-draft receipt output",
                ),
            )
            print(
                "PORTFOLIO GITHUB POPULATED DRAFT PASS: "
                f"tag={receipt['github_draft']['tag']} "
                f"id={receipt['github_draft']['id']} "
                f"assets={receipt['github_draft']['asset_count']} "
                f"endpoint={receipt['publish_endpoint']}"
            )
        elif options.command == "verify":
            api_paths = (
                options.release_id_json,
                options.release_tag_json,
                options.latest_json,
                options.tag_ref_json,
                options.tag_object_json,
                options.commit_object_json,
            )
            _reject_output_overlap(
                options.receipt,
                protected_directories=(
                    options.assets,
                    *(path.parent for path in api_paths),
                ),
                label="receipt output",
            )
            receipt = verify_saved_responses(
                assets=options.assets,
                ffprobe=options.ffprobe,
                release_id_json=options.release_id_json,
                release_tag_json=options.release_tag_json,
                latest_json=options.latest_json,
                tag_ref_json=options.tag_ref_json,
                tag_object_json=options.tag_object_json,
                commit_object_json=options.commit_object_json,
            )
            _write_new(options.receipt, _canonical_json(receipt), "receipt output")
            print(
                "PORTFOLIO GITHUB RELEASE SNAPSHOT PASS: "
                f"tag={receipt['github_release']['tag']} "
                f"immutable={str(receipt['github_release']['immutable']).lower()} "
                "scope=saved-public-API-responses"
            )
        else:
            api_paths = (
                options.release_json,
                options.latest_json,
                options.tag_ref_json,
                options.tag_object_json,
                options.commit_object_json,
                options.compare_json,
                options.successor_commit_json,
            )
            _reject_output_overlap(
                options.receipt,
                protected_directories=(
                    options.assets,
                    options.successor_root,
                    *(path.parent for path in api_paths),
                ),
                label="successor receipt output",
            )
            receipt = verify_presentation_successor(
                assets=options.assets,
                ffprobe=options.ffprobe,
                release_json=options.release_json,
                latest_json=options.latest_json,
                tag_ref_json=options.tag_ref_json,
                tag_object_json=options.tag_object_json,
                commit_object_json=options.commit_object_json,
                compare_json=options.compare_json,
                successor_commit_json=options.successor_commit_json,
                successor_root=options.successor_root,
            )
            _write_new(
                options.receipt,
                _canonical_json(receipt),
                "successor receipt output",
            )
            print(
                "PORTFOLIO PRESENTATION SUCCESSOR PASS: "
                f"c0={receipt['c0']['commit']} c1={receipt['c1']['commit']}"
            )
    except PortfolioReleaseError as error:
        print(f"PORTFOLIO GITHUB RELEASE FAIL: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
