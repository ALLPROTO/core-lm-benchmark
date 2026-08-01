#!/usr/bin/env python3
"""Stdlib-only integrity core for the beacon-selected held-out experiment."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import shutil
import ssl
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRATION_PATH = PROJECT_ROOT / "RealLLM" / "beacon_registration.json"
LEDGER_PATH = PROJECT_ROOT / "RealLLM" / "beacon_window_ledger.json"
FREEZE_PATH = PROJECT_ROOT / "RealLLM" / "beacon_freeze.json"
RESULT_DIRECTORY = PROJECT_ROOT / "real-llm-beacon-results"
ATTEMPT_PATH = RESULT_DIRECTORY / "attempt.json"
RESOLUTION_PATH = RESULT_DIRECTORY / "resolution.json"
OUTCOME_PATH = RESULT_DIRECTORY / "outcome.json"
REGRESSION_DIRECTORY = RESULT_DIRECTORY / "regressions"

SUITE_ID = "qwen2.5-0.5b-kv-voidtoken-v5-beacon-heldout-v1"
PUBLIC_ORIGIN = "https://github.com/ALLPROTO/core-lm-benchmark"
FREEZE_TAG = "corelm-beacon-heldout-v1"
PUBLIC_RELEASE_API = (
    "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/tags/"
    "corelm-beacon-heldout-v1"
)
PUBLIC_TAG_REF_API = (
    "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/git/ref/tags/"
    "corelm-beacon-heldout-v1"
)
PUBLIC_RELEASE_URL = (
    "https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/"
    "corelm-beacon-heldout-v1"
)
TARGET_TIMESTAMP = "2026-08-02T18:00:00.000Z"
TARGET_UNIX_MILLISECONDS = 1_785_693_600_000
PULSE_URL = (
    "https://beacon.nist.gov/beacon/2.0/pulse/time/1785693600000"
)
CERTIFICATE_URL_PREFIX = (
    "https://beacon.nist.gov/beacon/2.0/certificate/"
)
EXPECTED_CERTIFICATE_ID = (
    "528943a555f5f8ca54423be6dfb95925a35c7b552046420e7d7cd072058a14d6"
    "536ad3a8e9754b6582f164a90b0cd86a65d659f5426a2659a947595d1c816c8c"
)
EXPECTED_ELIGIBLE_STARTS = (
    16,
    48,
    80,
    112,
    144,
    176,
    208,
    240,
    272,
    304,
    336,
    448,
    480,
    512,
    544,
)
EXPECTED_EVALUATION = {
    "attentionImplementation": "eager",
    "blockTokens": 512,
    "cacheCanonicalization": "FP32-to-BF16-to-FP32",
    "candidateConfigurationId": "4c7be8c836aa7257",
    "candidateConfigurationSHA256": (
        "4c7be8c836aa725722b51f66dce78af7a5094e887432e622b5322f7ca2cf0af8"
    ),
    "candidateDevelopmentGridIndex": 32,
    "compressionByteAccounting": "complete-container-bytes",
    "layers": 24,
    "predictionMode": "teacher-forced",
    "predictionsPerBlock": 128,
    "prefillTokens": 383,
    "trajectoryShapePerLayer": [383, 256],
    "windowBlocks": 32,
}
EXPECTED_RUNTIME = {
    "hfHomePolicy": {
        "absolutePathRequired": True,
        "ownerOnlyRequired": True,
        "pathFrozen": False,
        "privateCacheRequired": True,
    },
    "processEnvironment": {
        "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
        "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "HF_HUB_OFFLINE": "1",
        "MKL_NUM_THREADS": "2",
        "NUMEXPR_NUM_THREADS": "2",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
        "PYTORCH_ENABLE_MPS_FALLBACK": "0",
        "PYTORCH_MPS_FAST_MATH": "0",
        "PYTORCH_MPS_HIGH_WATERMARK_RATIO": "0.85",
        "PYTORCH_MPS_LOW_WATERMARK_RATIO": "0.75",
        "PYTORCH_MPS_PREFER_METAL": "0",
        "TOKENIZERS_PARALLELISM": "false",
        "TRANSFORMERS_OFFLINE": "1",
        "VECLIB_MAXIMUM_THREADS": "2",
    },
    "resourcePolicy": {
        "concurrentProofRunsForbidden": True,
        "emptyMPSCacheAfterEachBlock": True,
        "evaluateBlocksSequentially": True,
        "minimumFreeMemoryPercent": 15,
        "minimumPhysicalMemoryGiB": 8,
    },
    "versions": {
        "huggingfaceHub": "1.25.1",
        "numpy": "2.5.1",
        "pyarrow": "23.0.1",
        "python": "3.12.13",
        "safetensors": "0.8.0",
        "tokenizers": "0.22.2",
        "torch": "2.13.0",
        "transformers": "5.14.1",
        "zlibCompileVersion": "1.2.12",
        "zlibRuntimeVersion": "1.2.12",
    },
}
_GIT_TIMEOUT_SECONDS = 90
_URL_TIMEOUT_SECONDS = 30
_MAX_PULSE_BYTES = 128 * 1024
_MAX_CERTIFICATE_BYTES = 64 * 1024
_MAX_RELEASE_METADATA_BYTES = 1024 * 1024
_SHA512_DIGEST_INFO_PREFIX = bytes.fromhex(
    "3051300d060960864801650304020305000440"
)


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _require_finite_json_numbers(value: Any) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number is forbidden")
        return
    if isinstance(value, list):
        for item in value:
            _require_finite_json_numbers(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            _require_finite_json_numbers(item)
        return
    raise ValueError(f"unsupported JSON value type: {type(value).__name__}")


def parse_json_bytes(data: bytes, *, label: str) -> Any:
    try:
        value = json.loads(
            data,
            parse_constant=_reject_nonfinite_json,
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label} JSON: {error}") from error
    _require_finite_json_numbers(value)
    return value


def load_json_object(path: Path, *, label: str | None = None) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError(f"cannot read {label or path.name}: {error}") from error
    value = parse_json_bytes(raw, label=label or path.name)
    if not isinstance(value, dict):
        raise ValueError(f"{label or path.name} must contain a JSON object")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    _require_finite_json_numbers(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def serialized_json_bytes(value: Any) -> bytes:
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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha512_bytes(value: bytes) -> str:
    return hashlib.sha512(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def registration_artifact_sha256() -> str:
    return sha256_file(REGISTRATION_PATH)


def registration_canonical_sha256() -> str:
    return sha256_bytes(canonical_json_bytes(load_registration()))


def load_registration() -> dict[str, Any]:
    return load_json_object(REGISTRATION_PATH, label="beacon registration")


def load_ledger() -> dict[str, Any]:
    return load_json_object(LEDGER_PATH, label="beacon window ledger")


def _parse_utc_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must use canonical UTC Z form")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"invalid UTC timestamp: {value}") from error
    return parsed.astimezone(timezone.utc)


def _window_end(window: dict[str, Any]) -> int:
    start = window.get("startBlock")
    blocks = window.get("blocks")
    if type(start) is not int or type(blocks) is not int:
        raise ValueError("window indices must be integers")
    return start + blocks


def validate_registration_and_ledger() -> tuple[dict[str, Any], dict[str, Any]]:
    registration = load_registration()
    ledger = load_ledger()
    if registration.get("schemaVersion") != "corelm-beacon-registration-v1":
        raise ValueError("unexpected beacon registration schema version")
    if ledger.get("schemaVersion") != "corelm-beacon-window-ledger-v1":
        raise ValueError("unexpected beacon ledger schema version")
    if registration.get("suiteId") != SUITE_ID or ledger.get("suiteId") != SUITE_ID:
        raise ValueError("registration and ledger suite IDs must match the runner")

    public_freeze = registration.get("publicFreeze")
    if public_freeze != {
        "freezeManifest": "RealLLM/beacon_freeze.json",
        "immutableReleaseRequired": True,
        "publicRepository": PUBLIC_ORIGIN,
        "releaseApi": PUBLIC_RELEASE_API,
        "releasePublishedBeforeBeacon": True,
        "releaseUrl": PUBLIC_RELEASE_URL,
        "requiredTag": FREEZE_TAG,
        "tagRefApi": PUBLIC_TAG_REF_API,
    }:
        raise ValueError("public freeze policy differs from the runner")

    beacon = registration.get("beacon", {})
    if (
        beacon.get("service") != "NIST Randomness Beacon"
        or beacon.get("version") != "2.0"
        or beacon.get("targetTimestamp") != TARGET_TIMESTAMP
        or beacon.get("targetUnixMilliseconds") != TARGET_UNIX_MILLISECONDS
        or beacon.get("pulseEndpoint") != PULSE_URL
        or beacon.get("certificateEndpointPrefix") != CERTIFICATE_URL_PREFIX
        or beacon.get("expectedCertificateId") != EXPECTED_CERTIFICATE_ID
        or beacon.get("periodMilliseconds") != 60_000
        or beacon.get("exactPulseRequired") is not True
        or beacon.get("fallback") != "forbidden"
    ):
        raise ValueError("beacon parameters differ from the runner")
    target = _parse_utc_timestamp(TARGET_TIMESTAMP)
    if int(target.timestamp() * 1000) != TARGET_UNIX_MILLISECONDS:
        raise ValueError("beacon timestamp and Unix milliseconds disagree")

    configuration = registration.get("configuration")
    if not isinstance(configuration, dict):
        raise ValueError("registered configuration must be an object")
    if sha256_bytes(canonical_json_bytes(configuration)) != registration.get(
        "configurationSHA256"
    ):
        raise ValueError("configuration digest is inconsistent")
    evaluation = registration.get("evaluation")
    if evaluation != EXPECTED_EVALUATION:
        raise ValueError("evaluation parameters differ from the runner")
    if (
        registration.get("configurationSHA256")
        != evaluation["candidateConfigurationSHA256"]
        or registration["configurationSHA256"][:16]
        != evaluation["candidateConfigurationId"]
    ):
        raise ValueError("candidate 32 identity is inconsistent")

    selection = registration.get("selection", {})
    if selection.get("windowLedgerPath") != "RealLLM/beacon_window_ledger.json":
        raise ValueError("ledger path differs from the runner")
    if selection.get("windowLedgerSHA256") != sha256_file(LEDGER_PATH):
        raise ValueError("ledger artifact digest differs from registration")
    if selection.get("candidateCount") != len(EXPECTED_ELIGIBLE_STARTS):
        raise ValueError("candidate count differs from the runner")
    if selection.get("windowBlocks") != evaluation["windowBlocks"]:
        raise ValueError("window size differs from the runner")
    domain = selection.get("domainSeparatorHex")
    if domain != "436f72654c4d2f626561636f6e2d68656c646f75742f763100":
        raise ValueError("selection domain separator differs from the runner")

    windows = ledger.get("eligibleWindows")
    if not isinstance(windows, list) or len(windows) != len(
        EXPECTED_ELIGIBLE_STARTS
    ):
        raise ValueError("ledger must contain the frozen eligible-window list")
    observed_starts: list[int] = []
    intervals: list[tuple[int, int]] = []
    full_blocks = ledger.get("corpus", {}).get("fullBlocks")
    for window in windows:
        if not isinstance(window, dict):
            raise ValueError("each eligible window must be an object")
        if window.get("split") != "test" or window.get("blocks") != 32:
            raise ValueError("eligible windows must be 32 test blocks")
        start = window.get("startBlock")
        if type(start) is not int:
            raise ValueError("eligible startBlock must be an integer")
        end = _window_end(window)
        if type(full_blocks) is not int or start < 0 or end > full_blocks:
            raise ValueError("eligible window is outside the inventoried split")
        if window.get("id") != f"test-{start:03d}-{end - 1:03d}":
            raise ValueError("eligible window ID is inconsistent")
        observed_starts.append(start)
        intervals.append((start, end))
    if tuple(observed_starts) != EXPECTED_ELIGIBLE_STARTS:
        raise ValueError("eligible windows differ from the frozen ordered pool")
    for index, (start, end) in enumerate(intervals):
        for other_start, other_end in intervals[index + 1 :]:
            if start < other_end and other_start < end:
                raise ValueError("eligible windows overlap")

    exclusions = ledger.get("excludedRanges")
    if not isinstance(exclusions, list):
        raise ValueError("ledger exclusions must be a list")
    for excluded in exclusions:
        if not isinstance(excluded, dict) or excluded.get("split") != "test":
            continue
        start = excluded.get("startBlock")
        end = excluded.get("endBlockExclusive")
        if type(start) is not int or type(end) is not int:
            raise ValueError("finite test exclusions require integer bounds")
        for candidate_start, candidate_end in intervals:
            if start < candidate_end and candidate_start < end:
                raise ValueError("eligible window overlaps an excluded range")

    corpus = registration.get("corpus", {})
    ledger_corpus = ledger.get("corpus", {})
    if corpus.get("blockTokens") != evaluation["blockTokens"]:
        raise ValueError("corpus block size differs from frozen evaluation")
    matching = {
        "repository": "repository",
        "revision": "revision",
        "configuration": "configuration",
        "split": "split",
        "fileBytes": "fileBytes",
        "fileSHA256": "fileSHA256",
        "blockTokens": "blockTokens",
    }
    for registration_key, ledger_key in matching.items():
        if corpus.get(registration_key) != ledger_corpus.get(ledger_key):
            raise ValueError(f"corpus field {registration_key} differs in ledger")
    tokenization = corpus.get("tokenization", {})
    if tokenization != {
        "addSpecialTokens": False,
        "allTokenIdsSHA256": (
            "b44603066a92719a20e2dc18d6c5f7f5342b1877c20c1e2bdd92deca662d3d56"
        ),
        "fullBlocks": 584,
        "remainderTokens": 70,
        "tokenCount": 299_078,
        "tokenizerRevision": (
            "060db6499f32faf8b98477b0a26969ef7d8b9987"
        ),
    }:
        raise ValueError("token inventory differs from the frozen runner")
    for key in (
        "allTokenIdsSHA256",
        "tokenCount",
        "fullBlocks",
        "remainderTokens",
        "tokenizerRevision",
    ):
        ledger_key = "tokenizerRevision" if key == "tokenizerRevision" else key
        if tokenization.get(key) != ledger_corpus.get(ledger_key):
            raise ValueError(f"token inventory field {key} differs in ledger")

    attempt_policy = registration.get("attemptPolicy", {})
    if (
        attempt_policy.get("attemptPath")
        != "real-llm-beacon-results/attempt.json"
        or attempt_policy.get("beaconFetchedAfterMarker") is not True
        or attempt_policy.get("createdBeforeBeaconAndDataResolution") is not True
        or attempt_policy.get("exclusiveDurableCreation") is not True
        or attempt_policy.get("crashConsumesSuite") is not True
        or attempt_policy.get("rerunAfterMarker") is not False
    ):
        raise ValueError("attempt policy differs from the runner")
    execution = registration.get("execution", {})
    if execution != {
        "deadline": "2026-08-04T18:00:00.000Z",
        "device": "mps",
        "localPythonBytecode": "forbidden",
        "modelDtype": "float32",
        "outcomePath": "real-llm-beacon-results/outcome.json",
        "primaryEvidenceDirectory": (
            "real-llm-beacon-results/primary-evidence"
        ),
        "pythonBytecodeWrites": False,
        "pythonIsolatedMode": True,
        "resolutionPath": "real-llm-beacon-results/resolution.json",
        "seed": 20_260_729,
        "torchDeterministicAlgorithms": "warn-only",
    }:
        raise ValueError("execution policy differs from the runner")
    if _parse_utc_timestamp(execution.get("deadline", "")) <= target:
        raise ValueError("execution deadline must be after the beacon pulse")
    if registration.get("outcomePolicy") != {
        "executionDeadlineMiss": "PROTOCOL_FAILURE",
        "missingOutcomeAfterAttempt": "CONSUMED_INCOMPLETE",
        "scientificFailExitCode": 2,
        "terminalVerdicts": ["PASS", "FAIL_GATES", "FAIL_EXECUTION"],
        "unexpectedErrorExitCode": 1,
    }:
        raise ValueError("outcome policy differs from the runner")
    if registration.get("runtime") != EXPECTED_RUNTIME:
        raise ValueError("runtime policy differs from the runner")

    source_files = registration.get("protocolSourceFiles")
    if (
        not isinstance(source_files, list)
        or not source_files
        or any(not isinstance(item, str) for item in source_files)
        or len(source_files) != len(set(source_files))
        or source_files != sorted(source_files)
    ):
        raise ValueError("protocolSourceFiles must be a sorted unique string list")
    for relative in source_files:
        path = PROJECT_ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"normative source is missing or not regular: {relative}")
    return registration, ledger


def _implementation_digest(entries: Iterable[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for relative, content in entries:
        encoded_path = relative.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(4, "little"))
        digest.update(encoded_path)
        digest.update(len(content).to_bytes(8, "little"))
        digest.update(content)
    return digest.hexdigest()


def implementation_sha256() -> str:
    registration = load_registration()
    paths = registration.get("protocolSourceFiles")
    if not isinstance(paths, list):
        raise ValueError("registration has no implementation manifest")
    entries: list[tuple[str, bytes]] = []
    for relative in paths:
        if not isinstance(relative, str):
            raise ValueError("normative source path must be a string")
        path = PROJECT_ROOT / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"normative source is missing or unsafe: {relative}")
        entries.append((relative, path.read_bytes()))
    return _implementation_digest(entries)


def _git_executable() -> str:
    for candidate in (Path("/usr/bin/git"), Path("/usr/local/bin/git")):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    discovered = shutil.which("git")
    if discovered is None:
        raise ValueError("cannot locate Git")
    resolved = Path(discovered).resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("resolved Git executable is not a regular file")
    return str(resolved)


def _sanitized_git_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith(("GIT_", "DYLD_")) or name == "LD_PRELOAD":
            environment.pop(name, None)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            "PATH": os.defpath,
        }
    )
    return environment


def _run_git(
    arguments: list[str] | tuple[str, ...], *, text: bool = False
) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(
            [_git_executable(), *arguments],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=text,
            env=_sanitized_git_environment(),
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"cannot execute bounded Git command: {error}") from error


def git_text(*arguments: str) -> str:
    completed = _run_git(arguments, text=True)
    if completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"git {' '.join(arguments)} failed: {message}")
    return completed.stdout.strip()


def _validate_full_commit(commit: str) -> None:
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise ValueError("Git commit must be a full lowercase SHA-1")


def git_file_bytes(commit: str, relative: str) -> bytes:
    _validate_full_commit(commit)
    if not relative or relative.startswith("/") or ".." in Path(relative).parts:
        raise ValueError("unsafe repository-relative path")
    completed = _run_git(["show", f"{commit}:{relative}"])
    if completed.returncode:
        raise ValueError(f"commit {commit} does not contain {relative}")
    return completed.stdout


def implementation_sha256_at_commit(commit: str) -> str:
    registration_bytes = git_file_bytes(commit, "RealLLM/beacon_registration.json")
    registration = parse_json_bytes(registration_bytes, label="committed registration")
    if not isinstance(registration, dict):
        raise ValueError("committed registration is not an object")
    paths = registration.get("protocolSourceFiles")
    if not isinstance(paths, list):
        raise ValueError("committed registration has no source manifest")
    entries = [(relative, git_file_bytes(commit, relative)) for relative in paths]
    return _implementation_digest(entries)


def _repository_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"path is outside repository: {path}") from error


def require_clean_head(*, allowed_untracked: tuple[Path, ...] = ()) -> str:
    allowed = {_repository_relative(path) for path in allowed_untracked}
    status = git_text(
        "status", "--porcelain=v1", "--untracked-files=all", "--ignored=no"
    )
    unexpected: list[str] = []
    for line in status.splitlines():
        if line.startswith("?? ") and line[3:] in allowed:
            continue
        unexpected.append(line)
    if unexpected:
        raise ValueError("frozen execution requires a clean checkout: " + ", ".join(unexpected))
    commit = git_text("rev-parse", "HEAD")
    _validate_full_commit(commit)
    return commit


def verify_public_release_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise ValueError("GitHub release metadata must be an object")
    if metadata.get("tag_name") != FREEZE_TAG:
        raise ValueError("GitHub release has a different tag")
    if metadata.get("html_url") != PUBLIC_RELEASE_URL:
        raise ValueError("GitHub release has an unexpected public URL")
    if metadata.get("draft") is not False:
        raise ValueError("GitHub freeze release is still a draft")
    if metadata.get("prerelease") is not False:
        raise ValueError("GitHub freeze release must not be a prerelease")
    if metadata.get("immutable") is not True:
        raise ValueError("GitHub freeze release is not immutable")
    published_at = metadata.get("published_at")
    published = _parse_utc_timestamp(published_at)
    if published >= _parse_utc_timestamp(TARGET_TIMESTAMP):
        raise ValueError("GitHub freeze release was not published before the beacon")
    return {
        "apiURL": PUBLIC_RELEASE_API,
        "htmlURL": PUBLIC_RELEASE_URL,
        "immutable": True,
        "publishedAt": published_at,
    }


def fetch_public_release_verification() -> dict[str, Any]:
    raw = _fetch_url(
        PUBLIC_RELEASE_API,
        maximum_bytes=_MAX_RELEASE_METADATA_BYTES,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        },
    )
    metadata = parse_json_bytes(raw, label="GitHub immutable release response")
    return verify_public_release_metadata(metadata)


def fetch_public_tag_commit(head: str) -> str:
    _validate_full_commit(head)
    raw = _fetch_url(
        PUBLIC_TAG_REF_API,
        maximum_bytes=_MAX_RELEASE_METADATA_BYTES,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        },
    )
    metadata = parse_json_bytes(raw, label="GitHub tag reference response")
    if not isinstance(metadata, dict):
        raise ValueError("GitHub tag reference metadata must be an object")
    expected_ref = f"refs/tags/{FREEZE_TAG}"
    expected_ref_url = PUBLIC_TAG_REF_API.replace("/git/ref/", "/git/refs/")
    if metadata.get("ref") != expected_ref or metadata.get("url") != expected_ref_url:
        raise ValueError("GitHub tag reference identity differs")
    target = metadata.get("object")
    if not isinstance(target, dict):
        raise ValueError("GitHub tag reference has no target object")
    expected_commit_url = (
        "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/git/commits/"
        + head
    )
    if (
        target.get("type") != "commit"
        or target.get("sha") != head
        or target.get("url") != expected_commit_url
    ):
        raise ValueError("GitHub lightweight tag does not point to frozen HEAD")
    return head


def require_public_freeze(head: str) -> dict[str, Any]:
    _validate_full_commit(head)
    if FREEZE_PATH.is_symlink() or not FREEZE_PATH.is_file():
        raise ValueError("beacon freeze manifest must be a regular non-symlink file")
    freeze = load_json_object(FREEZE_PATH, label="beacon freeze manifest")
    if freeze.get("schemaVersion") != "corelm-beacon-freeze-v1":
        raise ValueError("unexpected freeze manifest schema")
    if freeze.get("suiteId") != SUITE_ID:
        raise ValueError("freeze manifest has a different suite ID")
    if set(freeze) != {
        "schemaVersion",
        "suiteId",
        "status",
        "preparedAt",
        "protocolCommit",
        "registrationArtifactSHA256",
        "registrationCanonicalSHA256",
        "windowLedgerSHA256",
        "implementationSHA256",
        "normativeFiles",
    } or freeze.get("status") != "protocol-files-frozen-before-beacon":
        raise ValueError("freeze manifest fields or status differ")
    if _parse_utc_timestamp(str(freeze.get("preparedAt", ""))) >= _parse_utc_timestamp(
        TARGET_TIMESTAMP
    ):
        raise ValueError("freeze manifest was not prepared before the beacon")
    protocol_commit = freeze.get("protocolCommit")
    if not isinstance(protocol_commit, str):
        raise ValueError("freeze manifest has no protocol commit")
    _validate_full_commit(protocol_commit)
    parents = git_text("rev-list", "--parents", "-n", "1", head).split()
    if parents != [head, protocol_commit]:
        raise ValueError(
            "frozen tag commit must be the direct child of the protocol commit"
        )
    freeze_diff = git_text(
        "diff-tree",
        "--no-commit-id",
        "--name-status",
        "-r",
        protocol_commit,
        head,
    )
    if freeze_diff != "A\tRealLLM/beacon_freeze.json":
        raise ValueError(
            "freeze commit must add only RealLLM/beacon_freeze.json"
        )
    freeze_tree = git_text(
        "ls-tree", head, "--", "RealLLM/beacon_freeze.json"
    ).split()
    if (
        len(freeze_tree) != 4
        or freeze_tree[0] != "100644"
        or freeze_tree[1] != "blob"
        or freeze_tree[3] != "RealLLM/beacon_freeze.json"
    ):
        raise ValueError("freeze manifest is not a regular Git blob")
    if git_text("rev-parse", f"refs/tags/{FREEZE_TAG}^{{commit}}") != head:
        raise ValueError(f"HEAD is not the frozen tag {FREEZE_TAG}")
    origin = git_text("remote", "get-url", "origin").removesuffix(".git")
    if origin != PUBLIC_ORIGIN:
        raise ValueError("origin is not the registered public repository")
    fetch_public_tag_commit(head)
    release_verification = fetch_public_release_verification()

    committed_registration = git_file_bytes(
        protocol_commit, "RealLLM/beacon_registration.json"
    )
    committed_ledger = git_file_bytes(
        protocol_commit, "RealLLM/beacon_window_ledger.json"
    )
    expected = {
        "registrationArtifactSHA256": sha256_bytes(committed_registration),
        "registrationCanonicalSHA256": sha256_bytes(
            canonical_json_bytes(
                parse_json_bytes(committed_registration, label="committed registration")
            )
        ),
        "windowLedgerSHA256": sha256_bytes(committed_ledger),
        "implementationSHA256": implementation_sha256_at_commit(protocol_commit),
    }
    for key, value in expected.items():
        if freeze.get(key) != value:
            raise ValueError(f"freeze manifest {key} is inconsistent")
    committed_registration_object = parse_json_bytes(
        committed_registration, label="committed registration"
    )
    if not isinstance(committed_registration_object, dict):
        raise ValueError("committed registration is not an object")
    source_files = committed_registration_object.get("protocolSourceFiles")
    if not isinstance(source_files, list):
        raise ValueError("committed registration has no source manifest")
    expected_files = []
    for relative in source_files:
        content = git_file_bytes(protocol_commit, relative)
        expected_files.append(
            {
                "path": relative,
                "bytes": len(content),
                "sha256": sha256_bytes(content),
            }
        )
    if freeze.get("normativeFiles") != expected_files:
        raise ValueError("freeze individual file manifest is inconsistent")
    if registration_artifact_sha256() != expected["registrationArtifactSHA256"]:
        raise ValueError("current registration differs from protocol commit")
    if sha256_file(LEDGER_PATH) != expected["windowLedgerSHA256"]:
        raise ValueError("current ledger differs from protocol commit")
    if implementation_sha256() != expected["implementationSHA256"]:
        raise ValueError("current normative implementation differs from protocol commit")
    verified = dict(freeze)
    verified["publicReleaseVerification"] = release_verification
    return verified


def durable_exclusive_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_descriptor = None
        if directory_descriptor is not None:
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    except FileExistsError as error:
        raise ValueError(f"refusing to replace one-shot artifact {path}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _fetch_url(
    url: str,
    *,
    maximum_bytes: int,
    headers: dict[str, str] | None = None,
) -> bytes:
    request_headers = {"User-Agent": "core-lm-beacon-heldout-v1/1.0"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(
        url,
        headers=request_headers,
        method="GET",
    )
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(
            request, timeout=_URL_TIMEOUT_SECONDS, context=context
        ) as response:
            if response.status != 200:
                raise ValueError(f"unexpected HTTP status {response.status}")
            data = response.read(maximum_bytes + 1)
    except Exception as error:
        raise ValueError(f"cannot fetch frozen public resource {url}: {error}") from error
    if len(data) > maximum_bytes:
        raise ValueError("beacon response exceeds the frozen size limit")
    return data


def fetch_nist_pulse() -> tuple[dict[str, Any], bytes]:
    raw = _fetch_url(PULSE_URL, maximum_bytes=_MAX_PULSE_BYTES)
    envelope = parse_json_bytes(raw, label="NIST beacon response")
    if not isinstance(envelope, dict) or set(envelope) != {"pulse"}:
        raise ValueError("NIST response must contain exactly one pulse object")
    pulse = envelope["pulse"]
    if not isinstance(pulse, dict):
        raise ValueError("NIST pulse is not an object")
    certificate_id = pulse.get("certificateId")
    _decode_hex(certificate_id, expected_bytes=64, label="certificateId")
    certificate = _fetch_url(
        CERTIFICATE_URL_PREFIX + certificate_id,
        maximum_bytes=_MAX_CERTIFICATE_BYTES,
    )
    return pulse, certificate


def _decode_hex(value: Any, *, expected_bytes: int | None, label: str) -> bytes:
    if not isinstance(value, str) or not value or len(value) % 2:
        raise ValueError(f"{label} must be a non-empty even-length hex string")
    try:
        decoded = bytes.fromhex(value)
    except ValueError as error:
        raise ValueError(f"{label} is not valid hex") from error
    if expected_bytes is not None and len(decoded) != expected_bytes:
        raise ValueError(f"{label} must contain {expected_bytes} bytes")
    return decoded


def _serialize_string(value: Any, *, label: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded


def _serialize_hash(value: Any, *, label: str) -> bytes:
    decoded = _decode_hex(value, expected_bytes=64, label=label)
    return len(decoded).to_bytes(4, "big") + decoded


def _unsigned_integer(value: Any, size: int, *, label: str) -> bytes:
    if type(value) is not int or value < 0 or value >= (1 << (size * 8)):
        raise ValueError(f"{label} is outside uint{size * 8}")
    return value.to_bytes(size, "big")


def _list_value(pulse: dict[str, Any], kind: str) -> str:
    values = pulse.get("listValues")
    if not isinstance(values, list):
        raise ValueError("pulse listValues must be a list")
    matching = [
        item.get("value")
        for item in values
        if isinstance(item, dict) and item.get("type") == kind
    ]
    if len(matching) != 1:
        raise ValueError(f"pulse must contain exactly one {kind} list value")
    if not isinstance(matching[0], str):
        raise ValueError(f"pulse {kind} list value must be a string")
    return matching[0]


def serialize_nist_signed_fields(pulse: dict[str, Any]) -> bytes:
    external = pulse.get("external")
    if not isinstance(external, dict):
        raise ValueError("pulse external value must be an object")
    serialized = bytearray()
    serialized.extend(_serialize_string(pulse.get("uri"), label="uri"))
    serialized.extend(_serialize_string(pulse.get("version"), label="version"))
    serialized.extend(_unsigned_integer(pulse.get("cipherSuite"), 4, label="cipherSuite"))
    serialized.extend(_unsigned_integer(pulse.get("period"), 4, label="period"))
    serialized.extend(_serialize_hash(pulse.get("certificateId"), label="certificateId"))
    serialized.extend(_unsigned_integer(pulse.get("chainIndex"), 8, label="chainIndex"))
    serialized.extend(_unsigned_integer(pulse.get("pulseIndex"), 8, label="pulseIndex"))
    serialized.extend(_serialize_string(pulse.get("timeStamp"), label="timeStamp"))
    serialized.extend(_serialize_hash(pulse.get("localRandomValue"), label="localRandomValue"))
    serialized.extend(_serialize_hash(external.get("sourceId"), label="external.sourceId"))
    serialized.extend(_unsigned_integer(external.get("statusCode"), 4, label="external.statusCode"))
    serialized.extend(_serialize_hash(external.get("value"), label="external.value"))
    for kind in ("previous", "hour", "day", "month", "year"):
        serialized.extend(_serialize_hash(_list_value(pulse, kind), label=f"listValues.{kind}"))
    serialized.extend(_serialize_hash(pulse.get("precommitmentValue"), label="precommitmentValue"))
    serialized.extend(_unsigned_integer(pulse.get("statusCode"), 4, label="statusCode"))
    return bytes(serialized)


def _der_item(data: bytes, offset: int = 0) -> tuple[int, bytes, int]:
    if offset >= len(data):
        raise ValueError("truncated DER tag")
    tag = data[offset]
    offset += 1
    if offset >= len(data):
        raise ValueError("truncated DER length")
    first = data[offset]
    offset += 1
    if first & 0x80:
        count = first & 0x7F
        if count == 0 or count > 4 or offset + count > len(data):
            raise ValueError("invalid DER long-form length")
        if data[offset] == 0:
            raise ValueError("non-minimal DER length")
        length = int.from_bytes(data[offset : offset + count], "big")
        offset += count
        if length < 128:
            raise ValueError("non-minimal DER long-form length")
    else:
        length = first
    end = offset + length
    if end > len(data):
        raise ValueError("truncated DER value")
    return tag, data[offset:end], end


def _der_children(value: bytes) -> list[tuple[int, bytes]]:
    children: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(value):
        tag, child, offset = _der_item(value, offset)
        children.append((tag, child))
    return children


def _rsa_public_key_from_certificate(certificate_pem: bytes) -> tuple[int, int, bytes]:
    try:
        text = certificate_pem.decode("ascii")
        der = ssl.PEM_cert_to_DER_cert(text)
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"invalid PEM certificate: {error}") from error
    outer_tag, outer, outer_end = _der_item(der)
    if outer_tag != 0x30 or outer_end != len(der):
        raise ValueError("certificate is not one canonical DER sequence")
    certificate_children = _der_children(outer)
    if len(certificate_children) != 3 or certificate_children[0][0] != 0x30:
        raise ValueError("unexpected X.509 certificate structure")
    tbs_children = _der_children(certificate_children[0][1])
    index = 1 if tbs_children and tbs_children[0][0] == 0xA0 else 0
    spki_index = index + 5
    if len(tbs_children) <= spki_index or tbs_children[spki_index][0] != 0x30:
        raise ValueError("X.509 certificate has no supported subject public key")
    spki_children = _der_children(tbs_children[spki_index][1])
    if len(spki_children) != 2 or spki_children[1][0] != 0x03:
        raise ValueError("unsupported subjectPublicKeyInfo structure")
    bit_string = spki_children[1][1]
    if not bit_string or bit_string[0] != 0:
        raise ValueError("RSA public-key bit string is malformed")
    rsa_tag, rsa_value, rsa_end = _der_item(bit_string[1:])
    if rsa_tag != 0x30 or rsa_end != len(bit_string) - 1:
        raise ValueError("RSA public key is not a DER sequence")
    rsa_children = _der_children(rsa_value)
    if len(rsa_children) != 2 or any(tag != 0x02 for tag, _ in rsa_children):
        raise ValueError("RSA public key must contain modulus and exponent")
    modulus_bytes = rsa_children[0][1]
    exponent_bytes = rsa_children[1][1]
    if not modulus_bytes or not exponent_bytes:
        raise ValueError("RSA modulus or exponent is empty")
    if modulus_bytes[0] == 0:
        modulus_bytes = modulus_bytes[1:]
    modulus = int.from_bytes(modulus_bytes, "big")
    exponent = int.from_bytes(exponent_bytes, "big")
    if modulus.bit_length() < 3072 or exponent < 3 or exponent % 2 == 0:
        raise ValueError("NIST certificate RSA key is unexpectedly weak")
    return modulus, exponent, der


def _verify_rsa_pkcs1_v15_sha512(
    message: bytes, signature: bytes, modulus: int, exponent: int
) -> None:
    size = (modulus.bit_length() + 7) // 8
    if len(signature) != size:
        raise ValueError("RSA signature length differs from certificate key")
    signature_integer = int.from_bytes(signature, "big")
    if signature_integer >= modulus:
        raise ValueError("RSA signature representative is outside modulus")
    encoded = pow(signature_integer, exponent, modulus).to_bytes(size, "big")
    digest_info = _SHA512_DIGEST_INFO_PREFIX + hashlib.sha512(message).digest()
    padding_length = size - len(digest_info) - 3
    if padding_length < 8:
        raise ValueError("RSA key is too small for SHA-512 PKCS#1 v1.5")
    expected = b"\x00\x01" + b"\xff" * padding_length + b"\x00" + digest_info
    if not hmac.compare_digest(encoded, expected):
        raise ValueError("NIST pulse RSA signature verification failed")


def verify_nist_pulse(
    pulse: dict[str, Any],
    certificate_pem: bytes,
    *,
    expected_timestamp: str = TARGET_TIMESTAMP,
) -> dict[str, Any]:
    required_keys = {
        "uri",
        "version",
        "cipherSuite",
        "period",
        "certificateId",
        "chainIndex",
        "pulseIndex",
        "timeStamp",
        "localRandomValue",
        "external",
        "listValues",
        "precommitmentValue",
        "statusCode",
        "signatureValue",
        "outputValue",
    }
    if set(pulse) != required_keys:
        raise ValueError("NIST pulse fields differ from the frozen v2 structure")
    if pulse.get("version") != "2.0" or pulse.get("cipherSuite") != 0:
        raise ValueError("NIST pulse version or cipher suite differs")
    if pulse.get("period") != 60_000 or pulse.get("statusCode") != 0:
        raise ValueError("NIST pulse period or status is invalid")
    if pulse.get("timeStamp") != expected_timestamp:
        raise ValueError("NIST returned a different pulse timestamp; no fallback is allowed")
    chain_index = pulse.get("chainIndex")
    pulse_index = pulse.get("pulseIndex")
    if (
        type(chain_index) is not int
        or type(pulse_index) is not int
        or chain_index < 0
        or pulse_index < 1
    ):
        raise ValueError("NIST chain and pulse indices must be non-negative integers")
    expected_uri = (
        f"https://beacon.nist.gov/beacon/2.0/chain/{chain_index}/pulse/{pulse_index}"
    )
    if pulse.get("uri") != expected_uri:
        raise ValueError("NIST pulse URI disagrees with chain and pulse indices")
    values = pulse.get("listValues")
    if not isinstance(values, list) or len(values) != 5:
        raise ValueError("NIST pulse must contain five chain list values")
    expected_list_types = {
        "previous",
        "hour",
        "day",
        "month",
        "year",
    }
    if {item.get("type") for item in values if isinstance(item, dict)} != expected_list_types:
        raise ValueError("NIST pulse list-value types differ")
    list_uri_prefix = (
        f"https://beacon.nist.gov/beacon/2.0/chain/{chain_index}/pulse/"
    )
    for item in values:
        if not isinstance(item, dict) or set(item) != {"uri", "type", "value"}:
            raise ValueError("NIST list-value fields differ from the frozen structure")
        _decode_hex(
            item.get("value"),
            expected_bytes=64,
            label=f"listValues.{item.get('type')}.value",
        )
        uri = item.get("uri")
        if not isinstance(uri, str) or not uri.startswith(list_uri_prefix):
            raise ValueError("NIST list-value URI uses a different chain")
        referenced_text = uri[len(list_uri_prefix) :]
        if not referenced_text.isascii() or not referenced_text.isdigit():
            raise ValueError("NIST list-value URI has an invalid pulse index")
        referenced_index = int(referenced_text)
        if referenced_index >= pulse_index:
            raise ValueError("NIST list-value URI does not reference an earlier pulse")
        if item.get("type") == "previous" and referenced_index != pulse_index - 1:
            raise ValueError("NIST previous URI is not the immediately prior pulse")
    external = pulse.get("external")
    if not isinstance(external, dict) or set(external) != {
        "sourceId",
        "statusCode",
        "value",
    }:
        raise ValueError("NIST external fields differ from the frozen structure")
    if external.get("statusCode") != 0:
        raise ValueError("NIST external source status is not successful")
    _decode_hex(external.get("sourceId"), expected_bytes=64, label="external.sourceId")
    _decode_hex(external.get("value"), expected_bytes=64, label="external.value")

    modulus, exponent, certificate_der = _rsa_public_key_from_certificate(
        certificate_pem
    )
    certificate_id = _decode_hex(
        pulse.get("certificateId"), expected_bytes=64, label="certificateId"
    )
    if pulse.get("certificateId", "").lower() != EXPECTED_CERTIFICATE_ID:
        raise ValueError("NIST pulse uses a certificate outside the public freeze")
    if not hmac.compare_digest(hashlib.sha512(certificate_der).digest(), certificate_id):
        raise ValueError("NIST certificate DER does not match certificateId")
    signed_fields = serialize_nist_signed_fields(pulse)
    signature = _decode_hex(
        pulse.get("signatureValue"), expected_bytes=None, label="signatureValue"
    )
    _verify_rsa_pkcs1_v15_sha512(signed_fields, signature, modulus, exponent)
    output = _decode_hex(
        pulse.get("outputValue"), expected_bytes=64, label="outputValue"
    )
    expected_output = hashlib.sha512(signed_fields + signature).digest()
    if not hmac.compare_digest(output, expected_output):
        raise ValueError("NIST outputValue is inconsistent with the signed pulse")
    return {
        "certificateDER_SHA512": hashlib.sha512(certificate_der).hexdigest(),
        "certificatePEM_SHA256": sha256_bytes(certificate_pem),
        "outputValue": output.hex().upper(),
        "pulseIndex": pulse_index,
        "chainIndex": chain_index,
        "signatureVerified": True,
        "outputValueVerified": True,
    }


def select_window(
    registration_bytes: bytes,
    output_value_hex: str,
    windows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not windows:
        raise ValueError("eligible-window list must not be empty")
    output = _decode_hex(
        output_value_hex, expected_bytes=64, label="beacon outputValue"
    )
    registration = parse_json_bytes(
        registration_bytes, label="selection registration"
    )
    if not isinstance(registration, dict):
        raise ValueError("selection registration must be an object")
    selection = registration.get("selection")
    if not isinstance(selection, dict):
        raise ValueError("selection registration has no selection object")
    domain = _decode_hex(
        selection.get("domainSeparatorHex"),
        expected_bytes=None,
        label="domainSeparatorHex",
    )
    count = len(windows)
    if selection.get("candidateCount") != count:
        raise ValueError("eligible-window count differs from registration")
    prefix = (
        domain
        + len(registration_bytes).to_bytes(8, "big")
        + registration_bytes
        + output
    )
    counter, index, digest, limit = map_candidate_from_digest_sequence(
        (
            hashlib.sha512(prefix + counter.to_bytes(8, "big")).digest()
            for counter in range(1 << 32)
        ),
        count,
    )
    return {
        "candidateCount": count,
        "candidateIndex": index,
        "counter": counter,
        "rejectionLimitHex": f"{limit:0128x}",
        "seedDigestSHA512": digest.hex(),
        "selectedWindow": windows[index],
    }


def map_candidate_from_digest_sequence(
    digests: Iterable[bytes], candidate_count: int
) -> tuple[int, int, bytes, int]:
    """Map 512-bit digests without modulo bias; exposed for known-answer tests."""

    if type(candidate_count) is not int or candidate_count < 1:
        raise ValueError("candidate_count must be a positive integer")
    universe = 1 << 512
    limit = universe - (universe % candidate_count)
    for counter, digest in enumerate(digests):
        if not isinstance(digest, bytes) or len(digest) != 64:
            raise ValueError("selection digest must contain exactly 512 bits")
        integer = int.from_bytes(digest, "big")
        if integer < limit:
            return counter, integer % candidate_count, digest, limit
    raise RuntimeError("selection rejection sampling exhausted its digest stream")


def build_resolution(
    *,
    pulse: dict[str, Any],
    certificate_pem: bytes,
    attempt: dict[str, Any],
) -> dict[str, Any]:
    verification = verify_nist_pulse(pulse, certificate_pem)
    registration_bytes = REGISTRATION_PATH.read_bytes()
    ledger = load_ledger()
    windows = ledger.get("eligibleWindows")
    if not isinstance(windows, list):
        raise ValueError("ledger has no eligible windows")
    selection = select_window(
        registration_bytes, str(verification["outputValue"]), windows
    )
    resolution: dict[str, Any] = {
        "schemaVersion": "corelm-beacon-resolution-v1",
        "suiteId": SUITE_ID,
        "status": "beacon-resolved-before-model-data",
        "resolvedAt": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "attemptSHA256": attempt.get("attemptSHA256"),
        "registrationArtifactSHA256": registration_artifact_sha256(),
        "windowLedgerSHA256": sha256_file(LEDGER_PATH),
        "pulseEndpoint": PULSE_URL,
        "pulse": pulse,
        "certificatePEMBase64": base64.b64encode(certificate_pem).decode("ascii"),
        "verification": verification,
        "selection": selection,
    }
    resolution["resolutionSHA256"] = sha256_bytes(canonical_json_bytes(resolution))
    return resolution


def verify_resolution(
    resolution: dict[str, Any], *, registration_bytes: bytes | None = None
) -> list[str]:
    errors: list[str] = []
    try:
        if resolution.get("schemaVersion") != "corelm-beacon-resolution-v1":
            raise ValueError("resolution schema version differs")
        if resolution.get("suiteId") != SUITE_ID:
            raise ValueError("resolution suite ID differs")
        pulse = resolution.get("pulse")
        if not isinstance(pulse, dict):
            raise ValueError("resolution has no pulse object")
        encoded_certificate = resolution.get("certificatePEMBase64")
        if not isinstance(encoded_certificate, str):
            raise ValueError("resolution has no certificate")
        certificate = base64.b64decode(encoded_certificate, validate=True)
        verification = verify_nist_pulse(pulse, certificate)
        if resolution.get("verification") != verification:
            raise ValueError("resolution verification record is inconsistent")
        ledger = load_ledger()
        windows = ledger.get("eligibleWindows")
        if not isinstance(windows, list):
            raise ValueError("ledger has no windows")
        expected_selection = select_window(
            registration_bytes or REGISTRATION_PATH.read_bytes(),
            str(verification["outputValue"]),
            windows,
        )
        if resolution.get("selection") != expected_selection:
            raise ValueError("resolved window differs from deterministic selection")
        if resolution.get("registrationArtifactSHA256") != sha256_bytes(
            registration_bytes or REGISTRATION_PATH.read_bytes()
        ):
            raise ValueError("resolution registration digest differs")
        if resolution.get("windowLedgerSHA256") != sha256_file(LEDGER_PATH):
            raise ValueError("resolution ledger digest differs")
        digest_input = dict(resolution)
        recorded = digest_input.pop("resolutionSHA256", None)
        if recorded != sha256_bytes(canonical_json_bytes(digest_input)):
            raise ValueError("resolution digest is inconsistent")
    except (KeyError, TypeError, ValueError) as error:
        errors.append(str(error))
    return errors


def artifact_digest_without_field(value: dict[str, Any], field: str) -> str:
    copy = dict(value)
    copy.pop(field, None)
    return sha256_bytes(canonical_json_bytes(copy))
