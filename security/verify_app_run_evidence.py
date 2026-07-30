#!/usr/bin/env python3
"""Verify the sanitized macOS application real-LLM integration evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RealLLM.verify_voidtoken_v5_development import _verify_shard  # noqa: E402


DEFAULT_EVIDENCE = PROJECT_ROOT / "app-real-llm-evidence"
MAX_RESULT_BYTES = 4 * 1024 * 1024
MAX_RECEIPT_BYTES = 64 * 1024
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


def verify(evidence_directory: Path, app_bundle: Path | None = None) -> None:
    evidence = evidence_directory.resolve()
    if evidence_directory.is_symlink() or not evidence.is_dir():
        raise ValueError("evidence directory is missing or unsafe")

    checksums = _load_checksums(evidence / "SHA256SUMS")
    for name, expected in checksums.items():
        candidate = evidence / name
        if _sha256(candidate) != expected:
            raise ValueError(f"{name} differs from SHA256SUMS")

    result_path = evidence / "validation-064-071.json"
    receipt_path = evidence / "app-run-receipt.json"
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
    shard_errors, records, baselines = _verify_shard(result, shard_artifact)
    if shard_errors:
        raise ValueError("result verification failed: " + "; ".join(shard_errors))
    if len(records) != 8 or len(baselines) != 8:
        raise ValueError("result does not contain exactly eight verified blocks")

    _require_exact_keys(
        receipt,
        {
            "application",
            "createdAt",
            "error",
            "protocol",
            "result",
            "schemaVersion",
            "startedAt",
            "worker",
        },
        "receipt",
    )
    if receipt["schemaVersion"] != "corelm-macos-app-real-llm-run-v2":
        raise ValueError("receipt schema version is unsupported")
    if receipt["error"] is not None:
        raise ValueError("receipt records an application error")

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
        or application["version"] != "0.4.0"
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
    if (
        worker["python"] != "signed-runtime-manifest"
        or worker["script"] != "Resources/RealLLM/develop_voidtoken_v5.py"
        or type(worker["processIdentifier"]) is not int
        or worker["processIdentifier"] <= 0
        or worker["terminationStatus"] != 0
    ):
        raise ValueError("worker identity or termination status is inconsistent")
    _require_sha256(worker["pythonExecutableSHA256"], "Python executable")
    _require_sha256(worker["runtimeManifestSHA256"], "runtime manifest")
    _require_sha256(worker["scriptSHA256"], "runner script")
    source_script = PROJECT_ROOT / "RealLLM" / "develop_voidtoken_v5.py"
    if _sha256(source_script) != worker["scriptSHA256"]:
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
        app = app_bundle.resolve()
        executable = app / "Contents" / "MacOS" / "CoreLMBenchmarkApp"
        resources = app / "Contents" / "Resources"
        manifest = resources / "python-runtime-manifest.json"
        runner = resources / "RealLLM" / "develop_voidtoken_v5.py"
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
