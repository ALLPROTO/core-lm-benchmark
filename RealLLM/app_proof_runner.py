#!/usr/bin/env python3
"""Run the single registered validation-only proof used by the macOS app."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTERED_CANDIDATE_INDEX = 32
SEED = 20260729
LIVE_EVENT_SCHEMA = "corelm-live-proof-event-v1"
LIVE_EVENT_PRODUCER = "app_worker"
LIVE_EVENT_INITIAL_SHA256 = "0" * 64
LIVE_EVENT_FACT_KEYS = {
    "runtime_ready": {"device", "python", "torch", "transformers"},
    "assets_verified": {
        "model_repository",
        "model_revision",
        "model_weights_sha256",
        "dataset_repository",
        "dataset_revision",
        "dataset_sha256",
        "split",
    },
    "model_load_started": set(),
    "model_loaded_mps": {
        "model_repository",
        "model_revision",
        "device",
        "parameter_count",
    },
    "token_slice_selected_and_hashed": {
        "start_block",
        "blocks",
        "tokens_per_block",
        "selected_token_ids_sha256",
    },
    "block_started": {"block_index", "ordinal", "total"},
    "codec_roundtrip_written": {
        "block_index",
        "layer_index",
        "bits",
        "container_bytes",
        "container_sha256",
    },
    "block_metrics_measured": {
        "block_index",
        "dense_bf16_bytes",
        "encoded_file_bytes",
        "compression_ratio_vs_bf16",
        "delta_nll_nat_per_token",
        "top1_agreement",
        "prediction_tokens",
    },
    "primary_evidence_sealed": {
        "container_count",
        "container_bytes",
        "blocks",
        "prediction_tokens",
        "manifest_sha256",
    },
    "result_sealed": {"result_sha256", "output_filename"},
    "run_complete": {"passed"},
}


def _canonical_live_event_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_session_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("live session ID must be a canonical UUID")
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError) as error:
        raise ValueError("live session ID must be a canonical UUID") from error
    if parsed.int == 0 or str(parsed) != value:
        raise ValueError("live session ID must be a canonical UUID")
    return value


def _sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError(f"{label} must be bounded non-empty text")
    if any(
        ord(character) < 0x20 or ord(character) == 0x7F
        for character in value
    ):
        raise ValueError(f"{label} contains a forbidden character")
    return value


def _integer(
    value: Any,
    label: str,
    *,
    minimum: int = 0,
    maximum: int = 2**63 - 1,
) -> int:
    if type(value) is not int or value < minimum or value > maximum:
        raise ValueError(f"{label} is outside its integer bound")
    return value


def _number(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if type(value) not in {int, float} or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be a finite number")
    observed = float(value)
    if minimum is not None and observed < minimum:
        raise ValueError(f"{label} is below its bound")
    if maximum is not None and observed > maximum:
        raise ValueError(f"{label} exceeds its bound")
    return observed


def _validate_live_event_facts(event: str, facts: dict[str, Any]) -> None:
    expected = LIVE_EVENT_FACT_KEYS.get(event)
    if expected is None or not isinstance(facts, dict) or set(facts) != expected:
        raise ValueError(f"{event} live-event facts are not exact")

    if event == "runtime_ready":
        if facts["device"] != "mps":
            raise ValueError("runtime_ready device must be mps")
        for name in ("python", "torch", "transformers"):
            _text(facts[name], f"runtime_ready {name}")
    elif event == "assets_verified":
        for name in (
            "model_repository",
            "model_revision",
            "dataset_repository",
            "dataset_revision",
        ):
            _text(facts[name], f"assets_verified {name}")
        _sha256(facts["model_weights_sha256"], "model weights")
        _sha256(facts["dataset_sha256"], "validation dataset")
        if facts["split"] != "validation":
            raise ValueError("assets_verified split must be validation")
    elif event == "model_load_started":
        return
    elif event == "model_loaded_mps":
        _text(facts["model_repository"], "loaded model repository")
        _text(facts["model_revision"], "loaded model revision")
        if facts["device"] != "mps":
            raise ValueError("model_loaded_mps device must be mps")
        _integer(
            facts["parameter_count"],
            "loaded model parameter count",
            minimum=1,
            maximum=10_000_000_000,
        )
    elif event == "token_slice_selected_and_hashed":
        _integer(facts["start_block"], "token slice start block", minimum=64)
        _integer(facts["blocks"], "token slice blocks", minimum=1, maximum=32)
        if facts["tokens_per_block"] != 512:
            raise ValueError("token slice must contain 512 tokens per block")
        _sha256(facts["selected_token_ids_sha256"], "selected token IDs")
    elif event == "block_started":
        _integer(facts["block_index"], "started block index", minimum=64)
        _integer(facts["ordinal"], "started block ordinal", minimum=1, maximum=32)
        _integer(facts["total"], "started block total", minimum=1, maximum=32)
    elif event == "codec_roundtrip_written":
        _integer(facts["block_index"], "container block index", minimum=64)
        _integer(facts["layer_index"], "container layer index", maximum=23)
        _integer(facts["bits"], "container bits", minimum=1, maximum=16)
        _integer(
            facts["container_bytes"],
            "container bytes",
            minimum=9,
            maximum=256 * 1024 * 1024,
        )
        _sha256(facts["container_sha256"], "container")
    elif event == "block_metrics_measured":
        _integer(facts["block_index"], "metric block index", minimum=64)
        dense_bytes = _integer(
            facts["dense_bf16_bytes"], "dense BF16 bytes", minimum=1
        )
        encoded_bytes = _integer(
            facts["encoded_file_bytes"], "encoded file bytes", minimum=1
        )
        ratio = _number(
            facts["compression_ratio_vs_bf16"],
            "block compression ratio",
            minimum=0.0,
            maximum=100.0,
        )
        if ratio != dense_bytes / encoded_bytes:
            raise ValueError("block compression ratio does not match byte counts")
        _number(
            facts["delta_nll_nat_per_token"],
            "block delta NLL",
            minimum=-100.0,
            maximum=100.0,
        )
        _number(
            facts["top1_agreement"],
            "block top-1 agreement",
            minimum=0.0,
            maximum=1.0,
        )
        if facts["prediction_tokens"] != 128:
            raise ValueError("block metrics must cover 128 prediction tokens")
    elif event == "primary_evidence_sealed":
        blocks = _integer(
            facts["blocks"], "primary evidence blocks", minimum=1, maximum=32
        )
        container_count = _integer(
            facts["container_count"],
            "primary evidence container count",
            minimum=1,
            maximum=32 * 24,
        )
        if container_count != blocks * 24:
            raise ValueError("primary evidence container count is inconsistent")
        _integer(
            facts["container_bytes"], "primary evidence container bytes", minimum=1
        )
        prediction_tokens = _integer(
            facts["prediction_tokens"],
            "primary evidence prediction tokens",
            minimum=1,
            maximum=32 * 128,
        )
        if prediction_tokens != blocks * 128:
            raise ValueError("primary evidence prediction count is inconsistent")
        _sha256(facts["manifest_sha256"], "primary evidence manifest")
    elif event == "result_sealed":
        _sha256(facts["result_sha256"], "sealed result")
        filename = _text(facts["output_filename"], "sealed output filename")
        if (
            filename in {".", ".."}
            or Path(filename).name != filename
            or "\\" in filename
        ):
            raise ValueError("sealed output filename is not a safe basename")
    elif event == "run_complete":
        if type(facts["passed"]) is not bool:
            raise ValueError("run_complete passed must be Boolean")


class LiveProofEventWriter:
    """Write a strict, hash-chained, machine-only live event sequence."""

    def __init__(self, session_id: str, stream: Any) -> None:
        self.session_id = _canonical_session_id(session_id)
        self.stream = stream
        self.sequence = 0
        self.previous_event_sha256 = LIVE_EVENT_INITIAL_SHA256
        self.stage = "runtime_ready"
        self.start_block: int | None = None
        self.total_blocks: int | None = None
        self.completed_blocks = 0
        self.active_block: int | None = None
        self.next_layer = 0
        self.device: str | None = None
        self.model_repository: str | None = None
        self.model_revision: str | None = None
        self.container_count = 0
        self.container_bytes = 0

    def _validate_transition(self, event: str, facts: dict[str, Any]) -> None:
        if self.stage == "runtime_ready":
            if event != "runtime_ready":
                raise ValueError("live event sequence must start with runtime_ready")
        elif self.stage == "assets_verified":
            if event != "assets_verified":
                raise ValueError("assets_verified live event is missing")
        elif self.stage == "model_load_started":
            if event != "model_load_started":
                raise ValueError("model_load_started live event is missing")
        elif self.stage == "model_loaded_mps":
            if event != "model_loaded_mps":
                raise ValueError("model_loaded_mps live event is missing")
            if (
                facts["model_repository"] != self.model_repository
                or facts["model_revision"] != self.model_revision
                or facts["device"] != self.device
            ):
                raise ValueError("loaded model facts differ from verified assets")
        elif self.stage == "token_slice_selected_and_hashed":
            if event != "token_slice_selected_and_hashed":
                raise ValueError("token slice live event is missing")
        elif self.stage == "blocks":
            if event == "block_started":
                if self.start_block is None or self.total_blocks is None:
                    raise ValueError("live block geometry is unavailable")
                if self.completed_blocks >= self.total_blocks:
                    raise ValueError("live event sequence contains an extra block")
                if facts != {
                    "block_index": self.start_block + self.completed_blocks,
                    "ordinal": self.completed_blocks + 1,
                    "total": self.total_blocks,
                }:
                    raise ValueError("block_started facts do not match the token slice")
            elif event == "primary_evidence_sealed":
                if self.total_blocks is None or self.completed_blocks != self.total_blocks:
                    raise ValueError("primary evidence was sealed before all blocks")
                if facts["blocks"] != self.total_blocks:
                    raise ValueError("primary evidence block count changed")
                if (
                    facts["container_count"] != self.container_count
                    or facts["container_bytes"] != self.container_bytes
                ):
                    raise ValueError("primary evidence totals differ from live containers")
            else:
                raise ValueError("live block event is out of order")
        elif self.stage == "layers":
            if self.active_block is None:
                raise ValueError("live layer event has no active block")
            if event == "codec_roundtrip_written":
                if self.next_layer >= 24 or (
                    facts["block_index"] != self.active_block
                    or facts["layer_index"] != self.next_layer
                ):
                    raise ValueError("codec live event block/layer order changed")
            elif event == "block_metrics_measured":
                if self.next_layer != 24 or facts["block_index"] != self.active_block:
                    raise ValueError("block metrics preceded 24 written containers")
            else:
                raise ValueError("live layer event is out of order")
        elif self.stage == "result_sealed":
            if event != "result_sealed":
                raise ValueError("result_sealed live event is missing")
            if self.start_block is None or self.total_blocks is None:
                raise ValueError("sealed result has no live block geometry")
            expected_filename = (
                f"validation-{self.start_block:03d}-"
                f"{self.start_block + self.total_blocks - 1:03d}.json"
            )
            if facts["output_filename"] != expected_filename:
                raise ValueError("sealed result filename differs from live block geometry")
        elif self.stage == "run_complete":
            if event != "run_complete":
                raise ValueError("run_complete live event is missing")
        else:
            raise ValueError("live event sequence is already complete")

    def _advance(self, event: str, facts: dict[str, Any]) -> None:
        if event == "runtime_ready":
            self.device = facts["device"]
            self.stage = "assets_verified"
        elif event == "assets_verified":
            self.model_repository = facts["model_repository"]
            self.model_revision = facts["model_revision"]
            self.stage = "model_load_started"
        elif event == "model_load_started":
            self.stage = "model_loaded_mps"
        elif event == "model_loaded_mps":
            self.stage = "token_slice_selected_and_hashed"
        elif event == "token_slice_selected_and_hashed":
            self.start_block = facts["start_block"]
            self.total_blocks = facts["blocks"]
            self.stage = "blocks"
        elif event == "block_started":
            self.active_block = facts["block_index"]
            self.next_layer = 0
            self.stage = "layers"
        elif event == "codec_roundtrip_written":
            self.next_layer += 1
            self.container_count += 1
            self.container_bytes += facts["container_bytes"]
        elif event == "block_metrics_measured":
            self.completed_blocks += 1
            self.active_block = None
            self.next_layer = 0
            self.stage = "blocks"
        elif event == "primary_evidence_sealed":
            self.stage = "result_sealed"
        elif event == "result_sealed":
            self.stage = "run_complete"
        elif event == "run_complete":
            self.stage = "complete"

    def emit(self, event: str, facts: dict[str, Any]) -> dict[str, Any]:
        _validate_live_event_facts(event, facts)
        self._validate_transition(event, facts)
        document = {
            "schema_version": LIVE_EVENT_SCHEMA,
            "session_id": self.session_id,
            "sequence": self.sequence + 1,
            "producer": LIVE_EVENT_PRODUCER,
            "event": event,
            "facts": dict(facts),
            "previous_event_sha256": self.previous_event_sha256,
        }
        canonical = _canonical_live_event_bytes(document)
        payload = canonical + b"\n"
        offset = 0
        while offset < len(payload):
            written = self.stream.write(payload[offset:])
            if type(written) is not int or written <= 0:
                raise OSError("live event stream write made no progress")
            offset += written
        self.stream.flush()
        self.previous_event_sha256 = hashlib.sha256(canonical).hexdigest()
        self.sequence += 1
        self._advance(event, facts)
        return document


def establish_worker_process_group() -> int:
    """Become a group leader before importing the model or starting work."""

    identifier = os.getpid()
    if os.getpgrp() != identifier:
        os.setpgid(0, 0)
    if os.getpgrp() != identifier:
        raise RuntimeError("worker could not establish its process group")
    return identifier


def register_worker_process_group(identifier: int) -> Path | None:
    """Publish the group PID for the outer proof's crash-only cleanup."""

    raw_path = os.environ.get("CORELM_WORKER_GROUP_FILE")
    if raw_path is None:
        return None
    path = Path(raw_path)
    if not path.is_absolute() or path.name != ".worker-process-group":
        raise ValueError("worker group file has an invalid path")
    parent_status = path.parent.stat()
    if (
        not path.parent.is_dir()
        or path.parent.is_symlink()
        or parent_status.st_uid != os.getuid()
        or parent_status.st_mode & 0o022
    ):
        raise ValueError("worker group file parent is not private")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        payload = f"{identifier}\n".encode("ascii")
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("worker group registration write stalled")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def remove_worker_process_group_registration(
    path: Path | None, identifier: int | None
) -> None:
    if path is None or identifier is None:
        return
    try:
        if path.is_symlink() or path.read_text(encoding="ascii") != (
            f"{identifier}\n"
        ):
            return
        path.unlink()
    except FileNotFoundError:
        pass


def _load_core() -> Any:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from RealLLM import app_proof_core

    return app_proof_core


def _download_validation_only(
    core: Any, local_files_only: bool
) -> dict[str, Path]:
    """Resolve and verify model weights plus validation, never test parquet."""

    from huggingface_hub import hf_hub_download

    model_path = Path(
        hf_hub_download(
            core.MODEL_REPOSITORY,
            revision=core.MODEL_REVISION,
            filename="model.safetensors",
            local_files_only=local_files_only,
            token=False,
        )
    )
    if model_path.stat().st_size != core.MODEL_WEIGHTS_BYTES:
        raise RuntimeError("pinned model weight size mismatch")
    if core.sha256_file(model_path) != core.MODEL_WEIGHTS_SHA256:
        raise RuntimeError("pinned model weight digest mismatch")
    for filename, asset in core.MODEL_ASSET_FILES.items():
        asset_path = Path(
            hf_hub_download(
                core.MODEL_REPOSITORY,
                revision=core.MODEL_REVISION,
                filename=filename,
                local_files_only=local_files_only,
                token=False,
            )
        )
        if asset_path.stat().st_size != asset["bytes"]:
            raise RuntimeError(f"pinned model asset size mismatch: {filename}")
        if core.sha256_file(asset_path) != asset["sha256"]:
            raise RuntimeError(
                f"pinned model asset digest mismatch: {filename}"
            )

    specification = core.DATASET_FILES["validation"]
    validation_path = Path(
        hf_hub_download(
            core.DATASET_REPOSITORY,
            repo_type="dataset",
            revision=core.DATASET_REVISION,
            filename=specification["path"],
            local_files_only=local_files_only,
            token=False,
        )
    )
    if validation_path.stat().st_size != specification["bytes"]:
        raise RuntimeError("pinned validation dataset size mismatch")
    if core.sha256_file(validation_path) != specification["sha256"]:
        raise RuntimeError("pinned validation dataset digest mismatch")
    return {
        "modelSnapshot": model_path.parent,
        "modelWeights": model_path,
        "validation": validation_path,
    }


def _live_primary_evidence_writer(
    core: Any,
    directory: Path,
    *,
    result_filename: str,
    live_events: LiveProofEventWriter,
) -> Any:
    bits_by_layer = core.APP_CONFIGURATION.get("bitsByLayer")
    if (
        not isinstance(bits_by_layer, list)
        or len(bits_by_layer) != 24
        or any(type(value) is not int for value in bits_by_layer)
    ):
        raise ValueError("app configuration has no exact 24-layer bit schedule")

    class LivePrimaryEvidenceWriter(core.PrimaryEvidenceWriter):
        def write_container(
            self,
            *,
            block_index: int,
            layer_index: int,
            container: bytes,
        ) -> None:
            super().write_container(
                block_index=block_index,
                layer_index=layer_index,
                container=container,
            )
            live_events.emit(
                "codec_roundtrip_written",
                {
                    "block_index": block_index,
                    "layer_index": layer_index,
                    "bits": bits_by_layer[layer_index],
                    "container_bytes": len(container),
                    "container_sha256": core.sha256_bytes(container),
                },
            )

    return LivePrimaryEvidenceWriter(
        directory,
        result_filename=result_filename,
    )


def run_app_proof(
    output_path: Path,
    *,
    device_requested: str,
    validation_start_block: int,
    validation_blocks: int,
    local_files_only: bool,
    primary_evidence_directory: Path,
    live_events: LiveProofEventWriter,
) -> dict[str, Any]:
    core = _load_core()
    if device_requested != "mps":
        raise ValueError("the production app proof requires MPS")
    if validation_start_block < 64 or validation_start_block > 512:
        raise ValueError("validation start block is outside the app limits")
    if validation_blocks < 1 or validation_blocks > 32:
        raise ValueError("validation block count is outside the app limits")
    if not local_files_only:
        raise ValueError("the production app proof requires offline assets")
    if (
        primary_evidence_directory.parent.resolve()
        != output_path.parent.resolve()
        or primary_evidence_directory.name != "primary-evidence"
    ):
        raise ValueError("primary evidence must be beside the result file")

    import numpy as np
    import pyarrow
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(SEED)
    np.random.seed(SEED)
    if hasattr(torch, "use_deterministic_algorithms"):
        torch.use_deterministic_algorithms(True, warn_only=True)
    device = core._resolve_device(device_requested, torch)
    live_events.emit(
        "runtime_ready",
        {
            "device": device,
            "python": platform.python_version(),
            "torch": str(torch.__version__),
            "transformers": str(transformers.__version__),
        },
    )
    primary_evidence_writer = _live_primary_evidence_writer(
        core,
        primary_evidence_directory,
        result_filename=output_path.name,
        live_events=live_events,
    )
    inputs = _download_validation_only(core, local_files_only)
    live_events.emit(
        "assets_verified",
        {
            "model_repository": core.MODEL_REPOSITORY,
            "model_revision": core.MODEL_REVISION,
            "model_weights_sha256": core.MODEL_WEIGHTS_SHA256,
            "dataset_repository": core.DATASET_REPOSITORY,
            "dataset_revision": core.DATASET_REVISION,
            "dataset_sha256": core.DATASET_FILES["validation"]["sha256"],
            "split": "validation",
        },
    )

    tokenizer = AutoTokenizer.from_pretrained(
        inputs["modelSnapshot"],
        local_files_only=True,
        trust_remote_code=False,
    )
    live_events.emit("model_load_started", {})
    model = AutoModelForCausalLM.from_pretrained(
        inputs["modelSnapshot"],
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.float32,
        attn_implementation="eager",
    ).to(device)
    model.eval()
    parameter_count = sum(
        int(parameter.numel()) for parameter in model.parameters()
    )
    live_events.emit(
        "model_loaded_mps",
        {
            "model_repository": core.MODEL_REPOSITORY,
            "model_revision": core.MODEL_REVISION,
            "device": device,
            "parameter_count": parameter_count,
        },
    )

    blocks, token_digest = core._token_blocks(
        tokenizer,
        inputs["validation"],
        validation_blocks,
        start_block=validation_start_block,
    )
    live_events.emit(
        "token_slice_selected_and_hashed",
        {
            "start_block": validation_start_block,
            "blocks": len(blocks),
            "tokens_per_block": core.BLOCK_TOKENS,
            "selected_token_ids_sha256": token_digest,
        },
    )
    configuration = core.APP_CONFIGURATION
    candidate_grid = (configuration,)
    baselines: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for relative_index, block in enumerate(blocks):
        block_index = validation_start_block + relative_index
        live_events.emit(
            "block_started",
            {
                "block_index": block_index,
                "ordinal": relative_index + 1,
                "total": len(blocks),
            },
        )
        print(
            f"validation block {relative_index + 1}/{len(blocks)} "
            f"(source block {block_index})",
            file=sys.stderr,
            flush=True,
        )
        baseline, candidates = core._evaluate_block(
            block,
            block_index,
            candidate_grid,
            model=model,
            device=device,
            torch_module=torch,
            primary_evidence_writer=primary_evidence_writer,
        )
        baselines.append(baseline)
        records.extend(candidates)
        if len(candidates) != 1:
            raise RuntimeError("app proof did not produce exactly one block record")
        block_record = candidates[0]
        dense_bytes = int(block_record["denseBF16Bytes"])
        encoded_bytes = int(block_record["encodedFileBytes"])
        live_events.emit(
            "block_metrics_measured",
            {
                "block_index": block_index,
                "dense_bf16_bytes": dense_bytes,
                "encoded_file_bytes": encoded_bytes,
                "compression_ratio_vs_bf16": dense_bytes / encoded_bytes,
                "delta_nll_nat_per_token": float(
                    block_record["deltaNLLNatPerToken"]
                ),
                "top1_agreement": float(block_record["top1Agreement"]),
                "prediction_tokens": int(block_record["predictionTokens"]),
            },
        )

    aggregates = core._aggregate_phase(candidate_grid, records)
    selected: dict[str, Any] | None = configuration
    selection_error: str | None = None
    if (
        aggregates[0]["compressionRatioVsBF16"]
        < core.THRESHOLDS["minimumCompressionRatioVsBF16"]
    ):
        selected = None
        selection_error = "registered app candidate missed the compression gate"
    result: dict[str, Any] = {
        "schemaVersion": "corelm-voidtoken-v5-validation-development-v3",
        "status": "validation-only-development",
        "createdAt": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "testDataOpened": False,
        "protocol": {
            "modelRepository": core.MODEL_REPOSITORY,
            "modelRevision": core.MODEL_REVISION,
            "modelWeightsSHA256": core.MODEL_WEIGHTS_SHA256,
            "datasetRepository": core.DATASET_REPOSITORY,
            "datasetRevision": core.DATASET_REVISION,
            "split": "validation",
            "validationStartBlock": validation_start_block,
            "validationBlocks": validation_blocks,
            "thresholds": core.THRESHOLDS,
            "fullDevelopmentGrid": core.FULL_DEVELOPMENT_GRID,
            "evaluatedCandidateIndices": [REGISTERED_CANDIDATE_INDEX],
            "evaluatedGrid": [configuration],
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "device": device,
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "numpy": np.__version__,
            "pyarrow": pyarrow.__version__,
            "hfHome": "configured" if os.environ.get("HF_HOME") else None,
            "seed": SEED,
        },
        "selectedTokenIdsSHA256": token_digest,
        "baselines": baselines,
        "records": records,
        "aggregates": aggregates,
        "selected": selected,
        "selectionError": selection_error,
    }
    primary_evidence = primary_evidence_writer.finalize()
    result["primaryEvidence"] = primary_evidence
    live_events.emit(
        "primary_evidence_sealed",
        {
            "container_count": primary_evidence["containerCount"],
            "container_bytes": primary_evidence["containerBytes"],
            "blocks": primary_evidence["blocks"],
            "prediction_tokens": primary_evidence["predictionTokens"],
            "manifest_sha256": primary_evidence["manifestSHA256"],
        },
    )
    result["resultSHA256"] = core.sha256_bytes(
        core.canonical_json_bytes(result)
    )
    core._exclusive_write_bytes(
        output_path,
        json.dumps(
            result,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n",
    )
    live_events.emit(
        "result_sealed",
        {
            "result_sha256": result["resultSHA256"],
            "output_filename": output_path.name,
        },
    )
    live_events.emit(
        "run_complete",
        {"passed": bool(aggregates[0]["pass"])},
    )
    return result


def _summary(result: dict[str, Any]) -> str:
    aggregate = result["aggregates"][0]
    return "\n".join(
        (
            "Core LM app proof complete.",
            f"Result SHA-256: {result['resultSHA256']}",
            (
                "- schedule="
                f"{aggregate['configuration']['schedule']}: "
                f"{aggregate['compressionRatioVsBF16']:.3f}x, "
                f"delta NLL {aggregate['deltaNLLNatPerToken']:+.6f}, "
                f"top-1 {aggregate['top1Agreement']:.4f}, "
                f"{'PASS' if aggregate['pass'] else 'FAIL'}"
            ),
        )
    )


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("mps",), required=True)
    parser.add_argument("--validation-start-block", type=int, required=True)
    parser.add_argument("--validation-blocks", type=int, required=True)
    parser.add_argument(
        "--candidate-index",
        type=int,
        choices=(REGISTERED_CANDIDATE_INDEX,),
        required=True,
    )
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument(
        "--primary-evidence-directory",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--live-session-id",
        type=_canonical_session_id,
        required=True,
    )
    return parser.parse_args(arguments)


def main() -> int:
    group_identifier: int | None = None
    group_file: Path | None = None
    try:
        group_identifier = establish_worker_process_group()
        group_file = register_worker_process_group(group_identifier)
        arguments = parse_arguments()
        live_events = LiveProofEventWriter(
            arguments.live_session_id,
            sys.stdout.buffer,
        )
        result = run_app_proof(
            arguments.output,
            device_requested=arguments.device,
            validation_start_block=arguments.validation_start_block,
            validation_blocks=arguments.validation_blocks,
            local_files_only=arguments.local_files_only,
            primary_evidence_directory=arguments.primary_evidence_directory,
            live_events=live_events,
        )
    except Exception as error:
        print(f"CORE LM APP PROOF FAILED: {error}", file=sys.stderr)
        return 1
    finally:
        remove_worker_process_group_registration(
            group_file, group_identifier
        )
    print(_summary(result), file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
