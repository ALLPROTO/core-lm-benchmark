#!/usr/bin/env python3
"""Query OSV for explicitly pinned Python packages without third-party tools."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OSV_QUERY_BATCH = "https://api.osv.dev/v1/querybatch"
PIN = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)=="
    r"([A-Za-z0-9][A-Za-z0-9._+!-]*)"
    r"(?:\s|\\|$)"
)


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def pinned_packages(paths: list[Path]) -> list[tuple[str, str, tuple[str, ...]]]:
    sources: dict[tuple[str, str], set[str]] = {}
    for path in paths:
        if not path.is_file():
            raise ValueError(f"missing dependency manifest: {path}")
        display = str(path.relative_to(ROOT))
        for line_number, raw_line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("--hash="):
                continue
            match = PIN.match(line)
            if match is None:
                if line == "\\":
                    continue
                raise ValueError(
                    f"{display}:{line_number}: dependency is not exactly pinned"
                )
            key = (canonical_name(match.group(1)), match.group(2))
            sources.setdefault(key, set()).add(display)
    return [
        (name, version, tuple(sorted(manifests)))
        for (name, version), manifests in sorted(sources.items())
    ]


def query(packages: list[tuple[str, str, tuple[str, ...]]]) -> list[dict]:
    payload = {
        "queries": [
            {
                "package": {"ecosystem": "PyPI", "name": name},
                "version": version,
            }
            for name, version, _ in packages
        ]
    }
    request = urllib.request.Request(
        OSV_QUERY_BATCH,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "CoreLMBenchmark-security-audit/1",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        document = json.load(response)
    results = document.get("results")
    if not isinstance(results, list) or len(results) != len(packages):
        raise ValueError("OSV returned an invalid result set")
    return results


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    paths = [
        path if path.is_absolute() else ROOT / path
        for path in arguments.manifests
    ]
    try:
        packages = pinned_packages(paths)
        results = query(packages)
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as error:
        print(f"OSV AUDIT ERROR: {error}", file=sys.stderr)
        return 2

    findings: list[tuple[str, str, list[str], tuple[str, ...]]] = []
    for (name, version, sources), result in zip(packages, results):
        identifiers = sorted(
            {
                vulnerability.get("id", "UNKNOWN")
                for vulnerability in result.get("vulns", [])
                if isinstance(vulnerability, dict)
            }
        )
        if identifiers:
            findings.append((name, version, identifiers, sources))

    if findings:
        print("OSV AUDIT FAIL")
        for name, version, identifiers, sources in findings:
            print(
                f"- {name}=={version}: {', '.join(identifiers)} "
                f"({', '.join(sources)})"
            )
        return 1

    print(f"OSV AUDIT PASS: {len(packages)} unique pinned package versions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
