#!/usr/bin/env python3
"""Collect one completed real macOS proof into portfolio-release inputs.

This command is deliberately offline and does not execute a model.  The proof
must already contain the canonical reports created by the structural verifier
and the author-side heavyweight replay.  All identities are recomputed from retained
bytes, the signed app, the clean tagged source, and local Git object databases.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO


ROOT = Path(__file__).resolve().parents[1]
sys.path[:] = [entry for entry in sys.path if entry != str(ROOT)]
sys.path.insert(0, str(ROOT))

from publication import build_portfolio_release as portfolio  # noqa: E402
from RealLLM.pinned_assets import PINNED_RELEASE_ASSETS  # noqa: E402
from security.generate_build_provenance import (  # noqa: E402
    canonical_json_bytes as canonical_build_bytes,
    validate_build_manifest,
)
from security.generate_python_runtime_manifest import (  # noqa: E402
    MANIFEST_KEYS as PYTHON_RUNTIME_MANIFEST_KEYS,
    SCHEMA_VERSION as PYTHON_RUNTIME_SCHEMA_VERSION,
)
from security.proof_reports import (  # noqa: E402
    REPLAY_REPORT_NAME,
    REPORT_DIRECTORY_NAME,
    STRUCTURAL_REPORT_NAME,
    TERMINAL_LOG_NAME,
    WORKLOAD_CLASSIFICATION,
    derive_binding,
    read_json_object,
    validated_run_directory,
    verify_report,
)
from security.verify_app_run_evidence import verify_fresh_run  # noqa: E402


RESULT_NAME = "validation-064-071.json"
RECEIPT_NAME = "app-run-receipt.json"
BUILD_PROVENANCE_NAME = "build-provenance.json"
RUNTIME_PROVENANCE_NAME = "runtime-provenance.json"
PYTHON_CACHE_DIRECTORY_NAME = "python-cache"
MAX_TERMINAL_BYTES = 4096


class CollectionError(ValueError):
    """A fail-closed demo collection error."""


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        [
            "/usr/bin/git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            *arguments,
        ],
        cwd=repository,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
        env={
            "HOME": "/nonexistent",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        },
    )
    if completed.returncode != 0:
        raise CollectionError(f"local Git query failed: {' '.join(arguments)}")
    return completed.stdout.strip()


def _repository(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise CollectionError("repository path must be absolute and not symlinked")
    root = path.resolve(strict=True)
    if root != path or not root.is_dir():
        raise CollectionError("repository path must be canonical")
    return root


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_regular_input(path: Path, maximum_bytes: int, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise CollectionError(f"{label} must be an absolute non-symlink file")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise CollectionError(f"{label} is unavailable") from error
    if resolved != path:
        raise CollectionError(f"{label} path must be canonical")
    portfolio._require_regular_file(path, maximum_bytes)
    return path


def _safe_output(output: Path) -> tuple[Path, Path]:
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise CollectionError("output must be an absent absolute directory")
    parent = output.parent
    if parent.is_symlink():
        raise CollectionError("output parent must not be symlinked")
    resolved_parent = parent.resolve(strict=True)
    if resolved_parent != parent:
        raise CollectionError("output parent must be canonical")
    status = parent.stat()
    if (
        not stat.S_ISDIR(status.st_mode)
        or status.st_uid != os.getuid()
        or status.st_mode & 0o022
    ):
        raise CollectionError("output parent is not owner-controlled")
    staging = Path(tempfile.mkdtemp(prefix=".corelm-demo-", dir=parent))
    staging.chmod(0o700)
    return output, staging


def _read_terminal(path: Path, metric_verdict: str) -> bytes:
    if metric_verdict not in {"PASS", "FAIL"}:
        raise CollectionError("verified metric verdict is not exact")
    try:
        status = path.lstat()
    except OSError as error:
        raise CollectionError("canonical terminal outcome is missing") from error
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_nlink != 1
        or status.st_size <= 0
        or status.st_size > MAX_TERMINAL_BYTES
        or status.st_uid != os.getuid()
        or stat.S_IMODE(status.st_mode) != 0o600
    ):
        raise CollectionError("canonical terminal outcome is unsafe")
    expected = (
        b"END-TO-END PROOF PASS\n"
        if metric_verdict == "PASS"
        else "END-TO-END PROOF VERIFIED — METRIC FAIL\n".encode("utf-8")
    )
    payload = path.read_bytes()
    if payload != expected or b"rerun-to-pass" in payload.lower():
        raise CollectionError("terminal outcome is missing or metric-selection-tainted")
    return payload


def _probe_video(path: Path, executable: Path) -> tuple[dict[str, Any], str]:
    portfolio._validate_mp4_atoms(path)
    ffprobe = portfolio._resolve_executable(executable, "ffprobe")
    version = portfolio._ffprobe_version(ffprobe)
    completed = portfolio._run(
        (
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            (
                "format=duration:format_tags:"
                "stream=codec_name,codec_type,width,height:stream_tags"
            ),
            "-of",
            "json",
            str(path),
        ),
        cwd=path.parent,
        timeout=60,
    )
    if completed.returncode != 0:
        raise CollectionError("ffprobe rejected the recorded demo")
    try:
        report = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CollectionError("ffprobe returned invalid JSON") from error
    streams = report.get("streams") if isinstance(report, dict) else None
    if not isinstance(streams, list):
        raise CollectionError("ffprobe report has no stream list")
    try:
        portfolio._validate_ffprobe_metadata(report)
    except portfolio.PortfolioReleaseError as error:
        raise CollectionError(str(error)) from error
    videos = [
        row
        for row in streams
        if isinstance(row, dict) and row.get("codec_type") == "video"
    ]
    audios = [
        row
        for row in streams
        if isinstance(row, dict) and row.get("codec_type") == "audio"
    ]
    if len(videos) != 1 or videos[0].get("codec_name") != "h264":
        raise CollectionError("demo must contain exactly one H.264 video stream")
    width = videos[0].get("width")
    height = videos[0].get("height")
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or width <= 0
        or isinstance(height, bool)
        or not isinstance(height, int)
        or height <= 0
    ):
        raise CollectionError("demo video dimensions are invalid")
    if audios and (len(audios) != 1 or audios[0].get("codec_name") != "aac"):
        raise CollectionError("demo audio must be absent or one AAC stream")
    try:
        duration = float(report["format"]["duration"])
    except (KeyError, TypeError, ValueError) as error:
        raise CollectionError("demo duration is unavailable") from error
    if not math.isfinite(duration) or not (0 < duration <= 90):
        raise CollectionError("demo duration must be in (0, 90] seconds")
    return (
        {
            "duration_seconds": duration,
            "width": width,
            "height": height,
            "codec": "h264",
            "audio_codec": "silent" if not audios else "aac",
        },
        version,
    )


def _tar_info(name: str, size: int) -> tarfile.TarInfo:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != name:
        raise CollectionError(f"unsafe evidence member name: {name}")
    entry = tarfile.TarInfo(name)
    entry.size = size
    entry.mode = 0o600
    entry.mtime = 0
    entry.uid = 0
    entry.gid = 0
    entry.uname = ""
    entry.gname = ""
    return entry


def _write_evidence_archive(
    destination: Path,
    members: dict[str, Path | bytes],
) -> None:
    if destination.exists() or destination.is_symlink():
        raise CollectionError("evidence archive target already exists")
    with destination.open("xb") as raw:
        os.chmod(destination, 0o600, follow_symlinks=False)
        with gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=9,
            fileobj=raw,
            mtime=0,
        ) as compressed:
            with tarfile.open(
                fileobj=compressed,
                mode="w|",
                format=tarfile.PAX_FORMAT,
            ) as archive:
                for name in sorted(members, key=lambda item: item.encode("utf-8")):
                    source = members[name]
                    if isinstance(source, bytes):
                        archive.addfile(_tar_info(name, len(source)), io.BytesIO(source))
                        continue
                    status = portfolio._require_regular_file(
                        source, portfolio.MAX_TAR_EXPANDED_BYTES
                    )
                    with source.open("rb") as handle:
                        archive.addfile(_tar_info(name, status.st_size), handle)
        raw.flush()
        os.fsync(raw.fileno())


def _primary_members(run: Path) -> dict[str, Path]:
    primary = run / "primary-evidence"
    if primary.is_symlink() or not primary.is_dir():
        raise CollectionError("proof has no retained primary evidence")
    members: dict[str, Path] = {}
    for candidate in primary.rglob("*"):
        if candidate.is_dir() and not candidate.is_symlink():
            continue
        portfolio._require_regular_file(candidate, portfolio.MAX_TAR_EXPANDED_BYTES)
        relative = candidate.relative_to(run).as_posix()
        members[f"run/{relative}"] = candidate
    if not members or "run/primary-evidence/manifest.json" not in members:
        raise CollectionError("proof primary evidence topology is incomplete")
    return members


def _stable_identity(status: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        status.st_dev,
        status.st_ino,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def _stable_directory_identity(
    status: os.stat_result,
) -> tuple[int, int, int, int, int, int, int, int, int]:
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_nlink,
        status.st_uid,
        status.st_gid,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def _open_empty_python_cache(path: Path) -> tuple[int, tuple[int, ...]]:
    """Hold the app-created, non-evidence bytecode cache while sealing."""

    try:
        before = path.lstat()
    except OSError as error:
        raise CollectionError("proof python-cache directory is missing") from error
    if (
        not stat.S_ISDIR(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o700
    ):
        raise CollectionError(
            "proof python-cache must be an owner-only non-symlink directory"
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise CollectionError("proof python-cache cannot be opened safely") from error
    try:
        opened = os.fstat(descriptor)
        identity = _stable_directory_identity(opened)
        if identity != _stable_directory_identity(before):
            raise CollectionError("proof python-cache changed before sealing")
        if os.listdir(descriptor):
            raise CollectionError("proof python-cache must be empty")
        return descriptor, identity
    except Exception:
        os.close(descriptor)
        raise


def _recheck_empty_python_cache(
    path: Path, descriptor: int, identity: tuple[int, ...]
) -> None:
    try:
        opened = os.fstat(descriptor)
        current = path.lstat()
    except OSError as error:
        raise CollectionError("proof python-cache changed while sealing") from error
    if (
        _stable_directory_identity(opened) != identity
        or _stable_directory_identity(current) != identity
        or os.listdir(descriptor)
    ):
        raise CollectionError("proof python-cache changed while sealing")


def _copy_snapshot_file(
    source: Path, destination: Path, maximum_bytes: int
) -> int:
    before = source.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.getuid()
        or before.st_mode & 0o022
        or before.st_size <= 0
        or before.st_size > maximum_bytes
    ):
        raise CollectionError(f"unsafe proof input while sealing: {source.name}")
    source_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    source_flags |= getattr(os, "O_NOFOLLOW", 0)
    source_fd = os.open(source, source_flags)
    destination_fd = -1
    try:
        opened = os.fstat(source_fd)
        if _stable_identity(opened) != _stable_identity(before):
            raise CollectionError(f"proof input changed before sealing: {source.name}")
        destination_fd = os.open(
            destination,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        remaining = opened.st_size
        while remaining:
            chunk = os.read(source_fd, min(1024 * 1024, remaining))
            if not chunk:
                raise CollectionError(f"proof input truncated while sealing: {source.name}")
            view = memoryview(chunk)
            while view:
                written = os.write(destination_fd, view)
                if written <= 0:
                    raise OSError("sealed proof copy made no progress")
                view = view[written:]
            remaining -= len(chunk)
        if os.read(source_fd, 1):
            raise CollectionError(f"proof input grew while sealing: {source.name}")
        os.fsync(destination_fd)
        finished = os.fstat(source_fd)
        current = source.lstat()
        if (
            _stable_identity(finished) != _stable_identity(opened)
            or _stable_identity(current) != _stable_identity(opened)
        ):
            raise CollectionError(f"proof input changed while sealing: {source.name}")
    finally:
        if destination_fd >= 0:
            os.close(destination_fd)
        os.close(source_fd)
    return before.st_size


def _snapshot_run(live_run: Path, snapshot_parent: Path) -> Path:
    """Copy one exact completed proof into an unshared private snapshot."""

    run = validated_run_directory(live_run)
    expected_topology = {
        RECEIPT_NAME,
        RESULT_NAME,
        "primary-evidence",
        REPORT_DIRECTORY_NAME,
        PYTHON_CACHE_DIRECTORY_NAME,
    }
    if {entry.name for entry in run.iterdir()} != expected_topology:
        raise CollectionError("completed proof directory has missing or extra top-level inputs")
    cache_path = run / PYTHON_CACHE_DIRECTORY_NAME
    cache_descriptor, cache_identity = _open_empty_python_cache(cache_path)
    try:
        snapshot = snapshot_parent / run.name
        snapshot.mkdir(mode=0o700)
        total_bytes = _copy_snapshot_file(
            run / RECEIPT_NAME, snapshot / RECEIPT_NAME, portfolio.MAX_JSON_BYTES
        )
        total_bytes += _copy_snapshot_file(
            run / RESULT_NAME, snapshot / RESULT_NAME, portfolio.MAX_JSON_BYTES
        )
        total_files = 2
        for directory_name in ("primary-evidence", REPORT_DIRECTORY_NAME):
            source_root = run / directory_name
            if source_root.is_symlink() or not source_root.is_dir():
                raise CollectionError(f"proof {directory_name} directory is unsafe")
            source_root_status = source_root.stat()
            if (
                source_root_status.st_uid != os.getuid()
                or source_root_status.st_mode & 0o022
            ):
                raise CollectionError(f"proof {directory_name} directory is not private")
            target_root = snapshot / directory_name
            target_root.mkdir(mode=0o700)
            before_paths = sorted([
                item.relative_to(source_root).as_posix()
                for item in source_root.rglob("*")
            ], key=lambda item: item.encode("utf-8"))
            for relative in sorted(before_paths, key=lambda item: item.encode("utf-8")):
                source = source_root.joinpath(*PurePosixPath(relative).parts)
                target = target_root.joinpath(*PurePosixPath(relative).parts)
                status = source.lstat()
                if stat.S_ISDIR(status.st_mode) and not stat.S_ISLNK(status.st_mode):
                    if status.st_uid != os.getuid() or status.st_mode & 0o022:
                        raise CollectionError(
                            f"proof {directory_name} contains a writable directory"
                        )
                    target.mkdir(mode=0o700)
                    continue
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                total_bytes += _copy_snapshot_file(
                    source, target, portfolio.MAX_TAR_EXPANDED_BYTES
                )
                if total_bytes > portfolio.MAX_TAR_EXPANDED_BYTES:
                    raise CollectionError("completed proof exceeds the sealed byte bound")
                total_files += 1
                if total_files > portfolio.MAX_TAR_MEMBERS:
                    raise CollectionError("completed proof has too many retained inputs")
            after_paths = sorted([
                item.relative_to(source_root).as_posix()
                for item in source_root.rglob("*")
            ], key=lambda item: item.encode("utf-8"))
            if before_paths != after_paths:
                raise CollectionError(f"proof {directory_name} topology changed while sealing")
        if {entry.name for entry in run.iterdir()} != expected_topology:
            raise CollectionError("completed proof topology changed while sealing")
        _recheck_empty_python_cache(
            cache_path, cache_descriptor, cache_identity
        )
        return snapshot
    finally:
        os.close(cache_descriptor)


def _public_runtime_provenance(
    path: Path,
    receipt: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Project a verified private runtime manifest without publishing roots.

    ``verify_fresh_run`` has already re-hashed every runtime entry.  This
    projection retains its canonical digest, aggregate structure, entry-list
    digest, and exact Python identity while excluding owner-specific absolute
    paths that cannot be public evidence.
    """

    raw = portfolio._read_canonical_json(path)
    if not isinstance(raw, dict) or set(raw) != PYTHON_RUNTIME_MANIFEST_KEYS:
        raise CollectionError("Python runtime manifest fields are not exact")
    worker = receipt.get("worker")
    environment = result.get("environment")
    if not isinstance(worker, dict) or not isinstance(environment, dict):
        raise CollectionError("proof has no exact worker/runtime environment")
    source_digest = portfolio._sha256(path)
    if (
        raw.get("schemaVersion") != PYTHON_RUNTIME_SCHEMA_VERSION
        or source_digest != worker.get("runtimeManifestSHA256")
        or raw.get("pythonExecutableSHA256")
        != worker.get("pythonExecutableSHA256")
        or raw.get("pythonVersion") != environment.get("python")
    ):
        raise CollectionError("Python runtime identity differs across proof bytes")
    for key in ("fileCount", "symlinkCount", "totalBytes"):
        observed = raw.get(key)
        minimum = 0 if key == "symlinkCount" else 1
        if type(observed) is not int or observed < minimum:
            raise CollectionError("Python runtime manifest totals are invalid")
    entries = raw.get("entries")
    roots = raw.get("roots")
    if not isinstance(entries, list) or not isinstance(roots, list) or len(roots) != 2:
        raise CollectionError("Python runtime manifest structure is malformed")
    return {
        "schema_version": 1,
        "source_manifest": {
            "schema_version": PYTHON_RUNTIME_SCHEMA_VERSION,
            "sha256": source_digest,
            "file_count": raw["fileCount"],
            "symlink_count": raw["symlinkCount"],
            "total_bytes": raw["totalBytes"],
            "entries_sha256": _sha256_bytes(portfolio._canonical_json(entries)),
        },
        "python": {
            "version": raw["pythonVersion"],
            "executable_sha256": raw["pythonExecutableSHA256"],
        },
    }


def _runtime_assets(
    *,
    tag: str,
    source: dict[str, str],
    receipt: dict[str, Any],
    receipt_path: Path,
    build_document: dict[str, Any],
    runtime_provenance: dict[str, Any],
    evidence_sha256: str,
    ffprobe: Path,
    ffprobe_version: str,
    repository: Path,
) -> dict[str, Any]:
    worker = receipt["worker"]
    application = receipt["application"]
    result_receipt = receipt["result"]
    toolchain = build_document["toolchain"]
    pinned_model = PINNED_RELEASE_ASSETS["model"]
    pinned_corpus = PINNED_RELEASE_ASSETS["corpus"]
    manifest = {
        "schema_version": 1,
        "tag": tag,
        "source": source,
        "platform": {"system": "macOS", "architecture": "arm64"},
        "python": {
            **runtime_provenance["python"],
        },
        "toolchain": toolchain,
        "ffprobe": {
            "executable_sha256": portfolio._sha256(ffprobe),
            "version": ffprobe_version,
        },
        "lockfiles": [
            {"path": path, "sha256": portfolio._sha256(repository / path)}
            for path in portfolio.LOCKFILE_PATHS
        ],
        "model": {
            "repository": pinned_model["repository"],
            "revision": pinned_model["revision"],
            "license": pinned_model["license"],
            "files": [
                {
                    "path": path,
                    "sha256": value["sha256"],
                    "size_bytes": int(value["bytes"]),
                }
                for path, value in sorted(pinned_model["files"].items())
            ],
        },
        "corpus": {
            "repository": pinned_corpus["repository"],
            "revision": pinned_corpus["revision"],
            "path": pinned_corpus["path"],
            "size_bytes": pinned_corpus["bytes"],
            "sha256": pinned_corpus["sha256"],
            "license": pinned_corpus["license"],
            "source_url": pinned_corpus["source_url"],
        },
        "application": {
            "executable_sha256": application["executableSHA256"]
        },
        "proof": {
            "receipt_sha256": portfolio._sha256(receipt_path),
            "result_sha256": result_receipt["resultFileSHA256"],
            "evidence_sha256": evidence_sha256,
        },
        "verifiers": [
            {"path": path, "sha256": portfolio._sha256(repository / path)}
            for path in portfolio.VERIFIER_PATHS
        ],
    }
    return manifest


def _blind_lifecycle() -> str:
    schema = portfolio._read_json(portfolio.INPUT_SCHEMA)
    try:
        value = schema["properties"]["related_sources"]["properties"][
            "blind_v1_draft"
        ]["properties"]["lifecycle_state"]["const"]
    except (KeyError, TypeError) as error:
        raise CollectionError("tracked release schema has no exact Blind lifecycle") from error
    if not isinstance(value, str) or not value:
        raise CollectionError("tracked Blind lifecycle constant is invalid")
    return value


def _related_sources(lab: Path) -> dict[str, Any]:
    root = _repository(lab)
    if _git(root, "remote", "get-url", "origin") != f"{portfolio.LAB_REPOSITORY}.git":
        raise CollectionError("cross-model lab remote is not canonical")
    return {
        "cross_model_lab": {
            "commit": _git(root, "rev-parse", "refs/remotes/origin/main^{commit}"),
            "tree": _git(root, "rev-parse", "refs/remotes/origin/main^{tree}"),
        },
        "blind_v1_draft": {
            "commit": _git(
                root,
                "rev-parse",
                "refs/remotes/origin/pull/5/head^{commit}",
            ),
            "tree": _git(
                root,
                "rev-parse",
                "refs/remotes/origin/pull/5/head^{tree}",
            ),
            "lifecycle_state": _blind_lifecycle(),
            "pull_request": portfolio.BLIND_PULL_REQUEST,
        },
    }


def _collect_snapshot(
    arguments: argparse.Namespace, repository: Path, run: Path
) -> dict[str, Any]:
    binding = derive_binding(run)
    reports = run / REPORT_DIRECTORY_NAME
    if reports.is_symlink() or not reports.is_dir():
        raise CollectionError("proof report directory is missing or unsafe")
    report_directory_status = reports.stat()
    if (
        report_directory_status.st_uid != os.getuid()
        or stat.S_IMODE(report_directory_status.st_mode) != 0o700
    ):
        raise CollectionError("proof report directory is not private mode 0700")
    expected_report_names = {
        STRUCTURAL_REPORT_NAME,
        REPLAY_REPORT_NAME,
        TERMINAL_LOG_NAME,
    }
    if {path.name for path in reports.iterdir()} != expected_report_names:
        raise CollectionError("proof report directory does not have the exact file set")
    structural_path = reports / STRUCTURAL_REPORT_NAME
    replay_path = reports / REPLAY_REPORT_NAME
    terminal_path = reports / TERMINAL_LOG_NAME
    for report_path, report_label in (
        (structural_path, "structural verifier report"),
        (replay_path, "author-recorded model replay report"),
    ):
        _canonical_regular_input(report_path, portfolio.MAX_JSON_BYTES, report_label)
        report_status = report_path.stat()
        if (
            report_status.st_uid != os.getuid()
            or stat.S_IMODE(report_status.st_mode) != 0o600
        ):
            raise CollectionError(f"{report_label} is not private mode 0600")
    verify_report(structural_path, run, "structural_verifier")
    verify_report(replay_path, run, "fresh_model_replay")
    terminal = _read_terminal(terminal_path, binding["metric_verdict"])

    receipt_path = run / RECEIPT_NAME
    result_path = run / RESULT_NAME
    receipt = read_json_object(receipt_path)
    challenge = receipt.get("challengeNonce")
    verified_result = verify_fresh_run(
        run,
        arguments.app,
        challenge_nonce=challenge,
        require_metric_pass=False,
    )
    expected_metric = "PASS" if verified_result["aggregates"][0]["pass"] else "FAIL"
    if expected_metric != binding["metric_verdict"]:
        raise CollectionError("replayed structural result changed metric outcome")

    build_receipt = receipt["buildProvenance"]
    build_document = build_receipt["document"]
    validate_build_manifest(build_document)
    build_bytes = canonical_build_bytes(build_document)
    if _sha256_bytes(build_bytes) != build_receipt["sha256"]:
        raise CollectionError("build provenance receipt digest changed")
    source_document = build_document["source"]
    source = {
        "commit": source_document["commit"],
        "tree": source_document["tree"],
    }
    if (
        source != binding["source"]
        or source_document.get("remote") != portfolio.CANONICAL_REMOTE
        or source_document.get("exactTag") != arguments.tag
        or source_document.get("dirty") is not False
    ):
        raise CollectionError("proof is not bound to the exact clean portfolio tag")
    if (
        _git(repository, "status", "--porcelain=v1", "--untracked-files=all")
        or _git(repository, "remote", "get-url", "origin")
        != portfolio.CANONICAL_REMOTE
        or _git(repository, "rev-parse", "HEAD^{commit}") != source["commit"]
        or _git(repository, "rev-parse", "HEAD^{tree}") != source["tree"]
    ):
        raise CollectionError("collector checkout differs from proof source")
    tag_object = _git(repository, "rev-parse", f"refs/tags/{arguments.tag}")
    portfolio._verify_signed_tag(
        repository,
        arguments.tag,
        source["commit"],
        source["tree"],
    )

    if not arguments.app.is_absolute() or arguments.app.is_symlink():
        raise CollectionError("app bundle must be an absolute non-symlink path")
    app = arguments.app.resolve(strict=True)
    if app != arguments.app or not app.is_dir():
        raise CollectionError("app bundle path must be canonical")
    executable = app / "Contents" / "MacOS" / "CoreLMBenchmarkApp"
    runtime_path = app / "Contents" / "Resources" / "python-runtime-manifest.json"
    build_path = app / "Contents" / "Resources" / "build-provenance.json"
    for path in (executable, runtime_path, build_path):
        portfolio._require_regular_file(path, 64 * 1024 * 1024)
    if (
        portfolio._sha256(executable)
        != receipt["application"]["executableSHA256"]
        or portfolio._sha256(runtime_path)
        != receipt["worker"]["runtimeManifestSHA256"]
        or build_path.read_bytes() != build_bytes
    ):
        raise CollectionError("app bundle differs from proof receipt")
    runtime_provenance = _public_runtime_provenance(
        runtime_path, receipt, verified_result
    )
    runtime_provenance_bytes = portfolio._canonical_json(runtime_provenance)

    output, staging = _safe_output(arguments.output)
    try:
        source_video = _canonical_regular_input(
            arguments.video,
            portfolio.MAX_VIDEO_BYTES,
            "demo video",
        )
        source_poster = _canonical_regular_input(
            arguments.poster,
            portfolio.MAX_POSTER_BYTES,
            "demo poster",
        )
        video_suffix = source_video.suffix.lower()
        if video_suffix not in {".mov", ".mp4"}:
            raise CollectionError("demo video must use a .mov or .mp4 filename")
        video = staging / f"demo-video{video_suffix}"
        poster = staging / "demo-poster.png"
        portfolio._copy_regular(source_video, video, portfolio.MAX_VIDEO_BYTES)
        portfolio._copy_regular(source_poster, poster, portfolio.MAX_POSTER_BYTES)
        video_identity, ffprobe_version = _probe_video(video, arguments.ffprobe)
        poster_width, poster_height = portfolio._png_dimensions(poster)
        timestamp = arguments.poster_frame_timestamp_seconds
        if (
            not math.isfinite(timestamp)
            or timestamp < 0
            or timestamp > float(video_identity["duration_seconds"])
        ):
            raise CollectionError("poster frame timestamp is outside the video")

        members: dict[str, Path | bytes] = {
            f"run/{RECEIPT_NAME}": receipt_path,
            f"run/{RESULT_NAME}": result_path,
            f"run/{BUILD_PROVENANCE_NAME}": build_bytes,
            f"run/{RUNTIME_PROVENANCE_NAME}": runtime_provenance_bytes,
            "reports/structural-verifier.json": structural_path,
            "reports/fresh-model-replay.json": replay_path,
            "logs/terminal.log": terminal,
        }
        members.update(_primary_members(run))
        evidence = staging / "demo-evidence.tar.gz"
        _write_evidence_archive(evidence, members)
        evidence_sha256 = portfolio._sha256(evidence)

        provenance = {
            "schema_version": 1,
            "tag": arguments.tag,
            "source": source,
            "video": {
                **video_identity,
                "sha256": portfolio._sha256(video),
                "evidence_role": portfolio.MEDIA_CLASSIFICATION,
            },
            "poster": {
                "sha256": portfolio._sha256(poster),
                "width": poster_width,
                "height": poster_height,
                "frame_timestamp_seconds": timestamp,
                "evidence_role": portfolio.MEDIA_CLASSIFICATION,
            },
            "capture": {"platform": "macOS", "architecture": "arm64"},
            "application_executable_sha256": receipt["application"][
                "executableSHA256"
            ],
            "result_sha256": portfolio._sha256(result_path),
            "receipt_sha256": portfolio._sha256(receipt_path),
            "evidence_sha256": evidence_sha256,
            "workload_classification": WORKLOAD_CLASSIFICATION,
            "synthetic_data": False,
        }
        provenance_path = staging / "demo-provenance.json"
        provenance_path.write_bytes(portfolio._canonical_json(provenance))
        provenance_path.chmod(0o600)

        runtime = _runtime_assets(
            tag=arguments.tag,
            source=source,
            receipt=receipt,
            receipt_path=receipt_path,
            build_document=build_document,
            runtime_provenance=runtime_provenance,
            evidence_sha256=evidence_sha256,
            ffprobe=portfolio._resolve_executable(arguments.ffprobe, "ffprobe"),
            ffprobe_version=ffprobe_version,
            repository=repository,
        )
        runtime_assets_path = staging / "runtime-assets.json"
        runtime_assets_path.write_bytes(portfolio._canonical_json(runtime))
        runtime_assets_path.chmod(0o600)

        related = _related_sources(arguments.cross_model_lab)
        release_input = {
            "schema_version": 1,
            "tag": arguments.tag,
            "release_date": arguments.release_date,
            "source": {
                "commit": source["commit"],
                "tag_object": tag_object,
                "tree": source["tree"],
            },
            "continuous_integration": {
                "linux_x86_64": {
                    "commit": source["commit"],
                    "conclusion": "success",
                    "required": True,
                    "url": arguments.linux_ci_url,
                },
                "macos_arm64": {
                    "commit": source["commit"],
                    "conclusion": "success",
                    "required": True,
                    "url": arguments.macos_ci_url,
                },
            },
            "related_sources": related,
            "local_assets": {
                "demo_video": str(output / video.name),
                "demo_poster": str(output / poster.name),
                "demo_provenance": str(output / provenance_path.name),
                "demo_evidence": str(output / evidence.name),
                "runtime_assets": str(output / runtime_assets_path.name),
            },
        }
        portfolio._validate_schema(
            release_input, portfolio.INPUT_SCHEMA, "release input draft"
        )
        portfolio._validate_ci_bindings(release_input)
        portfolio._validate_source(repository, release_input)
        portfolio._validate_related_sources(
            arguments.cross_model_lab, release_input
        )
        release_input_path = staging / "release-input.private.json"
        release_input_path.write_bytes(portfolio._canonical_json(release_input))
        release_input_path.chmod(0o600)

        portfolio._validate_demo_provenance(
            provenance_path,
            tag=arguments.tag,
            commit=source["commit"],
            tree=source["tree"],
            video=video,
            poster=poster,
            evidence=evidence,
        )
        portfolio._validate_runtime_assets(
            runtime_assets_path,
            tag=arguments.tag,
            commit=source["commit"],
            tree=source["tree"],
            provenance=provenance,
            repository=repository,
        )
        portfolio._validate_video(
            video,
            provenance,
            arguments.ffprobe,
            runtime,
            require_recorded_ffprobe=True,
        )
        portfolio._validate_evidence_archive(
            evidence,
            provenance=provenance,
            source=source,
            expected_toolchain=runtime["toolchain"],
            expected_python=runtime["python"],
        )
        for public_asset in (
            video,
            poster,
            provenance_path,
            evidence,
            runtime_assets_path,
        ):
            with public_asset.open("rb") as handle:
                portfolio._assert_public_stream(
                    handle,
                    public_asset.name,
                    reject_absolute_paths=True,
                    strict_credentials=True,
                )
        verify_report(structural_path, run, "structural_verifier")
        verify_report(replay_path, run, "fresh_model_replay")
        staging.rename(output)
        return {
            "status": "PORTFOLIO_DEMO_COLLECTION_PASS",
            "tag": arguments.tag,
            "commit": source["commit"],
            "tree": source["tree"],
            "metric_verdict": binding["metric_verdict"],
            "evidence_sha256": evidence_sha256,
            "video_sha256": provenance["video"]["sha256"],
        }
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def collect(arguments: argparse.Namespace) -> dict[str, Any]:
    repository = _repository(arguments.repository)
    if repository != ROOT:
        raise CollectionError("collector must execute from its exact tracked repository")
    live_run = validated_run_directory(arguments.run_directory)
    with tempfile.TemporaryDirectory(prefix="corelm-sealed-proof-") as temporary:
        snapshot_parent = Path(temporary).resolve(strict=True)
        snapshot_status = snapshot_parent.stat()
        if (
            snapshot_status.st_uid != os.getuid()
            or stat.S_IMODE(snapshot_status.st_mode) != 0o700
        ):
            raise CollectionError("sealed proof parent is not private mode 0700")
        run = _snapshot_run(live_run, snapshot_parent)
        return _collect_snapshot(arguments, repository, run)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--cross-model-lab", type=Path, required=True)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--poster", type=Path, required=True)
    parser.add_argument("--poster-frame-timestamp-seconds", type=float, required=True)
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--release-date", required=True)
    parser.add_argument("--linux-ci-url", required=True)
    parser.add_argument("--macos-ci-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    try:
        result = collect(parse_arguments())
    except (
        CollectionError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
        tarfile.TarError,
    ) as error:
        print(f"PORTFOLIO DEMO COLLECTION FAIL: {error}", file=sys.stderr)
        return 1
    print("PORTFOLIO DEMO COLLECTION PASS")
    print(f"Source commit: {result['commit']}")
    print(f"Source tree: {result['tree']}")
    print(f"Metric verdict: {result['metric_verdict']}")
    print(f"Video SHA-256: {result['video_sha256']}")
    print(f"Evidence SHA-256: {result['evidence_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
