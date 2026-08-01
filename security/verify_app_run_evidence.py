#!/usr/bin/env python3
"""Verify the sanitized macOS application real-LLM integration evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import plistlib
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RealLLM.verify_voidtoken_v5_development import _verify_shard  # noqa: E402
from security.generate_build_provenance import (  # noqa: E402
    DEFAULT_ARCHIVE_MANIFEST,
    canonical_json_bytes as canonical_provenance_bytes,
    inspect_git_source,
    inspect_source_archive,
    validate_build_manifest,
    verify_build_manifest,
)
from security.generate_python_runtime_manifest import (  # noqa: E402
    validate_manifest_files,
)
from security.verify_primary_evidence import (  # noqa: E402
    verify_primary_evidence,
)


DEFAULT_EVIDENCE = PROJECT_ROOT / "app-real-llm-evidence"
MAX_RESULT_BYTES = 4 * 1024 * 1024
MAX_RECEIPT_BYTES = 64 * 1024
MAX_BUILD_PROVENANCE_BYTES = 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_FILES = {
    "validation-064-071.json",
    "app-run-receipt.json",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_duplicate_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _load_object(path: Path, maximum_bytes: int) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path} is not a regular file")
    size = path.stat().st_size
    if size <= 0 or size > maximum_bytes:
        raise ValueError(f"{path} exceeds its resource bound")
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def _load_checksums(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("SHA256SUMS is missing or unsafe")
    checksums: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line)
        if match is None:
            raise ValueError("SHA256SUMS contains a malformed line")
        digest, name = match.groups()
        if name in checksums:
            raise ValueError("SHA256SUMS contains a duplicate filename")
        checksums[name] = digest
    if set(checksums) != EXPECTED_FILES:
        raise ValueError("SHA256SUMS does not name the exact evidence set")
    return checksums


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} is not a lowercase SHA-256 digest")
    return value


def _require_exact_keys(
    value: Any,
    expected: set[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} fields are not exact")
    return value


def _close(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if not isinstance(left, (int, float)) or not isinstance(
        right, (int, float)
    ):
        return False
    return math.isfinite(float(left)) and math.isfinite(float(right)) and (
        math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)
    )


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} is not a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} is not ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} has no timezone")
    return parsed


def _verify_build_provenance_receipt(
    value: Any,
    app_bundle: Path | None,
    *,
    compare_source_tree: bool,
) -> dict[str, Any]:
    receipt = _require_exact_keys(
        value,
        {"document", "path", "sha256"},
        "build provenance receipt",
    )
    if receipt["path"] != "Resources/build-provenance.json":
        raise ValueError("build provenance receipt path is inconsistent")
    recorded_digest = _require_sha256(
        receipt["sha256"], "build provenance document"
    )
    document = receipt["document"]
    validate_build_manifest(document)
    canonical = canonical_provenance_bytes(document)
    if (
        len(canonical) > MAX_BUILD_PROVENANCE_BYTES
        or hashlib.sha256(canonical).hexdigest() != recorded_digest
    ):
        raise ValueError("build provenance receipt digest is inconsistent")
    source = document["source"]
    if source["dirty"] is not False:
        raise ValueError("fresh proof was built from a dirty source tree")

    if app_bundle is not None:
        bundled_path = (
            app_bundle
            / "Contents"
            / "Resources"
            / "build-provenance.json"
        )
        bundled = verify_build_manifest(bundled_path)
        if bundled != document or _sha256(bundled_path) != recorded_digest:
            raise ValueError(
                "provided app build provenance differs from the receipt"
            )

    if compare_source_tree:
        if source["mode"] == "git":
            observed_source = inspect_git_source(PROJECT_ROOT)
        else:
            observed_source = inspect_source_archive(
                PROJECT_ROOT,
                PROJECT_ROOT / DEFAULT_ARCHIVE_MANIFEST,
            )
        if observed_source != source:
            raise ValueError(
                "current source tree differs from the app build provenance"
            )
    return document


def _verify_local_bundle(app: Path) -> None:
    verifier = PROJECT_ROOT / "security" / "verify_app_bundle.sh"
    completed = subprocess.run(
        [str(verifier), str(app)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
        env={
            "HOME": str(Path.home()),
            "LANG": "C",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        },
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"local app bundle verification failed: {detail}")


def _verify_result_and_receipt(
    result_path: Path,
    receipt_path: Path,
    app_bundle: Path | None,
    *,
    portable_macos_environment: bool,
    expected_challenge_nonce: str | None,
) -> dict[str, Any]:
    if app_bundle is not None:
        if app_bundle.is_symlink() or not app_bundle.is_dir():
            raise ValueError("provided app bundle is missing or unsafe")
        app_bundle = app_bundle.resolve(strict=True)
    result, _ = _load_object(result_path, MAX_RESULT_BYTES)
    receipt, receipt_raw = _load_object(receipt_path, MAX_RECEIPT_BYTES)

    if "/Users/" in receipt_raw or "\\Users\\" in receipt_raw:
        raise ValueError("receipt discloses an absolute user path")

    shard_artifact = {
        "path": str(result_path),
        "startBlock": 64,
        "blocks": 8,
        "resultSHA256": result.get("resultSHA256"),
    }
    shard_errors, records, baselines = _verify_shard(
        result,
        shard_artifact,
        portable_macos_environment=portable_macos_environment,
    )
    if shard_errors:
        raise ValueError("result verification failed: " + "; ".join(shard_errors))
    if len(records) != 8 or len(baselines) != 8:
        raise ValueError("result does not contain exactly eight verified blocks")

    receipt_schema = receipt.get("schemaVersion")
    receipt_keys = {
        "application",
        "createdAt",
        "error",
        "protocol",
        "result",
        "schemaVersion",
        "startedAt",
        "worker",
    }
    if "challengeNonce" in receipt:
        receipt_keys.add("challengeNonce")
    if receipt_schema == "corelm-macos-app-real-llm-run-v4":
        receipt_keys.add("primaryEvidence")
        receipt_keys.add("buildProvenance")
    _require_exact_keys(
        receipt,
        receipt_keys,
        "receipt",
    )
    if receipt_schema not in {
        "corelm-macos-app-real-llm-run-v2",
        "corelm-macos-app-real-llm-run-v3",
        "corelm-macos-app-real-llm-run-v4",
    }:
        raise ValueError("receipt schema version is unsupported")
    if not portable_macos_environment and receipt_schema != (
        "corelm-macos-app-real-llm-run-v2"
    ):
        raise ValueError("historical evidence requires the v2 receipt")
    if expected_challenge_nonce is not None:
        _require_sha256(expected_challenge_nonce, "expected challenge nonce")
        if (
            receipt_schema != "corelm-macos-app-real-llm-run-v4"
            or receipt.get("challengeNonce") != expected_challenge_nonce
        ):
            raise ValueError("receipt does not contain the proof challenge")
    elif "challengeNonce" in receipt:
        _require_sha256(receipt.get("challengeNonce"), "receipt challenge")
    if receipt["error"] is not None:
        raise ValueError("receipt records an application error")
    if receipt_schema == "corelm-macos-app-real-llm-run-v4":
        if result.get("schemaVersion") != (
            "corelm-voidtoken-v5-validation-development-v3"
        ):
            raise ValueError("v4 receipt requires retained primary evidence")
        primary = _require_exact_keys(
            receipt["primaryEvidence"],
            {
                "schemaVersion",
                "path",
                "manifestSHA256",
                "manifestBytes",
                "containerCount",
                "containerBytes",
                "blocks",
                "predictionTokens",
            },
            "receipt primary evidence",
        )
        if primary != result.get("primaryEvidence"):
            raise ValueError("receipt does not bind the primary evidence")
        _verify_build_provenance_receipt(
            receipt["buildProvenance"],
            app_bundle,
            compare_source_tree=portable_macos_environment,
        )
        verify_primary_evidence(result_path.parent, result)
    elif result.get("schemaVersion") == (
        "corelm-voidtoken-v5-validation-development-v3"
    ):
        raise ValueError("primary evidence result requires a v4 receipt")
    started_at = _timestamp(receipt["startedAt"], "receipt startedAt")
    result_created_at = _timestamp(result.get("createdAt"), "result createdAt")
    receipt_created_at = _timestamp(receipt["createdAt"], "receipt createdAt")
    if not started_at <= result_created_at <= receipt_created_at:
        raise ValueError("result and receipt timestamps are out of order")

    application = _require_exact_keys(
        receipt["application"],
        {
            "bundleIdentifier",
            "bundleName",
            "executableSHA256",
            "processIdentifier",
            "version",
        },
        "application receipt",
    )
    if (
        application["bundleIdentifier"] != "com.corelm.benchmark"
        or application["bundleName"] != "CoreLMBenchmark.app"
        or (
            not portable_macos_environment
            and application["version"] != "0.4.0"
        )
        or not isinstance(application["version"], str)
        or type(application["processIdentifier"]) is not int
        or application["processIdentifier"] <= 0
    ):
        raise ValueError("application identity is inconsistent")
    _require_sha256(application["executableSHA256"], "application executable")

    worker = _require_exact_keys(
        receipt["worker"],
        {
            "processIdentifier",
            "python",
            "pythonExecutableSHA256",
            "runtimeManifestSHA256",
            "script",
            "scriptSHA256",
            "terminationStatus",
        },
        "worker receipt",
    )
    runner_sources = {
        "Resources/RealLLM/app_proof_runner.py": (
            PROJECT_ROOT / "RealLLM" / "app_proof_runner.py"
        ),
        # Retain verification of the already-published historical app receipt.
        "Resources/RealLLM/develop_voidtoken_v5.py": (
            PROJECT_ROOT / "RealLLM" / "develop_voidtoken_v5.py"
        ),
    }
    worker_script = worker.get("script")
    if (
        worker["python"] != "signed-runtime-manifest"
        or not isinstance(worker_script, str)
        or worker_script not in runner_sources
        or type(worker["processIdentifier"]) is not int
        or worker["processIdentifier"] <= 0
        or worker["terminationStatus"] != 0
    ):
        raise ValueError("worker identity or termination status is inconsistent")
    _require_sha256(worker["pythonExecutableSHA256"], "Python executable")
    _require_sha256(worker["runtimeManifestSHA256"], "runtime manifest")
    _require_sha256(worker["scriptSHA256"], "runner script")
    source_script = runner_sources[worker_script]
    if (
        portable_macos_environment
        and _sha256(source_script) != worker["scriptSHA256"]
    ):
        raise ValueError("receipt runner digest differs from the source tree")

    protocol = _require_exact_keys(
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
        "protocol receipt",
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
        raise ValueError("application protocol receipt is inconsistent")

    result_receipt = _require_exact_keys(
        receipt["result"],
        {
            "compressionRatioVsBF16",
            "deltaNLLNatPerToken",
            "path",
            "resultFileSHA256",
            "resultSHA256",
            "scientificVerdict",
            "swiftStructuralVerification",
            "top1Agreement",
        },
        "result receipt",
    )
    aggregate = result.get("aggregates")
    if not isinstance(aggregate, list) or len(aggregate) != 1:
        raise ValueError("result must contain exactly one aggregate")
    aggregate_item = aggregate[0]
    if (
        result_receipt["path"] != result_path.name
        or result_receipt["resultFileSHA256"] != _sha256(result_path)
        or result_receipt["resultSHA256"] != result.get("resultSHA256")
        or result_receipt["scientificVerdict"] != "PASS"
        or result_receipt["swiftStructuralVerification"] != "PASS"
        or not _close(
            result_receipt["compressionRatioVsBF16"],
            aggregate_item.get("compressionRatioVsBF16"),
        )
        or not _close(
            result_receipt["deltaNLLNatPerToken"],
            aggregate_item.get("deltaNLLNatPerToken"),
        )
        or not _close(
            result_receipt["top1Agreement"],
            aggregate_item.get("top1Agreement"),
        )
    ):
        raise ValueError("receipt does not bind to the verified result")

    if app_bundle is not None:
        if app_bundle.is_symlink() or not app_bundle.is_dir():
            raise ValueError("provided app bundle is missing or unsafe")
        app = app_bundle.resolve()
        _verify_local_bundle(app)
        executable = app / "Contents" / "MacOS" / "CoreLMBenchmarkApp"
        resources = app / "Contents" / "Resources"
        manifest = resources / "python-runtime-manifest.json"
        runner = resources.joinpath(*Path(worker_script).parts[1:])
        info_plist = app / "Contents" / "Info.plist"
        for label, path in (
            ("application executable", executable),
            ("runtime manifest", manifest),
            ("bundled runner", runner),
            ("Info.plist", info_plist),
        ):
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"{label} is missing or unsafe")
        if (
            _sha256(executable) != application["executableSHA256"]
            or _sha256(manifest) != worker["runtimeManifestSHA256"]
            or _sha256(runner) != worker["scriptSHA256"]
        ):
            raise ValueError("provided app bundle differs from the receipt")
        manifest_value, _ = _load_object(manifest, 32 * 1024 * 1024)
        if (
            manifest_value.get("pythonExecutableSHA256")
            != worker["pythonExecutableSHA256"]
        ):
            raise ValueError("app runtime identity differs from the receipt")
        validate_manifest_files(manifest_value)
        environment = result.get("environment")
        if (
            not isinstance(environment, dict)
            or manifest_value.get("pythonVersion") != environment.get("python")
        ):
            raise ValueError("result Python version differs from live runtime")
        if info_plist.stat().st_size > 1024 * 1024:
            raise ValueError("Info.plist exceeds its resource bound")
        with info_plist.open("rb") as handle:
            plist = plistlib.load(handle)
        if (
            not isinstance(plist, dict)
            or plist.get("CFBundleIdentifier")
            != application["bundleIdentifier"]
            or plist.get("CFBundleShortVersionString")
            != application["version"]
        ):
            raise ValueError("receipt application identity differs from plist")
    return result


def verify(evidence_directory: Path, app_bundle: Path | None = None) -> None:
    evidence = evidence_directory.resolve()
    if evidence_directory.is_symlink() or not evidence.is_dir():
        raise ValueError("evidence directory is missing or unsafe")

    checksums = _load_checksums(evidence / "SHA256SUMS")
    for name, expected in checksums.items():
        candidate = evidence / name
        if _sha256(candidate) != expected:
            raise ValueError(f"{name} differs from SHA256SUMS")

    _verify_result_and_receipt(
        evidence / "validation-064-071.json",
        evidence / "app-run-receipt.json",
        app_bundle,
        portable_macos_environment=False,
        expected_challenge_nonce=None,
    )


def verify_fresh_run(
    run_directory: Path,
    app_bundle: Path,
    *,
    challenge_nonce: str | None = None,
) -> dict[str, Any]:
    run = run_directory.resolve()
    if run_directory.is_symlink() or not run.is_dir():
        raise ValueError("fresh run directory is missing or unsafe")
    if app_bundle.is_symlink() or not app_bundle.resolve().is_dir():
        raise ValueError("local app bundle is missing or unsafe")
    return _verify_result_and_receipt(
        run / "validation-064-071.json",
        run / "app-run-receipt.json",
        app_bundle,
        portable_macos_environment=True,
        expected_challenge_nonce=challenge_nonce,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence",
        type=Path,
        default=DEFAULT_EVIDENCE,
        help="directory containing result, receipt, and SHA256SUMS",
    )
    parser.add_argument(
        "--app",
        type=Path,
        help="optionally bind the receipt to a local CoreLMBenchmark.app",
    )
    arguments = parser.parse_args()
    try:
        verify(arguments.evidence, arguments.app)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"APP REAL-LLM EVIDENCE FAIL: {error}", file=sys.stderr)
        return 1
    suffix = " and app bundle" if arguments.app is not None else ""
    print(f"APP REAL-LLM EVIDENCE PASS: result, receipt{suffix}, and hashes agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
