#!/usr/bin/env python3
"""Generate or verify the deterministic direct-dependency CycloneDX document."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = (ROOT / "requirements.txt", ROOT / "RealLLM/requirements.txt")
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][^\s;]*)$")


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def project_version() -> str:
    for line in (ROOT / "CITATION.cff").read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    raise ValueError("CITATION.cff has no version")


def components() -> list[dict]:
    collected: dict[tuple[str, str], set[str]] = {}
    for manifest in MANIFESTS:
        source = str(manifest.relative_to(ROOT))
        for line_number, raw_line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), 1
        ):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = PIN.fullmatch(line)
            if match is None:
                raise ValueError(f"{source}:{line_number}: dependency is not pinned")
            key = (canonical_name(match.group(1)), match.group(2))
            collected.setdefault(key, set()).add(source)

    result = []
    for (name, version), sources in sorted(collected.items()):
        purl = f"pkg:pypi/{quote(name, safe='-')}@{quote(version, safe='.+!-')}"
        result.append(
            {
                "bom-ref": purl,
                "name": name,
                "properties": [
                    {
                        "name": "corelm:source-manifests",
                        "value": ", ".join(sorted(sources)),
                    }
                ],
                "purl": purl,
                "scope": "required",
                "type": "library",
                "version": version,
            }
        )
    return result


def document() -> dict:
    version = project_version()
    app_ref = f"pkg:github/ALLPROTO/core-lm-benchmark@{quote(version, safe='.-')}"
    entries = components()
    return {
        "bomFormat": "CycloneDX",
        "components": entries,
        "dependencies": [
            {
                "dependsOn": [entry["bom-ref"] for entry in entries],
                "ref": app_ref,
            }
        ],
        "metadata": {
            "component": {
                "bom-ref": app_ref,
                "name": "CoreLMBenchmark",
                "purl": app_ref,
                "type": "application",
                "version": version,
            },
            "properties": [
                {
                    "name": "corelm:sbom-scope",
                    "value": "direct-python-dependencies-only",
                }
            ],
        },
        "specVersion": "1.5",
        "version": 1,
    }


def serialized() -> str:
    return json.dumps(
        document(), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", type=Path)
    mode.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        expected = serialized()
    except (OSError, ValueError) as error:
        print(f"SBOM ERROR: {error}", file=sys.stderr)
        return 2
    if arguments.check is not None:
        target = (
            arguments.check
            if arguments.check.is_absolute()
            else ROOT / arguments.check
        )
        try:
            actual = target.read_text(encoding="utf-8")
        except OSError as error:
            print(f"SBOM CHECK ERROR: {error}", file=sys.stderr)
            return 2
        if actual != expected:
            print(f"SBOM CHECK FAIL: regenerate {target}", file=sys.stderr)
            return 1
        print(f"SBOM CHECK PASS: {target}")
        return 0
    if arguments.output is not None:
        target = (
            arguments.output
            if arguments.output.is_absolute()
            else ROOT / arguments.output
        )
        target.write_text(expected, encoding="utf-8")
        print(target)
        return 0
    sys.stdout.write(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
