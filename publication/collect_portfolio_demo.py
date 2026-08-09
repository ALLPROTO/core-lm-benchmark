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

from publication import build_portfolio_release as portfolio  # noqa: E402
from RealLLM.pinned_assets import PINNED_RELEASE_ASSETS  # noqa: E402
from security import automated_media  # noqa: E402
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
from security.verify_git_checkout import (  # noqa: E402
    StrictCheckoutError,
    verify_clean_checkout,
)
from security.verify_portfolio_tag_ci import (  # noqa: E402
    DEFAULT_REPOSITORY as TAG_CI_REPOSITORY,
    PUBLIC_RECEIPT_FILENAME,
    RESPONSE_FILENAMES,
    RESPONSE_ROLES,
    TagCIAdmissionError,
    canonical_receipt_bytes as canonical_tag_ci_receipt_bytes,
    read_response_bundle,
    write_response_bundle,
)


RESULT_NAME = "validation-064-071.json"
RECEIPT_NAME = "app-run-receipt.json"
BUILD_PROVENANCE_NAME = "build-provenance.json"
RUNTIME_PROVENANCE_NAME = "runtime-provenance.json"
PYTHON_CACHE_DIRECTORY_NAME = "python-cache"
MAX_TERMINAL_BYTES = 4096


class CollectionError(ValueError):
    """A fail-closed demo collection error."""


def _fixed_metric_text(value: Any, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CollectionError(f"{label} is not numeric")
    observed = float(value)
    if not math.isfinite(observed):
        raise CollectionError(f"{label} is non-finite")
    return f"{observed:.6f}"


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


def _canonical_owner_directory(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise CollectionError(f"{label} must be an absolute non-symlink directory")
    try:
        resolved = path.resolve(strict=True)
        status = path.lstat()
    except OSError as error:
        raise CollectionError(f"{label} is unavailable") from error
    if (
        resolved != path
        or not stat.S_ISDIR(status.st_mode)
        or status.st_uid != os.getuid()
        or stat.S_IMODE(status.st_mode) != 0o700
    ):
        raise CollectionError(f"{label} is not a canonical owner-only directory")
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
            "-show_chapters",
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
    if audios or len(streams) != 1 or report.get("chapters", []) != []:
        raise CollectionError(
            "automated demo must contain one video stream and no audio, chapters, or extra streams"
        )
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
            "audio_codec": "silent",
        },
        version,
    )


def _tool_version(executable: Path, label: str) -> tuple[Path, str]:
    resolved = portfolio._resolve_executable(executable, label)
    completed = portfolio._run(
        (str(resolved), "-version"), cwd=resolved.parent, timeout=30
    )
    if completed.returncode != 0:
        raise CollectionError(f"{label} version query failed")
    try:
        first = completed.stdout.decode("utf-8").splitlines()[0]
    except (UnicodeDecodeError, IndexError) as error:
        raise CollectionError(f"{label} version identity is unavailable") from error
    prefix = f"{label} version "
    if (
        not first.startswith(prefix)
        or len(first.encode("utf-8")) > 1024
        or "\r" in first
    ):
        raise CollectionError(f"{label} version identity is malformed")
    return resolved, first


def _verify_poster_from_video(
    video: Path, poster: Path, ffmpeg: Path
) -> None:
    with tempfile.TemporaryDirectory(prefix="corelm-poster-replay-") as temporary:
        root = Path(temporary).resolve(strict=True)
        replay = root / "poster.png"
        completed = portfolio._run(
            (
                str(ffmpeg),
                "-v",
                "error",
                "-ss",
                f"{automated_media.POSTER_TIMESTAMP_SECONDS:.6f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-an",
                "-map_metadata",
                "-1",
                "-compression_level",
                "9",
                "-pred",
                "mixed",
                str(replay),
            ),
            cwd=root,
            timeout=60,
        )
        if completed.returncode != 0 or not replay.is_file():
            raise CollectionError("fixed poster-frame replay failed")
        portfolio._require_regular_file(replay, portfolio.MAX_POSTER_BYTES)
        if replay.read_bytes() != poster.read_bytes():
            raise CollectionError("poster bytes are not the fixed final-video frame")


def _decoded_video_identity(
    video: Path,
    ffmpeg: Path,
    ffprobe: Path,
    *,
    width: int,
    height: int,
) -> dict[str, Any]:
    probe = portfolio._run(
        (
            str(ffprobe),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_frames",
            "-show_entries",
            "frame=best_effort_timestamp_time,duration_time,width,height",
            "-of",
            "json",
            str(video),
        ),
        cwd=video.parent,
        timeout=120,
    )
    if probe.returncode != 0:
        raise CollectionError("ffprobe frame enumeration failed")
    try:
        parsed = json.loads(probe.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CollectionError("ffprobe frame enumeration is malformed") from error
    frames = parsed.get("frames") if isinstance(parsed, dict) else None
    try:
        frame_count, pts_sha256 = automated_media.frame_pts_identity(
            frames, width=width, height=height
        )
    except automated_media.AutomatedMediaError as error:
        raise CollectionError("decoded frame PTS identity is invalid") from error
    decoded = portfolio._run(
        (
            str(ffmpeg),
            "-v",
            "error",
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-f",
            "framemd5",
            "-",
        ),
        cwd=video.parent,
        timeout=120,
    )
    if decoded.returncode != 0 or not decoded.stdout:
        raise CollectionError("decoded frame digest replay failed")
    return {
        "frame_count": frame_count,
        "pts_sha256": pts_sha256,
        "decoded_frames_sha256": _sha256_bytes(decoded.stdout),
    }


def _raw_segment_identity(
    path: Path,
    ffmpeg: Path,
    ffprobe: Path,
) -> dict[str, Any]:
    portfolio._validate_mp4_atoms(path)
    completed = portfolio._run(
        (
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-show_chapters",
            "-of",
            "json",
            str(path),
        ),
        cwd=path.parent,
        timeout=120,
    )
    if completed.returncode != 0:
        raise CollectionError("ffprobe rejected a retained raw segment")
    try:
        value = json.loads(completed.stdout.decode("utf-8"))
        streams = value["streams"]
        duration = float(value["format"]["duration"])
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise CollectionError("retained raw segment metadata is malformed") from error
    videos = [
        row
        for row in streams
        if isinstance(row, dict) and row.get("codec_type") == "video"
    ] if isinstance(streams, list) else []
    if (
        len(videos) != 1
        or len(streams) != 1
        or value.get("chapters", []) != []
        or type(videos[0].get("width")) is not int
        or type(videos[0].get("height")) is not int
        or not math.isfinite(duration)
        or duration <= 0
        or duration > 90
    ):
        raise CollectionError("retained raw segment topology is invalid")
    decoded = _decoded_video_identity(
        path,
        ffmpeg,
        ffprobe,
        width=videos[0]["width"],
        height=videos[0]["height"],
    )
    return {
        "sha256": portfolio._sha256(path),
        "duration_seconds": duration,
        "width": videos[0]["width"],
        "height": videos[0]["height"],
        "frame_count": decoded["frame_count"],
        "pts_sha256": decoded["pts_sha256"],
    }


def _composition_argv(
    ffmpeg: Path,
    post_proof_presentation: Path,
    result: Path,
    video: Path,
) -> tuple[str, ...]:
    common = (
        f"fps={automated_media.OUTPUT_FRAME_RATE},"
        f"scale={automated_media.OUTPUT_WIDTH}:{automated_media.OUTPUT_HEIGHT}:"
        "force_original_aspect_ratio=decrease,"
        f"pad={automated_media.OUTPUT_WIDTH}:{automated_media.OUTPUT_HEIGHT}:"
        "(ow-iw)/2:(oh-ih)/2:color=0x111318,setsar=1"
    )
    presentation_seconds = (
        automated_media.POST_PROOF_PRESENTATION_SEGMENT_SECONDS
    )
    result_seconds = automated_media.RESULT_SEGMENT_SECONDS
    filter_value = (
        f"[0:v]{common},tpad=stop_mode=clone:stop_duration={presentation_seconds:g},"
        f"trim=duration={presentation_seconds:g},setpts=PTS-STARTPTS[presentation];"
        f"[1:v]{common},tpad=stop_mode=clone:stop_duration={result_seconds:g},"
        f"trim=duration={result_seconds:g},setpts=PTS-STARTPTS[result];"
        "[presentation][result]concat=n=2:v=1:a=0[outv]"
    )
    return (
        str(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(post_proof_presentation), "-i", str(result),
        "-filter_complex", filter_value,
        "-map", "[outv]", "-an", "-c:v", "h264_videotoolbox", "-b:v", "8M",
        "-pix_fmt", "yuv420p", "-r", str(automated_media.OUTPUT_FRAME_RATE),
        "-fflags", "+bitexact", "-flags:v", "+bitexact", "-map_metadata", "-1",
        "-map_chapters", "-1", "-metadata", "title=", "-metadata", "comment=",
        "-metadata", "creation_time=", "-metadata", "encoder=",
        "-metadata:s:v:0", "title=", "-metadata:s:v:0", "encoder=",
        "-empty_hdlr_name", "1", "-movflags", "+faststart", str(video),
    )


def _verify_composition_from_raw(
    *,
    post_proof_presentation: Path,
    result: Path,
    video: Path,
    poster: Path,
    ffmpeg: Path,
) -> None:
    with tempfile.TemporaryDirectory(prefix="corelm-composition-replay-") as temporary:
        root = Path(temporary).resolve(strict=True)
        replay_video = root / "recomposed.mp4"
        completed = portfolio._run(
            _composition_argv(
                ffmpeg, post_proof_presentation, result, replay_video
            ),
            cwd=root,
            timeout=300,
        )
        if completed.returncode != 0 or not replay_video.is_file():
            raise CollectionError("fixed raw-segment composition replay failed")
        portfolio._require_regular_file(replay_video, portfolio.MAX_VIDEO_BYTES)
        if replay_video.read_bytes() != video.read_bytes():
            raise CollectionError("final video bytes are not the exact raw composition")
        replay_poster = root / "poster.png"
        poster_result = portfolio._run(
            (
                str(ffmpeg), "-v", "error", "-ss",
                f"{automated_media.POSTER_TIMESTAMP_SECONDS:.6f}",
                "-i", str(replay_video), "-frames:v", "1", "-an",
                "-map_metadata", "-1", "-compression_level", "9",
                "-pred", "mixed", str(replay_poster),
            ),
            cwd=root,
            timeout=120,
        )
        if poster_result.returncode != 0 or not replay_poster.is_file():
            raise CollectionError("fixed raw-composition poster replay failed")
        if replay_poster.read_bytes() != poster.read_bytes():
            raise CollectionError("poster bytes are not derived from raw composition")


def _copy_private_regular(source: Path, destination: Path, maximum_bytes: int) -> None:
    portfolio._copy_regular(source, destination, maximum_bytes)
    destination.chmod(0o600)
    if stat.S_IMODE(destination.stat().st_mode) != 0o600:
        raise CollectionError("private evidence staging mode is not 0600")


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
    automation_report: dict[str, Any],
    repository: Path,
) -> dict[str, Any]:
    worker = receipt["worker"]
    application = receipt["application"]
    result_receipt = receipt["result"]
    toolchain = build_document["toolchain"]
    pinned_model = PINNED_RELEASE_ASSETS["model"]
    pinned_corpus = PINNED_RELEASE_ASSETS["corpus"]
    manifest = {
        "schema_version": 2,
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
        "capture_tools": automation_report["tools"],
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
    try:
        verify_clean_checkout(
            repository,
            expected_commit=source["commit"],
            expected_tree=source["tree"],
            expected_origins={portfolio.CANONICAL_REMOTE},
            expected_branch="main",
            expected_upstream="origin/main",
        )
    except StrictCheckoutError as error:
        raise CollectionError(
            "collector checkout differs from the exact signed proof source tree"
        ) from error
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
        source_automation = _canonical_regular_input(
            arguments.automation_receipt,
            automated_media.MAX_REPORT_BYTES,
            "automation receipt",
        )
        source_readiness = _canonical_regular_input(
            arguments.result_readiness,
            automated_media.MAX_READINESS_BYTES,
            "result readiness receipt",
        )
        source_attempt_state = _canonical_regular_input(
            arguments.attempt_state,
            automated_media.MAX_ATTEMPT_STATE_BYTES,
            "attempt-state snapshot",
        )
        source_preflight = _canonical_regular_input(
            arguments.preflight_segment,
            portfolio.MAX_VIDEO_BYTES,
            "preflight raw segment",
        )
        source_post_proof_presentation = _canonical_regular_input(
            arguments.post_proof_presentation_segment,
            portfolio.MAX_VIDEO_BYTES,
            "post-proof presentation raw segment",
        )
        source_result_segment = _canonical_regular_input(
            arguments.result_segment,
            portfolio.MAX_VIDEO_BYTES,
            "same-run result raw segment",
        )
        source_helper = _canonical_regular_input(
            arguments.window_helper,
            128 * 1024 * 1024,
            "compiled window helper",
        )
        if not source_helper.stat().st_mode & stat.S_IXUSR:
            raise CollectionError("compiled window helper is not executable")
        source_tag_ci = _canonical_regular_input(
            arguments.tag_ci_receipt,
            portfolio.MAX_JSON_BYTES,
            "tag-CI receipt",
        )
        if not isinstance(portfolio._read_canonical_json(source_tag_ci), dict):
            raise CollectionError("tag-CI receipt root is malformed")
        source_local_tag_trust = _canonical_regular_input(
            arguments.local_tag_trust_receipt,
            automated_media.MAX_READINESS_BYTES,
            "local tag trust receipt",
        )
        source_tag_ci_bundle = _canonical_owner_directory(
            arguments.tag_ci_bundle, "tag-CI response bundle"
        )
        try:
            tag_ci_responses, recomputed_tag_ci = read_response_bundle(
                source_tag_ci_bundle,
                repository=TAG_CI_REPOSITORY,
                expected_tag=arguments.tag,
                expected_commit=source["commit"],
                expected_tree=source["tree"],
            )
        except TagCIAdmissionError as error:
            raise CollectionError("tag-CI response bundle is invalid") from error
        if source_tag_ci.read_bytes() != canonical_tag_ci_receipt_bytes(
            recomputed_tag_ci
        ):
            raise CollectionError("tag-CI receipt differs from recomputed response bundle")
        if recomputed_tag_ci["source"]["annotated_tag_object"] != tag_object:
            raise CollectionError(
                "public tag-CI annotated object differs from the signed local tag object"
            )
        video_suffix = source_video.suffix.lower()
        if video_suffix not in {".mov", ".mp4"}:
            raise CollectionError("demo video must use a .mov or .mp4 filename")
        video = staging / f"demo-video{video_suffix}"
        poster = staging / "demo-poster.png"
        automation_path = staging / "automation-receipt.json"
        readiness_path = staging / "result-readiness.json"
        attempt_state_path = staging / "attempt-state.jsonl"
        preflight_path = staging / "preflight-window.mov"
        post_proof_presentation_path = staging / "post-proof-presentation.mov"
        result_segment_path = staging / "same-run-result.mov"
        helper_path = staging / "find-proof-window"
        tag_ci_path = staging / "tag-ci-receipt.json"
        local_tag_trust_path = staging / "local-tag-trust-receipt.json"
        tag_ci_bundle_path = staging / "tag-ci-bundle"
        portfolio._copy_regular(source_video, video, portfolio.MAX_VIDEO_BYTES)
        portfolio._copy_regular(source_poster, poster, portfolio.MAX_POSTER_BYTES)
        _copy_private_regular(
            source_automation, automation_path, automated_media.MAX_REPORT_BYTES
        )
        _copy_private_regular(
            source_readiness, readiness_path, automated_media.MAX_READINESS_BYTES
        )
        _copy_private_regular(
            source_attempt_state,
            attempt_state_path,
            automated_media.MAX_ATTEMPT_STATE_BYTES,
        )
        _copy_private_regular(
            source_preflight, preflight_path, portfolio.MAX_VIDEO_BYTES
        )
        _copy_private_regular(
            source_post_proof_presentation,
            post_proof_presentation_path,
            portfolio.MAX_VIDEO_BYTES,
        )
        _copy_private_regular(
            source_result_segment, result_segment_path, portfolio.MAX_VIDEO_BYTES
        )
        _copy_private_regular(source_helper, helper_path, 128 * 1024 * 1024)
        _copy_private_regular(source_tag_ci, tag_ci_path, portfolio.MAX_JSON_BYTES)
        _copy_private_regular(
            source_local_tag_trust,
            local_tag_trust_path,
            automated_media.MAX_READINESS_BYTES,
        )
        try:
            write_response_bundle(
                tag_ci_bundle_path, tag_ci_responses, recomputed_tag_ci
            )
        except TagCIAdmissionError as error:
            raise CollectionError("tag-CI response bundle could not be sealed") from error
        video_identity, ffprobe_version = _probe_video(video, arguments.ffprobe)
        poster_width, poster_height = portfolio._png_dimensions(poster)
        automation_report = automated_media.read_canonical_report(automation_path)
        if automation_report.get("schema_version") != automated_media.SCHEMA_VERSION:
            raise CollectionError("automation receipt schema is not exact")
        readiness = automated_media.read_canonical_readiness(readiness_path)
        receipt_sha256 = portfolio._sha256(receipt_path)
        result_sha256 = portfolio._sha256(result_path)
        video_sha256 = portfolio._sha256(video)
        poster_sha256 = portfolio._sha256(poster)
        try:
            receipt_result = receipt["result"]
            automated_media.validate_readiness(
                readiness,
                expected={
                    "run_identifier": run.name,
                    "receipt_sha256": receipt_sha256,
                    "result_sha256": result_sha256,
                    "application_executable_sha256": receipt["application"][
                        "executableSHA256"
                    ],
                    "metric_verdict": binding["metric_verdict"],
                    "compression_ratio_vs_bf16": _fixed_metric_text(
                        receipt_result["compressionRatioVsBF16"],
                        "readiness compression ratio",
                    ),
                    "delta_nll_nat_per_token": _fixed_metric_text(
                        receipt_result["deltaNLLNatPerToken"],
                        "readiness delta NLL",
                    ),
                    "top1_agreement": _fixed_metric_text(
                        receipt_result["top1Agreement"],
                        "readiness top-1 agreement",
                    ),
                },
            )
            automated_media.validate_report(
                automation_report,
                expected={
                    "tag": arguments.tag,
                    "commit": source["commit"],
                    "tree": source["tree"],
                    "run_identifier": run.name,
                    "challenge_sha256": automated_media.challenge_sha256(challenge),
                    "receipt_sha256": receipt_sha256,
                    "result_sha256": result_sha256,
                    "application_executable_sha256": receipt["application"][
                        "executableSHA256"
                    ],
                    "metric_verdict": binding["metric_verdict"],
                    "video_sha256": video_sha256,
                    "poster_sha256": poster_sha256,
                    "duration_seconds": video_identity["duration_seconds"],
                    "width": video_identity["width"],
                    "height": video_identity["height"],
                    "frame_count": automation_report["output"]["frame_count"],
                    "poster_frame_timestamp_seconds": automated_media.POSTER_TIMESTAMP_SECONDS,
                    "result_readiness_sha256": portfolio._sha256(readiness_path),
                    "attempt_state_sha256": portfolio._sha256(attempt_state_path),
                    "tag_ci_receipt_sha256": portfolio._sha256(tag_ci_path),
                    "local_tag_trust_receipt_sha256": portfolio._sha256(
                        local_tag_trust_path
                    ),
                    "preflight_segment_sha256": portfolio._sha256(preflight_path),
                    "post_proof_presentation_segment_sha256": portfolio._sha256(
                        post_proof_presentation_path
                    ),
                    "result_segment_sha256": portfolio._sha256(result_segment_path),
                    "window_helper_sha256": portfolio._sha256(helper_path),
                },
            )
            automated_media.validate_tag_ci_receipt_bytes(
                tag_ci_path.read_bytes(),
                expected={
                    "repository": "ALLPROTO/core-lm-benchmark",
                    "tag": arguments.tag,
                    "commit": source["commit"],
                    "tree": source["tree"],
                },
            )
            automated_media.validate_local_tag_trust_receipt_bytes(
                local_tag_trust_path.read_bytes(),
                expected={
                    "tag": arguments.tag,
                    "tag_object": recomputed_tag_ci["source"][
                        "annotated_tag_object"
                    ],
                    "commit": source["commit"],
                    "tree": source["tree"],
                },
            )
        except automated_media.AutomatedMediaError as error:
            raise CollectionError(
                "automation receipt does not bind the exact retained proof and media"
            ) from error
        output_identity = automation_report["output"]
        timestamp = output_identity["poster_frame_timestamp_seconds"]
        if (
            not math.isclose(
                float(output_identity["duration_seconds"]),
                float(video_identity["duration_seconds"]),
                rel_tol=0,
                abs_tol=0.1,
            )
            or (output_identity["width"], output_identity["height"])
            != (video_identity["width"], video_identity["height"])
            or (poster_width, poster_height)
            != (video_identity["width"], video_identity["height"])
        ):
            raise CollectionError("automation receipt media dimensions/duration differ")
        ffmpeg, ffmpeg_version = _tool_version(arguments.ffmpeg, "ffmpeg")
        ffprobe = portfolio._resolve_executable(arguments.ffprobe, "ffprobe")
        observed_tools = automation_report["tools"]
        if observed_tools["ffmpeg"] != {
            "executable_sha256": portfolio._sha256(ffmpeg),
            "version": ffmpeg_version,
        } or observed_tools["ffprobe"] != {
            "executable_sha256": portfolio._sha256(ffprobe),
            "version": ffprobe_version,
        }:
            raise CollectionError("automation receipt media tool identity changed")
        _verify_poster_from_video(video, poster, ffmpeg)
        raw_paths = (
            preflight_path,
            post_proof_presentation_path,
            result_segment_path,
        )
        raw_records = (
            automation_report["capture"]["preflight_segment"],
            *automation_report["capture"]["segments"],
        )
        for raw_path, record in zip(raw_paths, raw_records, strict=True):
            observed_raw = _raw_segment_identity(raw_path, ffmpeg, ffprobe)
            for key in ("sha256", "width", "height", "frame_count", "pts_sha256"):
                if observed_raw[key] != record[key]:
                    raise CollectionError(
                        f"retained {record['role']} raw segment differs from report"
                    )
            if not math.isclose(
                observed_raw["duration_seconds"],
                float(record["duration_seconds"]),
                rel_tol=0,
                abs_tol=1e-6,
            ):
                raise CollectionError(
                    f"retained {record['role']} raw duration differs from report"
                )
        if observed_tools["window_helper"]["executable_sha256"] != portfolio._sha256(
            helper_path
        ):
            raise CollectionError("compiled window helper bytes changed")
        if automation_report["attempt"]["tag_ci_receipt_sha256"] != portfolio._sha256(
            tag_ci_path
        ):
            raise CollectionError("tag-CI receipt bytes changed")
        if automation_report["attempt"][
            "local_tag_trust_receipt_sha256"
        ] != portfolio._sha256(local_tag_trust_path):
            raise CollectionError("local tag trust receipt bytes changed")
        try:
            attempt_events = automated_media.read_canonical_attempt_state(
                attempt_state_path, report=automation_report
            )
        except automated_media.AutomatedMediaError as error:
            raise CollectionError("attempt-state snapshot is not report-bound") from error
        if any(
            event.get("schema_version")
            != automated_media.ATTEMPT_STATE_SCHEMA_VERSION
            for event in attempt_events
        ):
            raise CollectionError("attempt-state schema is not exact")
        _verify_composition_from_raw(
            post_proof_presentation=post_proof_presentation_path,
            result=result_segment_path,
            video=video,
            poster=poster,
            ffmpeg=ffmpeg,
        )
        for retained_session_asset in (
            attempt_state_path,
            preflight_path,
            post_proof_presentation_path,
            result_segment_path,
            helper_path,
            tag_ci_path,
            local_tag_trust_path,
            readiness_path,
        ):
            with retained_session_asset.open("rb") as handle:
                portfolio._assert_public_stream(
                    handle,
                    f"retained session {retained_session_asset.name}",
                    reject_absolute_paths=True,
                    strict_credentials=True,
                )
        for tag_ci_member in tag_ci_bundle_path.iterdir():
            with tag_ci_member.open("rb") as handle:
                portfolio._assert_public_stream(
                    handle,
                    f"retained tag-CI response {tag_ci_member.name}",
                    reject_absolute_paths=True,
                    strict_credentials=True,
                )
        decoded_identity = _decoded_video_identity(
            video,
            ffmpeg,
            ffprobe,
            width=video_identity["width"],
            height=video_identity["height"],
        )
        if any(
            output_identity[key] != value
            for key, value in decoded_identity.items()
        ):
            raise CollectionError("automation receipt decoded-frame identity changed")
        helper_source = repository / "platforms/macos/scripts/find-proof-window.swift"
        if observed_tools["window_helper"]["source_sha256"] != portfolio._sha256(
            helper_source
        ):
            raise CollectionError("automation receipt window helper source changed")
        screencapture = Path("/usr/sbin/screencapture")
        if observed_tools["screencapture"]["executable_sha256"] != portfolio._sha256(
            screencapture
        ):
            raise CollectionError("automation receipt screencapture identity changed")

        members: dict[str, Path | bytes] = {
            f"run/{RECEIPT_NAME}": receipt_path,
            f"run/{RESULT_NAME}": result_path,
            f"run/{BUILD_PROVENANCE_NAME}": build_bytes,
            f"run/{RUNTIME_PROVENANCE_NAME}": runtime_provenance_bytes,
            "reports/structural-verifier.json": structural_path,
            "reports/fresh-model-replay.json": replay_path,
            "reports/automated-media.json": automation_path,
            "reports/result-readiness.json": readiness_path,
            "reports/tag-ci-receipt.json": tag_ci_path,
            "reports/local-tag-trust-receipt.json": local_tag_trust_path,
            "session/attempt-state.jsonl": attempt_state_path,
            "session/preflight-window.mov": preflight_path,
            "session/post-proof-presentation.mov": post_proof_presentation_path,
            "session/same-run-result.mov": result_segment_path,
            "session/find-proof-window": helper_path,
            "logs/terminal.log": terminal,
        }
        for role in RESPONSE_ROLES:
            filename = RESPONSE_FILENAMES[role]
            members[f"tag-ci-responses/{filename}"] = tag_ci_bundle_path / filename
        members[
            f"tag-ci-responses/{PUBLIC_RECEIPT_FILENAME}"
        ] = tag_ci_bundle_path / PUBLIC_RECEIPT_FILENAME
        members.update(_primary_members(run))
        evidence = staging / "demo-evidence.tar.gz"
        _write_evidence_archive(evidence, members)
        evidence_sha256 = portfolio._sha256(evidence)

        provenance = {
            "schema_version": 2,
            "tag": arguments.tag,
            "source": source,
            "video": {
                **video_identity,
                "sha256": video_sha256,
                "evidence_role": portfolio.MEDIA_CLASSIFICATION,
            },
            "poster": {
                "sha256": poster_sha256,
                "width": poster_width,
                "height": poster_height,
                "frame_timestamp_seconds": timestamp,
                "evidence_role": portfolio.MEDIA_CLASSIFICATION,
            },
            "capture": {
                "platform": "macOS",
                "architecture": "arm64",
                "automation_contract": automated_media.AUTOMATION_CONTRACT,
                "mode": automated_media.CAPTURE_MODE,
                "automation_only": True,
                "human_reviewed": False,
                "manual_edits": False,
                "machine_evidence": False,
                "pixel_semantics_verified": False,
                "automation_receipt_sha256": portfolio._sha256(automation_path),
                "result_readiness_sha256": automation_report["capture"][
                    "result_readiness_sha256"
                ],
            },
            "application_executable_sha256": receipt["application"][
                "executableSHA256"
            ],
            "result_sha256": result_sha256,
            "receipt_sha256": receipt_sha256,
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
            ffprobe=ffprobe,
            ffprobe_version=ffprobe_version,
            automation_report=automation_report,
            repository=repository,
        )
        runtime_assets_path = staging / "runtime-assets.json"
        runtime_assets_path.write_bytes(portfolio._canonical_json(runtime))
        runtime_assets_path.chmod(0o600)

        related = _related_sources(arguments.cross_model_lab)
        release_input = {
            "schema_version": 2,
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
                    "url": recomputed_tag_ci["workflows"][0]["html_url"],
                },
                "macos_arm64": {
                    "commit": source["commit"],
                    "conclusion": "success",
                    "required": True,
                    "url": recomputed_tag_ci["workflows"][1]["html_url"],
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
            "presentation": portfolio.PRESENTATION_CONTRACT,
        }
        portfolio._validate_schema(
            release_input, portfolio.INPUT_SCHEMA, "release input draft"
        )
        portfolio._validate_ci_bindings(release_input, recomputed_tag_ci)
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
            automation_report=automation_report,
        )
        portfolio._validate_video(
            video,
            provenance,
            arguments.ffprobe,
            runtime,
            require_recorded_ffprobe=True,
        )
        validated_automation_report = portfolio._validate_evidence_archive(
            evidence,
            provenance=provenance,
            source=source,
            expected_toolchain=runtime["toolchain"],
            expected_python=runtime["python"],
        )
        if validated_automation_report != automation_report:
            raise CollectionError("automation receipt changed across collection")
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
    parser.add_argument("--automation-receipt", type=Path, required=True)
    parser.add_argument("--result-readiness", type=Path, required=True)
    parser.add_argument("--attempt-state", type=Path, required=True)
    parser.add_argument("--preflight-segment", type=Path, required=True)
    parser.add_argument(
        "--post-proof-presentation-segment", type=Path, required=True
    )
    parser.add_argument("--result-segment", type=Path, required=True)
    parser.add_argument("--window-helper", type=Path, required=True)
    parser.add_argument("--tag-ci-receipt", type=Path, required=True)
    parser.add_argument("--local-tag-trust-receipt", type=Path, required=True)
    parser.add_argument("--tag-ci-bundle", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--release-date", required=True)
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
