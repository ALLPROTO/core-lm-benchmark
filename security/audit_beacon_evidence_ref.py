#!/usr/bin/env python3
"""Audit the fixed public beacon evidence tag without executing the experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


EVIDENCE_TAG = "corelm-beacon-heldout-v1-evidence"
FREEZE_COMMIT = "0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44"
REGISTERED_ORIGIN = "https://github.com/ALLPROTO/core-lm-benchmark"
RESULT_DIRECTORY = Path("real-llm-beacon-results")
ATTEMPT_PATH = RESULT_DIRECTORY / "attempt.json"
OUTCOME_PATH = RESULT_DIRECTORY / "outcome.json"
RELEASE_API = (
    "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/tags/"
    + EVIDENCE_TAG
)
LATEST_RELEASE_API = (
    "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/latest"
)
FROZEN_RELEASE_API = (
    "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/tags/"
    "corelm-beacon-heldout-v1"
)
FROZEN_TAG_API = (
    "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/git/ref/tags/"
    "corelm-beacon-heldout-v1"
)
ALLOWED_PUBLIC_APIS = frozenset(
    {RELEASE_API, LATEST_RELEASE_API, FROZEN_RELEASE_API, FROZEN_TAG_API}
)
RELEASE_URL = (
    "https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/" + EVIDENCE_TAG
)
RELEASE_TITLE = "CoreLM beacon heldout v1 evidence"
RELEASE_BODY = (
    "First and only normative corelm-beacon-heldout-v1 attempt. "
    "All surviving runner artifacts are published unchanged. The authoritative "
    "state is the verdict in real-llm-beacon-results/outcome.json, or "
    "CONSUMED_INCOMPLETE when attempt.json exists without outcome.json, or "
    "CONSUMED_INVALID_EVIDENCE when the published artifacts or verifier are "
    "invalid. No retry can change this scientific record."
)

TERMINAL_VERDICTS = {"PASS", "FAIL_GATES", "FAIL_EXECUTION"}
CONSUMED_CLASSIFICATIONS = {
    "CONSUMED_INCOMPLETE",
    "CONSUMED_INVALID_EVIDENCE",
}
MAX_ATTEMPT_BYTES = 64 * 1024
MAX_RESOLUTION_BYTES = 256 * 1024
MAX_OUTCOME_BYTES = 64 * 1024 * 1024
MAX_RELEASE_BYTES = 1024 * 1024
MAX_VERIFIER_OUTPUT_CHARS = 200_000
AUDIT_DISTRIBUTIONS = {
    "attrs": "26.1.0",
    "jsonschema": "4.25.1",
    "jsonschema-specifications": "2025.9.1",
    "numpy": "2.5.1",
    "referencing": "0.37.0",
    "rpds-py": "2026.6.3",
    "typing-extensions": "4.16.0",
}
LOCK_REQUIREMENT = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)=="
    r"([A-Za-z0-9][A-Za-z0-9._+!-]*)(?:\s|\\|$)"
)
CONTAINER_PATH = re.compile(
    r"^real-llm-beacon-results/primary-evidence/containers/"
    r"block-([0-9]{3})/layer-([0-9]{2})\.vtl5$"
)
ELIGIBLE_START_BLOCKS = (
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
ELIGIBLE_BLOCKS = frozenset(
    block
    for start in ELIGIBLE_START_BLOCKS
    for block in range(start, start + 32)
)
PRIMARY_MANIFEST_PATH = RESULT_DIRECTORY / "primary-evidence/manifest.json"
TOKEN_METRICS_PATH = RESULT_DIRECTORY / "primary-evidence/token-metrics.json"
FROZEN_AUDIT_FILE_SHA256 = {
    Path("RealLLM/requirements.lock"): (
        "e731ab2076b171d731b42ee8609d5943954911a10c92564ab52b7bed7a9fa561"
    ),
    Path(".github/locks/pip-bootstrap.txt"): (
        "587c4946469d33bb2e83b0d34cbe54d0c4c4799896e5af672331e108743f1fca"
    ),
    Path("security/verify_locked_environment.py"): (
        "5b75b13efa93abddcaa8a69310905a61dbf8f12a713c1c7a57e96f1a982e8ba9"
    ),
    Path("RealLLM/verify_beacon_evidence.py"): (
        "9923c7ac7c2dd80fedd17e72f9c0b4d1dc8e7c00bda5c726a7792fb73f5d5005"
    ),
    Path("RealLLM/beacon_protocol.py"): (
        "c6a6abfcf3535b5116fc83acda40e27489bca6723cc6477256d52f6d3b615e62"
    ),
}
FROZEN_VERIFIER_ALLOWED_URLS = frozenset(
    {FROZEN_RELEASE_API, FROZEN_TAG_API}
)


class AuditFailure(ValueError):
    """The immutable reference or audit environment is not trustworthy."""


@dataclass(frozen=True)
class VerifierResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _bounded_regular_bytes(path: Path, maximum: int, *, label: str) -> bytes:
    try:
        before = path.lstat()
    except OSError as error:
        raise ValueError(f"cannot stat {label}: {error}") from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} is not a regular non-symlink file")
    if before.st_size < 1 or before.st_size > maximum:
        raise ValueError(
            f"{label} byte length {before.st_size} is outside 1..{maximum}"
        )
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
                or opened.st_size != before.st_size
            ):
                raise ValueError(f"{label} changed between stat and open")
            raw = handle.read(maximum + 1)
    except OSError as error:
        raise ValueError(f"cannot read {label}: {error}") from error
    if len(raw) != before.st_size or len(raw) > maximum:
        raise ValueError(f"{label} changed or exceeded its byte cap while read")
    return raw


def _path_present(path: Path) -> bool:
    return os.path.lexists(path)


def _reason_from_verifier(result: VerifierResult) -> str:
    message = result.stderr.strip() or result.stdout.strip()
    if not message:
        message = f"verifier exited with status {result.returncode}"
    return message[:2000]


def classify_artifacts(
    repository: Path,
    *,
    verify_attempt: Callable[[Path], VerifierResult],
    verify_outcome: Callable[[Path], VerifierResult],
) -> dict[str, Any]:
    """Classify bytes already present; never create or repair an outcome."""

    attempt_path = repository / ATTEMPT_PATH
    outcome_path = repository / OUTCOME_PATH
    base: dict[str, Any] = {
        "auditCountsTowardScientificVerdict": False,
        "auditOnly": True,
        "evidenceConsumed": False,
        "modelLoadedByAudit": False,
        "newScientificAttemptPerformedByAudit": False,
        "nistNetworkFetchedByAudit": False,
        "scientificVerdict": None,
        "verifierExitCode": None,
        "windowSelectionRecomputedForVerification": False,
    }
    if not _path_present(attempt_path):
        if _path_present(outcome_path):
            return {
                **base,
                "classification": "CONSUMED_INVALID_EVIDENCE",
                "evidenceConsumed": True,
                "reason": "an outcome artifact exists without an attempt marker",
            }
        return {
            **base,
            "classification": "NOT_STARTED_PREFLIGHT_REJECTION",
            "reason": "the immutable evidence ref has no attempt marker",
        }

    base["evidenceConsumed"] = True
    try:
        attempt_raw = _bounded_regular_bytes(
            attempt_path, MAX_ATTEMPT_BYTES, label="attempt artifact"
        )
        _parse_json_object(attempt_raw, label="attempt artifact")
    except ValueError as error:
        return {
            **base,
            "classification": "CONSUMED_INVALID_EVIDENCE",
            "reason": str(error),
        }

    if not _path_present(outcome_path):
        attempt_verification = verify_attempt(repository)
        base["attemptVerifierExitCode"] = attempt_verification.returncode
        if attempt_verification.returncode != 0:
            return {
                **base,
                "classification": "CONSUMED_INVALID_EVIDENCE",
                "reason": _reason_from_verifier(attempt_verification),
            }
        return {
            **base,
            "classification": "CONSUMED_INCOMPLETE",
            "reason": "a verified attempt exists without an outcome artifact",
        }

    try:
        outcome_raw = _bounded_regular_bytes(
            outcome_path, MAX_OUTCOME_BYTES, label="outcome artifact"
        )
        outcome = _parse_json_object(outcome_raw, label="outcome artifact")
    except ValueError as error:
        return {
            **base,
            "classification": "CONSUMED_INVALID_EVIDENCE",
            "reason": str(error),
        }

    claimed_verdict = outcome.get("verdict")
    if claimed_verdict not in TERMINAL_VERDICTS:
        return {
            **base,
            "classification": "CONSUMED_INVALID_EVIDENCE",
            "claimedVerdict": claimed_verdict,
            "reason": "outcome does not claim a registered terminal verdict",
        }

    verification = verify_outcome(repository)
    base["verifierExitCode"] = verification.returncode
    if verification.returncode != 0:
        return {
            **base,
            "classification": "CONSUMED_INVALID_EVIDENCE",
            "claimedVerdict": claimed_verdict,
            "reason": _reason_from_verifier(verification),
            "windowSelectionRecomputedForVerification": None,
        }
    return {
        **base,
        "classification": claimed_verdict,
        "reason": "the frozen independent verifier accepted the terminal outcome",
        "scientificVerdict": claimed_verdict,
        "windowSelectionRecomputedForVerification": _path_present(
            repository / RESULT_DIRECTORY / "resolution.json"
        ),
    }


def classification_exit_code(classification: str) -> int:
    if classification in TERMINAL_VERDICTS:
        return 0
    if classification in CONSUMED_CLASSIFICATIONS:
        return 2
    return 1


def _logical_lock_blocks(source: str) -> dict[str, tuple[str, str]]:
    lines = source.splitlines()
    blocks: dict[str, tuple[str, str]] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        match = LOCK_REQUIREMENT.match(line)
        if match is None:
            raise AuditFailure(f"unsupported frozen lock entry at line {index + 1}")
        name, version = match.groups()
        block = [line]
        while block[-1].endswith("\\"):
            index += 1
            if index >= len(lines):
                raise AuditFailure("frozen lock ends inside a requirement block")
            block.append(lines[index])
        if not any("--hash=sha256:" in item for item in block[1:]):
            raise AuditFailure(f"frozen lock entry has no SHA-256: {name}")
        if name in blocks:
            raise AuditFailure(f"duplicate frozen lock entry: {name}")
        blocks[name] = (version, "\n".join(block))
        index += 1
    return blocks


def minimal_audit_lock(source: str) -> str:
    """Derive the verifier-only closure from the frozen RealLLM lock."""

    blocks = _logical_lock_blocks(source)
    selected: list[str] = []
    for name, expected_version in AUDIT_DISTRIBUTIONS.items():
        observed = blocks.get(name)
        if observed is None or observed[0] != expected_version:
            raise AuditFailure(
                f"frozen lock does not contain {name}=={expected_version}"
            )
        selected.append(observed[1])
    return (
        "# Derived verifier-only closure from frozen RealLLM/requirements.lock.\n"
        "# No model, tokenizer, dataset, or inference package is installed.\n"
        + "\n".join(selected)
        + "\n"
    )


def write_minimal_audit_lock(source: Path, destination: Path) -> None:
    raw = _bounded_regular_bytes(
        source, 4 * 1024 * 1024, label="frozen RealLLM lock"
    )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AuditFailure("frozen RealLLM lock is not UTF-8") from error
    output = minimal_audit_lock(text).encode("utf-8")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(output)
        handle.flush()
        os.fsync(handle.fileno())


def _git_environment() -> dict[str, str]:
    return {
        "HOME": os.environ.get("HOME", ""),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(repository: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["/usr/bin/git", *arguments],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AuditFailure(f"cannot execute bounded Git command: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise AuditFailure(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip()


def parse_name_status_z(raw: str) -> list[tuple[str, str]]:
    if not raw:
        return []
    fields = raw.split("\0")
    if fields[-1] != "" or (len(fields) - 1) % 2 != 0:
        raise AuditFailure("Git name-status output is malformed")
    changes: list[tuple[str, str]] = []
    for index in range(0, len(fields) - 1, 2):
        status, path = fields[index], fields[index + 1]
        if not status or not path:
            raise AuditFailure("Git name-status entry is empty")
        changes.append((status, path))
    return changes


def is_allowed_runner_artifact_path(path: str) -> bool:
    if path in {
        ATTEMPT_PATH.as_posix(),
        (RESULT_DIRECTORY / "resolution.json").as_posix(),
        OUTCOME_PATH.as_posix(),
        PRIMARY_MANIFEST_PATH.as_posix(),
        TOKEN_METRICS_PATH.as_posix(),
    }:
        return True
    match = CONTAINER_PATH.fullmatch(path)
    if match is None:
        return False
    block, layer = (int(value) for value in match.groups())
    return block in ELIGIBLE_BLOCKS and 0 <= layer < 24


def validate_added_artifact_changes(
    changes: list[tuple[str, str]],
) -> list[str]:
    if not changes:
        raise AuditFailure("evidence commit adds no runner artifacts")
    paths: list[str] = []
    for status, path in changes:
        if status != "A":
            raise AuditFailure(
                f"evidence commit contains non-addition status {status}: {path}"
            )
        if not is_allowed_runner_artifact_path(path):
            raise AuditFailure(f"path is not a runner-produced artifact: {path}")
        if path in paths:
            raise AuditFailure(f"evidence commit repeats an artifact path: {path}")
        paths.append(path)
    return paths


def parse_ls_tree_z(raw: str) -> dict[str, tuple[str, str, str]]:
    if not raw:
        return {}
    records = raw.split("\0")
    if records[-1] != "":
        raise AuditFailure("Git tree output is malformed")
    entries: dict[str, tuple[str, str, str]] = {}
    for record in records[:-1]:
        if "\t" not in record:
            raise AuditFailure("Git tree entry has no path separator")
        metadata, path = record.split("\t", 1)
        fields = metadata.split(" ")
        if len(fields) != 3 or not path:
            raise AuditFailure("Git tree entry metadata is malformed")
        mode, object_type, object_id = fields
        if path in entries:
            raise AuditFailure(f"Git tree repeats an artifact path: {path}")
        entries[path] = (mode, object_type, object_id)
    return entries


def validate_added_blob_entries(
    added_paths: list[str],
    entries: dict[str, tuple[str, str, str]],
) -> None:
    for path in added_paths:
        entry = entries.get(path)
        if entry is None:
            raise AuditFailure(
                f"added artifact is absent from the evidence tree: {path}"
            )
        mode, object_type, object_id = entry
        if (
            mode != "100644"
            or object_type != "blob"
            or re.fullmatch(r"[0-9a-f]{40}", object_id) is None
        ):
            raise AuditFailure(
                f"added artifact is not a regular non-executable Git blob: {path}"
            )


def verify_frozen_audit_files(repository: Path) -> dict[str, str]:
    verified: dict[str, str] = {}
    for relative, expected in FROZEN_AUDIT_FILE_SHA256.items():
        raw = _bounded_regular_bytes(
            repository / relative,
            8 * 1024 * 1024,
            label=f"frozen audit file {relative.as_posix()}",
        )
        observed = hashlib.sha256(raw).hexdigest()
        if observed != expected:
            raise AuditFailure(
                f"frozen audit file digest differs: {relative.as_posix()}"
            )
        verified[relative.as_posix()] = observed
    return verified


def verify_local_topology(repository: Path) -> dict[str, Any]:
    if repository.is_symlink() or not repository.is_dir():
        raise AuditFailure("evidence checkout must be a real directory")
    status = _git(
        repository,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignored=no",
    )
    if status:
        raise AuditFailure("evidence checkout is not clean: " + status)
    head = _git(repository, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise AuditFailure("evidence HEAD is not a full lowercase commit")
    if _git(repository, "cat-file", "-t", f"refs/tags/{EVIDENCE_TAG}") != "commit":
        raise AuditFailure("evidence tag must be lightweight")
    tagged = _git(repository, "rev-parse", f"refs/tags/{EVIDENCE_TAG}^{{commit}}")
    if tagged != head:
        raise AuditFailure("evidence tag does not point to checked-out HEAD")
    parents = _git(repository, "rev-list", "--parents", "-n", "1", head).split()
    if parents != [head, FREEZE_COMMIT]:
        raise AuditFailure("evidence commit is not the direct child of the freeze")
    raw_changes = _git(
        repository,
        "diff-tree",
        "--no-commit-id",
        "--name-status",
        "--no-renames",
        "-r",
        "-z",
        FREEZE_COMMIT,
        head,
    )
    changed = validate_added_artifact_changes(parse_name_status_z(raw_changes))
    tree = _git(
        repository,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        head,
        "--",
        RESULT_DIRECTORY.as_posix(),
    )
    validate_added_blob_entries(changed, parse_ls_tree_z(tree))
    origin = _git(repository, "remote", "get-url", "origin").removesuffix(".git")
    if origin != REGISTERED_ORIGIN:
        raise AuditFailure("evidence checkout origin is not the registered repository")
    remote = _git(
        repository,
        "ls-remote",
        "--tags",
        "origin",
        f"refs/tags/{EVIDENCE_TAG}",
    ).splitlines()
    expected = f"{head}\trefs/tags/{EVIDENCE_TAG}"
    if remote != [expected]:
        raise AuditFailure("public evidence tag does not resolve to evidence HEAD")
    return {"addedPaths": changed, "evidenceCommit": head}


def _selected_start_block(repository: Path) -> int:
    raw = _bounded_regular_bytes(
        repository / RESULT_DIRECTORY / "resolution.json",
        MAX_RESOLUTION_BYTES,
        label="beacon resolution",
    )
    resolution = _parse_json_object(raw, label="beacon resolution")
    selection = resolution.get("selection")
    selected = selection.get("selectedWindow") if isinstance(selection, dict) else None
    start = selected.get("startBlock") if isinstance(selected, dict) else None
    if type(start) is not int or start not in ELIGIBLE_START_BLOCKS:
        raise AuditFailure("resolution does not contain an eligible selected window")
    return start


def _expected_container_paths(start: int) -> list[str]:
    return [
        (
            RESULT_DIRECTORY
            / "primary-evidence/containers"
            / f"block-{block:03d}"
            / f"layer-{layer:02d}.vtl5"
        ).as_posix()
        for block in range(start, start + 32)
        for layer in range(24)
    ]


def _manifest_primary_paths(repository: Path, start: int) -> set[str]:
    raw = _bounded_regular_bytes(
        repository / PRIMARY_MANIFEST_PATH,
        4 * 1024 * 1024,
        label="primary-evidence manifest",
    )
    manifest = _parse_json_object(raw, label="primary-evidence manifest")
    if set(manifest) != {
        "schemaVersion",
        "resultFile",
        "containers",
        "tokenMetrics",
    }:
        raise AuditFailure("primary-evidence manifest fields differ")
    if (
        manifest.get("schemaVersion") != "corelm-real-llm-primary-evidence-v1"
        or manifest.get("resultFile") != "outcome.json"
    ):
        raise AuditFailure("primary-evidence manifest identity differs")
    expected_containers = _expected_container_paths(start)
    entries = manifest.get("containers")
    if not isinstance(entries, list) or len(entries) != len(expected_containers):
        raise AuditFailure("primary-evidence manifest container count differs")
    observed_containers: list[str] = []
    for entry, expected_path in zip(entries, expected_containers):
        if not isinstance(entry, dict) or set(entry) != {
            "blockIndex",
            "layerIndex",
            "path",
            "bytes",
            "sha256",
        }:
            raise AuditFailure("primary-evidence container entry fields differ")
        relative = expected_path.removeprefix(RESULT_DIRECTORY.as_posix() + "/")
        match = CONTAINER_PATH.fullmatch(expected_path)
        assert match is not None
        block, layer = (int(value) for value in match.groups())
        if (
            entry.get("path") != relative
            or entry.get("blockIndex") != block
            or entry.get("layerIndex") != layer
        ):
            raise AuditFailure("primary-evidence container path or order differs")
        observed_containers.append(expected_path)
    token = manifest.get("tokenMetrics")
    if not isinstance(token, dict) or set(token) != {
        "path",
        "bytes",
        "sha256",
        "blocks",
        "predictionTokens",
    }:
        raise AuditFailure("primary-evidence token-metrics fields differ")
    token_relative = TOKEN_METRICS_PATH.as_posix().removeprefix(
        RESULT_DIRECTORY.as_posix() + "/"
    )
    if (
        token.get("path") != token_relative
        or token.get("blocks") != 32
        or token.get("predictionTokens") != 4096
    ):
        raise AuditFailure("primary-evidence token-metrics path differs")
    return {
        PRIMARY_MANIFEST_PATH.as_posix(),
        TOKEN_METRICS_PATH.as_posix(),
        *observed_containers,
    }


def _expected_primary_artifact_set(
    repository: Path,
    observed_primary: set[str],
) -> set[str]:
    if not observed_primary:
        return set()
    resolution_path = RESULT_DIRECTORY / "resolution.json"
    if not _path_present(repository / resolution_path):
        raise AuditFailure("primary evidence exists without a resolution")
    start = _selected_start_block(repository)
    if PRIMARY_MANIFEST_PATH.as_posix() in observed_primary:
        return _manifest_primary_paths(repository, start)
    full_sequence = _expected_container_paths(start)
    observed_containers = {
        path for path in observed_primary if CONTAINER_PATH.fullmatch(path)
    }
    prefix = set(full_sequence[: len(observed_containers)])
    if observed_containers != prefix:
        raise AuditFailure(
            "partial primary containers are not an exact writer-order prefix"
        )
    expected_primary = set(observed_containers)
    if TOKEN_METRICS_PATH.as_posix() in observed_primary:
        if len(observed_containers) != len(full_sequence):
            raise AuditFailure(
                "token metrics exist before the complete container sequence"
            )
        expected_primary.add(TOKEN_METRICS_PATH.as_posix())
    return expected_primary


def verify_terminal_artifact_set(
    repository: Path,
    added_paths: list[str],
    verdict: str,
) -> None:
    if verdict not in TERMINAL_VERDICTS:
        raise AuditFailure("terminal artifact-set check received a nonterminal verdict")
    observed = set(added_paths)
    if len(observed) != len(added_paths):
        raise AuditFailure("terminal artifact set contains duplicate paths")
    expected = {ATTEMPT_PATH.as_posix(), OUTCOME_PATH.as_posix()}
    resolution_path = (RESULT_DIRECTORY / "resolution.json").as_posix()
    resolution_exists = _path_present(repository / resolution_path)
    if resolution_exists:
        expected.add(resolution_path)

    primary_prefix = (RESULT_DIRECTORY / "primary-evidence").as_posix() + "/"
    observed_primary = {path for path in observed if path.startswith(primary_prefix)}
    if verdict in {"PASS", "FAIL_GATES"} and not resolution_exists:
        raise AuditFailure("scientific terminal evidence has no resolution")
    expected.update(_expected_primary_artifact_set(repository, observed_primary))
    if verdict in {"PASS", "FAIL_GATES"} and (
        PRIMARY_MANIFEST_PATH.as_posix() not in expected
        or TOKEN_METRICS_PATH.as_posix() not in expected
    ):
        raise AuditFailure(
            "scientific terminal evidence is missing its exact manifest set"
        )
    if observed != expected:
        extra = sorted(observed - expected)
        missing = sorted(expected - observed)
        raise AuditFailure(
            f"terminal artifact set differs (missing={missing}, extra={extra})"
        )


def verify_consumed_artifact_set(
    repository: Path,
    added_paths: list[str],
) -> None:
    observed = set(added_paths)
    if len(observed) != len(added_paths):
        raise AuditFailure("consumed artifact set contains duplicate paths")
    if ATTEMPT_PATH.as_posix() not in observed:
        raise AuditFailure("consumed artifact set has no attempt marker")
    resolution_path = (RESULT_DIRECTORY / "resolution.json").as_posix()
    if resolution_path in observed:
        _selected_start_block(repository)
    primary_prefix = (RESULT_DIRECTORY / "primary-evidence").as_posix() + "/"
    observed_primary = {path for path in observed if path.startswith(primary_prefix)}
    expected = {
        path
        for path in observed
        if path
        in {
            ATTEMPT_PATH.as_posix(),
            resolution_path,
            OUTCOME_PATH.as_posix(),
        }
    }
    expected.update(_expected_primary_artifact_set(repository, observed_primary))
    if observed != expected:
        extra = sorted(observed - expected)
        missing = sorted(expected - observed)
        raise AuditFailure(
            f"consumed artifact set differs (missing={missing}, extra={extra})"
        )


def apply_artifact_set_classification(
    repository: Path,
    added_paths: list[str],
    classification: dict[str, Any],
) -> dict[str, Any]:
    state = classification.get("classification")
    try:
        if state in TERMINAL_VERDICTS:
            verify_terminal_artifact_set(repository, added_paths, str(state))
        elif state in CONSUMED_CLASSIFICATIONS:
            verify_consumed_artifact_set(repository, added_paths)
    except (OSError, ValueError) as error:
        claimed = state if state in TERMINAL_VERDICTS else classification.get(
            "claimedVerdict"
        )
        return {
            **classification,
            "classification": "CONSUMED_INVALID_EVIDENCE",
            "claimedVerdict": claimed,
            "evidenceConsumed": True,
            "reason": f"published artifact-set validation failed: {error}",
            "scientificVerdict": None,
        }
    return classification


def validate_release_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise AuditFailure("evidence release metadata must be an object")
    expected = {
        "tag_name": EVIDENCE_TAG,
        "name": RELEASE_TITLE,
        "html_url": RELEASE_URL,
        "draft": False,
        "prerelease": False,
        "immutable": True,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise AuditFailure(f"evidence release field {key} differs")
    body = metadata.get("body")
    if body != RELEASE_BODY:
        raise AuditFailure("evidence release body differs from the fixed disclosure")
    if metadata.get("assets") != []:
        raise AuditFailure("evidence release must not contain uploaded assets")
    published_at = metadata.get("published_at")
    if not isinstance(published_at, str) or re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
        published_at,
    ) is None:
        raise AuditFailure("evidence release has no canonical publication time")
    try:
        published = datetime.strptime(
            published_at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise AuditFailure("evidence release publication time is invalid") from error
    if published.isoformat(timespec="seconds").replace("+00:00", "Z") != published_at:
        raise AuditFailure("evidence release publication time is not canonical UTC")
    return {
        "immutable": True,
        "publishedAt": published_at,
        "releaseURL": RELEASE_URL,
    }


def _fetch_public_github_object(url: str, *, label: str) -> dict[str, Any]:
    if url not in ALLOWED_PUBLIC_APIS:
        raise AuditFailure("public audit URL is outside the fixed GitHub allowlist")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "corelm-beacon-evidence-audit/1.0",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise AuditFailure(
                    f"unexpected {label} HTTP status {response.status}"
                )
            raw = response.read(MAX_RELEASE_BYTES + 1)
    except (OSError, urllib.error.URLError) as error:
        raise AuditFailure(f"cannot fetch {label}: {error}") from error
    if len(raw) > MAX_RELEASE_BYTES:
        raise AuditFailure(f"{label} response exceeds its byte cap")
    return _parse_json_object(raw, label=f"{label} response")


def fetch_release_metadata() -> dict[str, Any]:
    return _fetch_public_github_object(RELEASE_API, label="public evidence release")


def fetch_latest_release_metadata() -> dict[str, Any]:
    return _fetch_public_github_object(
        LATEST_RELEASE_API, label="public latest release"
    )


def validate_latest_release_metadata(metadata: Any) -> dict[str, str]:
    if not isinstance(metadata, dict):
        raise AuditFailure("latest release metadata must be an object")
    tag = metadata.get("tag_name")
    if not isinstance(tag, str) or not tag or tag == EVIDENCE_TAG:
        raise AuditFailure("evidence release unexpectedly became the latest release")
    return {"latestReleaseTag": tag}


def fetch_frozen_verifier_resources() -> dict[str, bytes]:
    resources: dict[str, bytes] = {}
    for url in sorted(FROZEN_VERIFIER_ALLOWED_URLS):
        value = _fetch_public_github_object(url, label="frozen GitHub verification")
        resources[url] = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    return resources


def verifier_network_guard_source(resources: dict[str, bytes]) -> str:
    if set(resources) != set(FROZEN_VERIFIER_ALLOWED_URLS) or any(
        not isinstance(raw, bytes) or not raw for raw in resources.values()
    ):
        raise AuditFailure("frozen verifier resources differ from the URL allowlist")
    return f"""
import io
import socket
import urllib.request
_CORELM_FROZEN_RESPONSES = {resources!r}
class _CoreLMOfflineResponse:
    status = 200
    def __init__(self, raw):
        self._stream = io.BytesIO(raw)
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        return False
    def read(self, size=-1):
        return self._stream.read(size)
def _corelm_offline_urlopen(target, *args, **kwargs):
    url = getattr(target, "full_url", target)
    raw = _CORELM_FROZEN_RESPONSES.get(url)
    if raw is None:
        raise RuntimeError("frozen verifier attempted a non-allowlisted URL")
    return _CoreLMOfflineResponse(raw)
def _corelm_block_socket(*args, **kwargs):
    raise RuntimeError("frozen verifier attempted an outbound socket")
urllib.request.urlopen = _corelm_offline_urlopen
socket.create_connection = _corelm_block_socket
socket.socket.connect = _corelm_block_socket
socket.socket.connect_ex = _corelm_block_socket
"""


def _verifier_environment() -> dict[str, str]:
    return {
        "HOME": os.environ.get("HOME", ""),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    }


def _run_verifier_process(
    repository: Path,
    arguments: list[str],
    *,
    timeout: int,
) -> VerifierResult:
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-B", *arguments],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_verifier_environment(),
        )
    except (OSError, subprocess.SubprocessError) as error:
        return VerifierResult(1, stderr=f"cannot execute frozen verifier: {error}")
    return VerifierResult(
        completed.returncode,
        completed.stdout[:MAX_VERIFIER_OUTPUT_CHARS],
        completed.stderr[:MAX_VERIFIER_OUTPUT_CHARS],
    )


def run_frozen_attempt_verifier(repository: Path) -> VerifierResult:
    try:
        guard = verifier_network_guard_source(fetch_frozen_verifier_resources())
    except (OSError, ValueError) as error:
        return VerifierResult(1, stderr=f"cannot stage frozen verifier inputs: {error}")
    source = guard + """
from pathlib import Path
import sys
root = Path.cwd().resolve(strict=True)
sys.path.insert(0, str(root))
from RealLLM import verify_beacon_evidence as verifier
from RealLLM.beacon_protocol import parse_json_bytes, validate_registration_and_ledger
registration, _ = validate_registration_and_ledger()
raw = verifier._bounded_file_bytes(
    verifier.ATTEMPT_PATH,
    verifier._MAX_ATTEMPT_BYTES,
    label="one-shot attempt",
)
attempt = parse_json_bytes(raw, label="one-shot attempt")
if not isinstance(attempt, dict):
    raise ValueError("one-shot attempt must contain a JSON object")
verifier._verify_attempt_and_freeze(attempt, registration)
print("BEACON ATTEMPT VERIFIED: no outcome, model, NIST fetch, or selection executed")
"""
    return _run_verifier_process(repository, ["-c", source], timeout=180)


def run_frozen_outcome_verifier(repository: Path) -> VerifierResult:
    try:
        guard = verifier_network_guard_source(fetch_frozen_verifier_resources())
    except (OSError, ValueError) as error:
        return VerifierResult(1, stderr=f"cannot stage frozen verifier inputs: {error}")
    source = guard + """
from pathlib import Path
import sys
root = Path.cwd().resolve(strict=True)
sys.path.insert(0, str(root))
from RealLLM import verify_beacon_evidence as verifier
raise SystemExit(verifier.main())
"""
    return _run_verifier_process(repository, ["-c", source], timeout=900)


def _summary_text(result: dict[str, Any]) -> str:
    verdict = result.get("scientificVerdict") or "none"
    consumed_value = result.get("evidenceConsumed")
    consumed = "unknown" if consumed_value is None else str(consumed_value).lower()
    return "\n".join(
        [
            "## CoreLM immutable beacon evidence audit",
            "",
            f"- Classification: `{result.get('classification')}`",
            f"- Scientific verdict: `{verdict}`",
            f"- Publication audit passed: `"
            f"{str(result.get('publicationAuditPassed')).lower()}`",
            f"- Publication audit reason: {result.get('publicationAuditReason')}",
            f"- Evidence commit: `{result.get('evidenceCommit', 'unknown')}`",
            f"- Evidence consumed: `{consumed}`",
            "- Audit counts toward scientific verdict: `false`",
            "- Model loaded by audit: `false`",
            "- New scientific attempt performed by audit: `false`",
            "- NIST network fetched by audit: `false`",
            f"- Window selection recomputed for verification: `"
            f"{result.get('windowSelectionRecomputedForVerification')}`",
            f"- Frozen attempt verifier exit: `"
            f"{result.get('attemptVerifierExitCode')}`",
            f"- Frozen verifier exit: `{result.get('verifierExitCode')}`",
            "",
            "Workflow success means evidence integrity was verified; it does not "
            "mean the scientific verdict was PASS.",
            "",
        ]
    )


def _append_summary(path: Path | None, result: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_summary_text(result))


def preflight_repository(repository: Path) -> dict[str, Any]:
    resolved = repository.resolve(strict=True)
    topology = verify_local_topology(resolved)
    frozen_files = verify_frozen_audit_files(resolved)
    return {
        "schemaVersion": "corelm-beacon-publication-preflight-v1",
        "evidenceRef": EVIDENCE_TAG,
        **topology,
        "frozenAuditFileSHA256": frozen_files,
        "safeToDeriveAuditLock": True,
    }


def audit_repository(repository: Path) -> dict[str, Any]:
    resolved = repository.resolve(strict=True)
    topology = verify_local_topology(resolved)
    frozen_files = verify_frozen_audit_files(resolved)
    classification = classify_artifacts(
        resolved,
        verify_attempt=run_frozen_attempt_verifier,
        verify_outcome=run_frozen_outcome_verifier,
    )
    classification = apply_artifact_set_classification(
        resolved,
        topology["addedPaths"],
        classification,
    )
    topology_after = verify_local_topology(resolved)
    frozen_files_after = verify_frozen_audit_files(resolved)
    if topology_after != topology or frozen_files_after != frozen_files:
        raise AuditFailure("evidence checkout changed during frozen verification")
    try:
        release = validate_release_metadata(fetch_release_metadata())
        latest = validate_latest_release_metadata(fetch_latest_release_metadata())
        publication_audit = {
            "publicationAuditPassed": True,
            "publicationAuditReason": "immutable public tag and release verified",
            **release,
            **latest,
        }
    except (OSError, ValueError) as error:
        publication_audit = {
            "publicationAuditPassed": False,
            "publicationAuditReason": str(error),
        }
    return {
        "schemaVersion": "corelm-beacon-publication-audit-v1",
        "evidenceRef": EVIDENCE_TAG,
        **topology,
        "frozenAuditFileSHA256": frozen_files,
        **classification,
        **publication_audit,
    }


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    extract = subparsers.add_parser("extract-lock")
    extract.add_argument("--source", required=True, type=Path)
    extract.add_argument("--output", required=True, type=Path)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--repository", required=True, type=Path)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--repository", required=True, type=Path)
    audit.add_argument("--summary", type=Path)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    parsed = parse_arguments(arguments)
    if parsed.command == "extract-lock":
        try:
            write_minimal_audit_lock(parsed.source, parsed.output)
        except (OSError, ValueError) as error:
            print(f"BEACON AUDIT LOCK FAIL: {error}", file=sys.stderr)
            return 1
        print(f"BEACON AUDIT LOCK READY: {parsed.output}")
        return 0
    if parsed.command == "preflight":
        try:
            result = preflight_repository(parsed.repository)
        except (OSError, ValueError) as error:
            print(f"BEACON AUDIT PREFLIGHT FAIL: {error}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    try:
        result = audit_repository(parsed.repository)
    except (OSError, ValueError) as error:
        result = {
            "schemaVersion": "corelm-beacon-publication-audit-v1",
            "classification": "AUDIT_FAILURE",
            "publicationAuditPassed": False,
            "publicationAuditReason": str(error),
            "auditOnly": True,
            "auditCountsTowardScientificVerdict": False,
            "evidenceConsumed": None,
            "modelLoadedByAudit": False,
            "newScientificAttemptPerformedByAudit": False,
            "nistNetworkFetchedByAudit": False,
            "reason": str(error),
            "scientificVerdict": None,
            "verifierExitCode": None,
            "windowSelectionRecomputedForVerification": None,
        }
    _append_summary(parsed.summary, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result.get("publicationAuditPassed") is not True:
        return 1
    return classification_exit_code(str(result["classification"]))


if __name__ == "__main__":
    raise SystemExit(main())
