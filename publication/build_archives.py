#!/usr/bin/env python3
"""Build deterministic arXiv and reproducibility archives."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


ROOT = Path(__file__).resolve().parents[1]
PUBLICATION = ROOT / "publication"
ARXIV_V5 = PUBLICATION / "arxiv-v5"
OUTPUT = ROOT / "output"
BEACON_FREEZE_PATH = ROOT / "RealLLM/beacon_freeze.json"
ARCHIVE_MTIME = 0
PUBLIC_ORIGIN = "https://github.com/ALLPROTO/core-lm-benchmark"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from security.generate_build_provenance import (  # noqa: E402
    DEFAULT_ARCHIVE_MANIFEST,
    build_source_archive_manifest,
    canonical_json_bytes,
    clean_subprocess_environment,
)
V5_PHASE_PATHS = {
    "selectionAttempt": ROOT
    / "real-llm-v5-results"
    / "selection.attempt.json",
    "selectionResult": ROOT / "real-llm-v5-results" / "selection.json",
    "holdoutAttempt": ROOT / "real-llm-v5-results" / "holdout.attempt.json",
    "holdoutResult": ROOT / "real-llm-v5-results" / "holdout.json",
}
V5_ARXIV_SOURCE_FILES = (
    "main.tex",
    "author.tex",
    "references.bib",
    "main.bbl",
    "results_table.tex",
    "figures/block_metrics.pdf",
    "figures/codec_pipeline.pdf",
    "figures/protocol_timeline.pdf",
)


def _git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["/usr/bin/git", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env=clean_subprocess_environment(),
    )
    if check and completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"git {' '.join(arguments)} failed: {message}")
    return completed


def _normalized_origin(value: str) -> str:
    return value.removesuffix(".git").rstrip("/")


def _build_context(release_tag: str | None) -> dict[str, object]:
    top = _git("rev-parse", "--show-toplevel", check=False)
    if top.returncode:
        if release_tag is not None:
            raise ValueError("a final release archive requires a Git worktree")
        return {
            "buildMode": "preview-artifact-tree",
            "builtFromCleanHead": False,
            "gitHeadCommit": None,
            "gitHeadTree": None,
            "releaseTag": None,
            "remoteTagVerified": False,
            "trackedFiles": None,
        }
    if Path(top.stdout.strip()).resolve() != ROOT.resolve():
        raise ValueError("archive builder must run from its exact Git worktree")
    head = _git("rev-parse", "HEAD").stdout.strip()
    head_tree = _git("rev-parse", "HEAD^{tree}").stdout.strip()
    status = _git(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignored=no",
    ).stdout
    clean = not status.strip()
    tracked_files = set(_git("ls-files", "-z").stdout.split("\0"))
    tracked_files.discard("")
    context: dict[str, object] = {
        "buildMode": "preview-working-tree",
        "builtFromCleanHead": clean,
        "gitHeadCommit": head,
        "gitHeadTree": head_tree,
        "releaseTag": None,
        "remoteTagVerified": False,
        "trackedFiles": tracked_files,
    }
    if release_tag is None:
        return context
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", release_tag)
        or ".." in release_tag
        or "//" in release_tag
    ):
        raise ValueError("release tag contains unsafe or ambiguous characters")
    if not clean:
        raise ValueError(
            "final release archives require a completely clean worktree"
        )
    reference = f"refs/tags/{release_tag}"
    if _git("cat-file", "-t", reference).stdout.strip() != "commit":
        raise ValueError("final release tag must be a lightweight Git tag")
    tag_commit = _git(
        "rev-parse", "--verify", f"{reference}^{{commit}}"
    ).stdout.strip()
    if tag_commit != head:
        raise ValueError("final release tag does not resolve to HEAD")
    origin = _git("remote", "get-url", "origin").stdout.strip()
    if _normalized_origin(origin) != _normalized_origin(PUBLIC_ORIGIN):
        raise ValueError("origin does not match the registered public repository")
    remote = _git("ls-remote", "--exit-code", "origin", reference)
    remote_lines = [line.split() for line in remote.stdout.splitlines()]
    if remote_lines != [[head, reference]]:
        raise ValueError("public origin does not expose the exact release tag")
    context.update(
        {
            "buildMode": "clean-public-tag-release",
            "releaseTag": release_tag,
            "remoteTagVerified": True,
        }
    )
    return context


def _assert_release_source(
    source: Path, build_context: dict[str, object]
) -> None:
    if build_context.get("releaseTag") is None:
        return
    try:
        relative = source.resolve(strict=True).relative_to(
            ROOT.resolve(strict=True)
        ).as_posix()
    except (OSError, ValueError) as error:
        raise ValueError(f"release input is outside the worktree: {source}") from error
    tracked = build_context.get("trackedFiles")
    if not isinstance(tracked, set) or relative not in tracked:
        raise ValueError(f"release input is not tracked by Git: {relative}")
    committed = subprocess.run(
        ["/usr/bin/git", "show", f"HEAD:{relative}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        timeout=30,
        env=clean_subprocess_environment(),
    )
    if committed.returncode or committed.stdout != source.read_bytes():
        raise ValueError(f"release input differs from HEAD: {relative}")


def _copy_optional_beacon_freeze(
    stage: Path, build_context: dict[str, object]
) -> bool:
    """Include the second-commit freeze when building at or after that commit."""

    if not os.path.lexists(BEACON_FREEZE_PATH):
        return False
    if BEACON_FREEZE_PATH.is_symlink() or not BEACON_FREEZE_PATH.is_file():
        raise ValueError("beacon freeze manifest must be a regular file")
    _assert_release_source(BEACON_FREEZE_PATH, build_context)
    destination = stage / "RealLLM/beacon_freeze.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BEACON_FREEZE_PATH, destination)
    return True


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read JSON artifact {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact is not an object: {path}")
    return value


def _v5_evidence_state() -> tuple[str, list[Path]]:
    present = {name: path.is_file() for name, path in V5_PHASE_PATHS.items()}
    if present["selectionResult"] and not present["selectionAttempt"]:
        raise ValueError("selection result exists without its attempt marker")
    if present["holdoutResult"] and not present["holdoutAttempt"]:
        raise ValueError("holdout result exists without its attempt marker")
    if (
        present["holdoutAttempt"] or present["holdoutResult"]
    ) and not present["selectionResult"]:
        raise ValueError("holdout artifact exists without a selection result")
    included: list[Path] = []
    if not present["selectionAttempt"]:
        if any(present.values()):
            raise ValueError("prospective v5 artifact state is inconsistent")
        return "registration-only", included
    included.append(V5_PHASE_PATHS["selectionAttempt"])
    if not present["selectionResult"]:
        return "selection-consumed-incomplete", included
    selection = _load_json_object(V5_PHASE_PATHS["selectionResult"])
    if type(selection.get("pass")) is not bool:
        raise ValueError("selection result has no strict boolean verdict")
    included.append(V5_PHASE_PATHS["selectionResult"])
    if selection["pass"] is False:
        if present["holdoutAttempt"] or present["holdoutResult"]:
            raise ValueError("holdout exists after terminal selection FAIL")
        return "selection-fail-terminal", included
    if not present["holdoutAttempt"]:
        if present["holdoutResult"]:
            raise ValueError("holdout result exists without its attempt marker")
        return "selection-pass-awaiting-holdout", included
    included.append(V5_PHASE_PATHS["holdoutAttempt"])
    if not present["holdoutResult"]:
        return "holdout-consumed-incomplete", included
    holdout = _load_json_object(V5_PHASE_PATHS["holdoutResult"])
    if type(holdout.get("pass")) is not bool:
        raise ValueError("holdout result has no strict boolean verdict")
    included.append(V5_PHASE_PATHS["holdoutResult"])
    return (
        "holdout-pass" if holdout["pass"] else "holdout-fail",
        included,
    )


def _validate_v5_evidence(
    *, git_provenance: bool
) -> tuple[str, list[Path]]:
    from security.verify_app_run_evidence import verify as verify_app_evidence
    from RealLLM.verify_voidtoken_v5_development import (
        verify_development_evidence,
    )
    from RealLLM.verify_voidtoken_v5_evidence import verify_available_evidence

    development_errors, _ = verify_development_evidence()
    if development_errors:
        raise ValueError(
            "v5 development evidence is invalid: "
            + "; ".join(development_errors)
        )
    prospective_errors, _ = verify_available_evidence(
        git_provenance=git_provenance
    )
    if prospective_errors:
        raise ValueError(
            "v5 prospective evidence is invalid: "
            + "; ".join(prospective_errors)
        )
    try:
        verify_app_evidence(ROOT / "app-real-llm-evidence")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(
            f"macOS app integration evidence is invalid: {error}"
        ) from error
    return _v5_evidence_state()


def normalized_tarinfo(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Remove host-specific metadata from one archive member."""
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = ARCHIVE_MTIME
    info.pax_headers = {}
    if info.isdir():
        info.mode = 0o755
    elif info.isfile():
        info.mode = 0o755 if info.mode & 0o111 else 0o644
    elif info.issym():
        info.mode = 0o777
    return info


def add_path(archive: tarfile.TarFile, source: Path, arcname: str) -> None:
    """Add one path recursively in a stable order with normalized metadata."""
    info = normalized_tarinfo(archive.gettarinfo(str(source), arcname=arcname))
    if info.isfile():
        with source.open("rb") as handle:
            archive.addfile(info, handle)
        return

    archive.addfile(info)
    if info.isdir():
        for child in sorted(source.iterdir(), key=lambda item: item.name):
            add_path(archive, child, f"{arcname}/{child.name}")


def _safe_output_directory(path: Path) -> Path:
    candidate = Path(os.path.abspath(os.fspath(path)))
    if candidate.exists() or candidate.is_symlink():
        status = candidate.lstat()
        if (
            not stat.S_ISDIR(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_mode & 0o022
        ):
            raise ValueError(
                "archive output directory is symlinked, writable, or unowned"
            )
    else:
        parent = candidate.parent.resolve(strict=True)
        if not parent.is_dir():
            raise ValueError(
                "archive output parent must be an existing canonical directory"
            )
        candidate = parent / candidate.name
        candidate.mkdir(mode=0o700)
    return candidate.resolve(strict=True)


@contextmanager
def _atomic_output_path(target: Path) -> Iterator[Path]:
    directory = _safe_output_directory(target.parent)
    canonical_target = directory / target.name
    if canonical_target.exists() or canonical_target.is_symlink():
        status = canonical_target.lstat()
        if (
            not stat.S_ISREG(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.getuid()
        ):
            raise ValueError(
                f"archive output target is unsafe: {canonical_target.name}"
            )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{canonical_target.name}.",
        dir=directory,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        yield temporary
        status = temporary.lstat()
        if not stat.S_ISREG(status.st_mode) or stat.S_ISLNK(status.st_mode):
            raise ValueError("staged archive output is not a regular file")
        temporary.chmod(0o644)
        os.replace(temporary, canonical_target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def deterministic_tar_gz(target: Path) -> Iterator[tarfile.TarFile]:
    """Create a gzip-compressed tar archive without wall-clock metadata."""
    with _atomic_output_path(target) as staged:
        with staged.open("wb") as raw:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw,
                mtime=ARCHIVE_MTIME,
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed,
                    mode="w",
                    format=tarfile.PAX_FORMAT,
                ) as archive:
                    yield archive


def build_arxiv_v5(
    output_directory: Path = OUTPUT,
    build_context: dict[str, object] | None = None,
) -> Path:
    output_directory = _safe_output_directory(output_directory)
    context = build_context or _build_context(None)
    target = (
        output_directory / "corelm_voidtoken_v5_arxiv_source.tar.gz"
    )
    main_source = (ARXIV_V5 / "main.tex").read_text(encoding="ascii")
    required_main_fragments = [
        "VoidToken v5: Prospectively Frozen Evidence",
        "voidtoken-v5-evidence-v1",
        "d1c16e88655c1fbc9884324742dee3f",
        "0b9b4bc86d973c2bf38df3a02cc090eaa",
    ]
    for fragment in required_main_fragments:
        if fragment not in main_source:
            raise ValueError(
                f"VoidToken v5 manuscript is missing: {fragment}"
            )
    forbidden_main_fragments = [
        "Closed-Loop Residual Tokenization for Stable Compression",
        "figures/metrics_by_dimension.pdf",
        "figures/error_feedback.pdf",
    ]
    for fragment in forbidden_main_fragments:
        if fragment in main_source:
            raise ValueError(
                f"VoidToken v5 manuscript contains stale v3 content: {fragment}"
            )
    results_source = (ARXIV_V5 / "results_table.tex").read_text(
        encoding="ascii"
    )
    for fragment in ["Holdout", "2.053291", "99.3896", "PASS"]:
        if fragment not in results_source:
            raise ValueError(
                f"VoidToken v5 result table is missing: {fragment}"
            )
    with deterministic_tar_gz(target) as archive:
        for relative in sorted(V5_ARXIV_SOURCE_FILES):
            source = ARXIV_V5 / relative
            if not source.is_file():
                raise FileNotFoundError(source)
            _assert_release_source(source, context)
            add_path(archive, source, relative)
    return target


def build_arxiv(
    output_directory: Path = OUTPUT,
    build_context: dict[str, object] | None = None,
) -> Path:
    """Backward-compatible entry point for the current v5 paper."""
    return build_arxiv_v5(output_directory, build_context)


def _v5_provenance_document(
    build_context: dict[str, object],
    evidence_state: str,
    prospective_artifacts: list[Path],
) -> dict[str, object]:
    from RealLLM.run_voidtoken_v5_frozen import (
        FROZEN_CONFIGURATION_SHA256,
        SUITE_ID,
        implementation_sha256,
        registration_sha256,
    )

    evidence_paths = [
        ROOT / "real-llm-results" / "aggregate.json",
        ROOT / "RealLLM" / "v5_registration.json",
        ROOT / "real-llm-v5-development" / "manifest.json",
        *[
            ROOT / artifact["path"]
            for artifact in json.loads(
                (
                    ROOT
                    / "real-llm-v5-development"
                    / "manifest.json"
                ).read_text(encoding="utf-8")
            )["artifacts"]
        ],
        *prospective_artifacts,
        ROOT / "app-real-llm-evidence" / "validation-064-071.json",
        ROOT / "app-real-llm-evidence" / "app-run-receipt.json",
        ROOT / "app-real-llm-evidence" / "SHA256SUMS",
    ]
    files: list[dict[str, object]] = []
    for path in evidence_paths:
        _assert_release_source(path, build_context)
        files.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sizeBytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return {
        "schemaVersion": "corelm-reproducibility-provenance-v1",
        "repository": PUBLIC_ORIGIN,
        "buildMode": build_context["buildMode"],
        "builtFromCleanHead": build_context["builtFromCleanHead"],
        "gitHeadCommit": build_context["gitHeadCommit"],
        "releaseTag": build_context["releaseTag"],
        "remoteTagVerified": build_context["remoteTagVerified"],
        "gitObjectsIncluded": False,
        "provenanceScope": (
            "This manifest records the builder's source state and hashes. "
            "It is not a substitute for Git objects, tags, or a public "
            "timestamp. Full Git provenance requires a tagged clone."
        ),
        "voidTokenV5": {
            "suiteId": SUITE_ID,
            "evidenceState": evidence_state,
            "configurationSHA256": FROZEN_CONFIGURATION_SHA256,
            "registrationSHA256": registration_sha256(),
            "implementationSHA256": implementation_sha256(),
        },
        "evidenceFiles": files,
    }


def build_reproducibility(
    output_directory: Path = OUTPUT,
    build_context: dict[str, object] | None = None,
) -> Path:
    output_directory = _safe_output_directory(output_directory)
    context = build_context or _build_context(None)
    evidence_state, prospective_artifacts = _validate_v5_evidence(
        git_provenance=bool(context.get("builtFromCleanHead"))
    )
    target = output_directory / "corelm_reproducibility.tar.gz"
    with tempfile.TemporaryDirectory(prefix="corelm-repro-") as temporary:
        stage = Path(temporary) / "corelm_reproducibility"
        stage.mkdir()

        files = [
            "AGENTS.md",
            "CITATION.cff",
            "LICENSE",
            "Package.swift",
            "README.md",
            "SECURITY.md",
            "corelm",
            "requirements.lock",
            "requirements.txt",
            "scripts/verify-python.sh",
        ]
        for relative in files:
            source = ROOT / relative
            _assert_release_source(source, context)
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        source_files = [
            ".github/dependabot.yml",
            ".github/locks/core-linux-py312.txt",
            ".github/locks/core-macos-arm64-py312.txt",
            ".github/locks/pip-bootstrap.txt",
            ".github/locks/real-llm-linux-cpu-py312.txt",
            ".github/locks/torch-linux-cpu-py312.txt",
            ".github/workflows/real-qwen-linux-cpu.yml",
            ".github/workflows/verify-linux.yml",
            ".github/workflows/verify-macos.yml",
            "platforms/README.md",
            "platforms/beacon/README.md",
            "platforms/beacon/scripts/verify-frozen-tag.py",
            "platforms/macos/README.md",
            "platforms/macos/BUILD_AND_VERIFY.md",
            "platforms/macos/App/Info.plist",
            "platforms/macos/App/Sources/BenchmarkStore.swift",
            "platforms/macos/App/Sources/ContentView.swift",
            "platforms/macos/App/Sources/CoreLMBenchmarkApp.swift",
            "platforms/macos/App/Sources/Models.swift",
            "platforms/macos/App/Sources/PrimaryEvidenceValidation.swift",
            "platforms/macos/App/Sources/PythonRuntimeManifest.swift",
            "platforms/macos/App/Sources/RealLLMModels.swift",
            "platforms/macos/App/Sources/SecurityValidation.swift",
            "platforms/macos/Tests/SecurityValidationTests.swift",
            "platforms/macos/Tests/Fixtures/real-llm-validation-064-071.json",
            "platforms/macos/scripts/bootstrap-python.sh",
            "platforms/macos/scripts/build-app.sh",
            "platforms/macos/scripts/doctor.sh",
            "platforms/macos/scripts/package-app.sh",
            "platforms/macos/scripts/prepare-offline.sh",
            "platforms/macos/scripts/run-proof.sh",
            "platforms/linux/README.md",
            "platforms/linux/RECORDED_RUN_2026-08-01.md",
            "platforms/linux/scripts/doctor.sh",
            "platforms/linux/scripts/build-runtime.sh",
            "platforms/linux/scripts/run-regression.sh",
            "BenchmarkCore/corelm_benchmark.py",
            "BenchmarkCore/README.md",
            "docs/ARCHITECTURE.md",
            "docs/BEACON_LAUNCH_RUNBOOK.md",
            "docs/README.md",
            "docs/RESULTS.md",
            "docs/LIMITATIONS.md",
            "docs/development/BEACON_V1_AUDIT_AND_V2.md",
            "docs/development/HISTORY.md",
            "docs/development/SCIENTIFIC_IDENTIFIERS.md",
            "docs/development/RELEASE_PROCESS.md",
            "Tests/test_app_real_llm_evidence.py",
            "Tests/test_beacon_launch_runbook.py",
            "Tests/test_beacon_protocol.py",
            "Tests/test_build_provenance.py",
            "Tests/test_local_app_build.py",
            "Tests/test_platform_boundaries.py",
            "Tests/test_publication_archives.py",
            "Tests/test_real_llm.py",
            "Tests/test_security_supply_chain.py",
            "Tests/test_swift_security_gate.py",
            "Tests/test_voidtoken_v5.py",
            "Tests/test_voidtoken_v5_development.py",
            "Tests/test_voidtoken_v5_frozen.py",
            "Tests/fixtures/nist-beacon-certificate-528943a5.pem",
            "Tests/fixtures/nist-beacon-chain-2-pulse-1884240.json",
            "schemas/beacon-attempt.schema.json",
            "schemas/beacon-freeze.schema.json",
            "schemas/beacon-outcome.schema.json",
            "schemas/beacon-registration.schema.json",
            "schemas/beacon-resolution.schema.json",
            "schemas/beacon-window-ledger.schema.json",
            "schemas/real-llm-result.schema.json",
            "schemas/voidtoken-v5-attempt.schema.json",
            "schemas/voidtoken-v5-phase-result.schema.json",
            "RealLLM/__init__.py",
            "RealLLM/BEACON_HELDOUT_PROTOCOL.md",
            "RealLLM/README.md",
            "RealLLM/PROTOCOL.md",
            "RealLLM/V5_PROTOCOL.md",
            "RealLLM/beacon_evaluation.py",
            "RealLLM/beacon_protocol.py",
            "RealLLM/beacon_registration.json",
            "RealLLM/beacon_window_ledger.json",
            "RealLLM/app_proof_core.py",
            "RealLLM/app_proof_runner.py",
            "RealLLM/benchmark_real_llm.py",
            "RealLLM/codecs.py",
            "RealLLM/develop_voidtoken_v5.py",
            "RealLLM/legacy_voidtoken_adapter.py",
            "RealLLM/prepare_app_assets.py",
            "RealLLM/prepare_beacon_assets.py",
            "RealLLM/prepare_beacon_freeze.py",
            "RealLLM/registration.json",
            "RealLLM/requirements.lock",
            "RealLLM/requirements.txt",
            "RealLLM/run_beacon_one_shot.py",
            "RealLLM/run_beacon_regression.py",
            "RealLLM/run_voidtoken_v5_frozen.py",
            "RealLLM/v5_registration.json",
            "RealLLM/verify_real_llm_evidence.py",
            "RealLLM/verify_beacon_evidence.py",
            "RealLLM/verify_voidtoken_v5_development.py",
            "RealLLM/verify_voidtoken_v5_evidence.py",
            "RealLLM/voidtoken_v5.py",
            "publication/build_archives.py",
            "security/direct-dependencies.cdx.json",
            "security/find_python312.sh",
            "security/generate_app_proof_core.py",
            "security/generate_build_provenance.py",
            "security/generate_python_runtime_manifest.py",
            "security/generate_direct_sbom.py",
            "security/manage_local_runtime.py",
            "security/osv_direct_audit.py",
            "security/proof_process_groups.sh",
            "security/run_process_group_tests.sh",
            "security/run_swift_security_tests.sh",
            "security/validate_proof_challenge.sh",
            "security/validate_python_bootstrap_archive.py",
            "security/verify_app_run_evidence.py",
            "security/verify_primary_evidence.py",
            "security/verify_primary_replay.py",
            "security/verify_app_bundle.sh",
            "security/verify_local_app_run.py",
            "security/verify_locked_environment.py",
            "security/verify_supply_chain.py",
            "app-real-llm-evidence/README.md",
            "app-real-llm-evidence/SHA256SUMS",
            "app-real-llm-evidence/app-run-receipt.json",
            "app-real-llm-evidence/validation-064-071.json",
            "real-llm-results/aggregate.json",
            "real-llm-results/README.md",
            "real-llm-beacon-results/README.md",
            "real-llm-v5-development/README.md",
            "real-llm-v5-development/manifest.json",
            "real-llm-v5-development/validation-000-007.json",
            "real-llm-v5-development/validation-008-015.json",
            "real-llm-v5-development/validation-016-023.json",
            "real-llm-v5-development/validation-024-031.json",
            "real-llm-v5-results/README.md",
        ]
        for relative in source_files:
            source = ROOT / relative
            _assert_release_source(source, context)
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        _copy_optional_beacon_freeze(stage, context)

        for source in prospective_artifacts:
            _assert_release_source(source, context)
            relative = source.relative_to(ROOT)
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        publication_arxiv = stage / "publication/arxiv-v5"
        publication_arxiv.mkdir(parents=True)
        reproducibility_readme = PUBLICATION / "reproducibility/README.md"
        _assert_release_source(reproducibility_readme, context)
        shutil.copy2(
            reproducibility_readme,
            stage / "publication/README.md",
        )
        original_reproducibility_path = (
            stage / "publication/reproducibility/README.md"
        )
        original_reproducibility_path.parent.mkdir(
            parents=True, exist_ok=True
        )
        shutil.copy2(
            reproducibility_readme,
            original_reproducibility_path,
        )
        for relative in (
            "generate_figures.py",
            "submission_metadata.md",
            *V5_ARXIV_SOURCE_FILES,
        ):
            source = ARXIV_V5 / relative
            if not source.is_file():
                raise FileNotFoundError(source)
            _assert_release_source(source, context)
            destination = publication_arxiv / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        provenance = _v5_provenance_document(
            context,
            evidence_state,
            prospective_artifacts,
        )
        (stage / "PROVENANCE.json").write_text(
            json.dumps(
                provenance,
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )

        commit = context.get("gitHeadCommit")
        tree = context.get("gitHeadTree")
        if (
            not isinstance(commit, str)
            or re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", commit) is None
            or not isinstance(tree, str)
            or re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", tree) is None
        ):
            raise ValueError(
                "reproducibility source archive requires exact Git commit/tree identity"
            )
        source_archive_manifest = stage / DEFAULT_ARCHIVE_MANIFEST
        source_archive_manifest.write_bytes(
            canonical_json_bytes(
                build_source_archive_manifest(
                    stage,
                    commit=commit,
                    tree=tree,
                    remote=PUBLIC_ORIGIN,
                    exact_tag=context.get("releaseTag")
                    if isinstance(context.get("releaseTag"), str)
                    else None,
                    dirty=not bool(context.get("builtFromCleanHead")),
                    output=source_archive_manifest,
                )
            )
        )

        with deterministic_tar_gz(target) as archive:
            add_path(archive, stage, stage.name)
    return target


def build_all(
    output_directory: Path = OUTPUT,
    build_context: dict[str, object] | None = None,
) -> list[Path]:
    output_directory = _safe_output_directory(output_directory)
    context = build_context or _build_context(None)
    paper_pdf = PUBLICATION / "corelm_voidtoken_v5.pdf"
    _assert_release_source(paper_pdf, context)
    copied_pdf = output_directory / paper_pdf.name
    with _atomic_output_path(copied_pdf) as staged_pdf:
        shutil.copyfile(paper_pdf, staged_pdf)
    return [
        build_arxiv_v5(output_directory, context),
        build_reproducibility(output_directory, context),
        copied_pdf,
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(artifacts: list[Path], output_directory: Path) -> Path:
    output_directory = _safe_output_directory(output_directory)
    target = output_directory / "SHA256SUMS"
    with _atomic_output_path(target) as staged:
        staged.write_text(
            "".join(f"{sha256(path)}  {path.name}\n" for path in artifacts),
            encoding="utf-8",
        )
    return target


def verify_determinism(
    build_context: dict[str, object] | None = None,
) -> bool:
    context = build_context or _build_context(None)
    with tempfile.TemporaryDirectory(prefix="corelm-archive-check-") as temporary:
        root = Path(temporary)
        first = build_all(root / "first", context)
        second = build_all(root / "second", context)
        matches = True
        for first_path, second_path in zip(first, second):
            first_digest = sha256(first_path)
            second_digest = sha256(second_path)
            same = first_digest == second_digest
            matches = matches and same
            print(
                f"{first_path.name}: "
                f"{'MATCH' if same else 'MISMATCH'} {first_digest}"
            )
        return matches


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="Directory for generated archives",
    )
    parser.add_argument(
        "--verify-determinism",
        action="store_true",
        help="Build each archive twice in temporary directories and compare SHA-256",
    )
    parser.add_argument(
        "--release-tag",
        help=(
            "Build a final archive only from clean HEAD at this lightweight "
            "tag after the exact tag is visible on public origin"
        ),
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        context = _build_context(arguments.release_tag)
    except ValueError as error:
        print(f"ARCHIVE RELEASE PREFLIGHT FAILED: {error}")
        return 1
    try:
        if arguments.verify_determinism:
            if not verify_determinism(context):
                return 1
        artifacts = build_all(arguments.output, context)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"ARCHIVE BUILD FAILED: {error}")
        return 1
    for artifact in artifacts:
        print(artifact)
    print(write_checksums(artifacts, arguments.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
