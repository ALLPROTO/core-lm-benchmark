#!/usr/bin/env python3
"""Fail-closed public GitHub tag-CI admission for the V11 portfolio run.

The validator is deliberately split in two:

* :func:`validate_saved_tag_ci` performs no network I/O.  It validates caller-
  supplied GitHub JSON response bytes and returns a canonicalizable receipt.
* :func:`fetch_public_tag_ci_responses` performs the constrained, anonymous
  HTTPS acquisition and refuses to return until the offline validator passes.

This module does not inspect a local Git checkout, start the benchmark, or
write evidence.  A caller must complete this admission before reserving a
scientific attempt or loading the model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import ssl
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


API_ORIGIN = "https://api.github.com"
DEFAULT_REPOSITORY = "ALLPROTO/core-lm-benchmark"
MAIN_REF = "refs/heads/main"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MIN_TIMEOUT_SECONDS = 1.0
MAX_TIMEOUT_SECONDS = 30.0
DEFAULT_TIMEOUT_SECONDS = 10.0
PAGE_SIZE = 100
MAX_GITHUB_ID = 2**63 - 1
API_VERSION = "2022-11-28"
GIT = "/usr/bin/git"
SSH_KEYGEN = "/usr/bin/ssh-keygen"
EXPECTED_PUBLIC_KEY_SHA256 = (
    "9d299ff032927caef3f1355fb55c01f206ebf27ef35bcb5da547f962168b1274"
)
EXPECTED_ALLOWED_SIGNERS_SHA256 = (
    "36fb4a170eee7664be32f2a5d562db209fa4f6f1f24667cf6a3ef0166d155c16"
)
EXPECTED_SIGNING_PRINCIPAL = "ivantyschenko777@gmail.com"
EXPECTED_FINGERPRINT = "SHA256:8A4y/GkoFglweSfg3rP21BtWWqIBOeQAUoAJDQM8sMM"

_SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")
_TAG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_REPOSITORY_PART_RE = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")


class TagCIAdmissionError(ValueError):
    """The public tag or its tag-push CI did not satisfy admission."""


@dataclass(frozen=True)
class _WorkflowContract:
    role: str
    jobs_role: str
    name: str
    filename: str
    expected_jobs: frozenset[str]

    @property
    def path(self) -> str:
        return f".github/workflows/{self.filename}"


_WORKFLOWS = (
    _WorkflowContract(
        role="linux_runs",
        jobs_role="linux_jobs",
        name="Verify Linux",
        filename="verify-linux.yml",
        expected_jobs=frozenset({"python-and-publication", "supply-chain"}),
    ),
    _WorkflowContract(
        role="macos_runs",
        jobs_role="macos_jobs",
        name="Verify macOS",
        filename="verify-macos.yml",
        expected_jobs=frozenset({"native-application"}),
    ),
)

_FIXED_RESPONSE_ROLES = ("tag_ref", "tag_object", "commit", "main_ref")
_ALL_RESPONSE_ROLES = _FIXED_RESPONSE_ROLES + tuple(
    role for workflow in _WORKFLOWS for role in (workflow.role, workflow.jobs_role)
)
RESPONSE_ROLES = _ALL_RESPONSE_ROLES
RESPONSE_FILENAMES = {
    "tag_ref": "github-tag-ref.json",
    "tag_object": "github-annotated-tag-object.json",
    "commit": "github-commit-object.json",
    "main_ref": "github-main-ref.json",
    "linux_runs": "github-verify-linux-runs.json",
    "linux_jobs": "github-verify-linux-jobs.json",
    "macos_runs": "github-verify-macos-runs.json",
    "macos_jobs": "github-verify-macos-jobs.json",
}
PUBLIC_RECEIPT_FILENAME = "github-tag-ci-admission-receipt.json"
LOCAL_TRUST_RECEIPT_FILENAME = "local-tag-trust-receipt.json"
TAG_REF_ASSERTION_STEP = "Require exact portfolio tag-push ref"
CURRENT_PORTFOLIO_TAG = "corelm-portfolio-v11"


def _reject_constant(value: str) -> None:
    raise TagCIAdmissionError(f"non-finite JSON number is forbidden: {value}")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TagCIAdmissionError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _decode_json(raw: bytes, label: str) -> Mapping[str, Any]:
    if type(raw) is not bytes:
        raise TagCIAdmissionError(f"{label} response must be immutable bytes")
    if not raw:
        raise TagCIAdmissionError(f"{label} response is empty")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise TagCIAdmissionError(f"{label} response exceeds the byte limit")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise TagCIAdmissionError(f"{label} response has a forbidden UTF-8 BOM")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except TagCIAdmissionError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise TagCIAdmissionError(f"{label} response is not strict UTF-8 JSON") from error
    return _mapping(value, f"{label} response")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise TagCIAdmissionError(f"{label} must be a JSON object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise TagCIAdmissionError(f"{label} must be a JSON array")
    return value


def _string(value: Any, label: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        raise TagCIAdmissionError(f"{label} must be a non-empty string")
    return value


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TagCIAdmissionError(f"{label} must be a positive integer")
    return value


def _github_identifier(value: Any, label: str) -> int:
    identifier = _positive_integer(value, label)
    if identifier > MAX_GITHUB_ID:
        raise TagCIAdmissionError(f"{label} is outside the positive signed 64-bit range")
    return identifier


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TagCIAdmissionError(f"{label} must be a non-negative integer")
    return value


def _exact(value: Any, expected: Any, label: str) -> None:
    if type(value) is not type(expected) or value != expected:
        raise TagCIAdmissionError(f"{label} must be exactly {expected!r}")


def _sha1(value: Any, label: str) -> str:
    candidate = _string(value, label)
    if _SHA1_RE.fullmatch(candidate) is None:
        raise TagCIAdmissionError(f"{label} must be a lowercase 40-hex Git object ID")
    return candidate


def _validate_inputs(
    repository: str, expected_tag: str, expected_commit: str, expected_tree: str
) -> tuple[str, str]:
    if not isinstance(repository, str):
        raise TagCIAdmissionError("repository must be a string")
    parts = repository.split("/")
    if (
        len(parts) != 2
        or any(_REPOSITORY_PART_RE.fullmatch(part) is None for part in parts)
        or any(part in {".", ".."} for part in parts)
    ):
        raise TagCIAdmissionError("repository must be an exact owner/name slug")
    if not isinstance(expected_tag, str) or _TAG_RE.fullmatch(expected_tag) is None:
        raise TagCIAdmissionError("expected tag is not a safe single Git ref component")
    if expected_tag != CURRENT_PORTFOLIO_TAG:
        raise TagCIAdmissionError(
            f"expected tag must be the active V11 contour {CURRENT_PORTFOLIO_TAG}"
        )
    _sha1(expected_commit, "expected commit")
    _sha1(expected_tree, "expected tree")
    return parts[0], parts[1]


def _api_base(repository: str) -> str:
    return f"{API_ORIGIN}/repos/{repository}"


def _tag_ref_url(repository: str, tag: str) -> str:
    return f"{_api_base(repository)}/git/ref/tags/{tag}"


def _tag_ref_object_url(repository: str, tag: str) -> str:
    return f"{_api_base(repository)}/git/refs/tags/{tag}"


def _tag_object_url(repository: str, tag_object: str) -> str:
    return f"{_api_base(repository)}/git/tags/{tag_object}"


def _commit_url(repository: str, commit: str) -> str:
    return f"{_api_base(repository)}/git/commits/{commit}"


def _main_ref_url(repository: str) -> str:
    return f"{_api_base(repository)}/git/ref/heads/main"


def _main_ref_object_url(repository: str) -> str:
    return f"{_api_base(repository)}/git/refs/heads/main"


def _workflow_runs_url(repository: str, workflow: _WorkflowContract, tag: str) -> str:
    query = urllib.parse.urlencode(
        (
            ("event", "push"),
            ("branch", tag),
            ("per_page", str(PAGE_SIZE)),
        )
    )
    return f"{_api_base(repository)}/actions/workflows/{workflow.filename}/runs?{query}"


def _jobs_url(repository: str, run_id: int) -> str:
    query = urllib.parse.urlencode((("filter", "latest"), ("per_page", str(PAGE_SIZE))))
    return f"{_api_base(repository)}/actions/runs/{run_id}/jobs?{query}"


def _exact_api_url(value: Any, expected: str, label: str) -> str:
    candidate = _string(value, label)
    _validate_api_url(candidate)
    if candidate != expected:
        raise TagCIAdmissionError(f"{label} does not match the expected GitHub API URL")
    return candidate


def _validate_api_url(url: str) -> None:
    if not isinstance(url, str):
        raise TagCIAdmissionError("GitHub API URL must be a string")
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise TagCIAdmissionError("GitHub API URL is malformed") from error
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.github.com"
        or parsed.hostname != "api.github.com"
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not parsed.path.startswith("/repos/")
    ):
        raise TagCIAdmissionError("only direct HTTPS URLs on api.github.com are allowed")


def _exact_web_url(value: Any, expected: str, label: str) -> str:
    candidate = _string(value, label)
    try:
        parsed = urllib.parse.urlsplit(candidate)
        port = parsed.port
    except ValueError as error:
        raise TagCIAdmissionError(f"{label} is malformed") from error
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.hostname != "github.com"
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or candidate != expected
    ):
        raise TagCIAdmissionError(f"{label} does not match the expected GitHub run URL")
    return candidate


def _validate_repository_object(value: Any, repository: str, label: str) -> None:
    document = _mapping(value, label)
    _exact(document.get("full_name"), repository, f"{label} full_name")
    _exact(document.get("private"), False, f"{label} private")
    if "visibility" in document:
        _exact(document.get("visibility"), "public", f"{label} visibility")


def _validate_github_signature(value: Any, label: str) -> None:
    verification = _mapping(value, f"{label} verification")
    _exact(verification.get("verified"), True, f"{label} verified")
    _exact(verification.get("reason"), "valid", f"{label} verification reason")
    _string(verification.get("signature"), f"{label} signature")
    _string(verification.get("payload"), f"{label} signed payload")


def _validate_tag_ref(
    document: Mapping[str, Any], repository: str, tag: str
) -> str:
    _exact(document.get("ref"), f"refs/tags/{tag}", "tag ref")
    _exact_api_url(
        document.get("url"), _tag_ref_object_url(repository, tag), "tag ref URL"
    )
    target = _mapping(document.get("object"), "tag ref object")
    _exact(target.get("type"), "tag", "tag ref object type")
    tag_object = _sha1(target.get("sha"), "annotated tag object")
    _exact_api_url(
        target.get("url"),
        _tag_object_url(repository, tag_object),
        "annotated tag object URL",
    )
    return tag_object


def _validate_tag_object(
    document: Mapping[str, Any],
    repository: str,
    tag: str,
    tag_object: str,
    expected_commit: str,
) -> None:
    _exact(_sha1(document.get("sha"), "tag object SHA"), tag_object, "tag object SHA")
    _exact(document.get("tag"), tag, "annotated tag name")
    _exact_api_url(
        document.get("url"),
        _tag_object_url(repository, tag_object),
        "tag object URL",
    )
    target = _mapping(document.get("object"), "annotated tag target")
    _exact(target.get("type"), "commit", "annotated tag target type")
    _exact(_sha1(target.get("sha"), "annotated tag target SHA"), expected_commit, "annotated tag target SHA")
    _exact_api_url(
        target.get("url"),
        _commit_url(repository, expected_commit),
        "annotated tag target URL",
    )
    _validate_github_signature(document.get("verification"), "annotated tag")


def _validate_commit(
    document: Mapping[str, Any], repository: str, expected_commit: str, expected_tree: str
) -> None:
    _exact(_sha1(document.get("sha"), "commit SHA"), expected_commit, "commit SHA")
    _exact_api_url(
        document.get("url"), _commit_url(repository, expected_commit), "commit URL"
    )
    tree = _mapping(document.get("tree"), "commit tree")
    _exact(_sha1(tree.get("sha"), "commit tree SHA"), expected_tree, "commit tree SHA")
    _exact_api_url(
        tree.get("url"),
        f"{_api_base(repository)}/git/trees/{expected_tree}",
        "commit tree URL",
    )
    _validate_github_signature(document.get("verification"), "commit")


def _validate_main_ref(
    document: Mapping[str, Any], repository: str, expected_commit: str
) -> None:
    _exact(document.get("ref"), MAIN_REF, "main ref")
    _exact_api_url(
        document.get("url"), _main_ref_object_url(repository), "main ref URL"
    )
    target = _mapping(document.get("object"), "main ref object")
    _exact(target.get("type"), "commit", "main ref object type")
    _exact(_sha1(target.get("sha"), "main ref SHA"), expected_commit, "main ref SHA")
    _exact_api_url(
        target.get("url"),
        _commit_url(repository, expected_commit),
        "main ref target URL",
    )


def _validate_workflow_run(
    document: Mapping[str, Any],
    workflow: _WorkflowContract,
    repository: str,
    tag: str,
    expected_commit: str,
    expected_tree: str,
) -> dict[str, Any]:
    total_count = _nonnegative_integer(
        document.get("total_count"), f"{workflow.name} run total_count"
    )
    runs = _array(document.get("workflow_runs"), f"{workflow.name} workflow_runs")
    if total_count != len(runs):
        raise TagCIAdmissionError(f"{workflow.name} run response is incomplete or paginated")
    if total_count != 1:
        raise TagCIAdmissionError(f"{workflow.name} must have exactly one matching tag-push run")
    run = _mapping(runs[0], f"{workflow.name} run")
    run_id = _github_identifier(run.get("id"), f"{workflow.name} run id")
    _positive_integer(run.get("run_number"), f"{workflow.name} run number")
    _exact(run.get("run_attempt"), 1, f"{workflow.name} run attempt")
    _exact(run.get("name"), workflow.name, f"{workflow.name} workflow name")
    _exact(run.get("path"), workflow.path, f"{workflow.name} workflow path")
    _exact(run.get("event"), "push", f"{workflow.name} event")
    _exact(run.get("head_branch"), tag, f"{workflow.name} head branch")
    _exact(_sha1(run.get("head_sha"), f"{workflow.name} head SHA"), expected_commit, f"{workflow.name} head SHA")
    _exact(run.get("status"), "completed", f"{workflow.name} status")
    _exact(run.get("conclusion"), "success", f"{workflow.name} conclusion")

    api_url = _exact_api_url(
        run.get("url"),
        f"{_api_base(repository)}/actions/runs/{run_id}",
        f"{workflow.name} run API URL",
    )
    jobs_api_url = _exact_api_url(
        run.get("jobs_url"),
        f"{_api_base(repository)}/actions/runs/{run_id}/jobs",
        f"{workflow.name} jobs API URL",
    )
    html_url = _exact_web_url(
        run.get("html_url"),
        f"https://github.com/{repository}/actions/runs/{run_id}",
        f"{workflow.name} run HTML URL",
    )
    _validate_repository_object(run.get("repository"), repository, f"{workflow.name} repository")
    _validate_repository_object(
        run.get("head_repository"), repository, f"{workflow.name} head repository"
    )
    head_commit = _mapping(run.get("head_commit"), f"{workflow.name} head commit")
    _exact(_sha1(head_commit.get("id"), f"{workflow.name} head commit id"), expected_commit, f"{workflow.name} head commit id")
    _exact(_sha1(head_commit.get("tree_id"), f"{workflow.name} head tree id"), expected_tree, f"{workflow.name} head tree id")
    return {
        "api_url": api_url,
        "html_url": html_url,
        "jobs_api_url": jobs_api_url,
        "run_id": run_id,
    }


def _validate_jobs(
    document: Mapping[str, Any],
    workflow: _WorkflowContract,
    repository: str,
    expected_commit: str,
    run: Mapping[str, Any],
) -> list[dict[str, Any]]:
    total_count = _nonnegative_integer(
        document.get("total_count"), f"{workflow.name} job total_count"
    )
    jobs = _array(document.get("jobs"), f"{workflow.name} jobs")
    if total_count != len(jobs):
        raise TagCIAdmissionError(f"{workflow.name} job response is incomplete or paginated")
    if total_count != len(workflow.expected_jobs):
        raise TagCIAdmissionError(f"{workflow.name} job count is not exact")

    observed: dict[str, dict[str, Any]] = {}
    run_id = _github_identifier(run.get("run_id"), f"{workflow.name} retained run id")
    for index, value in enumerate(jobs):
        job = _mapping(value, f"{workflow.name} job {index}")
        name = _string(job.get("name"), f"{workflow.name} job name")
        if name in observed:
            raise TagCIAdmissionError(f"{workflow.name} has duplicate job {name!r}")
        if name not in workflow.expected_jobs:
            raise TagCIAdmissionError(f"{workflow.name} has unexpected job {name!r}")
        job_id = _github_identifier(job.get("id"), f"{workflow.name} {name} job id")
        _exact(job.get("run_id"), run_id, f"{workflow.name} {name} run id")
        _exact(_sha1(job.get("head_sha"), f"{workflow.name} {name} head SHA"), expected_commit, f"{workflow.name} {name} head SHA")
        _exact(job.get("status"), "completed", f"{workflow.name} {name} status")
        _exact(job.get("conclusion"), "success", f"{workflow.name} {name} conclusion")
        _exact_api_url(
            job.get("url"),
            f"{_api_base(repository)}/actions/jobs/{job_id}",
            f"{workflow.name} {name} job API URL",
        )
        _exact_api_url(
            job.get("run_url"),
            f"{_api_base(repository)}/actions/runs/{run_id}",
            f"{workflow.name} {name} run API URL",
        )
        _exact_web_url(
            job.get("html_url"),
            f"https://github.com/{repository}/actions/runs/{run_id}/job/{job_id}",
            f"{workflow.name} {name} job HTML URL",
        )
        if "workflow_name" in job:
            _exact(job.get("workflow_name"), workflow.name, f"{workflow.name} job workflow name")

        steps = _array(job.get("steps"), f"{workflow.name} {name} steps")
        if not steps:
            raise TagCIAdmissionError(f"{workflow.name} {name} has no reported steps")
        step_numbers: set[int] = set()
        step_names: list[str] = []
        for step_index, step_value in enumerate(steps):
            step = _mapping(step_value, f"{workflow.name} {name} step {step_index}")
            step_names.append(
                _string(step.get("name"), f"{workflow.name} {name} step name")
            )
            number = _positive_integer(
                step.get("number"), f"{workflow.name} {name} step number"
            )
            if number in step_numbers:
                raise TagCIAdmissionError(f"{workflow.name} {name} has duplicate step numbers")
            step_numbers.add(number)
            _exact(step.get("status"), "completed", f"{workflow.name} {name} step status")
            _exact(step.get("conclusion"), "success", f"{workflow.name} {name} step conclusion")
        if step_names.count(TAG_REF_ASSERTION_STEP) != 1:
            raise TagCIAdmissionError(
                f"{workflow.name} {name} must contain exactly one successful tag-ref assertion step"
            )

        observed[name] = {
            "job_id": job_id,
            "name": name,
            "step_count": len(steps),
            "tag_ref_assertion": "PASS",
            "status": "completed",
            "conclusion": "success",
        }

    if frozenset(observed) != workflow.expected_jobs:
        raise TagCIAdmissionError(f"{workflow.name} job set is not exact")
    return [observed[name] for name in sorted(observed, key=lambda item: item.encode("ascii"))]


def _response_descriptor(role: str, url: str, raw: bytes) -> dict[str, Any]:
    return {
        "role": role,
        "url": url,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def canonical_receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    """Return the deterministic UTF-8 representation used for persistence."""

    if not isinstance(receipt, dict):
        raise TagCIAdmissionError("receipt must be a JSON object")
    try:
        encoded = json.dumps(
            receipt,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError) as error:
        raise TagCIAdmissionError("receipt is not canonical-JSON compatible") from error
    return encoded + b"\n"


def validate_saved_tag_ci(
    responses: Mapping[str, bytes],
    *,
    repository: str = DEFAULT_REPOSITORY,
    expected_tag: str,
    expected_commit: str,
    expected_tree: str,
) -> dict[str, Any]:
    """Validate saved GitHub response bytes without making a network request.

    The mapping must contain exactly eight roles: tag ref, annotated tag object,
    commit object, main ref, and run/job responses for both required workflows.
    Exact raw bytes are SHA-256-bound into the returned receipt.
    """

    _validate_inputs(repository, expected_tag, expected_commit, expected_tree)
    if not isinstance(responses, Mapping):
        raise TagCIAdmissionError("responses must be a mapping")
    if set(responses) != set(_ALL_RESPONSE_ROLES):
        raise TagCIAdmissionError("saved GitHub response roles are not exact")
    snapshot: dict[str, bytes] = {}
    for role in _ALL_RESPONSE_ROLES:
        raw = responses[role]
        if type(raw) is not bytes:
            raise TagCIAdmissionError(f"{role} response must be immutable bytes")
        snapshot[role] = memoryview(raw).tobytes()

    documents = {role: _decode_json(snapshot[role], role) for role in _ALL_RESPONSE_ROLES}
    tag_object = _validate_tag_ref(documents["tag_ref"], repository, expected_tag)
    _validate_tag_object(
        documents["tag_object"],
        repository,
        expected_tag,
        tag_object,
        expected_commit,
    )
    _validate_commit(documents["commit"], repository, expected_commit, expected_tree)
    _validate_main_ref(documents["main_ref"], repository, expected_commit)

    workflow_receipts: list[dict[str, Any]] = []
    run_details: dict[str, Mapping[str, Any]] = {}
    for workflow in _WORKFLOWS:
        run = _validate_workflow_run(
            documents[workflow.role],
            workflow,
            repository,
            expected_tag,
            expected_commit,
            expected_tree,
        )
        run_details[workflow.role] = run
        jobs = _validate_jobs(
            documents[workflow.jobs_role],
            workflow,
            repository,
            expected_commit,
            run,
        )
        workflow_receipts.append(
            {
                "workflow_name": workflow.name,
                "workflow_path": workflow.path,
                "run_id": run["run_id"],
                "run_attempt": 1,
                "event": "push",
                "head_branch": expected_tag,
                "head_sha": expected_commit,
                "status": "completed",
                "conclusion": "success",
                "api_url": run["api_url"],
                "html_url": run["html_url"],
                "jobs": jobs,
            }
        )

    response_urls = {
        "tag_ref": _tag_ref_url(repository, expected_tag),
        "tag_object": _tag_object_url(repository, tag_object),
        "commit": _commit_url(repository, expected_commit),
        "main_ref": _main_ref_url(repository),
    }
    for workflow in _WORKFLOWS:
        response_urls[workflow.role] = _workflow_runs_url(repository, workflow, expected_tag)
        response_urls[workflow.jobs_role] = _jobs_url(
            repository, _github_identifier(run_details[workflow.role]["run_id"], "run id")
        )

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "artifact_kind": "corelm_portfolio_tag_ci_admission_receipt",
        "status": "PASS",
        "admission_boundary": "PUBLIC_ANNOTATED_TAG_AND_FIRST_ATTEMPT_TAG_PUSH_CI",
        "automation_only": True,
        "human_reviewed": False,
        "source": {
            "repository": repository,
            "tag": expected_tag,
            "tag_ref": f"refs/tags/{expected_tag}",
            "annotated_tag_object": tag_object,
            "commit": expected_commit,
            "tree": expected_tree,
            "main_ref": MAIN_REF,
            "tag_github_verification": "VERIFIED_VALID",
            "commit_github_verification": "VERIFIED_VALID",
        },
        "network_contract": {
            "api_origin": API_ORIGIN,
            "authentication_sent_by_fetcher": False,
            "redirects": "FORBIDDEN",
            "response_limit_bytes": MAX_RESPONSE_BYTES,
            "timeout_max_seconds": MAX_TIMEOUT_SECONDS,
            "offline_validation": True,
        },
        "responses": [
            _response_descriptor(role, response_urls[role], snapshot[role])
            for role in _ALL_RESPONSE_ROLES
        ],
        "workflows": workflow_receipts,
    }
    canonical_receipt_bytes(receipt)
    return receipt


def _read_open_descriptor(
    descriptor: int, label: str, *, limit: int
) -> bytes:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_size <= 0 or before.st_size > limit:
        raise TagCIAdmissionError(f"{label} is not a bounded non-empty regular file")
    chunks: list[bytes] = []
    remaining = limit + 1
    while remaining:
        chunk = os.read(descriptor, min(remaining, 16 * 1024))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    after = os.fstat(descriptor)
    if len(raw) > limit:
        raise TagCIAdmissionError(f"{label} exceeds the byte limit")
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after or len(raw) != before.st_size:
        raise TagCIAdmissionError(f"{label} changed while it was read")
    return raw


def _read_small_regular(path: Path, label: str, *, limit: int = 64 * 1024) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise TagCIAdmissionError(f"{label} is not an accessible regular file") from error
    try:
        return _read_open_descriptor(descriptor, label, limit=limit)
    finally:
        os.close(descriptor)


def _read_named_regular(
    directory_descriptor: int, name: str, label: str, *, limit: int
) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    except OSError as error:
        raise TagCIAdmissionError(f"{label} is not an accessible regular file") from error
    try:
        return _read_open_descriptor(descriptor, label, limit=limit)
    finally:
        os.close(descriptor)


def _write_private_snapshot(directory: Path, name: str, raw: bytes) -> Path:
    destination = directory / name
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise TagCIAdmissionError("could not write pinned trust snapshot")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return destination


def _command_environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_COUNT": "0",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
    }


def _run_local_command(arguments: tuple[str, ...], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    if not arguments or arguments[0] not in {GIT, SSH_KEYGEN}:
        raise TagCIAdmissionError("local trust command is not allowlisted")
    try:
        completed = subprocess.run(
            arguments,
            cwd=cwd,
            env=_command_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise TagCIAdmissionError("pinned local trust command failed to execute") from error
    if len(completed.stdout) > 64 * 1024 or len(completed.stderr) > 64 * 1024:
        raise TagCIAdmissionError("pinned local trust command output exceeds the limit")
    return completed


def _git_read(repository: Path, *arguments: str) -> bytes:
    command = (
        GIT,
        "-C",
        str(repository),
        "--no-replace-objects",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        *arguments,
    )
    completed = _run_local_command(command, cwd=repository)
    if completed.returncode != 0 or completed.stderr:
        raise TagCIAdmissionError("read-only local Git identity command failed")
    return completed.stdout


def _single_ascii_line(raw: bytes, label: str) -> str:
    try:
        text = raw.decode("ascii", errors="strict")
    except UnicodeDecodeError as error:
        raise TagCIAdmissionError(f"{label} is not ASCII") from error
    lines = text.splitlines()
    if len(lines) != 1 or not lines[0] or text != lines[0] + "\n":
        raise TagCIAdmissionError(f"{label} is not exactly one LF-terminated line")
    return lines[0]


def _validate_pinned_trust_bytes(public_key: bytes, allowed_signers: bytes) -> None:
    if hashlib.sha256(public_key).hexdigest() != EXPECTED_PUBLIC_KEY_SHA256:
        raise TagCIAdmissionError("signing public key does not match the hard pin")
    if hashlib.sha256(allowed_signers).hexdigest() != EXPECTED_ALLOWED_SIGNERS_SHA256:
        raise TagCIAdmissionError("allowed_signers does not match the hard pin")
    public_fields = _single_ascii_line(public_key, "signing public key").split()
    signer_fields = _single_ascii_line(allowed_signers, "allowed_signers").split()
    if len(public_fields) < 2 or len(signer_fields) != 3:
        raise TagCIAdmissionError("pinned SSH trust material has malformed fields")
    if signer_fields[0] != EXPECTED_SIGNING_PRINCIPAL:
        raise TagCIAdmissionError("allowed_signers principal does not match the hard pin")
    if signer_fields[1:] != public_fields[:2]:
        raise TagCIAdmissionError("allowed_signers public key does not match the pinned key")


def verify_local_tag_trust(
    repository: str | os.PathLike[str],
    *,
    expected_tag: str,
    expected_tag_object: str,
    expected_commit: str,
    expected_tree: str,
) -> dict[str, Any]:
    """Bind the local annotated tag to the public object and pinned SSH trust.

    ``expected_tag_object`` must come from a successful public API admission
    receipt.  Mutable checkout trust files are only read to prove byte equality;
    Git and ``ssh-keygen`` operate on owner-only temporary snapshots of the
    hard-pinned bytes.
    """

    _validate_inputs(DEFAULT_REPOSITORY, expected_tag, expected_commit, expected_tree)
    _sha1(expected_tag_object, "expected annotated tag object")
    root = Path(repository)
    try:
        root_lstat = root.lstat()
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise TagCIAdmissionError("local repository is not accessible") from error
    if not stat.S_ISDIR(root_lstat.st_mode) or root.is_symlink() or not resolved.is_dir():
        raise TagCIAdmissionError("local repository must be a real directory, not a symlink")

    public_key_path = resolved / "signing" / "corelm-codec-signing.pub"
    allowed_signers_path = resolved / "signing" / "allowed_signers"
    public_key = _read_small_regular(public_key_path, "signing public key")
    allowed_signers = _read_small_regular(allowed_signers_path, "allowed_signers")
    _validate_pinned_trust_bytes(public_key, allowed_signers)

    replace_refs = _git_read(
        resolved, "for-each-ref", "--format=%(refname)", "refs/replace"
    )
    if replace_refs:
        raise TagCIAdmissionError("Git replacement refs are forbidden")
    git_directory_raw = _git_read(resolved, "rev-parse", "--absolute-git-dir")
    git_directory = Path(_single_ascii_line(git_directory_raw, "absolute Git directory"))
    if not git_directory.is_absolute() or (git_directory / "info" / "grafts").exists():
        raise TagCIAdmissionError("Git grafts or a relative Git directory are forbidden")

    reference = f"refs/tags/{expected_tag}"
    observed_tag_object = _single_ascii_line(
        _git_read(resolved, "rev-parse", "--verify", reference), "local tag object"
    )
    _exact(_sha1(observed_tag_object, "local tag object"), expected_tag_object, "local tag object")
    _exact(
        _single_ascii_line(_git_read(resolved, "cat-file", "-t", reference), "local tag type"),
        "tag",
        "local tag type",
    )
    observed_commit = _single_ascii_line(
        _git_read(resolved, "rev-parse", "--verify", f"{reference}^{{commit}}"),
        "local tag commit",
    )
    observed_tree = _single_ascii_line(
        _git_read(resolved, "rev-parse", "--verify", f"{reference}^{{tree}}"),
        "local tag tree",
    )
    _exact(_sha1(observed_commit, "local tag commit"), expected_commit, "local tag commit")
    _exact(_sha1(observed_tree, "local tag tree"), expected_tree, "local tag tree")

    with tempfile.TemporaryDirectory(prefix="corelm-pinned-tag-trust-") as temporary:
        trust_directory = Path(temporary)
        os.chmod(trust_directory, 0o700)
        key_snapshot = _write_private_snapshot(trust_directory, "signing.pub", public_key)
        policy_snapshot = _write_private_snapshot(
            trust_directory, "allowed_signers", allowed_signers
        )
        fingerprint = _run_local_command(
            (SSH_KEYGEN, "-E", "sha256", "-lf", str(key_snapshot)),
            cwd=trust_directory,
        )
        fingerprint_output = fingerprint.stdout + fingerprint.stderr
        try:
            fingerprint_text = fingerprint_output.decode("ascii", errors="strict")
        except UnicodeDecodeError as error:
            raise TagCIAdmissionError("pinned public-key fingerprint is not ASCII") from error
        if (
            fingerprint.returncode != 0
            or fingerprint.stderr
            or EXPECTED_FINGERPRINT not in fingerprint_text.split()
            or not fingerprint_text.startswith("256 ")
            or not fingerprint_text.rstrip("\n").endswith(" (ED25519)")
        ):
            raise TagCIAdmissionError("public-key fingerprint does not match the hard pin")

        verification = _run_local_command(
            (
                GIT,
                "-C",
                str(resolved),
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "-c",
                "gpg.format=ssh",
                "-c",
                f"gpg.ssh.program={SSH_KEYGEN}",
                "-c",
                f"gpg.ssh.allowedSignersFile={policy_snapshot}",
                "verify-tag",
                "--raw",
                expected_tag,
            ),
            cwd=resolved,
        )
        expected_verification = (
            f'Good "git" signature for {EXPECTED_SIGNING_PRINCIPAL} with ED25519 key '
            f"{EXPECTED_FINGERPRINT}\n"
        ).encode("ascii")
        if (
            verification.returncode != 0
            or verification.stdout
            or verification.stderr != expected_verification
        ):
            raise TagCIAdmissionError("local annotated tag SSH signature is invalid")

    if (
        _read_small_regular(public_key_path, "signing public key") != public_key
        or _read_small_regular(allowed_signers_path, "allowed_signers") != allowed_signers
    ):
        raise TagCIAdmissionError("local signing trust changed during verification")
    final_tag_object = _single_ascii_line(
        _git_read(resolved, "rev-parse", "--verify", reference), "final local tag object"
    )
    if final_tag_object != expected_tag_object:
        raise TagCIAdmissionError("local tag object changed during verification")

    receipt = {
        "schema_version": 1,
        "artifact_kind": "corelm_portfolio_local_tag_trust_receipt",
        "status": "PASS",
        "tag": expected_tag,
        "tag_object": expected_tag_object,
        "commit": expected_commit,
        "tree": expected_tree,
        "principal": EXPECTED_SIGNING_PRINCIPAL,
        "fingerprint": EXPECTED_FINGERPRINT,
        "public_key_sha256": EXPECTED_PUBLIC_KEY_SHA256,
        "allowed_signers_sha256": EXPECTED_ALLOWED_SIGNERS_SHA256,
        "git_binary": GIT,
        "ssh_keygen_binary": SSH_KEYGEN,
        "verification": "PINNED_SSH_GIT_NAMESPACE_PASS",
    }
    canonical_receipt_bytes(receipt)
    return receipt


def _receipt_source_identity(receipt: Mapping[str, Any]) -> tuple[str, str, str, str]:
    source = _mapping(receipt.get("source"), "tag-CI receipt source")
    repository = _string(source.get("repository"), "tag-CI receipt repository")
    tag = _string(source.get("tag"), "tag-CI receipt tag")
    commit = _sha1(source.get("commit"), "tag-CI receipt commit")
    tree = _sha1(source.get("tree"), "tag-CI receipt tree")
    _validate_inputs(repository, tag, commit, tree)
    return repository, tag, commit, tree


def write_response_bundle(
    directory: str | os.PathLike[str],
    responses: Mapping[str, bytes],
    receipt: Mapping[str, Any],
) -> Path:
    """Create one owner-only directory containing the exact saved-response set.

    The destination must not exist.  Each response is written under its fixed
    filename with ``O_EXCL`` mode 0600, followed by the recomputed canonical
    receipt.  On failure the newly-created incomplete directory is removed.
    """

    repository, tag, commit, tree = _receipt_source_identity(receipt)
    if not isinstance(responses, Mapping) or set(responses) != set(RESPONSE_ROLES):
        raise TagCIAdmissionError("saved GitHub response roles are not exact")
    snapshot: dict[str, bytes] = {}
    for role in RESPONSE_ROLES:
        raw = responses[role]
        if type(raw) is not bytes:
            raise TagCIAdmissionError(f"{role} response must be immutable bytes")
        snapshot[role] = memoryview(raw).tobytes()
    recomputed = validate_saved_tag_ci(
        snapshot,
        repository=repository,
        expected_tag=tag,
        expected_commit=commit,
        expected_tree=tree,
    )
    if canonical_receipt_bytes(receipt) != canonical_receipt_bytes(recomputed):
        raise TagCIAdmissionError("caller-supplied tag-CI receipt is not the recomputed receipt")

    requested = Path(directory)
    if requested.name in {"", ".", ".."}:
        raise TagCIAdmissionError("response bundle directory must have an exact final name")
    try:
        parent = requested.parent.resolve(strict=True)
        parent_status = parent.lstat()
    except OSError as error:
        raise TagCIAdmissionError("response bundle parent is not accessible") from error
    if not stat.S_ISDIR(parent_status.st_mode) or parent.is_symlink():
        raise TagCIAdmissionError("response bundle parent must be a real directory")
    target = parent / requested.name
    try:
        os.mkdir(target, 0o700)
        os.chmod(target, 0o700)
    except OSError as error:
        raise TagCIAdmissionError("response bundle destination must not already exist") from error

    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    directory_descriptor = -1
    created_names: list[str] = []
    try:
        directory_descriptor = os.open(target, directory_flags)
        for role in RESPONSE_ROLES:
            filename = RESPONSE_FILENAMES[role]
            descriptor = os.open(
                filename,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_descriptor,
            )
            created_names.append(filename)
            try:
                os.fchmod(descriptor, 0o600)
                view = memoryview(snapshot[role])
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise TagCIAdmissionError("could not write tag-CI response bundle")
                    view = view[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        receipt_bytes = canonical_receipt_bytes(recomputed)
        receipt_descriptor = os.open(
            PUBLIC_RECEIPT_FILENAME,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=directory_descriptor,
        )
        created_names.append(PUBLIC_RECEIPT_FILENAME)
        try:
            os.fchmod(receipt_descriptor, 0o600)
            view = memoryview(receipt_bytes)
            while view:
                written = os.write(receipt_descriptor, view)
                if written <= 0:
                    raise TagCIAdmissionError("could not write canonical tag-CI receipt")
                view = view[written:]
            os.fsync(receipt_descriptor)
        finally:
            os.close(receipt_descriptor)
        os.fsync(directory_descriptor)
    except (OSError, TagCIAdmissionError) as error:
        if directory_descriptor >= 0:
            for name in reversed(created_names):
                try:
                    os.unlink(name, dir_fd=directory_descriptor)
                except OSError:
                    pass
        if directory_descriptor >= 0:
            os.close(directory_descriptor)
            directory_descriptor = -1
        try:
            os.rmdir(target)
        except OSError:
            pass
        if isinstance(error, TagCIAdmissionError):
            raise
        raise TagCIAdmissionError("could not create the tag-CI response bundle") from error
    finally:
        if directory_descriptor >= 0:
            os.close(directory_descriptor)
    return target


def _directory_identity(status: os.stat_result) -> tuple[int, ...]:
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def read_response_bundle(
    directory: str | os.PathLike[str],
    *,
    repository: str = DEFAULT_REPOSITORY,
    expected_tag: str,
    expected_commit: str,
    expected_tree: str,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Read an exact nofollow bundle and independently recompute its receipt."""

    _validate_inputs(repository, expected_tag, expected_commit, expected_tree)
    path = Path(directory)
    try:
        path_status = path.lstat()
    except OSError as error:
        raise TagCIAdmissionError("response bundle directory is not accessible") from error
    if not stat.S_ISDIR(path_status.st_mode) or path.is_symlink():
        raise TagCIAdmissionError("response bundle must be a real directory, not a symlink")
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, directory_flags)
    except OSError as error:
        raise TagCIAdmissionError("response bundle directory cannot be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if _directory_identity(path_status) != _directory_identity(before):
            raise TagCIAdmissionError("response bundle directory was replaced before reading")
        expected_names = set(RESPONSE_FILENAMES.values()) | {PUBLIC_RECEIPT_FILENAME}
        first_names = set(os.listdir(descriptor))
        if first_names != expected_names:
            raise TagCIAdmissionError("response bundle file set is not exact")
        responses = {
            role: _read_named_regular(
                descriptor,
                RESPONSE_FILENAMES[role],
                f"saved {role} response",
                limit=MAX_RESPONSE_BYTES,
            )
            for role in RESPONSE_ROLES
        }
        receipt_raw = _read_named_regular(
            descriptor,
            PUBLIC_RECEIPT_FILENAME,
            "saved tag-CI receipt",
            limit=MAX_RESPONSE_BYTES,
        )
        second_names = set(os.listdir(descriptor))
        after = os.fstat(descriptor)
    except OSError as error:
        raise TagCIAdmissionError("response bundle changed or could not be read") from error
    finally:
        os.close(descriptor)
    if first_names != second_names or _directory_identity(before) != _directory_identity(after):
        raise TagCIAdmissionError("response bundle changed while it was read")

    recomputed = validate_saved_tag_ci(
        responses,
        repository=repository,
        expected_tag=expected_tag,
        expected_commit=expected_commit,
        expected_tree=expected_tree,
    )
    saved_receipt = _decode_json(receipt_raw, "saved tag-CI receipt")
    if receipt_raw != canonical_receipt_bytes(saved_receipt):
        raise TagCIAdmissionError("saved tag-CI receipt is not canonical JSON")
    if receipt_raw != canonical_receipt_bytes(recomputed):
        raise TagCIAdmissionError("saved tag-CI receipt does not match recomputed API semantics")
    return responses, recomputed


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        raise TagCIAdmissionError("GitHub API redirects are forbidden")


def _build_https_opener() -> urllib.request.OpenerDirector:
    context = ssl.create_default_context()
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _RejectRedirects(),
        urllib.request.HTTPSHandler(context=context),
    )


def _validated_timeout(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TagCIAdmissionError("timeout must be a finite number")
    timeout = float(value)
    if (
        not math.isfinite(timeout)
        or timeout < MIN_TIMEOUT_SECONDS
        or timeout > MAX_TIMEOUT_SECONDS
    ):
        raise TagCIAdmissionError(
            f"timeout must be between {MIN_TIMEOUT_SECONDS:g} and {MAX_TIMEOUT_SECONDS:g} seconds"
        )
    return timeout


def _fetch_public_json(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    timeout_seconds: float,
    label: str,
) -> bytes:
    _validate_api_url(url)
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "corelm-portfolio-tag-ci-admission/1",
            "X-GitHub-Api-Version": API_VERSION,
        },
    )
    if request.has_header("Authorization"):
        raise TagCIAdmissionError("authenticated GitHub requests are forbidden")
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", response.getcode())
            if status != 200:
                raise TagCIAdmissionError(f"{label} GitHub API status must be 200")
            if response.geturl() != url:
                raise TagCIAdmissionError(f"{label} GitHub API response was redirected")
            content_type = response.headers.get("Content-Type", "")
            media_type = content_type.split(";", 1)[0].strip().lower()
            if media_type not in {"application/json", "application/vnd.github+json"}:
                raise TagCIAdmissionError(f"{label} GitHub API response is not JSON")
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                if re.fullmatch(r"[0-9]+", content_length) is None:
                    raise TagCIAdmissionError(
                        f"{label} GitHub API Content-Length is malformed"
                    )
                try:
                    declared_length = int(content_length, 10)
                except ValueError as error:
                    raise TagCIAdmissionError(
                        f"{label} GitHub API Content-Length is malformed"
                    ) from error
                if declared_length < 0 or declared_length > MAX_RESPONSE_BYTES:
                    raise TagCIAdmissionError(
                        f"{label} GitHub API response exceeds the byte limit"
                    )
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except TagCIAdmissionError:
        raise
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
        raise TagCIAdmissionError(f"public GitHub request failed for {label}") from error
    if len(raw) > MAX_RESPONSE_BYTES:
        raise TagCIAdmissionError(f"{label} GitHub API response exceeds the byte limit")
    _decode_json(raw, label)
    return raw


def fetch_public_tag_ci_responses(
    *,
    repository: str = DEFAULT_REPOSITORY,
    expected_tag: str,
    expected_commit: str,
    expected_tree: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, bytes]:
    """Fetch and validate the exact public tag-CI response set.

    Acquisition is direct, anonymous HTTPS to ``api.github.com``.  Environment
    proxies and redirects are disabled; responses and request timeouts are
    bounded.  The returned bytes have already passed :func:`validate_saved_tag_ci`.
    """

    _validate_inputs(repository, expected_tag, expected_commit, expected_tree)
    timeout = _validated_timeout(timeout_seconds)
    opener = _build_https_opener()

    def fetch(url: str, label: str) -> bytes:
        return _fetch_public_json(
            opener, url, timeout_seconds=timeout, label=label
        )

    responses: dict[str, bytes] = {}
    responses["tag_ref"] = fetch(
        _tag_ref_url(repository, expected_tag), "tag ref"
    )
    tag_ref = _decode_json(responses["tag_ref"], "tag_ref")
    tag_object = _validate_tag_ref(tag_ref, repository, expected_tag)

    responses["tag_object"] = fetch(
        _tag_object_url(repository, tag_object), "annotated tag object"
    )
    _validate_tag_object(
        _decode_json(responses["tag_object"], "tag_object"),
        repository,
        expected_tag,
        tag_object,
        expected_commit,
    )
    responses["commit"] = fetch(
        _commit_url(repository, expected_commit), "commit object"
    )
    _validate_commit(
        _decode_json(responses["commit"], "commit"),
        repository,
        expected_commit,
        expected_tree,
    )
    responses["main_ref"] = fetch(_main_ref_url(repository), "main ref")
    _validate_main_ref(
        _decode_json(responses["main_ref"], "main_ref"),
        repository,
        expected_commit,
    )

    run_details: dict[str, Mapping[str, Any]] = {}
    for workflow in _WORKFLOWS:
        responses[workflow.role] = fetch(
            _workflow_runs_url(repository, workflow, expected_tag),
            f"{workflow.name} runs",
        )
        run = _validate_workflow_run(
            _decode_json(responses[workflow.role], workflow.role),
            workflow,
            repository,
            expected_tag,
            expected_commit,
            expected_tree,
        )
        run_details[workflow.role] = run

    for workflow in _WORKFLOWS:
        run_id = _github_identifier(
            run_details[workflow.role]["run_id"], f"{workflow.name} run id"
        )
        responses[workflow.jobs_role] = fetch(
            _jobs_url(repository, run_id), f"{workflow.name} jobs"
        )

    validate_saved_tag_ci(
        responses,
        repository=repository,
        expected_tag=expected_tag,
        expected_commit=expected_commit,
        expected_tree=expected_tree,
    )
    return responses


def _add_public_identity_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tree", required=True)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify exact public first-attempt tag-push CI admission."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser(
        "fetch", help="fetch anonymously, validate, and save the canonical response bundle"
    )
    _add_public_identity_arguments(fetch)
    fetch.add_argument("--output-directory", required=True)
    fetch.add_argument(
        "--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS
    )

    saved = commands.add_parser(
        "verify-saved", help="offline-verify one exact saved-response directory"
    )
    _add_public_identity_arguments(saved)
    saved.add_argument("--response-directory", required=True)

    local = commands.add_parser(
        "verify-local", help="verify the local annotated tag with hard-pinned SSH trust"
    )
    local.add_argument("--repository-path", required=True)
    local.add_argument("--tag", required=True)
    local.add_argument("--tag-object", required=True)
    local.add_argument("--commit", required=True)
    local.add_argument("--tree", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    try:
        if arguments.command == "fetch":
            responses = fetch_public_tag_ci_responses(
                repository=arguments.repository,
                expected_tag=arguments.tag,
                expected_commit=arguments.commit,
                expected_tree=arguments.tree,
                timeout_seconds=arguments.timeout_seconds,
            )
            receipt = validate_saved_tag_ci(
                responses,
                repository=arguments.repository,
                expected_tag=arguments.tag,
                expected_commit=arguments.commit,
                expected_tree=arguments.tree,
            )
            write_response_bundle(arguments.output_directory, responses, receipt)
        elif arguments.command == "verify-saved":
            _responses, receipt = read_response_bundle(
                arguments.response_directory,
                repository=arguments.repository,
                expected_tag=arguments.tag,
                expected_commit=arguments.commit,
                expected_tree=arguments.tree,
            )
        elif arguments.command == "verify-local":
            receipt = verify_local_tag_trust(
                arguments.repository_path,
                expected_tag=arguments.tag,
                expected_tag_object=arguments.tag_object,
                expected_commit=arguments.commit,
                expected_tree=arguments.tree,
            )
        else:  # pragma: no cover - argparse enforces the closed command set.
            raise TagCIAdmissionError("unknown admission command")
    except TagCIAdmissionError as error:
        print(f"PORTFOLIO TAG CI ADMISSION FAIL: {error}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(canonical_receipt_bytes(receipt))
    sys.stdout.buffer.flush()
    return 0


__all__ = [
    "API_ORIGIN",
    "DEFAULT_REPOSITORY",
    "EXPECTED_ALLOWED_SIGNERS_SHA256",
    "EXPECTED_FINGERPRINT",
    "EXPECTED_PUBLIC_KEY_SHA256",
    "EXPECTED_SIGNING_PRINCIPAL",
    "MAX_GITHUB_ID",
    "MAX_RESPONSE_BYTES",
    "LOCAL_TRUST_RECEIPT_FILENAME",
    "PUBLIC_RECEIPT_FILENAME",
    "RESPONSE_FILENAMES",
    "RESPONSE_ROLES",
    "CURRENT_PORTFOLIO_TAG",
    "TAG_REF_ASSERTION_STEP",
    "TagCIAdmissionError",
    "canonical_receipt_bytes",
    "fetch_public_tag_ci_responses",
    "main",
    "read_response_bundle",
    "validate_saved_tag_ci",
    "verify_local_tag_trust",
    "write_response_bundle",
]


if __name__ == "__main__":
    raise SystemExit(main())
