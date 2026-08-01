#!/usr/bin/env python3
"""Deterministically verify workflow pinning, locks, and repository secrets."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MAX_SCANNED_BLOB_BYTES = 5_000_000
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ACTION = re.compile(
    r"^\s*(?:-\s+)?uses:\s+([^@\s]+)@([^\s#]+)"
    r"(?:\s+#\s+(\S.*))?$",
    re.MULTILINE,
)
PIN = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)=="
    r"([A-Za-z0-9][A-Za-z0-9._+!-]*)"
    r"(?:\s|\\|$)"
)


class UniqueKeyLoader(yaml.BaseLoader):
    """Keep YAML scalar spelling while rejecting duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict:
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def run(*arguments: str) -> bytes:
    return subprocess.check_output(arguments, cwd=ROOT)


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _permission_errors(
    display: str,
    label: str,
    value: object,
) -> list[str]:
    if isinstance(value, str):
        if value == "read-all":
            return []
        return [f"{display}: {label} permission value {value!r} is forbidden"]
    if not isinstance(value, dict):
        return [f"{display}: {label} permissions must be a mapping or read-all"]
    errors = []
    for scope, access in value.items():
        if access not in ("read", "none"):
            errors.append(
                f"{display}: {label} permission {scope!r}: "
                f"{access!r} is forbidden"
            )
    return errors


def _semantic_workflow_errors(
    display: str,
    text: str,
) -> tuple[list[str], dict | None]:
    try:
        document = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as error:
        return [f"{display}: invalid or duplicate-key YAML: {error}"], None
    if not isinstance(document, dict):
        return [f"{display}: workflow root must be a mapping"], None

    errors: list[str] = []
    if document.get("permissions") != {"contents": "read"}:
        errors.append(
            f"{display}: top-level permissions must be exactly contents: read"
        )

    triggers = document.get("on")
    if isinstance(triggers, dict):
        trigger_names = set(triggers)
    elif isinstance(triggers, list):
        trigger_names = set(triggers)
    elif isinstance(triggers, str):
        trigger_names = {triggers}
    else:
        trigger_names = set()
    for forbidden in ("pull_request_target", "workflow_run"):
        if forbidden in trigger_names:
            errors.append(f"{display}: risky trigger {forbidden} is forbidden")

    jobs = document.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        errors.append(f"{display}: jobs must be a non-empty mapping")
        return errors, document

    action_uses: list[tuple[str, object, object]] = []
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            errors.append(f"{display}: job {job_name!r} must be a mapping")
            continue
        if "permissions" in job:
            errors.extend(
                _permission_errors(
                    display,
                    f"job {job_name!r}",
                    job["permissions"],
                )
            )
        if "uses" in job:
            action_uses.append(
                (f"job {job_name!r}", job["uses"], job.get("with"))
            )
        steps = job.get("steps", [])
        if not isinstance(steps, list):
            errors.append(f"{display}: job {job_name!r} steps must be a list")
            continue
        for step_index, step in enumerate(steps, 1):
            if not isinstance(step, dict) or "uses" not in step:
                continue
            action_uses.append(
                (
                    f"job {job_name!r} step {step_index}",
                    step["uses"],
                    step.get("with"),
                )
            )

    for label, value, options in action_uses:
        if not isinstance(value, str):
            errors.append(f"{display}: {label} uses value must be a string")
            continue
        if value.startswith("./"):
            continue
        if "@" not in value:
            errors.append(f"{display}: {label} action has no immutable reference")
            continue
        action_name, reference = value.rsplit("@", 1)
        if not action_name or FULL_SHA.fullmatch(reference) is None:
            errors.append(
                f"{display}: {label} action reference must be a full commit SHA"
            )
        if action_name == "actions/checkout":
            if (
                not isinstance(options, dict)
                or options.get("persist-credentials") != "false"
            ):
                errors.append(
                    f"{display}: {label} checkout must disable "
                    "credential persistence"
                )
    return errors, document


def workflow_text_errors(display: str, text: str) -> list[str]:
    errors, document = _semantic_workflow_errors(display, text)
    if document is None:
        return errors
    if not re.search(r"(?m)^permissions:\s*\n\s+contents:\s+read\s*$", text):
        # Semantic parsing above accepts harmless quoting/spacing. Keep this
        # textual check only as defense in depth, without duplicating an error.
        pass
    if re.search(r"(?mi)^\s*permissions:\s*write-all\s*(?:#.*)?$", text):
        errors.append(f"{display}: permissions: write-all is forbidden")
    if re.search(r"(?m)^\s+[A-Za-z-]+:\s+write\s*(?:#.*)?$", text):
        errors.append(f"{display}: write workflow permission is forbidden")
    for inline in re.finditer(
        r"(?mi)^\s*permissions:\s*\{([^}]*)\}\s*(?:#.*)?$",
        text,
    ):
        if re.search(r":\s*[\"']?write(?:[\"']?\s*[,}]|[\"']?\s*$)", inline.group(1)):
            errors.append(f"{display}: inline write workflow permission is forbidden")
    for trigger in ("pull_request_target:", "workflow_run:"):
        if re.search(rf"(?m)^\s*{re.escape(trigger)}\s*$", text):
            errors.append(f"{display}: risky trigger {trigger[:-1]} is forbidden")
    for match in ACTION.finditer(text):
        owner_action, reference, comment = match.groups()
        if owner_action.startswith("./"):
            continue
        line = text.count("\n", 0, match.start()) + 1
        if FULL_SHA.fullmatch(reference) is None:
            errors.append(
                f"{display}:{line}: action reference must be a full commit SHA"
            )
        if comment is None or re.match(r"v\d", comment) is None:
            errors.append(
                f"{display}:{line}: pinned action needs a version comment"
            )
        if owner_action == "actions/checkout":
            following = text[match.end() :].splitlines()[:8]
            if not any(
                line.strip() == "persist-credentials: false"
                for line in following
            ):
                errors.append(
                    f"{display}:{line}: checkout must disable credential persistence"
                )
    return errors


def workflow_errors() -> list[str]:
    errors: list[str] = []
    workflows = sorted((ROOT / ".github/workflows").glob("*.y*ml"))
    if not workflows:
        return ["no GitHub Actions workflows found"]
    for path in workflows:
        display = str(path.relative_to(ROOT))
        errors.extend(
            workflow_text_errors(display, path.read_text(encoding="utf-8"))
        )
    return errors


def dependabot_text_errors(display: str, text: str) -> list[str]:
    try:
        document = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as error:
        return [f"{display}: invalid or duplicate-key YAML: {error}"]
    if not isinstance(document, dict):
        return [f"{display}: root must be a mapping"]
    updates = document.get("updates")
    if not isinstance(updates, list):
        return [f"{display}: updates must be a list"]

    pip_entries = [
        entry
        for entry in updates
        if isinstance(entry, dict) and entry.get("package-ecosystem") == "pip"
    ]
    root_entries = [
        entry for entry in pip_entries if entry.get("directory") == "/"
    ]
    real_entries = [
        entry for entry in pip_entries if entry.get("directory") == "/RealLLM"
    ]
    errors: list[str] = []
    if len(root_entries) != 1:
        errors.append(f"{display}: exactly one root pip updater is required")
    else:
        excluded = root_entries[0].get("exclude-paths")
        if not isinstance(excluded, list) or "RealLLM/**" not in excluded:
            errors.append(
                f"{display}: root pip updater must exclude RealLLM/**"
            )
        if root_entries[0].get("open-pull-requests-limit") != "0":
            errors.append(
                f"{display}: root pip updates must use the lock workflow"
            )
    if len(real_entries) != 1:
        errors.append(f"{display}: exactly one RealLLM pip updater is required")
    elif real_entries[0].get("open-pull-requests-limit") != "0":
        errors.append(
            f"{display}: frozen RealLLM version updates must remain disabled"
        )
    return errors


def dependabot_errors() -> list[str]:
    config = ROOT / ".github" / "dependabot.yml"
    try:
        return dependabot_text_errors(
            str(config.relative_to(ROOT)),
            config.read_text(encoding="utf-8"),
        )
    except OSError as error:
        return [str(error)]


def manifest_pins(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    display = str(path.relative_to(ROOT))
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("--hash="):
            continue
        match = PIN.match(line)
        if match is None:
            raise ValueError(f"{display}:{line_number}: dependency is not pinned")
        pins[canonical_name(match.group(1))] = match.group(2)
    return pins


def hashed_lock_errors(path: Path) -> list[str]:
    """Require every logical requirement in a generated lock to carry a hash."""
    display = str(path.relative_to(ROOT))
    errors: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line or line.startswith("#"):
            index += 1
            continue
        match = PIN.match(line)
        if match is None:
            errors.append(f"{display}:{index + 1}: invalid locked requirement")
            index += 1
            continue
        logical_lines = [line]
        while logical_lines[-1].endswith("\\") and index + 1 < len(lines):
            index += 1
            logical_lines.append(lines[index].strip())
        if not any(
            item.startswith("--hash=sha256:") for item in logical_lines[1:]
        ):
            errors.append(
                f"{display}:{index + 2 - len(logical_lines)}: "
                "locked requirement has no SHA-256"
            )
        index += 1
    return errors


def dependency_errors() -> list[str]:
    errors: list[str] = []
    try:
        direct = manifest_pins(ROOT / "requirements.txt")
        portable = manifest_pins(ROOT / "requirements.lock")
        linux = manifest_pins(ROOT / ".github/locks/core-linux-py312.txt")
        macos = manifest_pins(
            ROOT / ".github/locks/core-macos-arm64-py312.txt"
        )
        bootstrap = manifest_pins(ROOT / ".github/locks/pip-bootstrap.txt")
        real_direct = manifest_pins(ROOT / "RealLLM/requirements.txt")
        real_portable = manifest_pins(ROOT / "RealLLM/requirements.lock")
        real_linux_cpu = manifest_pins(
            ROOT / ".github/locks/real-llm-linux-cpu-py312.txt"
        )
        linux_cpu_torch = manifest_pins(
            ROOT / ".github/locks/torch-linux-cpu-py312.txt"
        )
    except (OSError, ValueError) as error:
        return [str(error)]
    for platform, locked in (
        ("portable core", portable),
        ("linux", linux),
        ("macOS", macos),
    ):
        for name, version in direct.items():
            if locked.get(name) != version:
                errors.append(
                    f"{platform} lock does not contain {name}=={version}"
                )
    for name, version in real_direct.items():
        if real_portable.get(name) != version:
            errors.append(
                f"RealLLM lock does not contain {name}=={version}"
            )
    expected_linux_cpu = {
        name: version
        for name, version in real_portable.items()
        if name != "torch"
    }
    if real_linux_cpu != expected_linux_cpu:
        errors.append(
            "Linux CPU RealLLM lock must match the portable lock except torch"
        )
    if linux_cpu_torch != {"torch": "2.13.0+cpu"}:
        errors.append(
            "Linux CPU torch lock must contain only torch==2.13.0+cpu"
        )
    if set(bootstrap) != {"pip"}:
        errors.append("pip bootstrap lock must contain only pip")
    for lock in (
        ROOT / ".github/locks/pip-bootstrap.txt",
        ROOT / ".github/locks/core-linux-py312.txt",
        ROOT / ".github/locks/core-macos-arm64-py312.txt",
    ):
        text = lock.read_text(encoding="utf-8")
        pins = manifest_pins(lock)
        if text.count("--hash=sha256:") != len(pins):
            errors.append(
                f"{lock.relative_to(ROOT)}: every locked package needs one SHA-256"
            )
    for lock in (
        ROOT / "requirements.lock",
        ROOT / "RealLLM/requirements.lock",
        ROOT / ".github/locks/real-llm-linux-cpu-py312.txt",
        ROOT / ".github/locks/torch-linux-cpu-py312.txt",
    ):
        errors.extend(hashed_lock_errors(lock))
    return errors


def secret_patterns() -> list[tuple[str, re.Pattern[bytes]]]:
    return [
        (
            "private key",
            re.compile(
                rb"-{5}BEGIN " + rb"(?:[A-Z0-9 ]+ )?PRIVATE KEY-{5}"
            ),
        ),
        (
            "GitHub token",
            re.compile(
                rb"(?:gh" + rb"[pousr]_[A-Za-z0-9]{30,}|"
                + rb"github"
                + rb"_pat_[A-Za-z0-9_]{30,})"
            ),
        ),
        (
            "AWS access key",
            re.compile(rb"(?:AK" + rb"IA|AS" + rb"IA)[A-Z0-9]{16}"),
        ),
        (
            "OpenAI key",
            re.compile(
                rb"s" + rb"k-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}"
            ),
        ),
        (
            "Hugging Face token",
            re.compile(rb"h" + rb"f_[A-Za-z0-9]{30,}"),
        ),
        (
            "Slack token",
            re.compile(rb"xox" + rb"[baprs]-[A-Za-z0-9-]{20,}"),
        ),
        (
            "Google API key",
            re.compile(rb"AI" + rb"za[0-9A-Za-z_-]{30,}"),
        ),
    ]


def matching_secret(data: bytes) -> str | None:
    for label, pattern in secret_patterns():
        if pattern.search(data):
            return label
    return None


def secret_errors() -> list[str]:
    errors: list[str] = []
    tracked = (
        run("git", "ls-files", "-co", "--exclude-standard", "-z")
        .decode("utf-8")
        .split("\0")
    )
    for relative in tracked:
        if not relative:
            continue
        path = ROOT / relative
        try:
            if path.stat().st_size > MAX_SCANNED_BLOB_BYTES:
                errors.append(
                    f"{relative}: file exceeds deterministic secret-scan limit"
                )
                continue
            data = path.read_bytes()
        except OSError as error:
            errors.append(f"cannot scan {relative}: {error}")
            continue
        label = matching_secret(data)
        if label is not None:
            errors.append(f"{relative}: possible {label}")

    objects = (
        run(
            "git",
            "rev-list",
            "--objects",
            "--all",
            "--filter=object:type=blob",
        )
        .decode("utf-8", errors="replace")
        .splitlines()
    )
    scanned: set[str] = set()
    for entry in objects:
        if " " not in entry:
            continue
        object_id, path = entry.split(" ", 1)
        if object_id in scanned:
            continue
        scanned.add(object_id)
        try:
            size = int(run("git", "cat-file", "-s", object_id))
            if size > MAX_SCANNED_BLOB_BYTES:
                errors.append(
                    f"reachable Git object {object_id} ({path}) exceeds "
                    "deterministic secret-scan limit"
                )
                continue
            data = run("git", "cat-file", "blob", object_id)
        except (subprocess.CalledProcessError, ValueError):
            continue
        label = matching_secret(data)
        if label is not None:
            errors.append(
                f"reachable Git object {object_id} ({path}): possible {label}"
            )
    return errors


def main() -> int:
    checks = {
        "workflow policy": workflow_errors(),
        "Dependabot freeze boundary": dependabot_errors(),
        "dependency locks": dependency_errors(),
        "tracked and reachable-history secrets": secret_errors(),
    }
    failed = False
    for label, errors in checks.items():
        if errors:
            failed = True
            print(f"FAIL: {label}")
            for error in errors:
                print(f"- {error}")
        else:
            print(f"PASS: {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
