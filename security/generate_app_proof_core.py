#!/usr/bin/env python3
"""Derive the minimal app-proof engine from the frozen real-LLM engine.

The scientific implementation remains in ``benchmark_real_llm.py``.  The
macOS bundle does not need that module's exploratory grids, historical
backends, or command-line entry points, so this generator emits only the
functions reached by the fixed app proof and narrows encoding to VoidToken v5.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "RealLLM" / "benchmark_real_llm.py"
FREEZE = PROJECT_ROOT / "RealLLM" / "beacon_freeze.json"
REGISTRATION = PROJECT_ROOT / "RealLLM" / "v5_registration.json"
REFERENCE_RESULT = (
    PROJECT_ROOT / "app-real-llm-evidence" / "validation-064-071.json"
)
GENERATED = PROJECT_ROOT / "RealLLM" / "app_proof_core.py"

ROOT_SYMBOLS = {
    "PrimaryEvidenceWriter",
    "_aggregate_phase",
    "_evaluate_block",
    "_exclusive_write_bytes",
    "_resolve_device",
    "_token_blocks",
    "canonical_json_bytes",
    "sha256_bytes",
    "sha256_file",
}
CONSTANTS = {
    "BLOCK_TOKENS",
    "DATASET_FILES",
    "DATASET_REPOSITORY",
    "DATASET_REVISION",
    "MODEL_ASSET_FILES",
    "MODEL_REPOSITORY",
    "MODEL_REVISION",
    "MODEL_WEIGHTS_BYTES",
    "MODEL_WEIGHTS_SHA256",
    "PREDICTIONS_PER_BLOCK",
    "PREFILL_TOKENS",
    "THRESHOLDS",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _validate_frozen_source() -> None:
    freeze = _object(FREEZE)
    entries = {
        item.get("path"): item
        for item in freeze.get("normativeFiles", [])
        if isinstance(item, dict)
    }
    entry = entries.get("RealLLM/benchmark_real_llm.py")
    if not isinstance(entry, dict) or _sha256(SOURCE) != entry.get("sha256"):
        raise ValueError(
            "benchmark_real_llm.py differs from the public beacon freeze"
        )


def _definition_map(tree: ast.Module) -> dict[str, ast.AST]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
    }


def _reachable_definitions(
    definitions: dict[str, ast.AST],
) -> set[str]:
    selected: set[str] = set()
    pending = list(ROOT_SYMBOLS)
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        node = definitions.get(name)
        if node is None:
            raise ValueError(f"frozen engine no longer defines {name}")
        selected.add(name)
        references = {
            child.id
            for child in ast.walk(node)
            if isinstance(child, ast.Name)
            and isinstance(child.ctx, ast.Load)
        }
        pending.extend(sorted(references & definitions.keys()))
    selected.discard("_legacy_voidtoken_adapter")
    return selected


def _backend_comparison(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Compare) or len(node.ops) != 1:
        return None
    left = node.left
    if not (
        isinstance(left, ast.Subscript)
        and isinstance(left.value, ast.Name)
        and left.value.id == "configuration"
        and isinstance(left.slice, ast.Constant)
        and left.slice.value == "backend"
    ):
        return None
    comparator = node.comparators[0]
    if isinstance(comparator, ast.Constant) and isinstance(
        comparator.value, str
    ):
        return comparator.value
    return None


class _VoidTokenOnly(ast.NodeTransformer):
    """Remove unreachable backend branches from the bundled encoder."""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if node.name != "_encode_layers":
            return self.generic_visit(node)
        node = self.generic_visit(node)
        guard = ast.parse(
            """
if configuration != APP_CONFIGURATION:
    raise ValueError("app proof accepts only its registered configuration")
"""
        ).body
        node.body = guard + node.body
        return node

    def visit_If(self, node: ast.If) -> ast.AST | list[ast.stmt]:
        backend = _backend_comparison(node.test)
        if backend == "voidtoken-v5":
            return [self.visit(statement) for statement in node.body]
        if backend in {"voidtoken", "group-quant"}:
            if (
                len(node.orelse) == 1
                and isinstance(node.orelse[0], ast.If)
                and _backend_comparison(node.orelse[0].test)
                == "voidtoken-v5"
            ):
                return [
                    self.visit(statement)
                    for statement in node.orelse[0].body
                ]
        return self.generic_visit(node)


def _assigned_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            names.add(child.id)
    return names


def _registered_values() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    registration = _object(REGISTRATION)
    configuration = registration.get("configuration")
    result = _object(REFERENCE_RESULT)
    protocol = result.get("protocol")
    full_grid = (
        protocol.get("fullDevelopmentGrid")
        if isinstance(protocol, dict)
        else None
    )
    if not isinstance(configuration, dict):
        raise ValueError("v5 registration has no configuration")
    if (
        not isinstance(full_grid, list)
        or len(full_grid) <= 32
        or full_grid[32] != configuration
    ):
        raise ValueError("reference app grid differs from v5 registration")
    return configuration, full_grid


def generated_module() -> ast.Module:
    _validate_frozen_source()
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    definitions = _definition_map(tree)
    selected_names = _reachable_definitions(definitions)
    configuration, full_grid = _registered_values()

    body: list[ast.stmt] = ast.parse(
        '''"""Generated minimal engine for the fixed macOS app proof.

Do not edit this file directly; run security/generate_app_proof_core.py.
"""
from __future__ import annotations
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Iterable
import numpy as np
from RealLLM.voidtoken_v5 import VoidTokenV5Backend
'''
    ).body
    body.extend(
        ast.parse(
            "APP_CONFIGURATION = " + repr(configuration) + "\n"
            "FULL_DEVELOPMENT_GRID = " + repr(full_grid) + "\n"
        ).body
    )
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if _assigned_names(node) & CONSTANTS:
                body.append(node)
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            if node.name in selected_names:
                body.append(node)

    generated = ast.Module(body=body, type_ignores=[])
    generated = _VoidTokenOnly().visit(generated)
    ast.fix_missing_locations(generated)
    source = ast.unparse(generated).rstrip() + "\n"
    forbidden = (
        "legacy_voidtoken_adapter",
        "PackedGroupQuantBackend",
        "run_registered_pilot",
        "def main(",
        "def parse_arguments(",
    )
    if any(value in source for value in forbidden):
        raise ValueError("generated app core retains a non-production symbol")
    compile(source, str(GENERATED), "exec")
    return generated


def generate() -> bytes:
    return (ast.unparse(generated_module()).rstrip() + "\n").encode("utf-8")


def _semantic_ast(tree: ast.AST) -> str:
    # ast.unparse formatting differs between the system Python shipped by
    # macOS and the pinned app runtime.  Comparing the attribute-free AST
    # makes --verify version-independent while package cmp/provenance still
    # bind the exact checked-in bytes copied into the signed bundle.
    return ast.dump(tree, annotate_fields=True, include_attributes=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    arguments = parser.parse_args()
    if (arguments.output is None) == (arguments.verify is None):
        parser.error("choose exactly one of --output or --verify")
    if arguments.verify is not None:
        observed = ast.parse(
            arguments.verify.read_text(encoding="utf-8"),
            filename=str(arguments.verify),
        )
        if _semantic_ast(observed) != _semantic_ast(generated_module()):
            raise SystemExit(
                f"generated app core is stale: {arguments.verify}"
            )
        print(f"APP PROOF CORE PASS: {arguments.verify}")
        return 0
    expected = generate()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
