#!/usr/bin/env python3
"""Run one durable, automation-only tagged macOS portfolio demonstration.

The proof is invoked exactly once within the retained owner-local session.
Capture or media failures consume that local per-tag attempt and preserve its
state; this command never retries a proof to obtain a preferred metric or
presentation outcome.  This is not a global or historical impossibility claim.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence
import uuid


ROOT = Path(__file__).resolve().parents[3]


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

sys.path.insert(0, str(ROOT))

from security import automated_media  # noqa: E402
from security.proof_reports import (  # noqa: E402
    REPLAY_REPORT_NAME,
    REPORT_DIRECTORY_NAME,
    STRUCTURAL_REPORT_NAME,
    TERMINAL_LOG_NAME,
    derive_binding,
    verify_report,
)
from security.verify_app_run_evidence import verify_fresh_run  # noqa: E402
from security.verify_git_checkout import (  # noqa: E402
    StrictCheckoutError,
    verify_clean_checkout,
)
from security.verify_portfolio_tag_ci import (  # noqa: E402
    DEFAULT_REPOSITORY as TAG_CI_REPOSITORY,
    LOCAL_TRUST_RECEIPT_FILENAME,
    PUBLIC_RECEIPT_FILENAME,
    TagCIAdmissionError,
    canonical_receipt_bytes as canonical_tag_ci_receipt_bytes,
    fetch_public_tag_ci_responses,
    read_response_bundle,
    validate_saved_tag_ci,
    verify_local_tag_trust,
    write_response_bundle,
)


WINDOW_HELPER_SOURCE = ROOT / "platforms/macos/scripts/find-proof-window.swift"
APP_BUNDLE = ROOT / "dist/CoreLMBenchmark.app"
APP_EXECUTABLE = APP_BUNDLE / "Contents/MacOS/CoreLMBenchmarkApp"
ALLOWED_SIGNERS = ROOT / "signing/allowed_signers"
SCREENCAPTURE = Path("/usr/sbin/screencapture")
GIT = "/usr/bin/git"
XCRUN = "/usr/bin/xcrun"
CODESIGN = "/usr/bin/codesign"
PMSET = "/usr/bin/pmset"
MEMORY_PRESSURE = "/usr/bin/memory_pressure"
CANONICAL_REMOTES = frozenset(
    {
        "https://github.com/ALLPROTO/core-lm-benchmark",
        "https://github.com/ALLPROTO/core-lm-benchmark.git",
    }
)
MINIMUM_AVAILABLE_MEMORY_PERCENT = 50
MINIMUM_AVAILABLE_DISK_BYTES = 12 * 1024 * 1024 * 1024
OUTPUT_WIDTH = 1280
OUTPUT_HEIGHT = 720
OUTPUT_FRAME_RATE = 30
EXPECTED_FRAME_COUNT = int(
    (
        automated_media.POST_PROOF_PRESENTATION_SEGMENT_SECONDS
        + automated_media.RESULT_SEGMENT_SECONDS
    )
    * OUTPUT_FRAME_RATE
)
RESULT_WINDOW_WAIT_SECONDS = 30
RESULT_READINESS_WAIT_SECONDS = 30
PROOF_WAIT_SECONDS = 1_200
MAX_MEDIA_BYTES = 2 * 1024 * 1024 * 1024
TAG_PATTERN = re.compile(r"corelm-portfolio-v([1-9][0-9]*)\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
PRIVATE_BYTE_PATTERNS = (
    re.compile(rb"/Users/"),
    re.compile(rb"/home/"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9_]+"),
    re.compile(rb"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
)


class AutomatedDemoError(ValueError):
    """A fail-closed automated-demo orchestration error."""


@dataclass(frozen=True)
class Configuration:
    tag: str
    output: Path
    ffmpeg: Path
    ffprobe: Path
    home: Path
    wheelhouse: Path


@dataclass(frozen=True)
class SourceIdentity:
    tag: str
    commit: str
    tree: str


@dataclass(frozen=True)
class PreparedTools:
    staging: Path
    helper: Path
    report: dict[str, Any]
    preflight_capture: "CaptureSegment | None" = None
    tag_ci_receipt_sha256: str = ""
    local_tag_trust_receipt_sha256: str = ""


@dataclass(frozen=True)
class WindowIdentity:
    pid: int
    window_id: int
    width: float
    height: float
    executable_path: str | None
    executable_sha256: str | None
    x: float = 0.0
    y: float = 0.0


@dataclass(frozen=True)
class CaptureSegment:
    role: str
    owner_pid: int
    window_id: int
    width: int
    height: int
    duration_seconds: float
    sha256: str
    requested_duration_seconds: float | None = None
    frame_count: int = 1
    pts_sha256: str = "0" * 64

    def report(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "owner_pid": self.owner_pid,
            "window_id": self.window_id,
            "width": self.width,
            "height": self.height,
            "requested_duration_seconds": (
                self.duration_seconds
                if self.requested_duration_seconds is None
                else self.requested_duration_seconds
            ),
            "duration_seconds": self.duration_seconds,
            "frame_count": self.frame_count,
            "pts_sha256": self.pts_sha256,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class ProofIdentity:
    run_directory: Path
    identifier: str
    challenge_sha256: str
    receipt_sha256: str
    result_sha256: str
    application_executable_sha256: str
    metric_verdict: str
    terminal_outcome: str
    compression_ratio_vs_bf16: str
    delta_nll_nat_per_token: str
    top1_agreement: str


@dataclass(frozen=True)
class ReadinessIdentity:
    sha256: str
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass(frozen=True)
class MediaIdentity:
    video: Path
    poster: Path
    video_sha256: str
    poster_sha256: str
    duration_seconds: float
    width: int
    height: int
    frame_count: int
    pts_sha256: str
    decoded_frames_sha256: str


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    return automated_media.canonical_json_bytes(value)


def _safe_environment(home: Path | None = None) -> dict[str, str]:
    return {
        "HOME": str(home) if home is not None else "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }


def _run(
    arguments: Sequence[str],
    *,
    cwd: Path = ROOT,
    env: Mapping[str, str] | None = None,
    timeout: float = 60,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            list(arguments),
            cwd=cwd,
            env=dict(env) if env is not None else _safe_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AutomatedDemoError(
            f"command failed to execute: {Path(arguments[0]).name}"
        ) from error


def _decoded_stdout(completed: subprocess.CompletedProcess[bytes], label: str) -> str:
    if completed.returncode != 0:
        raise AutomatedDemoError(f"{label} failed")
    try:
        return completed.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise AutomatedDemoError(f"{label} returned non-UTF-8 output") from error


def _git(*arguments: str) -> str:
    completed = _run(
        (
            GIT,
            "--no-replace-objects",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            *arguments,
        ),
        cwd=ROOT,
    )
    return _decoded_stdout(completed, f"Git {' '.join(arguments[:2])}")


def _require_regular(
    path: Path,
    label: str,
    *,
    executable: bool = False,
    maximum_bytes: int = MAX_MEDIA_BYTES,
) -> os.stat_result:
    if not path.is_absolute() or path.is_symlink():
        raise AutomatedDemoError(f"{label} must be an absolute non-symlink file")
    try:
        resolved = path.resolve(strict=True)
        status = path.lstat()
    except OSError as error:
        raise AutomatedDemoError(f"{label} is unavailable") from error
    if (
        resolved != path
        or not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_nlink != 1
        or status.st_size <= 0
        or status.st_size > maximum_bytes
        or (executable and not status.st_mode & stat.S_IXUSR)
    ):
        raise AutomatedDemoError(f"{label} is not a bounded regular file")
    return status


def _resolve_tool(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise AutomatedDemoError(f"{label} path must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise AutomatedDemoError(f"{label} is unavailable") from error
    _require_regular(resolved, label, executable=True, maximum_bytes=128 * 1024 * 1024)
    return resolved


def _validate_configuration(arguments: argparse.Namespace) -> Configuration:
    match = TAG_PATTERN.fullmatch(arguments.tag)
    if match is None or arguments.tag != "corelm-portfolio-v10":
        raise AutomatedDemoError("tag must be exact corelm-portfolio-v10")
    if os.environ.get("CORELM_OFFLINE") != "1":
        raise AutomatedDemoError("CORELM_OFFLINE=1 is mandatory")
    wheelhouse_value = os.environ.get("CORELM_WHEELHOUSE", "")
    if not wheelhouse_value:
        raise AutomatedDemoError("CORELM_WHEELHOUSE must name the pinned offline wheelhouse")
    home = Path.home()
    if not home.is_absolute() or home.is_symlink() or home.resolve(strict=True) != home:
        raise AutomatedDemoError("home directory must be canonical and not symlinked")
    home_status = home.stat()
    if home_status.st_uid != os.getuid() or home_status.st_mode & 0o022:
        raise AutomatedDemoError("home directory is not owner-controlled")
    wheelhouse = Path(wheelhouse_value)
    if (
        not wheelhouse.is_absolute()
        or wheelhouse.is_symlink()
        or wheelhouse.resolve(strict=True) != wheelhouse
        or not wheelhouse.is_dir()
    ):
        raise AutomatedDemoError("offline wheelhouse must be a canonical directory")
    wheelhouse_status = wheelhouse.stat()
    if wheelhouse_status.st_uid != os.getuid() or wheelhouse_status.st_mode & 0o022:
        raise AutomatedDemoError("offline wheelhouse is not owner-controlled")
    output = arguments.output
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise AutomatedDemoError("output must be an absent absolute directory")
    parent = output.parent
    if parent.is_symlink() or parent.resolve(strict=True) != parent:
        raise AutomatedDemoError("output parent must be canonical and not symlinked")
    parent_status = parent.stat()
    if (
        not stat.S_ISDIR(parent_status.st_mode)
        or parent_status.st_uid != os.getuid()
        or parent_status.st_mode & 0o022
    ):
        raise AutomatedDemoError("output parent is not owner-controlled")
    ffmpeg = _resolve_tool(arguments.ffmpeg, "ffmpeg")
    ffprobe = _resolve_tool(arguments.ffprobe, "ffprobe")
    if ffmpeg.parent != ffprobe.parent:
        raise AutomatedDemoError("ffmpeg and ffprobe must come from one installation")
    return Configuration(
        tag=arguments.tag,
        output=output,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        home=home,
        wheelhouse=wheelhouse,
    )


def _validate_origin(fetch_urls: Sequence[str], push_urls: Sequence[str]) -> None:
    if (
        len(fetch_urls) != 1
        or fetch_urls[0] not in CANONICAL_REMOTES
        or list(push_urls) != list(fetch_urls)
    ):
        raise AutomatedDemoError("origin is not the exact canonical public repository")


def _source_preflight(tag: str) -> SourceIdentity:
    try:
        checkout = verify_clean_checkout(
            ROOT,
            expected_origins=CANONICAL_REMOTES,
            expected_branch="main",
            expected_upstream="origin/main",
        )
    except StrictCheckoutError as error:
        raise AutomatedDemoError(
            "source checkout does not exactly match the signed HEAD tree"
        ) from error
    head = checkout.commit
    tree = checkout.tree
    if (
        _git("rev-parse", "refs/heads/main^{commit}") != head
        or _git("rev-parse", "refs/remotes/origin/main^{commit}") != head
    ):
        raise AutomatedDemoError("main, origin/main, and HEAD are not exact")
    if (
        _git("cat-file", "-t", f"refs/tags/{tag}") != "tag"
        or _git("rev-parse", f"refs/tags/{tag}^{{commit}}") != head
        or _git("rev-parse", f"refs/tags/{tag}^{{tree}}") != tree
    ):
        raise AutomatedDemoError("portfolio tag is not an annotated tag at exact HEAD")

    verification = _run(
        (
            GIT,
            "--no-replace-objects",
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.allowedSignersFile={ALLOWED_SIGNERS}",
            "-c",
            "core.hooksPath=/dev/null",
            "verify-tag",
            "--raw",
            tag,
        ),
        cwd=ROOT,
    )
    if (
        verification.returncode != 0
        or b'Good "git" signature for ' not in verification.stderr
    ):
        raise AutomatedDemoError("portfolio tag SSH signature is not valid")
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    if f'version: "{tag}"' not in citation:
        raise AutomatedDemoError("CITATION.cff does not bind the requested tag")
    return SourceIdentity(tag=tag, commit=head, tree=tree)


def _first_version_line(tool: Path, prefix: str) -> tuple[str, bytes]:
    completed = _run((str(tool), "-version"), cwd=tool.parent, timeout=30)
    raw = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise AutomatedDemoError(f"{tool.name} version query failed")
    try:
        lines = completed.stdout.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise AutomatedDemoError(f"{tool.name} version is not UTF-8") from error
    if not lines or not lines[0].startswith(prefix) or len(lines[0]) > 1024:
        raise AutomatedDemoError(f"{tool.name} version line is malformed")
    return lines[0], raw


def _pre_marker_resources(configuration: Configuration) -> None:
    power = _run((PMSET, "-g", "batt"), cwd=ROOT, timeout=15)
    power_text = _decoded_stdout(power, "AC power preflight")
    if "AC Power" not in power_text:
        raise AutomatedDemoError("Mac must be connected to AC power")

    memory = _run((MEMORY_PRESSURE, "-Q"), cwd=ROOT, timeout=15)
    memory_text = _decoded_stdout(memory, "memory preflight")
    percentages = re.findall(
        r"^System-wide memory free percentage: ([0-9]{1,3})%$",
        memory_text,
        flags=re.MULTILINE,
    )
    if len(percentages) != 1 or not (0 <= int(percentages[0]) <= 100):
        raise AutomatedDemoError("available memory percentage is malformed")
    if int(percentages[0]) < MINIMUM_AVAILABLE_MEMORY_PERCENT:
        raise AutomatedDemoError("at least 50% available memory is required")

    try:
        volume = os.statvfs(configuration.output.parent)
    except OSError as error:
        raise AutomatedDemoError("output-volume capacity is unavailable") from error
    available_disk = volume.f_bavail * volume.f_frsize
    if available_disk < MINIMUM_AVAILABLE_DISK_BYTES:
        raise AutomatedDemoError("at least 12 GiB free disk is required")


def _host_and_tool_preflight(configuration: Configuration, staging: Path) -> PreparedTools:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise AutomatedDemoError("automated portfolio capture requires macOS arm64")
    _pre_marker_resources(configuration)

    ffmpeg_version, ffmpeg_raw = _first_version_line(
        configuration.ffmpeg, "ffmpeg version "
    )
    ffprobe_version, _ = _first_version_line(
        configuration.ffprobe, "ffprobe version "
    )
    if b"--disable-network" not in ffmpeg_raw:
        raise AutomatedDemoError("ffmpeg must be built with --disable-network")
    encoders = _run(
        (str(configuration.ffmpeg), "-hide_banner", "-encoders"),
        cwd=configuration.ffmpeg.parent,
        timeout=30,
    )
    if encoders.returncode != 0 or b"h264_videotoolbox" not in encoders.stdout:
        raise AutomatedDemoError("ffmpeg lacks the required h264_videotoolbox encoder")

    screencapture = _resolve_tool(SCREENCAPTURE, "screencapture")
    code_identity = _run(
        (CODESIGN, "-d", "--verbose=4", str(screencapture)),
        cwd=ROOT,
        timeout=30,
    )
    identity_output = code_identity.stdout + code_identity.stderr
    if (
        code_identity.returncode != 0
        or b"Identifier=com.apple.screencapture" not in identity_output.splitlines()
    ):
        raise AutomatedDemoError("screencapture code identity is not exact")

    compiler_query = _run((XCRUN, "--find", "swiftc"), cwd=ROOT, timeout=30)
    compiler = Path(_decoded_stdout(compiler_query, "Swift compiler lookup"))
    if not compiler.is_absolute() or not compiler.resolve(strict=True).is_file():
        raise AutomatedDemoError("Swift compiler path is invalid")
    sdk_query = _run(
        (XCRUN, "--sdk", "macosx", "--show-sdk-path"), cwd=ROOT, timeout=30
    )
    sdk = _decoded_stdout(sdk_query, "macOS SDK lookup")
    swift_version_query = _run((XCRUN, "swiftc", "--version"), cwd=ROOT, timeout=30)
    swift_version = _decoded_stdout(swift_version_query, "Swift version").splitlines()[0]
    if not swift_version.startswith("Apple Swift version "):
        raise AutomatedDemoError("Swift version identity is malformed")
    helper = staging / "find-proof-window"
    compile_environment = _safe_environment(configuration.home)
    compile_environment["SDKROOT"] = sdk
    compiled = _run(
        (
            XCRUN,
            "--sdk",
            "macosx",
            "swiftc",
            "-O",
            "-whole-module-optimization",
            str(WINDOW_HELPER_SOURCE),
            "-o",
            str(helper),
        ),
        cwd=ROOT,
        env=compile_environment,
        timeout=120,
    )
    if compiled.returncode != 0:
        raise AutomatedDemoError("window helper compilation failed")
    _require_regular(helper, "compiled window helper", executable=True)
    preflight = _run(
        (str(helper), "--preflight"),
        cwd=ROOT,
        env=_safe_environment(configuration.home),
        timeout=15,
    )
    if (
        preflight.returncode != 0
        or preflight.stdout != b'{"screen_capture_authorized":true}\n'
        or preflight.stderr
    ):
        raise AutomatedDemoError(
            "screen capture is not already authorized; no permission was requested"
        )

    build_environment = _proof_environment(configuration, "0" * 64)
    build_environment.pop("CORELM_PROOF_CHALLENGE")
    build_environment.update(
        {
            "CORELM_ASSETS_OFFLINE_ONLY": "1",
            "CORELM_SKIP_APP_LAUNCH_CHECK": "1",
            "BUILD_CONFIG": "release",
        }
    )
    built = _run(
        (str(ROOT / "corelm"), "macos", "build"),
        cwd=ROOT,
        env=build_environment,
        timeout=900,
    )
    if built.returncode != 0:
        raise AutomatedDemoError("offline preflight application build failed")
    _require_regular(APP_EXECUTABLE, "preflight application executable", executable=True)
    preflight_capture = _application_capture_preflight(
        configuration=configuration,
        helper=helper,
        staging=staging,
    )

    return PreparedTools(
        staging=staging,
        helper=helper,
        report={
            "window_helper": {
                "source_sha256": _sha256_path(WINDOW_HELPER_SOURCE),
                "executable_sha256": _sha256_path(helper),
                "swift_version": swift_version,
            },
            "screencapture": {
                "executable_sha256": _sha256_path(screencapture),
                "codesign_identifier": "com.apple.screencapture",
            },
            "ffmpeg": {
                "executable_sha256": _sha256_path(configuration.ffmpeg),
                "version": ffmpeg_version,
            },
            "ffprobe": {
                "executable_sha256": _sha256_path(configuration.ffprobe),
                "version": ffprobe_version,
            },
        },
        preflight_capture=preflight_capture,
    )


def _recheck_prepared_tools(
    configuration: Configuration,
    prepared: PreparedTools,
) -> None:
    tools = automated_media.validate_tools(prepared.report)
    _require_regular(prepared.helper, "compiled window helper", executable=True)
    observed = {
        "window_helper_source": _sha256_path(WINDOW_HELPER_SOURCE),
        "window_helper_executable": _sha256_path(prepared.helper),
        "screencapture": _sha256_path(SCREENCAPTURE),
        "ffmpeg": _sha256_path(configuration.ffmpeg),
        "ffprobe": _sha256_path(configuration.ffprobe),
    }
    expected = {
        "window_helper_source": tools["window_helper"]["source_sha256"],
        "window_helper_executable": tools["window_helper"]["executable_sha256"],
        "screencapture": tools["screencapture"]["executable_sha256"],
        "ffmpeg": tools["ffmpeg"]["executable_sha256"],
        "ffprobe": tools["ffprobe"]["executable_sha256"],
    }
    if observed != expected:
        raise AutomatedDemoError("capture tool identity changed during preflight")


def _prepare_verified_tag_ci_receipt(
    configuration: Configuration,
    source: SourceIdentity,
    staging: Path,
) -> tuple[Path, str, str]:
    """Fetch, validate, and durably retain the public tag-push CI admission."""

    del configuration
    destination = staging / "tag-ci-receipt.json"
    local_destination = staging / LOCAL_TRUST_RECEIPT_FILENAME
    bundle_destination = staging / "tag-ci-bundle"
    if any(path.exists() or path.is_symlink() for path in (
        destination, local_destination, bundle_destination
    )):
        raise AutomatedDemoError("tag-CI receipt target must be absent")
    try:
        responses = fetch_public_tag_ci_responses(
            repository=TAG_CI_REPOSITORY,
            expected_tag=source.tag,
            expected_commit=source.commit,
            expected_tree=source.tree,
        )
        receipt = validate_saved_tag_ci(
            responses,
            repository=TAG_CI_REPOSITORY,
            expected_tag=source.tag,
            expected_commit=source.commit,
            expected_tree=source.tree,
        )
        written_bundle = write_response_bundle(
            bundle_destination, responses, receipt
        )
        if written_bundle != bundle_destination:
            raise TagCIAdmissionError("tag-CI bundle path is not exact")
        _saved_responses, recomputed = read_response_bundle(
            bundle_destination,
            repository=TAG_CI_REPOSITORY,
            expected_tag=source.tag,
            expected_commit=source.commit,
            expected_tree=source.tree,
        )
        payload = canonical_tag_ci_receipt_bytes(recomputed)
        if payload != (bundle_destination / PUBLIC_RECEIPT_FILENAME).read_bytes():
            raise TagCIAdmissionError("saved tag-CI bundle receipt changed")
        automated_media.validate_tag_ci_receipt_bytes(
            payload,
            expected={
                "repository": TAG_CI_REPOSITORY,
                "tag": source.tag,
                "commit": source.commit,
                "tree": source.tree,
            },
        )
        public_source = recomputed["source"]
        local_receipt = verify_local_tag_trust(
            ROOT,
            expected_tag=source.tag,
            expected_tag_object=public_source["annotated_tag_object"],
            expected_commit=source.commit,
            expected_tree=source.tree,
        )
        local_payload = canonical_tag_ci_receipt_bytes(local_receipt)
        automated_media.validate_local_tag_trust_receipt_bytes(
            local_payload,
            expected={
                "tag": source.tag,
                "tag_object": public_source["annotated_tag_object"],
                "commit": source.commit,
                "tree": source.tree,
            },
        )
    except TagCIAdmissionError as error:
        raise AutomatedDemoError("public tag-CI admission failed") from error

    def write_private(target: Path, contents: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(target, flags, 0o600)
        try:
            view = memoryview(contents)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise AutomatedDemoError("tag trust receipt write made no progress")
                view = view[written:]
            os.fchmod(descriptor, 0o600)
            _sync_file_descriptor(descriptor)
        finally:
            os.close(descriptor)

    write_private(destination, payload)
    write_private(local_destination, local_payload)
    _sync_containing_directory(staging)
    if (
        destination.read_bytes() != payload
        or local_destination.read_bytes() != local_payload
    ):
        raise AutomatedDemoError("tag-CI receipt changed after durable write")
    return (
        destination,
        hashlib.sha256(payload).hexdigest(),
        hashlib.sha256(local_payload).hexdigest(),
    )


def _state_root(home: Path) -> Path:
    root = home / "Library/Application Support/CoreLMBenchmark/portfolio-automation"
    current = home
    for component in root.relative_to(home).parts:
        current = current / component
        if current.is_symlink():
            raise AutomatedDemoError("attempt-state path contains a symlink")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    status = root.stat()
    if (
        not stat.S_ISDIR(status.st_mode)
        or status.st_uid != os.getuid()
        or stat.S_IMODE(status.st_mode) != 0o700
    ):
        raise AutomatedDemoError("attempt-state directory is not owner-only")
    return root


def _sync_file_descriptor(descriptor: int) -> None:
    os.fsync(descriptor)
    full_sync = getattr(fcntl, "F_FULLFSYNC", None)
    if full_sync is not None:
        fcntl.fcntl(descriptor, full_sync)


def _sync_containing_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(directory, flags)
    try:
        status = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(status.st_mode)
            or status.st_uid != os.getuid()
            or stat.S_IMODE(status.st_mode) != 0o700
        ):
            raise AutomatedDemoError("attempt-state directory changed during sync")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class AttemptLog:
    def __init__(self, descriptor: int, path: Path, tag: str):
        self.descriptor = descriptor
        self.path = path
        self.tag = tag
        self.proof_invocation_count = 0

    @classmethod
    def reserve(
        cls,
        home: Path,
        tag: str,
        *,
        source: SourceIdentity | None = None,
        preflight_capture: CaptureSegment | None = None,
        window_helper_sha256: str | None = None,
        tag_ci_receipt_sha256: str | None = None,
        local_tag_trust_receipt_sha256: str | None = None,
    ) -> "AttemptLog":
        supplied = (
            source,
            preflight_capture,
            window_helper_sha256,
            tag_ci_receipt_sha256,
            local_tag_trust_receipt_sha256,
        )
        if any(value is not None for value in supplied) and any(
            value is None for value in supplied
        ):
            raise AutomatedDemoError("attempt-state initial bindings are incomplete")
        values: dict[str, Any] = {"proof_invocation_count": 0}
        if source is not None:
            assert preflight_capture is not None
            assert window_helper_sha256 is not None
            assert tag_ci_receipt_sha256 is not None
            assert local_tag_trust_receipt_sha256 is not None
            if (
                re.fullmatch(r"[0-9a-f]{40}", source.commit) is None
                or re.fullmatch(r"[0-9a-f]{40}", source.tree) is None
                or SHA256_PATTERN.fullmatch(preflight_capture.sha256) is None
                or SHA256_PATTERN.fullmatch(window_helper_sha256) is None
                or SHA256_PATTERN.fullmatch(tag_ci_receipt_sha256) is None
                or SHA256_PATTERN.fullmatch(local_tag_trust_receipt_sha256) is None
                or preflight_capture.role != "preflight"
                or preflight_capture.owner_pid <= 0
                or preflight_capture.window_id <= 0
            ):
                raise AutomatedDemoError("attempt-state initial binding is malformed")
            values.update(
                {
                    "source_commit": source.commit,
                    "source_tree": source.tree,
                    "preflight_segment_sha256": preflight_capture.sha256,
                    "preflight_owner_pid": preflight_capture.owner_pid,
                    "preflight_window_id": preflight_capture.window_id,
                    "window_helper_sha256": window_helper_sha256,
                    "tag_ci_receipt_sha256": tag_ci_receipt_sha256,
                    "local_tag_trust_receipt_sha256": local_tag_trust_receipt_sha256,
                }
            )
        path = _state_root(home) / f"{tag}.jsonl"
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError as error:
            raise AutomatedDemoError(
                f"the durable automated-demo attempt for {tag} is already consumed"
            ) from error
        attempt = cls(descriptor, path, tag)
        try:
            _sync_file_descriptor(descriptor)
            _sync_containing_directory(path.parent)
            attempt.append("ATTEMPT_STARTED", **values)
        except Exception:
            attempt.close()
            raise
        return attempt

    def append(self, event: str, **values: Any) -> None:
        if not event or not event.isascii():
            raise AutomatedDemoError("attempt event is invalid")
        provided_count = values.pop("proof_invocation_count", None)
        if provided_count is not None:
            if (
                type(provided_count) is not int
                or provided_count not in (0, 1)
                or provided_count < self.proof_invocation_count
            ):
                raise AutomatedDemoError("proof invocation count is not monotonic")
            self.proof_invocation_count = provided_count
        payload = _canonical_json(
            {
                "event": event,
                "proof_invocation_count": self.proof_invocation_count,
                "schema_version": automated_media.ATTEMPT_STATE_SCHEMA_VERSION,
                "tag": self.tag,
                **values,
            }
        )
        view = memoryview(payload)
        os.lseek(self.descriptor, 0, os.SEEK_END)
        while view:
            written = os.write(self.descriptor, view)
            if written <= 0:
                raise AutomatedDemoError("attempt-state write made no progress")
            view = view[written:]
        _sync_file_descriptor(self.descriptor)

    def stable_bytes(self) -> bytes:
        before = os.fstat(self.descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_uid != os.getuid()
            or before.st_size <= 0
            or before.st_size > automated_media.MAX_ATTEMPT_STATE_BYTES
        ):
            raise AutomatedDemoError("attempt-state file is not owner-only")
        os.lseek(self.descriptor, 0, os.SEEK_SET)
        payload = b""
        while len(payload) <= automated_media.MAX_ATTEMPT_STATE_BYTES:
            chunk = os.read(self.descriptor, 1024 * 1024)
            if not chunk:
                break
            payload += chunk
        after = os.fstat(self.descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or len(payload) != before.st_size:
            raise AutomatedDemoError("attempt-state file changed while reading")
        return payload

    def sha256(self) -> str:
        return hashlib.sha256(self.stable_bytes()).hexdigest()

    def snapshot_success(self, destination: Path) -> tuple[bytes, str]:
        payload = self.stable_bytes()
        automated_media.validate_attempt_state_bytes(payload)
        if not destination.is_absolute() or destination.exists() or destination.is_symlink():
            raise AutomatedDemoError("attempt-state snapshot target must be absent")
        if destination.parent.resolve(strict=True) != destination.parent:
            raise AutomatedDemoError("attempt-state snapshot parent is not canonical")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(destination, flags, 0o600)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise AutomatedDemoError("attempt-state snapshot write made no progress")
                view = view[written:]
            os.fchmod(descriptor, 0o600)
            _sync_file_descriptor(descriptor)
        finally:
            os.close(descriptor)
        _sync_containing_directory(destination.parent)
        observed = automated_media.read_canonical_attempt_state(destination)
        if len(observed) != automated_media.ATTEMPT_EVENT_COUNT:
            raise AutomatedDemoError("attempt-state snapshot verification failed")
        return payload, hashlib.sha256(payload).hexdigest()

    def close(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1


def _results_root(home: Path) -> Path:
    return home / "Library/Application Support/CoreLMBenchmark/real-llm-results"


def _snapshot_runs(home: Path) -> set[str]:
    root = _results_root(home)
    if not root.exists():
        return set()
    if root.is_symlink() or root.resolve(strict=True) != root or not root.is_dir():
        raise AutomatedDemoError("real-model results root is unsafe")
    result: set[str] = set()
    for entry in root.iterdir():
        if entry.is_symlink():
            raise AutomatedDemoError("real-model results root contains a symlink")
        if entry.is_dir():
            result.add(entry.name)
    return result


def _proof_environment(configuration: Configuration, challenge: str) -> dict[str, str]:
    return {
        "HOME": str(configuration.home),
        "TMPDIR": "/private/tmp",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
        "CORELM_OFFLINE": "1",
        "CORELM_WHEELHOUSE": str(configuration.wheelhouse),
        "CORELM_PROOF_CHALLENGE": challenge,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    }


def _proof_argv() -> tuple[str, ...]:
    return (str(ROOT / "corelm"), "macos", "proof")


def _post_proof_presentation_argv() -> tuple[str, ...]:
    return (str(APP_EXECUTABLE), "--portfolio-capture-presentation")


def _parse_window(raw: bytes, expected_pid: int) -> WindowIdentity:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AutomatedDemoError("window helper returned malformed JSON") from error
    base_keys = {
        "schema_version",
        "mode",
        "pid",
        "bundle_identifier",
        "window_id",
        "owner_name",
        "bounds",
    }
    optional_keys = {"executable_path", "executable_sha256"}
    if not isinstance(value, dict) or set(value) not in (base_keys, base_keys | optional_keys):
        raise AutomatedDemoError("window helper fields are not exact")
    if raw != _canonical_json(value):
        raise AutomatedDemoError("window helper JSON is not canonical")
    if (
        value["schema_version"] != 1
        or value["mode"] != "MACOS_WINDOW_ID_ONLY"
        or value["pid"] != expected_pid
        or value["bundle_identifier"] != automated_media.BUNDLE_IDENTIFIER
        or type(value["window_id"]) is not int
        or value["window_id"] <= 0
        or not isinstance(value["owner_name"], str)
        or not value["owner_name"]
    ):
        raise AutomatedDemoError("window helper identity is invalid")
    bounds = value["bounds"]
    if not isinstance(bounds, dict) or set(bounds) != {"x", "y", "width", "height"}:
        raise AutomatedDemoError("window helper bounds are not exact")
    for key in ("x", "y", "width", "height"):
        number = bounds[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise AutomatedDemoError("window helper bounds are nonnumeric")
        if not math.isfinite(float(number)):
            raise AutomatedDemoError("window helper bounds are non-finite")
    if float(bounds["width"]) <= 0 or float(bounds["height"]) <= 0:
        raise AutomatedDemoError("window helper dimensions are not positive")
    executable_path = value.get("executable_path")
    executable_sha256 = value.get("executable_sha256")
    if executable_path is not None and (
        not isinstance(executable_path, str)
        or not executable_path.startswith("/")
        or not isinstance(executable_sha256, str)
        or SHA256_PATTERN.fullmatch(executable_sha256) is None
    ):
        raise AutomatedDemoError("window executable identity is malformed")
    return WindowIdentity(
        pid=expected_pid,
        window_id=value["window_id"],
        width=float(bounds["width"]),
        height=float(bounds["height"]),
        executable_path=executable_path,
        executable_sha256=executable_sha256,
        x=float(bounds["x"]),
        y=float(bounds["y"]),
    )


def _window_for_pid(helper: Path, pid: int, home: Path) -> WindowIdentity | None:
    completed = _run(
        (
            str(helper),
            "--pid",
            str(pid),
            "--bundle-id",
            automated_media.BUNDLE_IDENTIFIER,
        ),
        cwd=ROOT,
        env=_safe_environment(home),
        timeout=5,
    )
    if completed.returncode != 0:
        return None
    if completed.stderr:
        raise AutomatedDemoError("window helper emitted stderr on success")
    return _parse_window(completed.stdout, pid)


def _wait_for_window(
    pid: int,
    helper: Path,
    home: Path,
    *,
    timeout: float,
) -> WindowIdentity:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        match = _window_for_pid(helper, pid, home)
        if match is not None:
            return match
        try:
            os.kill(pid, 0)
        except OSError:
            raise AutomatedDemoError("application exited before its exact window appeared")
        time.sleep(0.2)
    raise AutomatedDemoError("timed out waiting for the exact application window")


def _validate_window_executable(
    window: WindowIdentity,
    *,
    expected_sha256: str | None,
    label: str,
) -> None:
    if window.executable_path is None or window.executable_sha256 is None:
        raise AutomatedDemoError(f"{label} executable identity is unavailable")
    _require_regular(APP_EXECUTABLE, "application executable", executable=True)
    observed_sha256 = _sha256_path(APP_EXECUTABLE)
    if (
        Path(window.executable_path) != APP_EXECUTABLE
        or window.executable_sha256 != observed_sha256
        or (expected_sha256 is not None and observed_sha256 != expected_sha256)
    ):
        raise AutomatedDemoError(f"{label} executable differs from the proof app")


def _validate_proof_application_executable(
    proof: ProofIdentity,
    *,
    label: str,
) -> None:
    _require_regular(APP_EXECUTABLE, label, executable=True)
    if _sha256_path(APP_EXECUTABLE) != proof.application_executable_sha256:
        raise AutomatedDemoError(f"{label} differs from the verified proof app")


def _recheck_window(
    helper: Path,
    expected: WindowIdentity,
    home: Path,
    *,
    label: str,
) -> WindowIdentity:
    observed = _window_for_pid(helper, expected.pid, home)
    if observed != expected:
        raise AutomatedDemoError(f"{label} changed before exact-window capture")
    return observed


def _probe_segment(
    path: Path, ffprobe: Path, expected_duration: float
) -> tuple[int, int, float, int, str]:
    completed = _run(
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
        timeout=60,
    )
    if completed.returncode != 0:
        raise AutomatedDemoError("ffprobe rejected a raw capture segment")
    try:
        report = json.loads(completed.stdout.decode("utf-8"))
        streams = report["streams"]
        duration = float(report["format"]["duration"])
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise AutomatedDemoError("raw capture segment metadata is malformed") from error
    if (
        not isinstance(streams, list)
        or any(not isinstance(row, dict) for row in streams)
        or report.get("chapters", []) != []
    ):
        raise AutomatedDemoError("raw capture segment stream list is malformed")
    videos = [row for row in streams if row.get("codec_type") == "video"]
    if (
        len(videos) != 1
        or len(streams) != 1
        or not math.isfinite(duration)
        or abs(duration - expected_duration) > 1.0
    ):
        raise AutomatedDemoError("raw capture segment duration/topology is invalid")
    width = videos[0].get("width")
    height = videos[0].get("height")
    if (
        type(width) is not int
        or type(height) is not int
        or not (1 <= width <= 16_384)
        or not (1 <= height <= 16_384)
    ):
        raise AutomatedDemoError("raw capture segment dimensions are invalid")
    frame_count, pts_sha256 = _raw_frame_identity(
        path, ffprobe, width=width, height=height
    )
    return width, height, duration, frame_count, pts_sha256


def _raw_frame_identity(
    path: Path,
    ffprobe: Path,
    *,
    width: int,
    height: int,
) -> tuple[int, str]:
    completed = _run(
        _frame_probe_argv(path, ffprobe),
        cwd=path.parent,
        timeout=120,
    )
    if completed.returncode != 0:
        raise AutomatedDemoError("raw segment frame PTS extraction failed")
    try:
        value = json.loads(completed.stdout.decode("utf-8"))
        frames = value["frames"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise AutomatedDemoError("raw segment frame PTS output is malformed") from error
    try:
        return automated_media.frame_pts_identity(frames, width=width, height=height)
    except automated_media.AutomatedMediaError as error:
        raise AutomatedDemoError("raw segment frame PTS identity is invalid") from error


def _capture_segment(
    *,
    role: str,
    window: WindowIdentity,
    destination: Path,
    duration: float,
    ffprobe: Path,
) -> CaptureSegment:
    if destination.exists() or destination.is_symlink() or int(duration) != duration:
        raise AutomatedDemoError("capture segment destination/duration is invalid")
    completed = _run(
        (
            str(SCREENCAPTURE),
            "-x",
            "-o",
            "-v",
            f"-V{int(duration)}",
            f"-l{window.window_id}",
            str(destination),
        ),
        cwd=destination.parent,
        timeout=duration + 45,
    )
    if completed.returncode != 0:
        raise AutomatedDemoError(f"{role} exact-window capture failed")
    _require_regular(destination, f"{role} capture segment")
    width, height, observed_duration, frame_count, pts_sha256 = _probe_segment(
        destination, ffprobe, duration
    )
    return CaptureSegment(
        role=role,
        owner_pid=window.pid,
        window_id=window.window_id,
        width=width,
        height=height,
        duration_seconds=observed_duration,
        sha256=_sha256_path(destination),
        requested_duration_seconds=duration,
        frame_count=frame_count,
        pts_sha256=pts_sha256,
    )


def _application_capture_preflight(
    *,
    configuration: Configuration,
    helper: Path,
    staging: Path,
) -> CaptureSegment:
    log_path = staging / "preflight-ui.log"
    descriptor = os.open(
        log_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    log = os.fdopen(descriptor, "wb", closefd=True)
    process: subprocess.Popen[Any] | None = None
    try:
        process = subprocess.Popen(
            (str(APP_EXECUTABLE), "--portfolio-capture-preflight"),
            cwd=ROOT,
            env=_safe_environment(configuration.home),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        window = _wait_for_window(
            process.pid,
            helper,
            configuration.home,
            timeout=RESULT_WINDOW_WAIT_SECONDS,
        )
        _validate_window_executable(
            window,
            expected_sha256=_sha256_path(APP_EXECUTABLE),
            label="preflight window",
        )
        _recheck_window(
            helper,
            window,
            configuration.home,
            label="preflight window",
        )
        segment = _capture_segment(
            role="preflight",
            window=window,
            destination=staging / "preflight-window.mov",
            duration=automated_media.PREFLIGHT_SEGMENT_SECONDS,
            ffprobe=configuration.ffprobe,
        )
        _recheck_window(
            helper,
            window,
            configuration.home,
            label="preflight window after capture",
        )
        return segment
    finally:
        if process is not None:
            _terminate_process(process)
        log.close()


def _terminate_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _new_run_directory(home: Path, before: set[str]) -> Path:
    after = _snapshot_runs(home)
    if not before.issubset(after):
        raise AutomatedDemoError("an existing real-model run disappeared during proof")
    created = after - before
    if len(created) != 1:
        raise AutomatedDemoError(f"expected exactly one new real-model run; found {len(created)}")
    identifier = next(iter(created))
    try:
        if str(uuid.UUID(identifier)) != identifier:
            raise ValueError
    except ValueError as error:
        raise AutomatedDemoError("new run directory name is not a canonical UUID") from error
    run = _results_root(home) / identifier
    if run.is_symlink() or run.resolve(strict=True) != run or not run.is_dir():
        raise AutomatedDemoError("new real-model run directory is unsafe")
    return run


def _fixed_metric(
    value: Any,
    label: str,
    *,
    minimum: float,
    maximum: float,
    minimum_exclusive: bool = False,
) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AutomatedDemoError(f"{label} is not numeric")
    number = float(value)
    if (
        not math.isfinite(number)
        or number > maximum
        or (number <= minimum if minimum_exclusive else number < minimum)
    ):
        raise AutomatedDemoError(f"{label} is outside the capture contract")
    formatted = f"{number:.6f}"
    if re.fullmatch(r"-?[0-9]+\.[0-9]{6}", formatted) is None:
        raise AutomatedDemoError(f"{label} fixed decimal is malformed")
    return formatted


def _inspect_proof(
    run: Path,
    source: SourceIdentity,
    challenge: str,
) -> ProofIdentity:
    reports = run / REPORT_DIRECTORY_NAME
    structural = reports / STRUCTURAL_REPORT_NAME
    replay = reports / REPLAY_REPORT_NAME
    terminal = reports / TERMINAL_LOG_NAME
    verify_report(structural, run, "structural_verifier")
    verify_report(replay, run, "fresh_model_replay")
    verified_result = verify_fresh_run(
        run,
        APP_BUNDLE,
        challenge_nonce=challenge,
        require_metric_pass=False,
    )
    binding = derive_binding(run)
    if binding["source"] != {"commit": source.commit, "tree": source.tree}:
        raise AutomatedDemoError("proof source differs from exact tagged source")
    metric_verdict = binding["metric_verdict"]
    terminal_outcome = (
        "END-TO-END PROOF PASS"
        if metric_verdict == "PASS"
        else "END-TO-END PROOF VERIFIED — METRIC FAIL"
    )
    _require_regular(terminal, "terminal proof outcome", maximum_bytes=4096)
    if terminal.read_bytes() != (terminal_outcome + "\n").encode("utf-8"):
        raise AutomatedDemoError("first terminal proof outcome is not exact")
    receipt_path = run / "app-run-receipt.json"
    result_path = run / "validation-064-071.json"
    _require_regular(receipt_path, "app run receipt", maximum_bytes=16 * 1024 * 1024)
    _require_regular(result_path, "app result", maximum_bytes=16 * 1024 * 1024)
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AutomatedDemoError("app run receipt is malformed") from error
    if receipt.get("challengeNonce") != challenge:
        raise AutomatedDemoError("app run receipt differs from proof challenge")
    if not isinstance(verified_result, dict):
        raise AutomatedDemoError("verified result is malformed")
    aggregates = verified_result.get("aggregates")
    if (
        not isinstance(aggregates, list)
        or len(aggregates) != 1
        or not isinstance(aggregates[0], dict)
    ):
        raise AutomatedDemoError("verified result has no unique aggregate")
    aggregate = aggregates[0]
    application_sha256 = receipt.get("application", {}).get("executableSHA256")
    if (
        not isinstance(application_sha256, str)
        or SHA256_PATTERN.fullmatch(application_sha256) is None
    ):
        raise AutomatedDemoError("proof application digest is malformed")
    _require_regular(APP_EXECUTABLE, "proof application executable", executable=True)
    if _sha256_path(APP_EXECUTABLE) != application_sha256:
        raise AutomatedDemoError("proof application executable changed after proof")
    return ProofIdentity(
        run_directory=run,
        identifier=run.name,
        challenge_sha256=automated_media.challenge_sha256(challenge),
        receipt_sha256=_sha256_path(receipt_path),
        result_sha256=_sha256_path(result_path),
        application_executable_sha256=application_sha256,
        metric_verdict=metric_verdict,
        terminal_outcome=terminal_outcome,
        compression_ratio_vs_bf16=_fixed_metric(
            aggregate.get("compressionRatioVsBF16"),
            "compression ratio",
            minimum=0,
            maximum=64,
            minimum_exclusive=True,
        ),
        delta_nll_nat_per_token=_fixed_metric(
            aggregate.get("deltaNLLNatPerToken"),
            "delta NLL",
            minimum=-1,
            maximum=1,
        ),
        top1_agreement=_fixed_metric(
            aggregate.get("top1Agreement"),
            "top-1 agreement",
            minimum=0,
            maximum=1,
        ),
    )


def _result_readiness_value(proof: ProofIdentity) -> dict[str, Any]:
    value = {
        "application_executable_sha256": proof.application_executable_sha256,
        "compression_ratio_vs_bf16": proof.compression_ratio_vs_bf16,
        "delta_nll_nat_per_token": proof.delta_nll_nat_per_token,
        "metric_verdict": proof.metric_verdict,
        "module_states": {
            "compression": "COMPLETE",
            "heavy_replay": "PASS",
            "kv_cache": "COMPLETE",
            "primary_evidence": "COMPLETE",
            "qwen_model": "COMPLETE",
        },
        "receipt_sha256": proof.receipt_sha256,
        "result_sha256": proof.result_sha256,
        "run_identifier": proof.identifier,
        "schema_version": 1,
        "status": "CAPTURE_RESULT_READY",
        "top1_agreement": proof.top1_agreement,
        "verifier_state": "PASS",
    }
    automated_media.validate_readiness(value)
    return value


def _result_readiness_bytes(proof: ProofIdentity) -> bytes:
    return _canonical_json(_result_readiness_value(proof))


def _read_result_readiness(
    path: Path,
    proof: ProofIdentity,
) -> ReadinessIdentity:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise AutomatedDemoError("result readiness receipt is unsafe") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size <= 0
            or before.st_size > automated_media.MAX_READINESS_BYTES
        ):
            raise AutomatedDemoError(
                "result readiness receipt is not an owner-only bounded file"
            )
        payload = b""
        while len(payload) <= automated_media.MAX_READINESS_BYTES:
            chunk = os.read(
                descriptor,
                automated_media.MAX_READINESS_BYTES + 1 - len(payload),
            )
            if not chunk:
                break
            payload += chunk
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    stable_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    stable_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if stable_before != stable_after or len(payload) != before.st_size:
        raise AutomatedDemoError("result readiness receipt changed while reading")
    if payload != _result_readiness_bytes(proof):
        raise AutomatedDemoError("result readiness receipt does not bind the proof")
    return ReadinessIdentity(
        sha256=hashlib.sha256(payload).hexdigest(),
        device=before.st_dev,
        inode=before.st_ino,
        size=before.st_size,
        mtime_ns=before.st_mtime_ns,
        ctime_ns=before.st_ctime_ns,
    )


def _wait_for_result_readiness(
    path: Path,
    proof: ProofIdentity,
    *,
    timeout: float,
) -> ReadinessIdentity:
    deadline = time.monotonic() + timeout
    while True:
        try:
            return _read_result_readiness(path, proof)
        except FileNotFoundError:
            if time.monotonic() >= deadline:
                raise AutomatedDemoError(
                    "timed out waiting for the exact result readiness receipt"
                )
            time.sleep(0.1)


def _launch_result_capture(
    configuration: Configuration,
    helper: Path,
    proof: ProofIdentity,
    attempt: AttemptLog,
) -> tuple[CaptureSegment, str]:
    _validate_proof_application_executable(
        proof,
        label="pre-result application executable",
    )
    log_path = configuration.output / "result-ui.log"
    readiness_path = configuration.output / "result-readiness.json"
    if readiness_path.exists() or readiness_path.is_symlink():
        raise AutomatedDemoError("result readiness receipt path must be absent")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(log_path, flags, 0o600)
    log = os.fdopen(descriptor, "wb", closefd=True)
    process: subprocess.Popen[Any] | None = None
    try:
        process = subprocess.Popen(
            (
                str(APP_EXECUTABLE),
                "--portfolio-capture",
                "--portfolio-result-id",
                proof.identifier,
                "--portfolio-ready-file",
                str(readiness_path),
            ),
            cwd=ROOT,
            env=_safe_environment(configuration.home),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        window = _wait_for_window(
            process.pid,
            helper,
            configuration.home,
            timeout=RESULT_WINDOW_WAIT_SECONDS,
        )
        _validate_window_executable(
            window,
            expected_sha256=proof.application_executable_sha256,
            label="result window",
        )
        readiness = _wait_for_result_readiness(
            readiness_path,
            proof,
            timeout=RESULT_READINESS_WAIT_SECONDS,
        )
        _recheck_window(
            helper,
            window,
            configuration.home,
            label="result window",
        )
        attempt.append(
            "SAME_RUN_REOPENED",
            result_readiness_sha256=readiness.sha256,
            run_identifier=proof.identifier,
            window_id=window.window_id,
        )
        segment = _capture_segment(
            role="same_run_result",
            window=window,
            destination=configuration.output / "same-run-result.mov",
            duration=automated_media.RESULT_SEGMENT_SECONDS,
            ffprobe=configuration.ffprobe,
        )
        _recheck_window(
            helper,
            window,
            configuration.home,
            label="result window after capture",
        )
        if _read_result_readiness(readiness_path, proof) != readiness:
            raise AutomatedDemoError(
                "result readiness receipt changed during exact-window capture"
            )
        attempt.append(
            "RESULT_CAPTURED",
            segment_sha256=segment.sha256,
            window_id=segment.window_id,
        )
        return segment, readiness.sha256
    finally:
        if process is not None:
            _terminate_process(process)
        log.close()


def _fixed_filter() -> str:
    presentation = automated_media.POST_PROOF_PRESENTATION_SEGMENT_SECONDS
    result = automated_media.RESULT_SEGMENT_SECONDS
    common = (
        f"fps={OUTPUT_FRAME_RATE},"
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x111318,"
        "setsar=1"
    )
    return (
        f"[0:v]{common},tpad=stop_mode=clone:stop_duration={presentation:g},"
        f"trim=duration={presentation:g},setpts=PTS-STARTPTS[presentation];"
        f"[1:v]{common},tpad=stop_mode=clone:stop_duration={result:g},"
        f"trim=duration={result:g},setpts=PTS-STARTPTS[result];"
        "[presentation][result]concat=n=2:v=1:a=0[outv]"
    )


def _validate_public_metadata(report: dict[str, Any]) -> None:
    format_value = report.get("format")
    streams = report.get("streams")
    if not isinstance(format_value, dict) or not isinstance(streams, list):
        raise AutomatedDemoError("final media probe topology is malformed")
    format_tags = format_value.get("tags", {})
    allowed_format = {"major_brand", "minor_version", "compatible_brands"}
    if not isinstance(format_tags, dict) or not set(format_tags).issubset(allowed_format):
        raise AutomatedDemoError("final video contains free-text format metadata")
    known_brands = {"isom", "iso2", "avc1", "mp41", "mp42", "qt  ", "M4V ", "dash"}
    for key, value in format_tags.items():
        if not isinstance(value, str) or not value:
            raise AutomatedDemoError("final video contains malformed structural metadata")
        if key == "minor_version":
            safe = len(value) <= 10 and value.isascii() and value.isdecimal()
        elif key == "major_brand":
            safe = value in known_brands
        else:
            safe = (
                len(value) <= 32
                and len(value) % 4 == 0
                and all(
                    value[offset : offset + 4] in known_brands
                    for offset in range(0, len(value), 4)
                )
            )
        if not safe:
            raise AutomatedDemoError("final video contains unsafe structural metadata")
    for stream in streams:
        tags = stream.get("tags", {}) if isinstance(stream, dict) else None
        if not isinstance(tags, dict) or not set(tags).issubset({"language", "vendor_id"}):
            raise AutomatedDemoError("final video contains free-text stream metadata")
        if tags.get("language") not in (None, "und") or tags.get("vendor_id") not in (
            None,
            "appl",
            "[0][0][0][0]",
        ):
            raise AutomatedDemoError("final video contains unsafe structural metadata")


def _probe_final(video: Path, configuration: Configuration) -> tuple[float, int, int]:
    completed = _run(
        (
            str(configuration.ffprobe),
            "-v",
            "error",
            "-show_entries",
            (
                "format=duration:format_tags:"
                "stream=codec_name,codec_type,width,height:stream_tags"
            ),
            "-of",
            "json",
            str(video),
        ),
        cwd=configuration.output,
        timeout=120,
    )
    if completed.returncode != 0:
        raise AutomatedDemoError("ffprobe rejected the final video")
    try:
        report = json.loads(completed.stdout.decode("utf-8"))
        duration = float(report["format"]["duration"])
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise AutomatedDemoError("final video probe is malformed") from error
    _validate_public_metadata(report)
    videos = [row for row in report["streams"] if row.get("codec_type") == "video"]
    audios = [row for row in report["streams"] if row.get("codec_type") == "audio"]
    if len(videos) != 1 or audios or videos[0].get("codec_name") != "h264":
        raise AutomatedDemoError("final video must contain one silent H.264 stream")
    video_row = videos[0]
    if (
        not math.isfinite(duration)
        or abs(duration - 30.0) > 0.05
        or video_row.get("width") != OUTPUT_WIDTH
        or video_row.get("height") != OUTPUT_HEIGHT
    ):
        raise AutomatedDemoError("final media does not match the fixed 30-second pipeline")
    return duration, OUTPUT_WIDTH, OUTPUT_HEIGHT


def _frame_probe_argv(video: Path, ffprobe: Path) -> tuple[str, ...]:
    return (
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
    )


def _frame_identity(video: Path, ffprobe: Path) -> tuple[int, str]:
    completed = _run(
        _frame_probe_argv(video, ffprobe),
        cwd=video.parent,
        timeout=120,
    )
    if completed.returncode != 0:
        raise AutomatedDemoError("frame PTS extraction failed")
    try:
        report = json.loads(completed.stdout.decode("utf-8"))
        frames = report["frames"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise AutomatedDemoError("frame PTS output is malformed") from error
    try:
        return automated_media.frame_pts_identity(
            frames, width=OUTPUT_WIDTH, height=OUTPUT_HEIGHT
        )
    except automated_media.AutomatedMediaError as error:
        raise AutomatedDemoError("frame PTS identity is invalid") from error


def _framemd5_argv(video: Path, ffmpeg: Path) -> tuple[str, ...]:
    return (
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
    )


def _decoded_frames_digest(video: Path, ffmpeg: Path, frame_count: int) -> str:
    completed = _run(
        _framemd5_argv(video, ffmpeg),
        cwd=video.parent,
        timeout=300,
    )
    if completed.returncode != 0:
        raise AutomatedDemoError("decoded-frame hashing failed")
    try:
        rows = [
            line
            for line in completed.stdout.decode("ascii").splitlines()
            if line and not line.startswith("#")
        ]
    except UnicodeDecodeError as error:
        raise AutomatedDemoError("decoded-frame manifest is not ASCII") from error
    if len(rows) != frame_count or any(len(row.split(",")) != 6 for row in rows):
        raise AutomatedDemoError("decoded-frame manifest has unexpected topology")
    return hashlib.sha256(completed.stdout).hexdigest()


def _validate_png(path: Path) -> None:
    payload = path.read_bytes()
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AutomatedDemoError("poster is not PNG")
    offset = 8
    forbidden = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"iCCP"}
    saw_end = False
    dimensions: tuple[int, int] | None = None
    while offset + 12 <= len(payload):
        length = int.from_bytes(payload[offset : offset + 4], "big")
        kind = payload[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(payload) or kind in forbidden:
            raise AutomatedDemoError("poster contains malformed or free-text PNG metadata")
        if kind == b"IHDR":
            if length != 13 or dimensions is not None:
                raise AutomatedDemoError("poster PNG header is malformed")
            dimensions = (
                int.from_bytes(payload[offset + 8 : offset + 12], "big"),
                int.from_bytes(payload[offset + 12 : offset + 16], "big"),
            )
        offset = end
        if kind == b"IEND":
            saw_end = True
            break
    if (
        not saw_end
        or offset != len(payload)
        or dimensions != (OUTPUT_WIDTH, OUTPUT_HEIGHT)
    ):
        raise AutomatedDemoError("poster PNG topology is malformed")


def _privacy_scan(paths: Sequence[Path]) -> None:
    for path in paths:
        _require_regular(path, f"privacy input {path.name}")
        overlap = b""
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                payload = overlap + chunk
                if any(pattern.search(payload) for pattern in PRIVATE_BYTE_PATTERNS):
                    raise AutomatedDemoError(
                        f"configured privacy pattern detected in {path.name}"
                    )
                overlap = payload[-4096:]


def _poster_argv(ffmpeg: Path, video: Path, poster: Path) -> tuple[str, ...]:
    return (
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
        str(poster),
    )


def _composition_argv(
    ffmpeg: Path,
    presentation: Path,
    result: Path,
    video: Path,
) -> tuple[str, ...]:
    return (
        str(ffmpeg),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(presentation),
        "-i",
        str(result),
        "-filter_complex",
        _fixed_filter(),
        "-map",
        "[outv]",
        "-an",
        "-c:v",
        "h264_videotoolbox",
        "-b:v",
        "8M",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(OUTPUT_FRAME_RATE),
        "-fflags",
        "+bitexact",
        "-flags:v",
        "+bitexact",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-metadata",
        "title=",
        "-metadata",
        "comment=",
        "-metadata",
        "creation_time=",
        "-metadata",
        "encoder=",
        "-metadata:s:v:0",
        "title=",
        "-metadata:s:v:0",
        "encoder=",
        "-empty_hdlr_name",
        "1",
        "-movflags",
        "+faststart",
        str(video),
    )


def _assemble_media(configuration: Configuration) -> MediaIdentity:
    presentation = configuration.output / "post-proof-presentation.mov"
    result = configuration.output / "same-run-result.mov"
    video = configuration.output / f"{configuration.tag}-demo.mp4"
    poster = configuration.output / f"{configuration.tag}-demo-poster.png"
    for target in (video, poster):
        if target.exists() or target.is_symlink():
            raise AutomatedDemoError("final media target already exists")
    composition = _run(
        _composition_argv(configuration.ffmpeg, presentation, result, video),
        cwd=configuration.output,
        timeout=300,
    )
    if composition.returncode != 0:
        raise AutomatedDemoError("fixed FFmpeg composition failed")
    poster_result = _run(
        _poster_argv(configuration.ffmpeg, video, poster),
        cwd=configuration.output,
        timeout=120,
    )
    if poster_result.returncode != 0:
        raise AutomatedDemoError("fixed poster extraction failed")
    _require_regular(video, "final video")
    _require_regular(poster, "final poster", maximum_bytes=128 * 1024 * 1024)
    _validate_png(poster)
    duration, width, height = _probe_final(video, configuration)
    frame_count, pts_sha256 = _frame_identity(video, configuration.ffprobe)
    if frame_count != EXPECTED_FRAME_COUNT:
        raise AutomatedDemoError("final media frame count differs from the fixed pipeline")
    frames_sha256 = _decoded_frames_digest(video, configuration.ffmpeg, frame_count)
    _privacy_scan((video, poster))
    return MediaIdentity(
        video=video,
        poster=poster,
        video_sha256=_sha256_path(video),
        poster_sha256=_sha256_path(poster),
        duration_seconds=duration,
        width=width,
        height=height,
        frame_count=frame_count,
        pts_sha256=pts_sha256,
        decoded_frames_sha256=frames_sha256,
    )


def _build_report(
    *,
    source: SourceIdentity,
    proof: ProofIdentity,
    preflight: CaptureSegment,
    presentation: CaptureSegment,
    result: CaptureSegment,
    tools: dict[str, Any],
    media: MediaIdentity,
    state_sha256: str,
    result_readiness_sha256: str,
    tag_ci_receipt_sha256: str,
    local_tag_trust_receipt_sha256: str,
) -> dict[str, Any]:
    report = {
        "schema_version": automated_media.SCHEMA_VERSION,
        "report_kind": automated_media.REPORT_KIND,
        "verdict": automated_media.VERDICT,
        "automation_contract": automated_media.AUTOMATION_CONTRACT,
        "classification": automated_media.MEDIA_CLASSIFICATION,
        "automation_only": True,
        "human_reviewed": False,
        "manual_edits": False,
        "machine_evidence": False,
        "pixel_semantics_verified": False,
        "source": {
            "tag": source.tag,
            "commit": source.commit,
            "tree": source.tree,
        },
        "run": {
            "identifier": proof.identifier,
            "challenge_sha256": proof.challenge_sha256,
            "receipt_sha256": proof.receipt_sha256,
            "result_sha256": proof.result_sha256,
            "application_executable_sha256": proof.application_executable_sha256,
            "metric_verdict": proof.metric_verdict,
            "terminal_outcome": proof.terminal_outcome,
            "structural_verdict": "PASS",
            "replay_verdict": automated_media.REPLAY_VERDICT,
            "workload_classification": automated_media.WORKLOAD_CLASSIFICATION,
            "synthetic_data": False,
        },
        "capture": {
            "mode": automated_media.CAPTURE_MODE,
            "bundle_identifier": automated_media.BUNDLE_IDENTIFIER,
            "result_readiness_sha256": result_readiness_sha256,
            "preflight_segment": preflight.report(),
            "segments": [presentation.report(), result.report()],
        },
        "tools": tools,
        "output": {
            "video_sha256": media.video_sha256,
            "poster_sha256": media.poster_sha256,
            "poster_frame_timestamp_seconds": automated_media.POSTER_TIMESTAMP_SECONDS,
            "duration_seconds": media.duration_seconds,
            "width": media.width,
            "height": media.height,
            "frame_count": media.frame_count,
            "pts_sha256": media.pts_sha256,
            "decoded_frames_sha256": media.decoded_frames_sha256,
        },
        "privacy": {
            "input_surface": "ALLOWLISTED_APP_VIEW_ONLY",
            "byte_and_metadata_scan": "PASS",
            "ocr_role": "NOT_RUN_NOT_A_COMPLETENESS_PROOF",
            "verdict": "NO_CONFIGURED_PATTERN_DETECTED",
            "semantic_pixel_privacy": "NOT_CLAIMED",
        },
        "attempt": {
            "proof_invocation_count": 1,
            "event_count": automated_media.ATTEMPT_EVENT_COUNT,
            "scope": automated_media.ATTEMPT_SCOPE,
            "state_log_sha256": state_sha256,
            "tag_ci_receipt_sha256": tag_ci_receipt_sha256,
            "local_tag_trust_receipt_sha256": local_tag_trust_receipt_sha256,
        },
    }
    automated_media.validate_report(report)
    return report


def _execute_reserved_attempt(
    configuration: Configuration,
    source: SourceIdentity,
    prepared: PreparedTools,
    attempt: AttemptLog,
) -> dict[str, Any]:
    if prepared.preflight_capture is None:
        raise AutomatedDemoError("preflight segment identity was not retained")
    if SHA256_PATTERN.fullmatch(prepared.tag_ci_receipt_sha256) is None:
        raise AutomatedDemoError("verified tag-CI receipt identity is unavailable")
    if SHA256_PATTERN.fullmatch(prepared.local_tag_trust_receipt_sha256) is None:
        raise AutomatedDemoError("verified local tag trust identity is unavailable")
    before = _snapshot_runs(configuration.home)
    challenge = os.urandom(32).hex()
    proof_log_path = configuration.output / "proof-driver.log"
    proof_descriptor = os.open(
        proof_log_path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    proof_log = os.fdopen(proof_descriptor, "wb", closefd=True)
    proof_process: subprocess.Popen[Any] | None = None
    try:
        attempt.append(
            "PROOF_INVOKED",
            proof_invocation_count=1,
            challenge_sha256=automated_media.challenge_sha256(challenge),
        )
        proof_process = subprocess.Popen(
            _proof_argv(),
            cwd=ROOT,
            env=_proof_environment(configuration, challenge),
            stdout=proof_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            proof_status = proof_process.wait(timeout=PROOF_WAIT_SECONDS)
        except subprocess.TimeoutExpired as error:
            _terminate_process(proof_process)
            raise AutomatedDemoError(
                "the one proof invocation exceeded its hard timeout"
            ) from error
    finally:
        proof_log.close()

    if proof_process is None:
        raise AutomatedDemoError("the one proof invocation was not started")
    if proof_status != 0:
        raise AutomatedDemoError(f"the one proof invocation exited with status {proof_status}")
    run = _new_run_directory(configuration.home, before)
    proof = _inspect_proof(run, source, challenge)
    attempt.append(
        "PROOF_TERMINAL",
        metric_verdict=proof.metric_verdict,
        run_identifier=proof.identifier,
        terminal_outcome=proof.terminal_outcome,
    )
    attempt.append(
        "REPLAY_VERIFIED",
        replay_verdict=automated_media.REPLAY_VERDICT,
        run_identifier=proof.identifier,
    )

    _validate_proof_application_executable(
        proof,
        label="post-proof presentation application executable before launch",
    )
    presentation_log_path = configuration.output / "post-proof-presentation-ui.log"
    descriptor = os.open(
        presentation_log_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    presentation_log = os.fdopen(descriptor, "wb", closefd=True)
    presentation_process: subprocess.Popen[Any] | None = None
    try:
        presentation_process = subprocess.Popen(
            _post_proof_presentation_argv(),
            cwd=ROOT,
            env=_safe_environment(configuration.home),
            stdout=presentation_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        window = _wait_for_window(
            presentation_process.pid,
            prepared.helper,
            configuration.home,
            timeout=RESULT_WINDOW_WAIT_SECONDS,
        )
        _validate_window_executable(
            window,
            expected_sha256=proof.application_executable_sha256,
            label="post-proof presentation window",
        )
        window = _recheck_window(
            prepared.helper,
            window,
            configuration.home,
            label="post-proof presentation window",
        )
        _validate_window_executable(
            window,
            expected_sha256=proof.application_executable_sha256,
            label="post-proof presentation window before capture",
        )
        if window.executable_sha256 is None:
            raise AutomatedDemoError(
                "post-proof presentation executable identity is unavailable"
            )
        attempt.append(
            "POST_PROOF_PRESENTATION_SURFACE_READY",
            executable_sha256=window.executable_sha256,
            owner_pid=window.pid,
            window_id=window.window_id,
        )
        presentation = _capture_segment(
            role="post_proof_presentation",
            window=window,
            destination=configuration.output / "post-proof-presentation.mov",
            duration=automated_media.POST_PROOF_PRESENTATION_SEGMENT_SECONDS,
            ffprobe=configuration.ffprobe,
        )
        window = _recheck_window(
            prepared.helper,
            window,
            configuration.home,
            label="post-proof presentation window after capture",
        )
        _validate_window_executable(
            window,
            expected_sha256=proof.application_executable_sha256,
            label="post-proof presentation window after capture",
        )
        attempt.append(
            "POST_PROOF_PRESENTATION_CAPTURED",
            segment_sha256=presentation.sha256,
            window_id=presentation.window_id,
        )
    except Exception as error:
        raise AutomatedDemoError(
            f"post-proof presentation capture failed: {error}"
        ) from error
    finally:
        if presentation_process is not None:
            _terminate_process(presentation_process)
        presentation_log.close()

    result, result_readiness_sha256 = _launch_result_capture(
        configuration,
        prepared.helper,
        proof,
        attempt,
    )
    media = _assemble_media(configuration)
    attempt.append(
        "MEDIA_SEALED_FOR_COLLECTION",
        poster_sha256=media.poster_sha256,
        video_sha256=media.video_sha256,
    )
    state_bytes, state_sha256 = attempt.snapshot_success(
        configuration.output / "attempt-state.jsonl"
    )
    report = _build_report(
        source=source,
        proof=proof,
        preflight=prepared.preflight_capture,
        presentation=presentation,
        result=result,
        tools=prepared.report,
        media=media,
        state_sha256=state_sha256,
        result_readiness_sha256=result_readiness_sha256,
        tag_ci_receipt_sha256=prepared.tag_ci_receipt_sha256,
        local_tag_trust_receipt_sha256=prepared.local_tag_trust_receipt_sha256,
    )
    automated_media.validate_attempt_state_bytes(state_bytes, report=report)
    receipt = configuration.output / "automation-receipt.json"
    automated_media.write_report(receipt, report)
    return report


def orchestrate(configuration: Configuration) -> dict[str, Any]:
    source = _source_preflight(configuration.tag)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{configuration.tag}-automation-",
            dir=configuration.output.parent,
        )
    ).resolve(strict=True)
    staging.chmod(0o700)
    attempt: AttemptLog | None = None
    try:
        prepared = _host_and_tool_preflight(configuration, staging)
        confirmed_source = _source_preflight(configuration.tag)
        if confirmed_source != source:
            raise AutomatedDemoError("tagged source changed during capture preflight")
        _pre_marker_resources(configuration)
        _recheck_prepared_tools(configuration, prepared)
        (
            tag_ci_receipt,
            tag_ci_receipt_sha256,
            local_tag_trust_receipt_sha256,
        ) = _prepare_verified_tag_ci_receipt(
            configuration, confirmed_source, staging
        )
        if tag_ci_receipt != staging / "tag-ci-receipt.json":
            raise AutomatedDemoError("tag-CI receipt path is not the fixed session path")
        _require_regular(
            tag_ci_receipt,
            "verified tag-CI receipt",
            maximum_bytes=automated_media.MAX_REPORT_BYTES,
        )
        if _sha256_path(tag_ci_receipt) != tag_ci_receipt_sha256:
            raise AutomatedDemoError("verified tag-CI receipt digest changed")
        if prepared.preflight_capture is None:
            raise AutomatedDemoError("preflight capture identity is unavailable")
        helper_sha256 = prepared.report["window_helper"]["executable_sha256"]
        attempt = AttemptLog.reserve(
            configuration.home,
            configuration.tag,
            source=confirmed_source,
            preflight_capture=prepared.preflight_capture,
            window_helper_sha256=helper_sha256,
            tag_ci_receipt_sha256=tag_ci_receipt_sha256,
            local_tag_trust_receipt_sha256=local_tag_trust_receipt_sha256,
        )
        try:
            staging.rename(configuration.output)
            prepared = PreparedTools(
                staging=configuration.output,
                helper=configuration.output / prepared.helper.name,
                report=prepared.report,
                preflight_capture=prepared.preflight_capture,
                tag_ci_receipt_sha256=tag_ci_receipt_sha256,
                local_tag_trust_receipt_sha256=local_tag_trust_receipt_sha256,
            )
            return _execute_reserved_attempt(configuration, source, prepared, attempt)
        except Exception as error:
            try:
                attempt.append("ATTEMPT_FAILED", error_type=type(error).__name__)
            except Exception:
                pass
            raise
    except Exception:
        if attempt is None and staging.exists():
            shutil.rmtree(staging)
        raise
    finally:
        if attempt is not None:
            attempt.close()


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ffmpeg", required=True, type=Path)
    parser.add_argument("--ffprobe", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    os.umask(0o077)
    try:
        configuration = _validate_configuration(parse_arguments(argv))
        report = orchestrate(configuration)
    except (
        AutomatedDemoError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"AUTOMATED PORTFOLIO DEMO FAIL: {error}", file=sys.stderr)
        return 1
    print("AUTOMATED PORTFOLIO DEMO PASS")
    print(f"Tag: {report['source']['tag']}")
    print(f"Run: {report['run']['identifier']}")
    print(f"Metric verdict: {report['run']['metric_verdict']}")
    print(f"Video SHA-256: {report['output']['video_sha256']}")
    print(f"Poster SHA-256: {report['output']['poster_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
