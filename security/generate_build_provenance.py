#!/usr/bin/env python3
"""Generate and validate canonical source/build provenance for the macOS app."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit


BUILD_SCHEMA_VERSION = "corelm-build-provenance-v1"
ARCHIVE_SCHEMA_VERSION = "corelm-source-archive-manifest-v1"
DEFAULT_ARCHIVE_MANIFEST = "SOURCE_ARCHIVE_PROVENANCE.json"
MAXIMUM_MANIFEST_BYTES = 32 * 1024 * 1024
MAXIMUM_SOURCE_FILES = 100_000
MAXIMUM_SOURCE_BYTES = 16 * 1024 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024
GIT_OBJECT_ID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
SAFE_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+@-]{0,199}")
IGNORED_TOP_LEVEL = frozenset({".build", ".git", "dist", "output", "tmp"})

BUILD_KEYS = {"schemaVersion", "source", "toolchain"}
SOURCE_KEYS = {
    "archiveManifestSHA256",
    "commit",
    "dirty",
    "exactTag",
    "mode",
    "remote",
    "tree",
}
TOOLCHAIN_KEYS = {"developerTools", "macOS", "sdk", "swift"}
MACOS_KEYS = {"architecture", "buildVersion", "productName", "productVersion"}
SWIFT_KEYS = {"compiler", "compilerSHA256", "target", "version"}
SDK_KEYS = {"buildVersion", "canonicalName", "version"}
DEVELOPER_TOOLS_KEYS = {"buildVersion", "identifier", "kind", "version"}
ARCHIVE_KEYS = {"files", "schemaVersion", "source"}
ARCHIVE_SOURCE_KEYS = {"commit", "dirty", "exactTag", "remote", "tree"}
ARCHIVE_FILE_KEYS = {"path", "sha256", "sizeBytes"}


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _safe_text(value: Any, label: str, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > maximum
        or any(ord(character) < 0x20 and character not in "\n\t" for character in value)
    ):
        raise ValueError(f"{label} is missing or malformed")
    return value


def _object_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or GIT_OBJECT_ID.fullmatch(value) is None:
        raise ValueError(f"{label} is not a canonical Git object ID")
    return value


def _exact_tag(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or SAFE_TAG.fullmatch(value) is None:
        raise ValueError("exactTag is malformed")
    return value


def _remote(value: Any) -> str:
    remote = _safe_text(value, "source remote", maximum=2048)
    if "\n" in remote or "\r" in remote or remote.startswith(("/", "~", ".")):
        raise ValueError("source remote is local, unsafe, or malformed")
    parsed = urlsplit(remote)
    if parsed.scheme:
        if parsed.scheme not in {"https", "ssh", "git"} or not parsed.hostname:
            raise ValueError("source remote uses an unsupported URL form")
        if parsed.password is not None or (
            parsed.scheme in {"https", "git"} and parsed.username is not None
        ):
            raise ValueError("source remote must not embed credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("source remote must not contain a query or fragment")
        return remote
    if re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[^\s]+", remote) is None:
        raise ValueError("source remote is not a public URL or SSH remote")
    return remote


def clean_subprocess_environment() -> Dict[str, str]:
    """Return a deterministic environment with no Git/toolchain overrides."""

    return {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": "/var/empty",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    }


def _command(arguments: List[str], cwd: Optional[Path] = None) -> str:
    completed = subprocess.run(
        arguments,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=clean_subprocess_environment(),
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"{' '.join(arguments)} failed: {detail}")
    output = completed.stdout.strip()
    if not output:
        raise ValueError(f"{' '.join(arguments)} returned no output")
    return output


def _sha256_regular_file(path: Path) -> Tuple[str, int]:
    expected = path.lstat()
    if not stat.S_ISREG(expected.st_mode):
        raise ValueError(f"source entry is not a regular file: {path}")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != expected.st_dev
            or opened.st_ino != expected.st_ino
            or opened.st_size != expected.st_size
        ):
            raise ValueError(f"source entry changed before hashing: {path}")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
        finished = os.fstat(descriptor)
        if (
            finished.st_dev != opened.st_dev
            or finished.st_ino != opened.st_ino
            or finished.st_size != opened.st_size
            or finished.st_mtime_ns != opened.st_mtime_ns
            or finished.st_ctime_ns != opened.st_ctime_ns
        ):
            raise ValueError(f"source entry changed while hashing: {path}")
        return digest.hexdigest(), opened.st_size
    finally:
        os.close(descriptor)


def _ignored_source_path(relative: PurePosixPath) -> bool:
    if not relative.parts:
        return False
    return (
        relative.parts[0] in IGNORED_TOP_LEVEL
        or "__pycache__" in relative.parts
        or relative.name == ".DS_Store"
        or relative.suffix in {".pyc", ".pyo"}
    )


def _source_files(
    project: Path,
    excluded: Iterable[Path] = (),
) -> List[Dict[str, Any]]:
    root = project.resolve(strict=True)
    # Exclude only the exact lexical manifest path. Resolving exclusions here
    # would also exclude a different symlink that merely points at the
    # manifest, hiding an extra unsupported source-tree entry.
    exclusions = {
        Path(os.path.abspath(os.fspath(path)))
        for path in excluded
    }
    entries: List[Dict[str, Any]] = []
    total_bytes = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if _ignored_source_path(relative):
            continue
        status = path.lstat()
        lexical_path = Path(os.path.abspath(os.fspath(path)))
        if lexical_path in exclusions:
            if not stat.S_ISREG(status.st_mode):
                raise ValueError(
                    f"excluded source entry is not a regular file: {relative}"
                )
            continue
        if stat.S_ISDIR(status.st_mode):
            continue
        if not stat.S_ISREG(status.st_mode):
            raise ValueError(f"source archive contains an unsupported entry: {relative}")
        digest, size = _sha256_regular_file(path)
        total_bytes += size
        if total_bytes > MAXIMUM_SOURCE_BYTES:
            raise ValueError("source archive exceeds the byte limit")
        entries.append(
            {"path": relative.as_posix(), "sha256": digest, "sizeBytes": size}
        )
        if len(entries) > MAXIMUM_SOURCE_FILES:
            raise ValueError("source archive exceeds the file-count limit")
    return entries


def _validate_source_identity(source: Any) -> Dict[str, Any]:
    if not isinstance(source, dict) or set(source) != ARCHIVE_SOURCE_KEYS:
        raise ValueError("source archive identity fields are not exact")
    dirty = source.get("dirty")
    if not isinstance(dirty, bool):
        raise ValueError("source archive dirty state is malformed")
    return {
        "commit": _object_id(source.get("commit"), "source commit"),
        "dirty": dirty,
        "exactTag": _exact_tag(source.get("exactTag")),
        "remote": _remote(source.get("remote")),
        "tree": _object_id(source.get("tree"), "source tree"),
    }


def build_source_archive_manifest(
    project: Path,
    *,
    commit: str,
    tree: str,
    remote: str,
    exact_tag: Optional[str],
    dirty: bool,
    output: Path,
) -> Dict[str, Any]:
    project = project.resolve(strict=True)
    output = output if output.is_absolute() else project / output
    source = _validate_source_identity(
        {
            "commit": commit,
            "dirty": dirty,
            "exactTag": exact_tag,
            "remote": remote,
            "tree": tree,
        }
    )
    return {
        "files": _source_files(project, excluded=(output,)),
        "schemaVersion": ARCHIVE_SCHEMA_VERSION,
        "source": source,
    }


def _load_canonical_json(path: Path, expected_schema: str) -> Dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"manifest is missing or unsafe: {path}")
    if path.stat().st_size > MAXIMUM_MANIFEST_BYTES:
        raise ValueError("manifest exceeds the byte limit")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"manifest is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict) or value.get("schemaVersion") != expected_schema:
        raise ValueError("manifest schema is missing or unsupported")
    if raw != canonical_json_bytes(value):
        raise ValueError("manifest is not canonical JSON")
    return value


def inspect_source_archive(project: Path, manifest_path: Path) -> Dict[str, Any]:
    project = project.resolve(strict=True)
    if manifest_path.is_symlink():
        raise ValueError("source archive manifest must not be a symbolic link")
    manifest_path = manifest_path.resolve(strict=True)
    if project not in manifest_path.parents:
        raise ValueError("source archive manifest must be inside the source tree")
    manifest = _load_canonical_json(manifest_path, ARCHIVE_SCHEMA_VERSION)
    if set(manifest) != ARCHIVE_KEYS:
        raise ValueError("source archive manifest fields are not exact")
    source = _validate_source_identity(manifest.get("source"))
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) > MAXIMUM_SOURCE_FILES:
        raise ValueError("source archive file list is malformed")
    expected: Dict[str, Tuple[str, int]] = {}
    total_bytes = 0
    previous = ""
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != ARCHIVE_FILE_KEYS:
            raise ValueError("source archive file entry fields are not exact")
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
            raise ValueError("source archive file path is malformed")
        relative = PurePosixPath(raw_path)
        if relative.is_absolute() or "." in relative.parts or ".." in relative.parts:
            raise ValueError("source archive file path is unsafe")
        if raw_path <= previous or raw_path in expected:
            raise ValueError("source archive files are not strictly sorted and unique")
        previous = raw_path
        digest = entry.get("sha256")
        size = entry.get("sizeBytes")
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
        ):
            raise ValueError("source archive file digest or size is malformed")
        total_bytes += size
        if total_bytes > MAXIMUM_SOURCE_BYTES:
            raise ValueError("source archive manifest exceeds the byte limit")
        expected[raw_path] = (digest, size)

    observed_entries = _source_files(project, excluded=(manifest_path,))
    observed = {
        entry["path"]: (entry["sha256"], entry["sizeBytes"])
        for entry in observed_entries
    }
    dirty = bool(source["dirty"] or observed != expected)
    digest, _ = _sha256_regular_file(manifest_path)
    return {
        "archiveManifestSHA256": digest,
        "commit": source["commit"],
        "dirty": dirty,
        "exactTag": source["exactTag"],
        "mode": "archive",
        "remote": source["remote"],
        "tree": source["tree"],
    }


def inspect_git_source(project: Path) -> Dict[str, Any]:
    project = project.resolve(strict=True)
    git = "/usr/bin/git"
    top_level = Path(
        _command([git, "rev-parse", "--show-toplevel"], cwd=project)
    ).resolve(strict=True)
    if top_level != project:
        raise ValueError("project is not the exact root of its Git worktree")
    commit = _object_id(
        _command([git, "rev-parse", "--verify", "HEAD^{commit}"], cwd=project),
        "source commit",
    )
    tree = _object_id(
        _command([git, "rev-parse", "--verify", "HEAD^{tree}"], cwd=project),
        "source tree",
    )
    remote = _remote(
        _command([git, "remote", "get-url", "origin"], cwd=project)
    )
    tags_output = subprocess.run(
        [git, "tag", "--points-at", "HEAD"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=clean_subprocess_environment(),
    )
    if tags_output.returncode:
        raise ValueError("cannot determine exact Git tags")
    tags = sorted(line for line in tags_output.stdout.splitlines() if line)
    if len(tags) > 1:
        raise ValueError("HEAD has multiple exact tags; provenance is ambiguous")
    exact_tag = _exact_tag(tags[0] if tags else None)
    status = subprocess.run(
        [
            git,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored=no",
            "--ignore-submodules=none",
        ],
        cwd=project,
        check=False,
        capture_output=True,
        timeout=30,
        env=clean_subprocess_environment(),
    )
    if status.returncode:
        raise ValueError("cannot determine Git worktree state")
    return {
        "archiveManifestSHA256": None,
        "commit": commit,
        "dirty": bool(status.stdout),
        "exactTag": exact_tag,
        "mode": "git",
        "remote": remote,
        "tree": tree,
    }


def _developer_tools_identity(
    selected_swift: Path,
) -> Dict[str, Optional[str]]:
    selected = selected_swift.as_posix()
    if "/CommandLineTools/" in selected:
        details = _command(
            ["/usr/sbin/pkgutil", "--pkg-info", "com.apple.pkg.CLTools_Executables"]
        )
        version = next(
            (
                line.split(":", 1)[1].strip()
                for line in details.splitlines()
                if line.startswith("version:")
            ),
            None,
        )
        if not version:
            raise ValueError("Command Line Tools package version is missing")
        return {
            "buildVersion": None,
            "identifier": "com.apple.pkg.CLTools_Executables",
            "kind": "command-line-tools",
            "version": version,
        }
    if ".app/Contents/Developer/" in selected:
        output = _command(["/usr/bin/xcodebuild", "-version"])
        version = next(
            (
                line.removeprefix("Xcode ").strip()
                for line in output.splitlines()
                if line.startswith("Xcode ")
            ),
            None,
        )
        build = next(
            (
                line.removeprefix("Build version ").strip()
                for line in output.splitlines()
                if line.startswith("Build version ")
            ),
            None,
        )
        if not version or not build:
            raise ValueError("Xcode version identity is malformed")
        return {
            "buildVersion": build,
            "identifier": "com.apple.dt.Xcode",
            "kind": "xcode",
            "version": version,
        }
    raise ValueError("active Apple developer tools location is unsupported")


def inspect_toolchain() -> Dict[str, Any]:
    declared_swift = shutil.which("swift")
    if declared_swift is None:
        raise ValueError("Swift compiler is missing from PATH")
    selected_swift = declared_swift
    if Path(declared_swift).resolve(strict=True) == Path("/usr/bin/swift"):
        selected_swift = _command(["/usr/bin/xcrun", "--find", "swift"])
    resolved_swift = Path(selected_swift).resolve(strict=True)
    compiler_digest, _ = _sha256_regular_file(resolved_swift)
    version_output = _command([selected_swift, "--version"])
    lines = [line.strip() for line in version_output.splitlines() if line.strip()]
    target = next(
        (line.split(":", 1)[1].strip() for line in lines if line.startswith("Target:")),
        None,
    )
    version = next((line for line in lines if "Swift version" in line), None)
    if not version or not target:
        raise ValueError("Swift version output is malformed")
    return {
        "developerTools": _developer_tools_identity(resolved_swift),
        "macOS": {
            "architecture": _command(["/usr/bin/uname", "-m"]),
            "buildVersion": _command(["/usr/bin/sw_vers", "-buildVersion"]),
            "productName": _command(["/usr/bin/sw_vers", "-productName"]),
            "productVersion": _command(["/usr/bin/sw_vers", "-productVersion"]),
        },
        "sdk": {
            "buildVersion": _command(
                ["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-build-version"]
            ),
            "canonicalName": "macosx",
            "version": _command(
                ["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-version"]
            ),
        },
        "swift": {
            "compiler": resolved_swift.name,
            "compilerSHA256": compiler_digest,
            "target": target,
            "version": version,
        },
    }


def build_manifest(
    project: Path,
    *,
    archive_manifest: Optional[Path] = None,
    allow_dirty: bool = False,
) -> Dict[str, Any]:
    project = project.resolve(strict=True)
    git_probe = subprocess.run(
        ["/usr/bin/git", "rev-parse", "--is-inside-work-tree"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=clean_subprocess_environment(),
    )
    in_git = git_probe.returncode == 0 and git_probe.stdout.strip() == "true"
    if in_git:
        if archive_manifest is not None:
            raise ValueError("archive metadata is ambiguous inside a Git worktree")
        source = inspect_git_source(project)
    else:
        if archive_manifest is None:
            candidate = project / DEFAULT_ARCHIVE_MANIFEST
            if candidate.is_file() and not candidate.is_symlink():
                archive_manifest = candidate
            else:
                raise ValueError(
                    "non-Git source requires a documented "
                    f"{DEFAULT_ARCHIVE_MANIFEST}"
                )
        source = inspect_source_archive(project, archive_manifest)
    if source["dirty"] and not allow_dirty:
        raise ValueError(
            "source is dirty; evidence builds require an unchanged Git checkout "
            "or verified source archive"
        )
    manifest = {
        "schemaVersion": BUILD_SCHEMA_VERSION,
        "source": source,
        "toolchain": inspect_toolchain(),
    }
    validate_build_manifest(manifest)
    return manifest


def _validate_optional_tool_value(value: Any, label: str) -> Optional[str]:
    if value is None:
        return None
    return _safe_text(value, label, maximum=4096)


def validate_build_manifest(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != BUILD_KEYS:
        raise ValueError("build provenance fields are not exact")
    if value.get("schemaVersion") != BUILD_SCHEMA_VERSION:
        raise ValueError("build provenance schema is unsupported")
    serialized = canonical_json_bytes(value)
    if any(
        marker in serialized
        for marker in (
            b"/Users/",
            b"/home/",
            b"/private/",
            b"/tmp/",
            b"\\\\Users\\\\",
        )
    ):
        raise ValueError("build provenance must not disclose a local path")
    source = value.get("source")
    if not isinstance(source, dict) or set(source) != SOURCE_KEYS:
        raise ValueError("build provenance source fields are not exact")
    mode = source.get("mode")
    if mode not in {"git", "archive"}:
        raise ValueError("build provenance source mode is unsupported")
    _object_id(source.get("commit"), "source commit")
    _object_id(source.get("tree"), "source tree")
    _remote(source.get("remote"))
    _exact_tag(source.get("exactTag"))
    if not isinstance(source.get("dirty"), bool):
        raise ValueError("build provenance dirty state is malformed")
    archive_digest = source.get("archiveManifestSHA256")
    if mode == "git":
        if archive_digest is not None:
            raise ValueError("Git provenance must not claim an archive manifest")
    elif (
        not isinstance(archive_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", archive_digest) is None
    ):
        raise ValueError("archive provenance has no valid manifest digest")

    toolchain = value.get("toolchain")
    if not isinstance(toolchain, dict) or set(toolchain) != TOOLCHAIN_KEYS:
        raise ValueError("build provenance toolchain fields are not exact")
    macos = toolchain.get("macOS")
    if not isinstance(macos, dict) or set(macos) != MACOS_KEYS:
        raise ValueError("macOS toolchain identity fields are not exact")
    for key in MACOS_KEYS:
        _safe_text(macos.get(key), f"macOS {key}")
    swift = toolchain.get("swift")
    if not isinstance(swift, dict) or set(swift) != SWIFT_KEYS:
        raise ValueError("Swift toolchain identity fields are not exact")
    for key in ("compiler", "target", "version"):
        _safe_text(swift.get(key), f"Swift {key}")
    if "/" in swift["compiler"] or "\\" in swift["compiler"]:
        raise ValueError("Swift compiler identity must be a basename")
    if re.fullmatch(r"[0-9a-f]{64}", str(swift.get("compilerSHA256"))) is None:
        raise ValueError("Swift compiler digest is malformed")
    sdk = toolchain.get("sdk")
    if not isinstance(sdk, dict) or set(sdk) != SDK_KEYS:
        raise ValueError("SDK identity fields are not exact")
    if sdk.get("canonicalName") != "macosx":
        raise ValueError("SDK canonical name is unsupported")
    for key in ("version", "buildVersion"):
        _safe_text(sdk.get(key), f"SDK {key}")
    developer_tools = toolchain.get("developerTools")
    if (
        not isinstance(developer_tools, dict)
        or set(developer_tools) != DEVELOPER_TOOLS_KEYS
    ):
        raise ValueError("developer-tools identity fields are not exact")
    if developer_tools.get("kind") not in {"command-line-tools", "xcode"}:
        raise ValueError("developer-tools kind is unsupported")
    for key in ("identifier", "version"):
        _safe_text(developer_tools.get(key), f"developer tools {key}")
    _validate_optional_tool_value(
        developer_tools.get("buildVersion"), "developer tools buildVersion"
    )


def verify_build_manifest(path: Path) -> Dict[str, Any]:
    value = _load_canonical_json(path, BUILD_SCHEMA_VERSION)
    validate_build_manifest(value)
    return value


def _exclusive_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--verify", type=Path)
    mode.add_argument("--create-archive-manifest", type=Path)
    parser.add_argument("--archive-manifest", type=Path)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--commit")
    parser.add_argument("--tree")
    parser.add_argument("--remote")
    parser.add_argument("--exact-tag")
    parser.add_argument("--source-dirty", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        project = arguments.project.resolve(strict=True)
        if arguments.verify is not None:
            verify_build_manifest(arguments.verify)
            print(f"BUILD PROVENANCE PASS: {arguments.verify}")
            return 0
        if arguments.create_archive_manifest is not None:
            if not arguments.commit or not arguments.tree or not arguments.remote:
                raise ValueError(
                    "archive manifest creation requires --commit, --tree, and --remote"
                )
            output = arguments.create_archive_manifest
            if not output.is_absolute():
                output = project / output
            manifest = build_source_archive_manifest(
                project,
                commit=arguments.commit,
                tree=arguments.tree,
                remote=arguments.remote,
                exact_tag=arguments.exact_tag,
                dirty=arguments.source_dirty,
                output=output,
            )
            _exclusive_write(output, canonical_json_bytes(manifest))
            print(output)
            return 0
        output = arguments.output
        if output is None:
            raise ValueError("build provenance output is missing")
        if not output.is_absolute():
            output = project / output
        archive_manifest = arguments.archive_manifest
        if archive_manifest is not None and not archive_manifest.is_absolute():
            archive_manifest = project / archive_manifest
        manifest = build_manifest(
            project,
            archive_manifest=archive_manifest,
            allow_dirty=arguments.allow_dirty,
        )
        _exclusive_write(output, canonical_json_bytes(manifest))
        print(output)
        return 0
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"BUILD PROVENANCE FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
