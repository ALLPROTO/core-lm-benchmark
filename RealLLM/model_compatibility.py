#!/usr/bin/env python3
"""Inspect local causal-LM configuration metadata without executing a model.

This module is deliberately separate from the registered Qwen proof.  It does
not import Transformers, load weights, open a dataset, compute a metric, or
write evidence.  A positive inspection only means that a configuration has a
known structural adapter and is eligible for a future, separately pinned
admission run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path(__file__).with_name("pinned_model_registry.json")
REGISTRY_SHA256 = "05b1900a44462902a1a823a7e4213043cca3613a63c53f042ededa72dcbb9680"
MAXIMUM_CONFIG_BYTES = 1024 * 1024
CLASSIFICATION = "MODEL_METADATA_ADMISSION_NOT_BENCHMARK_EVIDENCE"
SCHEMA_VERSION = "corelm-model-compatibility-inspection-v1"


class CompatibilityError(ValueError):
    """A fail-closed metadata or path validation error."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _reject_duplicate_pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CompatibilityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _decode_json(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CompatibilityError(f"{label} is not UTF-8") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CompatibilityError(f"{label} contains non-finite {token}")
            ),
        )
    except json.JSONDecodeError as error:
        raise CompatibilityError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise CompatibilityError(f"{label} root must be an object")
    return value


def _require_exact_keys(value: dict[str, Any], keys: set[str], *, label: str) -> None:
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise CompatibilityError(
            f"{label} keys differ; missing={missing}, extra={extra}"
        )


def _require_identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(
        r"[a-z0-9][a-z0-9._-]{0,95}", value
    ) is None:
        raise CompatibilityError(f"{label} is not a bounded lowercase identifier")
    return value


def _require_string(value: Any, *, label: str, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise CompatibilityError(f"{label} is not a bounded printable string")
    return value


def _require_positive_int(
    value: Any,
    *,
    label: str,
    minimum: int,
    maximum: int,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise CompatibilityError(
            f"{label} must be an integer in {minimum}...{maximum}"
        )
    return value


def _require_bool(value: Any, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise CompatibilityError(f"{label} must be boolean")
    return value


def _registry() -> tuple[dict[str, Any], str]:
    raw = REGISTRY_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != REGISTRY_SHA256:
        raise CompatibilityError("pinned model registry digest differs")
    value = _decode_json(raw, label="pinned model registry")
    _require_exact_keys(
        value,
        {
            "adapters",
            "classification",
            "evidenceModelId",
            "limitations",
            "profiles",
            "schemaVersion",
        },
        label="pinned model registry",
    )
    if value["schemaVersion"] != "corelm-pinned-model-registry-v1":
        raise CompatibilityError("pinned model registry schema differs")
    if value["classification"] != CLASSIFICATION:
        raise CompatibilityError("pinned model registry classification differs")
    adapters = value["adapters"]
    profiles = value["profiles"]
    limitations = value["limitations"]
    if (
        not isinstance(adapters, list)
        or not adapters
        or not isinstance(profiles, list)
        or not profiles
        or not isinstance(limitations, list)
        or not limitations
    ):
        raise CompatibilityError("pinned model registry collections are invalid")

    adapter_ids: set[str] = set()
    type_to_adapter: dict[str, str] = {}
    architecture_to_adapter: dict[str, str] = {}
    for index, adapter in enumerate(adapters):
        label = f"adapter {index}"
        if not isinstance(adapter, dict):
            raise CompatibilityError(f"{label} must be an object")
        _require_exact_keys(
            adapter,
            {
                "adapterId",
                "architectures",
                "cacheAdapter",
                "modelTypes",
                "notes",
                "status",
            },
            label=label,
        )
        adapter_id = _require_identifier(adapter["adapterId"], label=f"{label} id")
        if adapter_id in adapter_ids:
            raise CompatibilityError("duplicate adapter id")
        adapter_ids.add(adapter_id)
        if adapter["cacheAdapter"] != "transformers-dynamic-cache-kv-v1":
            raise CompatibilityError(f"{label} cache adapter differs")
        if adapter["status"] != "admission-candidate":
            raise CompatibilityError(f"{label} status differs")
        _require_string(adapter["notes"], label=f"{label} notes", maximum=512)
        for key, destination in (
            ("modelTypes", type_to_adapter),
            ("architectures", architecture_to_adapter),
        ):
            entries = adapter[key]
            if not isinstance(entries, list) or len(entries) != 1:
                raise CompatibilityError(
                    f"{label} {key} must contain exactly one entry"
                )
            for entry in entries:
                name = _require_string(entry, label=f"{label} {key} entry")
                if name in destination:
                    raise CompatibilityError(f"duplicate registered {key} entry: {name}")
                destination[name] = adapter_id

    profile_ids: set[str] = set()
    for index, profile in enumerate(profiles):
        label = f"profile {index}"
        if not isinstance(profile, dict):
            raise CompatibilityError(f"{label} must be an object")
        _require_exact_keys(
            profile,
            {
                "adapterId",
                "architecture",
                "config",
                "files",
                "license",
                "modelType",
                "profileId",
                "repository",
                "revision",
                "status",
                "trustRemoteCode",
            },
            label=label,
        )
        profile_id = _require_identifier(profile["profileId"], label=f"{label} id")
        if profile_id in profile_ids:
            raise CompatibilityError("duplicate profile id")
        profile_ids.add(profile_id)
        if profile["adapterId"] not in adapter_ids:
            raise CompatibilityError(f"{label} references unknown adapter")
        if profile["status"] != "registered-evidence-model":
            raise CompatibilityError(f"{label} status differs")
        if profile["trustRemoteCode"] is not False:
            raise CompatibilityError(f"{label} must forbid remote code")
        revision = _require_string(profile["revision"], label=f"{label} revision")
        if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
            raise CompatibilityError(f"{label} revision is not a full lowercase commit")
        _require_string(profile["repository"], label=f"{label} repository")
        _require_string(profile["license"], label=f"{label} license")
        profile_architecture = _require_string(
            profile["architecture"], label=f"{label} architecture"
        )
        profile_model_type = _require_string(
            profile["modelType"], label=f"{label} model type"
        )
        if (
            architecture_to_adapter.get(profile_architecture)
            != profile["adapterId"]
            or type_to_adapter.get(profile_model_type) != profile["adapterId"]
        ):
            raise CompatibilityError(f"{label} architecture adapter differs")
        files = profile["files"]
        if not isinstance(files, list) or not files:
            raise CompatibilityError(f"{label} files are invalid")
        paths: set[str] = set()
        for file_index, record in enumerate(files):
            if not isinstance(record, dict):
                raise CompatibilityError(f"{label} file must be an object")
            _require_exact_keys(
                record,
                {"bytes", "path", "role", "sha256"},
                label=f"{label} file {file_index}",
            )
            path = _require_string(record["path"], label=f"{label} file path")
            if path.startswith("/") or ".." in Path(path).parts or path in paths:
                raise CompatibilityError(f"{label} file path is unsafe or duplicate")
            paths.add(path)
            _require_identifier(record["role"], label=f"{label} file role")
            _require_positive_int(
                record["bytes"],
                label=f"{label} file bytes",
                minimum=1,
                maximum=10**12,
            )
            digest_value = _require_string(
                record["sha256"], label=f"{label} file digest"
            )
            if len(digest_value) != 64 or any(
                character not in "0123456789abcdef" for character in digest_value
            ):
                raise CompatibilityError(f"{label} file digest is malformed")
        if not isinstance(profile["config"], dict):
            raise CompatibilityError(f"{label} config must be an object")
        geometry = profile["config"]
        _require_exact_keys(
            geometry,
            {
                "attentionHeads",
                "contextLength",
                "headDimension",
                "hiddenSize",
                "kvHeads",
                "layers",
                "vocabularySize",
            },
            label=f"{label} config",
        )
        for key, minimum, maximum in (
            ("attentionHeads", 1, 256),
            ("contextLength", 16, 10_000_000),
            ("headDimension", 8, 512),
            ("hiddenSize", 16, 32768),
            ("kvHeads", 1, 256),
            ("layers", 1, 256),
            ("vocabularySize", 256, 10_000_000),
        ):
            _require_positive_int(
                geometry[key],
                label=f"{label} config {key}",
                minimum=minimum,
                maximum=maximum,
            )
        if geometry["attentionHeads"] % geometry["kvHeads"]:
            raise CompatibilityError(f"{label} config KV geometry differs")

    evidence_model_id = _require_identifier(
        value["evidenceModelId"], label="evidence model id"
    )
    if evidence_model_id not in profile_ids:
        raise CompatibilityError("evidence model id is not a registered profile")
    for index, limitation in enumerate(limitations):
        _require_string(limitation, label=f"limitation {index}", maximum=512)
    return value, digest


def _safe_config_bytes(raw_path: str) -> tuple[Path, bytes]:
    if not raw_path or any(
        ord(character) < 32 or ord(character) == 127 for character in raw_path
    ):
        raise CompatibilityError("config path is empty or contains a control character")
    path = Path(raw_path)
    if not path.is_absolute():
        raise CompatibilityError("config path must be absolute")
    standardized = Path(os.path.normpath(raw_path))
    if standardized != path or str(path) != raw_path:
        raise CompatibilityError("config path must be canonical")
    status = path.lstat()
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_uid != os.getuid()
        or status.st_nlink != 1
        or status.st_mode & 0o022
        or status.st_size < 2
        or status.st_size > MAXIMUM_CONFIG_BYTES
    ):
        raise CompatibilityError("config must be a private owner-controlled regular file")
    if path.resolve(strict=True) != path:
        raise CompatibilityError("config path contains a symlink")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != status.st_dev
            or opened.st_ino != status.st_ino
            or opened.st_size != status.st_size
        ):
            raise CompatibilityError("config changed before reading")
        chunks = []
        remaining = MAXIMUM_CONFIG_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        finished = os.fstat(descriptor)
        path_finished = path.lstat()
        if (
            len(raw) != opened.st_size
            or finished.st_size != opened.st_size
            or finished.st_mtime_ns != opened.st_mtime_ns
            or finished.st_ctime_ns != opened.st_ctime_ns
            or path_finished.st_dev != opened.st_dev
            or path_finished.st_ino != opened.st_ino
            or path_finished.st_size != opened.st_size
            or path_finished.st_uid != opened.st_uid
            or path_finished.st_nlink != 1
            or path_finished.st_mode & 0o022
            or path_finished.st_mtime_ns != opened.st_mtime_ns
            or path_finished.st_ctime_ns != opened.st_ctime_ns
            or not stat.S_ISREG(path_finished.st_mode)
            or stat.S_ISLNK(path_finished.st_mode)
            or path.resolve(strict=True) != path
        ):
            raise CompatibilityError("config changed while reading")
    finally:
        os.close(descriptor)
    return path, raw


def _config_integer(config: dict[str, Any], keys: tuple[str, ...], *, label: str, minimum: int, maximum: int) -> int:
    present = [key for key in keys if key in config]
    if len(present) != 1:
        raise CompatibilityError(f"{label} must use exactly one of {list(keys)}")
    return _require_positive_int(
        config[present[0]], label=label, minimum=minimum, maximum=maximum
    )


def analyze_config(
    config: dict[str, Any],
    registry: dict[str, Any],
    *,
    config_sha256: str | None = None,
) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise CompatibilityError("model config root must be an object")
    if config.get("is_encoder_decoder", False) is not False:
        raise CompatibilityError("encoder-decoder models are outside this causal-LM lane")
    if config.get("add_cross_attention", False) is not False:
        raise CompatibilityError("cross-attention models are outside this causal-LM lane")
    for forbidden in (
        "auto_map",
        "quantization_config",
        "vision_config",
        "audio_config",
        "image_token_id",
        "mm_projector_type",
    ):
        if forbidden in config:
            raise CompatibilityError(f"model config contains forbidden key: {forbidden}")
    if config.get("trust_remote_code", False) is not False:
        raise CompatibilityError("remote model code is forbidden")
    for key in config:
        lowered = key.lower()
        if "expert" in lowered or "moe" in lowered:
            raise CompatibilityError("mixture-of-experts models are outside this lane")
    if "layer_types" in config:
        raise CompatibilityError("hybrid per-layer cache topology is outside this lane")
    if config.get("cache_implementation") not in (None, "dynamic"):
        raise CompatibilityError("non-dynamic cache implementations are outside this lane")
    if config.get("use_cache", True) is not True:
        raise CompatibilityError("model config must enable cache output")

    model_type = _require_string(config.get("model_type"), label="model_type")
    architectures_value = config.get("architectures")
    if (
        not isinstance(architectures_value, list)
        or len(architectures_value) != 1
    ):
        raise CompatibilityError("architectures must contain exactly one class")
    architecture = _require_string(
        architectures_value[0], label="architecture class"
    )

    matched: dict[str, Any] | None = None
    for adapter in registry["adapters"]:
        if model_type in adapter["modelTypes"] and architecture in adapter["architectures"]:
            matched = adapter
            break
    if matched is None:
        raise CompatibilityError(
            f"unsupported causal-LM architecture pair: {model_type}/{architecture}"
        )

    if model_type == "gpt2":
        layers = _config_integer(config, ("n_layer",), label="layers", minimum=1, maximum=256)
        hidden = _config_integer(config, ("n_embd",), label="hidden size", minimum=16, maximum=32768)
        attention_heads = _config_integer(config, ("n_head",), label="attention heads", minimum=1, maximum=256)
        kv_heads = attention_heads
        context = _config_integer(config, ("n_positions",), label="context length", minimum=16, maximum=10_000_000)
    else:
        layers = _config_integer(config, ("num_hidden_layers",), label="layers", minimum=1, maximum=256)
        hidden = _config_integer(config, ("hidden_size",), label="hidden size", minimum=16, maximum=32768)
        attention_heads = _config_integer(config, ("num_attention_heads",), label="attention heads", minimum=1, maximum=256)
        if "num_key_value_heads" in config:
            kv_heads = _config_integer(config, ("num_key_value_heads",), label="KV heads", minimum=1, maximum=256)
        else:
            kv_heads = attention_heads
        context = _config_integer(config, ("max_position_embeddings",), label="context length", minimum=16, maximum=10_000_000)
    vocab = _config_integer(config, ("vocab_size",), label="vocabulary size", minimum=256, maximum=10_000_000)
    if "head_dim" in config:
        head_dimension = _config_integer(config, ("head_dim",), label="head dimension", minimum=8, maximum=512)
    else:
        if hidden % attention_heads:
            raise CompatibilityError("hidden size is not divisible by attention heads")
        head_dimension = hidden // attention_heads
    if attention_heads % kv_heads:
        raise CompatibilityError("attention heads are not divisible by KV heads")

    cache_policy = "full-context-dynamic-cache"
    if model_type == "mistral":
        sliding = _require_positive_int(
            config.get("sliding_window"),
            label="sliding window",
            minimum=16,
            maximum=context,
        )
        cache_policy = f"sliding-window-dynamic-cache:{sliding}"
    elif "sliding_window" in config and config["sliding_window"] not in (None, False):
        if not (
            model_type == "qwen2"
            and config.get("use_sliding_window") is False
        ):
            raise CompatibilityError("unexpected sliding-window cache configuration")

    geometry_profile = None
    exact_config_profile = None
    for profile in registry["profiles"]:
        expected = profile["config"]
        if (
            profile["modelType"] == model_type
            and profile["architecture"] == architecture
            and expected
            == {
                "attentionHeads": attention_heads,
                "contextLength": context,
                "headDimension": head_dimension,
                "hiddenSize": hidden,
                "kvHeads": kv_heads,
                "layers": layers,
                "vocabularySize": vocab,
            }
        ):
            geometry_profile = profile["profileId"]
            pinned_config = next(
                (
                    record
                    for record in profile["files"]
                    if record["role"] == "model-config"
                ),
                None,
            )
            if (
                pinned_config is not None
                and config_sha256 == pinned_config["sha256"]
            ):
                exact_config_profile = profile["profileId"]
            break

    return {
        "adapterId": matched["adapterId"],
        "architecture": architecture,
        "cacheAdapter": matched["cacheAdapter"],
        "cachePolicy": cache_policy,
        "exactRegisteredConfigProfile": exact_config_profile,
        "geometry": {
            "attentionHeads": attention_heads,
            "contextLength": context,
            "headDimension": head_dimension,
            "hiddenSize": hidden,
            "kvHeads": kv_heads,
            "layers": layers,
            "vocabularySize": vocab,
        },
        "modelType": model_type,
        "matchingRegisteredGeometryProfile": geometry_profile,
        "status": (
            "registered-config-bytes-match"
            if exact_config_profile is not None
            else "eligible-for-separate-pinned-admission"
        ),
    }


def list_report() -> dict[str, Any]:
    registry, digest = _registry()
    return {
        "acceptedAsBenchmarkEvidence": False,
        "action": "list",
        "adapters": registry["adapters"],
        "classification": CLASSIFICATION,
        "countsTowardScientificVerdict": False,
        "limitations": registry["limitations"],
        "modelExecuted": False,
        "profiles": registry["profiles"],
        "registrySHA256": digest,
        "schemaVersion": SCHEMA_VERSION,
    }


def inspect_report(raw_path: str) -> dict[str, Any]:
    registry, digest = _registry()
    path, raw = _safe_config_bytes(raw_path)
    config = _decode_json(raw, label="model config")
    config_digest = hashlib.sha256(raw).hexdigest()
    analysis = analyze_config(
        config,
        registry,
        config_sha256=config_digest,
    )
    return {
        "acceptedAsBenchmarkEvidence": False,
        "action": "inspect-config",
        "analysis": analysis,
        "classification": CLASSIFICATION,
        "configPath": str(path),
        "configSHA256": config_digest,
        "countsTowardScientificVerdict": False,
        "modelExecuted": False,
        "registrySHA256": digest,
        "schemaVersion": SCHEMA_VERSION,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect causal-LM metadata without loading or executing a model."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="list closed architecture adapters")
    inspect = subparsers.add_parser(
        "inspect-config", help="inspect one owner-controlled local config.json"
    )
    inspect.add_argument("config", help="absolute canonical config.json path")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = (
            list_report()
            if arguments.command == "list"
            else inspect_report(arguments.config)
        )
    except (CompatibilityError, FileNotFoundError, OSError) as error:
        print(f"MODEL COMPATIBILITY FAIL: {error}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
