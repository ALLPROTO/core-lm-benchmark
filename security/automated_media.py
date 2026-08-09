#!/usr/bin/env python3
"""Strict contract for automation-only portfolio presentation media.

The report validated here is an author-side capture receipt.  It binds exact
bytes and a fixed, single-window capture pipeline to one retained proof.  It
does not turn pixels into metric evidence, prove semantic pixel privacy, or
constitute independent replication.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 1
REPORT_KIND = "corelm_automated_portfolio_media_v1"
VERDICT = "AUTOMATED_CAPTURE_INTEGRITY_PASS"
AUTOMATION_CONTRACT = "corelm-automated-presentation-v1"
MEDIA_CLASSIFICATION = "AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE"
CAPTURE_MODE = "MACOS_SINGLE_WINDOW_ID_V1"
BUNDLE_IDENTIFIER = "com.corelm.benchmark"
WORKLOAD_CLASSIFICATION = "AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION"
REPLAY_VERDICT = "AUTHOR_RECORDED_HEAVY_REPLAY_INTEGRITY_PASS"
POSTER_TIMESTAMP_SECONDS = 15.0
LIVE_SEGMENT_SECONDS = 12.0
RESULT_SEGMENT_SECONDS = 18.0
PREFLIGHT_SEGMENT_SECONDS = 1.0
OUTPUT_WIDTH = 1280
OUTPUT_HEIGHT = 720
OUTPUT_FRAME_RATE = 30
OUTPUT_DURATION_SECONDS = LIVE_SEGMENT_SECONDS + RESULT_SEGMENT_SECONDS
OUTPUT_FRAME_COUNT = int(OUTPUT_DURATION_SECONDS * OUTPUT_FRAME_RATE)
MAX_DECODED_FRAME_COUNT = 90 * 240
MAX_REPORT_BYTES = 1024 * 1024
MAX_READINESS_BYTES = 16 * 1024
MAX_ATTEMPT_STATE_BYTES = 256 * 1024
MAX_GITHUB_ID = 2**63 - 1
ATTEMPT_EVENT_COUNT = 9
ATTEMPT_SCOPE = "EXACTLY_ONE_INVOCATION_IN_RETAINED_OWNER_LOCAL_SESSION_ONLY"
ATTEMPT_SUCCESS_EVENTS = (
    "ATTEMPT_STARTED",
    "LIVE_SURFACE_READY",
    "PROOF_INVOKED",
    "LIVE_CAPTURED",
    "PROOF_TERMINAL",
    "REPLAY_VERIFIED",
    "SAME_RUN_REOPENED",
    "RESULT_CAPTURED",
    "MEDIA_SEALED_FOR_COLLECTION",
)

_HEX = frozenset("0123456789abcdef")
_TERMINAL_OUTCOMES = {
    "PASS": "END-TO-END PROOF PASS",
    "FAIL": "END-TO-END PROOF VERIFIED — METRIC FAIL",
}
_FRAME_PTS_FIELDS = frozenset(
    {"best_effort_timestamp_time", "duration_time", "width", "height"}
)
_FRAME_SIDE_DATA_FIELD = "side_data_list"
_FRAME_SEI_SIDE_DATA = [
    {"side_data_type": "H.26[45] User Data Unregistered SEI message"}
]


class AutomatedMediaError(ValueError):
    """A fail-closed automated-presentation contract violation."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AutomatedMediaError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise AutomatedMediaError(f"non-finite JSON number: {value}")


def read_canonical_report(path: Path) -> dict[str, Any]:
    try:
        status = path.lstat()
    except OSError as error:
        raise AutomatedMediaError("automation receipt is unavailable") from error
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_nlink != 1
        or status.st_size <= 0
        or status.st_size > MAX_REPORT_BYTES
        or status.st_mode & 0o022
    ):
        raise AutomatedMediaError("automation receipt is not a bounded regular file")
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise AutomatedMediaError("automation receipt has a forbidden UTF-8 BOM")
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AutomatedMediaError("automation receipt is not strict JSON") from error
    if not isinstance(value, dict) or data != canonical_json_bytes(value):
        raise AutomatedMediaError("automation receipt is not canonical JSON")
    return value


def read_canonical_readiness(path: Path) -> dict[str, Any]:
    try:
        status = path.lstat()
    except OSError as error:
        raise AutomatedMediaError("result readiness receipt is unavailable") from error
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_nlink != 1
        or status.st_size <= 0
        or status.st_size > MAX_READINESS_BYTES
        or stat.S_IMODE(status.st_mode) != 0o600
    ):
        raise AutomatedMediaError(
            "result readiness receipt is not an owner-only bounded regular file"
        )
    data = path.read_bytes()
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AutomatedMediaError("result readiness receipt is not strict JSON") from error
    if not isinstance(value, dict) or data != canonical_json_bytes(value):
        raise AutomatedMediaError("result readiness receipt is not canonical JSON")
    return validate_readiness(value)


def read_canonical_attempt_state(
    path: Path,
    *,
    report: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Read one owner-local successful attempt snapshot without overclaiming history."""

    try:
        status = path.lstat()
    except OSError as error:
        raise AutomatedMediaError("attempt-state snapshot is unavailable") from error
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_nlink != 1
        or status.st_size <= 0
        or status.st_size > MAX_ATTEMPT_STATE_BYTES
        or status.st_uid != os.getuid()
        or stat.S_IMODE(status.st_mode) != 0o600
    ):
        raise AutomatedMediaError(
            "attempt-state snapshot is not an owner-only bounded regular file"
        )
    return validate_attempt_state_bytes(path.read_bytes(), report=report)


def validate_tag_ci_receipt_bytes(
    data: bytes,
    *,
    expected: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the canonical public tag-push CI admission retained by the runner."""

    from security import verify_portfolio_tag_ci as tag_ci

    if type(data) is not bytes or not data or len(data) > MAX_REPORT_BYTES:
        raise AutomatedMediaError("tag-CI receipt bytes are not bounded")
    try:
        value = json.loads(
            data.decode("ascii"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
        canonical = tag_ci.canonical_receipt_bytes(value)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        tag_ci.TagCIAdmissionError,
    ) as error:
        raise AutomatedMediaError("tag-CI receipt is not strict canonical JSON") from error
    if not isinstance(value, dict) or data != canonical:
        raise AutomatedMediaError("tag-CI receipt is not strict canonical JSON")
    receipt = _exact_object(
        value,
        {
            "schema_version",
            "artifact_kind",
            "status",
            "admission_boundary",
            "automation_only",
            "human_reviewed",
            "source",
            "network_contract",
            "responses",
            "workflows",
        },
        "tag-CI receipt",
    )
    if (
        receipt["schema_version"] != 1
        or receipt["artifact_kind"]
        != "corelm_portfolio_tag_ci_admission_receipt"
        or receipt["status"] != "PASS"
        or receipt["admission_boundary"]
        != "PUBLIC_ANNOTATED_TAG_AND_FIRST_ATTEMPT_TAG_PUSH_CI"
        or receipt["automation_only"] is not True
        or receipt["human_reviewed"] is not False
    ):
        raise AutomatedMediaError("tag-CI admission boundary is not exact")
    source = _exact_object(
        receipt["source"],
        {
            "repository",
            "tag",
            "tag_ref",
            "annotated_tag_object",
            "commit",
            "tree",
            "main_ref",
            "tag_github_verification",
            "commit_github_verification",
        },
        "tag-CI source",
    )
    if (
        source["repository"] != tag_ci.DEFAULT_REPOSITORY
        or not isinstance(source["tag"], str)
        or source["tag_ref"] != f"refs/tags/{source['tag']}"
        or source["main_ref"] != tag_ci.MAIN_REF
        or source["tag_github_verification"] != "VERIFIED_VALID"
        or source["commit_github_verification"] != "VERIFIED_VALID"
    ):
        raise AutomatedMediaError("tag-CI source admission is not exact")
    _git_oid(source["annotated_tag_object"], "tag-CI annotated tag object")
    _git_oid(source["commit"], "tag-CI commit")
    _git_oid(source["tree"], "tag-CI tree")
    network = _exact_object(
        receipt["network_contract"],
        {
            "api_origin",
            "authentication_sent_by_fetcher",
            "redirects",
            "response_limit_bytes",
            "timeout_max_seconds",
            "offline_validation",
        },
        "tag-CI network contract",
    )
    if network != {
        "api_origin": tag_ci.API_ORIGIN,
        "authentication_sent_by_fetcher": False,
        "redirects": "FORBIDDEN",
        "response_limit_bytes": tag_ci.MAX_RESPONSE_BYTES,
        "timeout_max_seconds": tag_ci.MAX_TIMEOUT_SECONDS,
        "offline_validation": True,
    }:
        raise AutomatedMediaError("tag-CI network contract is not exact")
    responses = receipt["responses"]
    if not isinstance(responses, list) or len(responses) != len(tag_ci.RESPONSE_ROLES):
        raise AutomatedMediaError("tag-CI response topology is not exact")
    for role, response in zip(tag_ci.RESPONSE_ROLES, responses):
        descriptor = _exact_object(
            response, {"role", "url", "sha256", "size_bytes"}, "tag-CI response"
        )
        if (
            descriptor["role"] != role
            or not isinstance(descriptor["url"], str)
            or not descriptor["url"].startswith(tag_ci.API_ORIGIN + "/repos/")
        ):
            raise AutomatedMediaError("tag-CI response identity is not exact")
        _digest(descriptor["sha256"], f"tag-CI {role} response")
        _positive_int(
            descriptor["size_bytes"],
            f"tag-CI {role} response bytes",
            maximum=tag_ci.MAX_RESPONSE_BYTES,
        )
    workflows = receipt["workflows"]
    expected_workflows = (
        ("Verify Linux", ".github/workflows/verify-linux.yml", {"python-and-publication", "supply-chain"}),
        ("Verify macOS", ".github/workflows/verify-macos.yml", {"native-application"}),
    )
    if not isinstance(workflows, list) or len(workflows) != len(expected_workflows):
        raise AutomatedMediaError("tag-CI workflow topology is not exact")
    for workflow, (name, path, job_names) in zip(workflows, expected_workflows):
        record = _exact_object(
            workflow,
            {
                "workflow_name",
                "workflow_path",
                "run_id",
                "run_attempt",
                "event",
                "head_branch",
                "head_sha",
                "status",
                "conclusion",
                "api_url",
                "html_url",
                "jobs",
            },
            "tag-CI workflow",
        )
        if (
            record["workflow_name"] != name
            or record["workflow_path"] != path
            or record["run_attempt"] != 1
            or record["event"] != "push"
            or record["head_branch"] != source["tag"]
            or record["head_sha"] != source["commit"]
            or record["status"] != "completed"
            or record["conclusion"] != "success"
        ):
            raise AutomatedMediaError("tag-CI workflow admission is not exact")
        _positive_int(
            record["run_id"],
            "tag-CI workflow run",
            maximum=MAX_GITHUB_ID,
        )
        if not isinstance(record["jobs"], list) or {
            job.get("name") for job in record["jobs"] if isinstance(job, dict)
        } != job_names:
            raise AutomatedMediaError("tag-CI job topology is not exact")
        for job in record["jobs"]:
            job_record = _exact_object(
                job,
                {
                    "job_id",
                    "name",
                    "step_count",
                    "tag_ref_assertion",
                    "status",
                    "conclusion",
                },
                "tag-CI job",
            )
            _positive_int(
                job_record["job_id"],
                "tag-CI job ID",
                maximum=MAX_GITHUB_ID,
            )
            _positive_int(job_record["step_count"], "tag-CI job step count")
            if (
                job_record["tag_ref_assertion"] != "PASS"
                or job_record["status"] != "completed"
                or job_record["conclusion"] != "success"
            ):
                raise AutomatedMediaError("tag-CI job admission is not exact")
    if expected is not None:
        observed = {
            "repository": source["repository"],
            "tag": source["tag"],
            "commit": source["commit"],
            "tree": source["tree"],
        }
        unknown = set(expected) - set(observed)
        if unknown:
            raise AutomatedMediaError(
                f"unknown external tag-CI binding: {sorted(unknown)}"
            )
        if any(observed[key] != item for key, item in expected.items()):
            raise AutomatedMediaError("tag-CI receipt differs from exact source")
    return receipt


def validate_local_tag_trust_receipt_bytes(
    data: bytes,
    *,
    expected: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the canonical hard-pinned local annotated-tag trust receipt."""

    from security import verify_portfolio_tag_ci as tag_ci

    if type(data) is not bytes or not data or len(data) > MAX_READINESS_BYTES:
        raise AutomatedMediaError("local tag trust receipt bytes are not bounded")
    try:
        value = json.loads(
            data.decode("ascii"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
        canonical = tag_ci.canonical_receipt_bytes(value)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        tag_ci.TagCIAdmissionError,
    ) as error:
        raise AutomatedMediaError("local tag trust receipt is not canonical") from error
    if not isinstance(value, dict) or canonical != data:
        raise AutomatedMediaError("local tag trust receipt is not canonical")
    receipt = _exact_object(
        value,
        {
            "schema_version",
            "artifact_kind",
            "status",
            "tag",
            "tag_object",
            "commit",
            "tree",
            "principal",
            "fingerprint",
            "public_key_sha256",
            "allowed_signers_sha256",
            "git_binary",
            "ssh_keygen_binary",
            "verification",
        },
        "local tag trust receipt",
    )
    if (
        receipt["schema_version"] != 1
        or receipt["artifact_kind"] != "corelm_portfolio_local_tag_trust_receipt"
        or receipt["status"] != "PASS"
        or receipt["principal"] != tag_ci.EXPECTED_SIGNING_PRINCIPAL
        or receipt["fingerprint"] != tag_ci.EXPECTED_FINGERPRINT
        or receipt["public_key_sha256"] != tag_ci.EXPECTED_PUBLIC_KEY_SHA256
        or receipt["allowed_signers_sha256"]
        != tag_ci.EXPECTED_ALLOWED_SIGNERS_SHA256
        or receipt["git_binary"] != tag_ci.GIT
        or receipt["ssh_keygen_binary"] != tag_ci.SSH_KEYGEN
        or receipt["verification"] != "PINNED_SSH_GIT_NAMESPACE_PASS"
    ):
        raise AutomatedMediaError("local tag trust admission is not exact")
    for key in ("tag_object", "commit", "tree"):
        _git_oid(receipt[key], f"local tag trust {key}")
    if expected is not None:
        observed = {key: receipt[key] for key in ("tag", "tag_object", "commit", "tree")}
        unknown = set(expected) - set(observed)
        if unknown:
            raise AutomatedMediaError(
                f"unknown external local tag trust binding: {sorted(unknown)}"
            )
        if any(observed[key] != item for key, item in expected.items()):
            raise AutomatedMediaError("local tag trust receipt differs from exact source")
    return receipt


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def challenge_sha256(challenge_nonce: str) -> str:
    _digest(challenge_nonce, "proof challenge")
    return sha256_bytes(challenge_nonce.encode("ascii"))


def _exact_object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise AutomatedMediaError(f"{label} fields are not exact")
    return value


def _digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        raise AutomatedMediaError(f"{label} is not lowercase SHA-256")
    return value


def _git_oid(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in _HEX for character in value)
    ):
        raise AutomatedMediaError(f"{label} is not a lowercase Git SHA-1")
    return value


def _uuid(value: Any, label: str) -> str:
    import uuid

    if not isinstance(value, str) or len(value) != 36 or value.lower() != value:
        raise AutomatedMediaError(f"{label} is not a canonical lowercase UUID")
    try:
        observed = uuid.UUID(value)
    except ValueError as error:
        raise AutomatedMediaError(f"{label} is not a canonical lowercase UUID") from error
    if str(observed) != value:
        raise AutomatedMediaError(f"{label} is not a canonical lowercase UUID")
    return value


def _positive_int(value: Any, label: str, maximum: int = 2**31 - 1) -> int:
    if type(value) is not int or value <= 0 or value > maximum:
        raise AutomatedMediaError(f"{label} is not a bounded positive integer")
    return value


def _number(
    value: Any,
    label: str,
    *,
    minimum: float,
    maximum: float,
    exact: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AutomatedMediaError(f"{label} is not numeric")
    observed = float(value)
    if not math.isfinite(observed) or not (minimum <= observed <= maximum):
        raise AutomatedMediaError(f"{label} is outside its bound")
    if exact is not None and observed != exact:
        raise AutomatedMediaError(f"{label} is not the fixed pipeline value")
    return observed


def _bounded_text(value: Any, label: str, *, prefix: str | None = None) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\n" in value
        or "\r" in value
        or len(value.encode("utf-8")) > 1024
        or (prefix is not None and not value.startswith(prefix))
    ):
        raise AutomatedMediaError(f"{label} is not a bounded exact identity")
    return value


def _metric_string(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 64
        or re.fullmatch(r"-?[0-9]+\.[0-9]{6}", value) is None
        or not math.isfinite(float(value))
    ):
        raise AutomatedMediaError(f"{label} is not a fixed six-decimal metric")
    return value


def frame_pts_identity(
    value: Any,
    *,
    width: int,
    height: int,
) -> tuple[int, str]:
    """Validate and hash the exact FFprobe n8.1.2 frame-timing projection."""

    expected_width = _positive_int(width, "frame PTS width", maximum=16_384)
    expected_height = _positive_int(height, "frame PTS height", maximum=16_384)
    if (
        not isinstance(value, list)
        or not value
        or len(value) > MAX_DECODED_FRAME_COUNT
    ):
        raise AutomatedMediaError("frame PTS topology is outside the fixed bound")

    projected: list[dict[str, Any]] = []
    timestamps: list[float] = []
    for frame in value:
        if not isinstance(frame, dict) or set(frame) not in (
            _FRAME_PTS_FIELDS,
            _FRAME_PTS_FIELDS | {_FRAME_SIDE_DATA_FIELD},
        ):
            raise AutomatedMediaError("frame PTS fields are not exact")
        if (
            _FRAME_SIDE_DATA_FIELD in frame
            and frame[_FRAME_SIDE_DATA_FIELD] != _FRAME_SEI_SIDE_DATA
        ):
            raise AutomatedMediaError("frame PTS side data is not the exact bounded SEI")

        timestamp_text = _metric_string(
            frame["best_effort_timestamp_time"], "frame PTS timestamp"
        )
        duration_text = _metric_string(frame["duration_time"], "frame PTS duration")
        timestamp = float(timestamp_text)
        duration = float(duration_text)
        if (
            duration <= 0
            or type(frame["width"]) is not int
            or type(frame["height"]) is not int
            or frame["width"] != expected_width
            or frame["height"] != expected_height
        ):
            raise AutomatedMediaError("frame PTS entry is outside the exact topology")
        timestamps.append(timestamp)
        projected.append(
            {
                "best_effort_timestamp_time": timestamp_text,
                "duration_time": duration_text,
                "width": expected_width,
                "height": expected_height,
            }
        )

    if any(right <= left for left, right in zip(timestamps, timestamps[1:])):
        raise AutomatedMediaError("frame PTS sequence is not strictly monotonic")
    return len(projected), sha256_bytes(canonical_json_bytes({"frames": projected}))


def validate_readiness(
    value: Any,
    *,
    expected: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    readiness = _exact_object(
        value,
        {
            "schema_version",
            "status",
            "run_identifier",
            "receipt_sha256",
            "result_sha256",
            "application_executable_sha256",
            "metric_verdict",
            "compression_ratio_vs_bf16",
            "delta_nll_nat_per_token",
            "top1_agreement",
            "module_states",
            "verifier_state",
        },
        "result readiness receipt",
    )
    if readiness["schema_version"] != 1 or readiness["status"] != "CAPTURE_RESULT_READY":
        raise AutomatedMediaError("result readiness status/schema is not exact")
    _uuid(readiness["run_identifier"], "result readiness run identifier")
    for key in ("receipt_sha256", "result_sha256", "application_executable_sha256"):
        _digest(readiness[key], f"result readiness {key}")
    if readiness["metric_verdict"] not in _TERMINAL_OUTCOMES:
        raise AutomatedMediaError("result readiness metric verdict is not exact")
    for key in (
        "compression_ratio_vs_bf16",
        "delta_nll_nat_per_token",
        "top1_agreement",
    ):
        _metric_string(readiness[key], f"result readiness {key}")
    modules = _exact_object(
        readiness["module_states"],
        {
            "qwen_model",
            "kv_cache",
            "compression",
            "primary_evidence",
            "heavy_replay",
        },
        "result readiness module states",
    )
    if modules != {
        "qwen_model": "COMPLETE",
        "kv_cache": "COMPLETE",
        "compression": "COMPLETE",
        "primary_evidence": "COMPLETE",
        "heavy_replay": "PASS",
    } or readiness["verifier_state"] != "PASS":
        raise AutomatedMediaError("result readiness module/verifier states are not exact")
    if expected is not None:
        unknown = set(expected) - set(readiness)
        if unknown:
            raise AutomatedMediaError(
                f"unknown external readiness binding: {sorted(unknown)}"
            )
        for key, expected_value in expected.items():
            if readiness[key] != expected_value:
                raise AutomatedMediaError(f"result readiness differs from {key}")
    return readiness


def _tool(value: Any, label: str, *, version_prefix: str) -> dict[str, Any]:
    tool = _exact_object(value, {"executable_sha256", "version"}, label)
    _digest(tool["executable_sha256"], f"{label} executable")
    _bounded_text(tool["version"], f"{label} version", prefix=version_prefix)
    return tool


def _segment(value: Any, role: str) -> dict[str, Any]:
    segment = _exact_object(
        value,
        {
            "role",
            "owner_pid",
            "window_id",
            "width",
            "height",
            "requested_duration_seconds",
            "duration_seconds",
            "frame_count",
            "pts_sha256",
            "sha256",
        },
        f"{role} capture segment",
    )
    if segment["role"] != role:
        raise AutomatedMediaError("capture segment order/role is not exact")
    _positive_int(segment["owner_pid"], f"{role} owner PID")
    _positive_int(segment["window_id"], f"{role} window ID")
    width = _positive_int(segment["width"], f"{role} width", maximum=8_192)
    height = _positive_int(segment["height"], f"{role} height", maximum=8_192)
    if width < 1_120 or height < 720:
        raise AutomatedMediaError("capture segment is smaller than the fixed safe view")
    expected_duration = {
        "preflight": PREFLIGHT_SEGMENT_SECONDS,
        "live_presentation": LIVE_SEGMENT_SECONDS,
        "same_run_result": RESULT_SEGMENT_SECONDS,
    }.get(role)
    if expected_duration is None:
        raise AutomatedMediaError("capture segment role is unsupported")
    _number(
        segment["requested_duration_seconds"],
        f"{role} requested duration",
        minimum=0.1,
        maximum=90.0,
        exact=expected_duration,
    )
    observed_duration = _number(
        segment["duration_seconds"],
        f"{role} observed duration",
        minimum=0.1,
        maximum=90.0,
    )
    if abs(observed_duration - expected_duration) > 1.0:
        raise AutomatedMediaError("capture segment observed duration is out of tolerance")
    _positive_int(
        segment["frame_count"],
        f"{role} observed frame count",
        maximum=90 * 240,
    )
    _digest(segment["pts_sha256"], f"{role} observed frame PTS")
    _digest(segment["sha256"], f"{role} segment")
    return segment


def validate_attempt_state_bytes(
    data: bytes,
    *,
    report: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Validate the exact nine-event successful owner-local session transcript."""

    if (
        not isinstance(data, bytes)
        or not data
        or len(data) > MAX_ATTEMPT_STATE_BYTES
        or data.startswith(b"\xef\xbb\xbf")
        or not data.endswith(b"\n")
    ):
        raise AutomatedMediaError("attempt-state bytes are not bounded canonical JSONL")
    raw_lines = data.splitlines(keepends=True)
    if len(raw_lines) != ATTEMPT_EVENT_COUNT:
        raise AutomatedMediaError("attempt-state success event count is not exact")
    events: list[dict[str, Any]] = []
    for index, raw_line in enumerate(raw_lines):
        try:
            value = json.loads(
                raw_line.decode("utf-8"),
                object_pairs_hook=_object_without_duplicates,
                parse_constant=_reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AutomatedMediaError("attempt-state line is not strict JSON") from error
        if not isinstance(value, dict) or raw_line != canonical_json_bytes(value):
            raise AutomatedMediaError("attempt-state line is not canonical JSON")
        if value.get("event") != ATTEMPT_SUCCESS_EVENTS[index]:
            raise AutomatedMediaError("attempt-state success transition order is not exact")
        events.append(value)

    common = {"event", "proof_invocation_count", "schema_version", "tag"}
    extras = (
        {
            "source_commit",
            "source_tree",
            "preflight_segment_sha256",
            "preflight_owner_pid",
            "preflight_window_id",
            "window_helper_sha256",
            "tag_ci_receipt_sha256",
            "local_tag_trust_receipt_sha256",
        },
        {"executable_sha256", "owner_pid", "window_id"},
        {"challenge_sha256"},
        {"segment_sha256", "window_id"},
        {"metric_verdict", "run_identifier", "terminal_outcome"},
        {"replay_verdict", "run_identifier"},
        {"result_readiness_sha256", "run_identifier", "window_id"},
        {"segment_sha256", "window_id"},
        {"poster_sha256", "video_sha256"},
    )
    proof_counts = (0, 0, 1, 1, 1, 1, 1, 1, 1)
    tag = events[0].get("tag")
    if (
        not isinstance(tag, str)
        or not tag.startswith("corelm-portfolio-v")
        or not tag[len("corelm-portfolio-v") :].isdigit()
        or int(tag[len("corelm-portfolio-v") :]) < 3
    ):
        raise AutomatedMediaError("attempt-state tag is outside V3+")
    for index, event in enumerate(events):
        _exact_object(event, common | extras[index], f"attempt event {index + 1}")
        if (
            event["schema_version"] != 1
            or event["tag"] != tag
            or event["proof_invocation_count"] != proof_counts[index]
        ):
            raise AutomatedMediaError("attempt-state common transition fields differ")

    started, live_ready, invoked, live_captured, terminal, replay, reopened, result_captured, sealed = events
    _git_oid(started["source_commit"], "attempt source commit")
    _git_oid(started["source_tree"], "attempt source tree")
    for key in (
        "preflight_segment_sha256",
        "window_helper_sha256",
        "tag_ci_receipt_sha256",
        "local_tag_trust_receipt_sha256",
    ):
        _digest(started[key], f"attempt {key}")
    _positive_int(started["preflight_owner_pid"], "attempt preflight owner PID")
    _positive_int(started["preflight_window_id"], "attempt preflight window ID")
    _digest(live_ready["executable_sha256"], "attempt live executable")
    _positive_int(live_ready["owner_pid"], "attempt live owner PID")
    _positive_int(live_ready["window_id"], "attempt live window ID")
    _digest(invoked["challenge_sha256"], "attempt challenge")
    _digest(live_captured["segment_sha256"], "attempt live segment")
    _positive_int(live_captured["window_id"], "attempt live capture window ID")
    _uuid(terminal["run_identifier"], "attempt terminal run")
    if (
        terminal["metric_verdict"] not in _TERMINAL_OUTCOMES
        or terminal["terminal_outcome"]
        != _TERMINAL_OUTCOMES[terminal["metric_verdict"]]
    ):
        raise AutomatedMediaError("attempt terminal outcome is not exact")
    _uuid(replay["run_identifier"], "attempt replay run")
    if replay["replay_verdict"] != REPLAY_VERDICT:
        raise AutomatedMediaError("attempt replay verdict is not exact")
    _digest(reopened["result_readiness_sha256"], "attempt readiness")
    _uuid(reopened["run_identifier"], "attempt reopened run")
    _positive_int(reopened["window_id"], "attempt reopened window ID")
    _digest(result_captured["segment_sha256"], "attempt result segment")
    _positive_int(result_captured["window_id"], "attempt result capture window ID")
    _digest(sealed["poster_sha256"], "attempt poster")
    _digest(sealed["video_sha256"], "attempt video")
    if len({terminal["run_identifier"], replay["run_identifier"], reopened["run_identifier"]}) != 1:
        raise AutomatedMediaError("attempt-state events do not bind one exact run")

    if report is not None:
        validated_report = validate_report(report)
        preflight = validated_report["capture"]["preflight_segment"]
        live = validated_report["capture"]["segments"][0]
        result = validated_report["capture"]["segments"][1]
        expected_pairs = (
            (tag, validated_report["source"]["tag"]),
            (started["source_commit"], validated_report["source"]["commit"]),
            (started["source_tree"], validated_report["source"]["tree"]),
            (started["preflight_segment_sha256"], preflight["sha256"]),
            (started["preflight_owner_pid"], preflight["owner_pid"]),
            (started["preflight_window_id"], preflight["window_id"]),
            (
                started["window_helper_sha256"],
                validated_report["tools"]["window_helper"]["executable_sha256"],
            ),
            (
                started["tag_ci_receipt_sha256"],
                validated_report["attempt"]["tag_ci_receipt_sha256"],
            ),
            (
                started["local_tag_trust_receipt_sha256"],
                validated_report["attempt"]["local_tag_trust_receipt_sha256"],
            ),
            (
                live_ready["executable_sha256"],
                validated_report["run"]["application_executable_sha256"],
            ),
            (live_ready["owner_pid"], live["owner_pid"]),
            (live_ready["window_id"], live["window_id"]),
            (invoked["challenge_sha256"], validated_report["run"]["challenge_sha256"]),
            (live_captured["segment_sha256"], live["sha256"]),
            (live_captured["window_id"], live["window_id"]),
            (terminal["run_identifier"], validated_report["run"]["identifier"]),
            (terminal["metric_verdict"], validated_report["run"]["metric_verdict"]),
            (terminal["terminal_outcome"], validated_report["run"]["terminal_outcome"]),
            (replay["replay_verdict"], validated_report["run"]["replay_verdict"]),
            (reopened["result_readiness_sha256"], validated_report["capture"]["result_readiness_sha256"]),
            (reopened["window_id"], result["window_id"]),
            (result_captured["segment_sha256"], result["sha256"]),
            (result_captured["window_id"], result["window_id"]),
            (sealed["poster_sha256"], validated_report["output"]["poster_sha256"]),
            (sealed["video_sha256"], validated_report["output"]["video_sha256"]),
            (sha256_bytes(data), validated_report["attempt"]["state_log_sha256"]),
        )
        if any(observed != expected for observed, expected in expected_pairs):
            raise AutomatedMediaError("attempt-state bytes differ from automation report")
    return events


def validate_tools(value: Any) -> dict[str, Any]:
    """Validate the exact capture-tool identity object shared by runtime assets."""

    tools = _exact_object(
        value,
        {"window_helper", "screencapture", "ffmpeg", "ffprobe"},
        "capture tools",
    )
    helper = _exact_object(
        tools["window_helper"],
        {"source_sha256", "executable_sha256", "swift_version"},
        "window helper",
    )
    _digest(helper["source_sha256"], "window helper source")
    _digest(helper["executable_sha256"], "window helper executable")
    _bounded_text(
        helper["swift_version"],
        "window helper Swift",
        prefix="Apple Swift version ",
    )
    screencapture = _exact_object(
        tools["screencapture"],
        {"executable_sha256", "codesign_identifier"},
        "screencapture identity",
    )
    _digest(screencapture["executable_sha256"], "screencapture executable")
    if screencapture["codesign_identifier"] != "com.apple.screencapture":
        raise AutomatedMediaError("screencapture code identity is not exact")
    _tool(tools["ffmpeg"], "ffmpeg", version_prefix="ffmpeg version ")
    _tool(tools["ffprobe"], "ffprobe", version_prefix="ffprobe version ")
    return tools


def validate_report(
    value: Any,
    *,
    expected: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one exact automation receipt and optional external bindings."""

    report = _exact_object(
        value,
        {
            "schema_version",
            "report_kind",
            "verdict",
            "automation_contract",
            "classification",
            "automation_only",
            "human_reviewed",
            "manual_edits",
            "machine_evidence",
            "pixel_semantics_verified",
            "source",
            "run",
            "capture",
            "tools",
            "output",
            "privacy",
            "attempt",
        },
        "automation receipt",
    )
    if (
        report["schema_version"] != SCHEMA_VERSION
        or report["report_kind"] != REPORT_KIND
        or report["verdict"] != VERDICT
        or report["automation_contract"] != AUTOMATION_CONTRACT
        or report["classification"] != MEDIA_CLASSIFICATION
        or report["automation_only"] is not True
        or report["human_reviewed"] is not False
        or report["manual_edits"] is not False
        or report["machine_evidence"] is not False
        or report["pixel_semantics_verified"] is not False
    ):
        raise AutomatedMediaError("automation-only claim boundary is not exact")

    source = _exact_object(report["source"], {"tag", "commit", "tree"}, "source")
    if (
        not isinstance(source["tag"], str)
        or not source["tag"].startswith("corelm-portfolio-v")
        or not source["tag"][len("corelm-portfolio-v") :].isdigit()
        or int(source["tag"][len("corelm-portfolio-v") :]) < 3
    ):
        raise AutomatedMediaError("automation source tag is outside V3+")
    _git_oid(source["commit"], "source commit")
    _git_oid(source["tree"], "source tree")

    run = _exact_object(
        report["run"],
        {
            "identifier",
            "challenge_sha256",
            "receipt_sha256",
            "result_sha256",
            "application_executable_sha256",
            "metric_verdict",
            "terminal_outcome",
            "structural_verdict",
            "replay_verdict",
            "workload_classification",
            "synthetic_data",
        },
        "proof run",
    )
    _uuid(run["identifier"], "proof run identifier")
    for key in (
        "challenge_sha256",
        "receipt_sha256",
        "result_sha256",
        "application_executable_sha256",
    ):
        _digest(run[key], f"proof {key}")
    if (
        run["metric_verdict"] not in _TERMINAL_OUTCOMES
        or run["terminal_outcome"] != _TERMINAL_OUTCOMES[run["metric_verdict"]]
        or run["structural_verdict"] != "PASS"
        or run["replay_verdict"] != REPLAY_VERDICT
        or run["workload_classification"] != WORKLOAD_CLASSIFICATION
        or run["synthetic_data"] is not False
    ):
        raise AutomatedMediaError("proof outcome is not exact or is selection-tainted")

    capture = _exact_object(
        report["capture"],
        {
            "mode",
            "bundle_identifier",
            "preflight_segment",
            "segments",
            "result_readiness_sha256",
        },
        "capture",
    )
    if (
        capture["mode"] != CAPTURE_MODE
        or capture["bundle_identifier"] != BUNDLE_IDENTIFIER
        or not isinstance(capture["segments"], list)
        or len(capture["segments"]) != 2
    ):
        raise AutomatedMediaError("capture target/mode/topology is not exact")
    preflight_segment = _segment(capture["preflight_segment"], "preflight")
    live_segment = _segment(capture["segments"][0], "live_presentation")
    result_segment = _segment(capture["segments"][1], "same_run_result")
    if (live_segment["width"], live_segment["height"]) != (
        result_segment["width"],
        result_segment["height"],
    ) or (preflight_segment["width"], preflight_segment["height"]) != (
        live_segment["width"],
        live_segment["height"],
    ):
        raise AutomatedMediaError("capture segment dimensions are not exact and equal")
    _digest(capture["result_readiness_sha256"], "result readiness receipt")

    validate_tools(report["tools"])

    output = _exact_object(
        report["output"],
        {
            "video_sha256",
            "poster_sha256",
            "poster_frame_timestamp_seconds",
            "duration_seconds",
            "width",
            "height",
            "frame_count",
            "pts_sha256",
            "decoded_frames_sha256",
        },
        "media output",
    )
    for key in ("video_sha256", "poster_sha256", "pts_sha256", "decoded_frames_sha256"):
        _digest(output[key], f"media {key}")
    _number(
        output["poster_frame_timestamp_seconds"],
        "poster timestamp",
        minimum=0,
        maximum=90,
        exact=POSTER_TIMESTAMP_SECONDS,
    )
    _number(
        output["duration_seconds"],
        "final video duration",
        minimum=OUTPUT_DURATION_SECONDS,
        maximum=OUTPUT_DURATION_SECONDS,
        exact=OUTPUT_DURATION_SECONDS,
    )
    if (
        output["width"] != OUTPUT_WIDTH
        or output["height"] != OUTPUT_HEIGHT
        or output["frame_count"] != OUTPUT_FRAME_COUNT
    ):
        raise AutomatedMediaError("final media geometry/frame topology is not exact")

    privacy = _exact_object(
        report["privacy"],
        {
            "input_surface",
            "byte_and_metadata_scan",
            "ocr_role",
            "verdict",
            "semantic_pixel_privacy",
        },
        "privacy boundary",
    )
    if privacy != {
        "input_surface": "ALLOWLISTED_APP_VIEW_ONLY",
        "byte_and_metadata_scan": "PASS",
        "ocr_role": "NOT_RUN_NOT_A_COMPLETENESS_PROOF",
        "verdict": "NO_CONFIGURED_PATTERN_DETECTED",
        "semantic_pixel_privacy": "NOT_CLAIMED",
    }:
        raise AutomatedMediaError("automated privacy boundary is not exact")

    attempt = _exact_object(
        report["attempt"],
        {
            "proof_invocation_count",
            "event_count",
            "scope",
            "state_log_sha256",
            "tag_ci_receipt_sha256",
            "local_tag_trust_receipt_sha256",
        },
        "attempt state",
    )
    if (
        attempt["proof_invocation_count"] != 1
        or attempt["event_count"] != ATTEMPT_EVENT_COUNT
        or attempt["scope"] != ATTEMPT_SCOPE
    ):
        raise AutomatedMediaError(
            "automation receipt does not bind one retained owner-local session"
        )
    _digest(attempt["state_log_sha256"], "attempt state log")
    _digest(attempt["tag_ci_receipt_sha256"], "attempt tag-CI receipt")
    _digest(
        attempt["local_tag_trust_receipt_sha256"],
        "attempt local tag trust receipt",
    )

    if expected is not None:
        observed = {
            "tag": source["tag"],
            "commit": source["commit"],
            "tree": source["tree"],
            "run_identifier": run["identifier"],
            "challenge_sha256": run["challenge_sha256"],
            "receipt_sha256": run["receipt_sha256"],
            "result_sha256": run["result_sha256"],
            "application_executable_sha256": run["application_executable_sha256"],
            "metric_verdict": run["metric_verdict"],
            "video_sha256": output["video_sha256"],
            "poster_sha256": output["poster_sha256"],
            "duration_seconds": output["duration_seconds"],
            "width": output["width"],
            "height": output["height"],
            "frame_count": output["frame_count"],
            "poster_frame_timestamp_seconds": output[
                "poster_frame_timestamp_seconds"
            ],
            "result_readiness_sha256": capture["result_readiness_sha256"],
            "attempt_state_sha256": attempt["state_log_sha256"],
            "tag_ci_receipt_sha256": attempt["tag_ci_receipt_sha256"],
            "local_tag_trust_receipt_sha256": attempt[
                "local_tag_trust_receipt_sha256"
            ],
            "preflight_segment_sha256": preflight_segment["sha256"],
            "live_segment_sha256": live_segment["sha256"],
            "result_segment_sha256": result_segment["sha256"],
            "window_helper_sha256": report["tools"]["window_helper"][
                "executable_sha256"
            ],
        }
        unknown = set(expected) - set(observed)
        if unknown:
            raise AutomatedMediaError(
                f"unknown external automation binding: {sorted(unknown)}"
            )
        for key, expected_value in expected.items():
            if observed[key] != expected_value:
                raise AutomatedMediaError(f"automation receipt differs from {key}")
    return report


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    validate_report(report)
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise AutomatedMediaError("automation receipt output must be an absent absolute path")
    parent = path.parent.resolve(strict=True)
    if parent != path.parent or parent.is_symlink():
        raise AutomatedMediaError("automation receipt output parent is not canonical")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        payload = canonical_json_bytes(report)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise AutomatedMediaError("automation receipt write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
