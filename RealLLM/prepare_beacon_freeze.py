#!/usr/bin/env python3
"""Print the second-commit freeze manifest for a clean protocol commit."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RealLLM.beacon_protocol import (  # noqa: E402
    FREEZE_PATH,
    SUITE_ID,
    canonical_json_bytes,
    durable_exclusive_write,
    git_file_bytes,
    implementation_sha256_at_commit,
    parse_json_bytes,
    require_clean_head,
    serialized_json_bytes,
    sha256_bytes,
)


def build_freeze_manifest(protocol_commit: str) -> dict[str, Any]:
    registration_bytes = git_file_bytes(
        protocol_commit, "RealLLM/beacon_registration.json"
    )
    registration = parse_json_bytes(
        registration_bytes, label="committed beacon registration"
    )
    if not isinstance(registration, dict) or registration.get("suiteId") != SUITE_ID:
        raise ValueError("protocol commit contains a different registration")
    source_files = registration.get("protocolSourceFiles")
    if not isinstance(source_files, list):
        raise ValueError("protocol commit has no normative source manifest")
    files: list[dict[str, Any]] = []
    for relative in source_files:
        content = git_file_bytes(protocol_commit, relative)
        files.append(
            {
                "path": relative,
                "bytes": len(content),
                "sha256": sha256_bytes(content),
            }
        )
    ledger_bytes = git_file_bytes(
        protocol_commit, "RealLLM/beacon_window_ledger.json"
    )
    return {
        "schemaVersion": "corelm-beacon-freeze-v1",
        "suiteId": SUITE_ID,
        "status": "protocol-files-frozen-before-beacon",
        "preparedAt": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "protocolCommit": protocol_commit,
        "registrationArtifactSHA256": sha256_bytes(registration_bytes),
        "registrationCanonicalSHA256": sha256_bytes(
            canonical_json_bytes(registration)
        ),
        "windowLedgerSHA256": sha256_bytes(ledger_bytes),
        "implementationSHA256": implementation_sha256_at_commit(
            protocol_commit
        ),
        "normativeFiles": files,
    }


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol-commit",
        help="full commit containing protocol files; defaults to clean HEAD",
    )
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help=(
            "durably create RealLLM/beacon_freeze.json after the clean-tree "
            "check; avoids shell redirection contaminating the preflight"
        ),
    )
    return parser.parse_args(arguments)


def main() -> int:
    arguments = parse_arguments()
    try:
        clean_head = require_clean_head()
        protocol_commit = arguments.protocol_commit or clean_head
        if protocol_commit != clean_head:
            raise ValueError(
                "freeze preparation must run at the exact clean protocol commit"
            )
        manifest = build_freeze_manifest(protocol_commit)
    except Exception as error:
        print(f"BEACON FREEZE PREPARATION FAILED: {error}", file=sys.stderr)
        return 1
    if arguments.write_manifest:
        try:
            durable_exclusive_write(FREEZE_PATH, serialized_json_bytes(manifest))
        except Exception as error:
            print(f"BEACON FREEZE WRITE FAILED: {error}", file=sys.stderr)
            return 1
        print(f"BEACON FREEZE MANIFEST CREATED: {FREEZE_PATH}")
    else:
        print(
            json.dumps(
                manifest,
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
