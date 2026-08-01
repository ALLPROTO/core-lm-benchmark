#!/usr/bin/env python3
"""Run one real Qwen/MPS block using deterministic synthetic token IDs.

The rehearsal never opens the registered test corpus, resolves a beacon
window, imports the one-shot runner, or writes to the normative result tree.
It uses only the installed hash-locked runtime and cached model bytes.
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from security import rehearse_beacon_protocol as protocol_rehearsal  # noqa: E402
from security.verify_locked_environment import verify_environment  # noqa: E402


REHEARSAL_CUTOFF = datetime(2026, 8, 2, 17, 0, tzinfo=timezone.utc)
RUNTIME = Path.home() / ".cache" / "corelm-app-runtime"
MODEL_CACHE = Path.home() / ".cache" / "corelm-model-assets"
RESULT_DIRECTORY = PROJECT_ROOT / "real-llm-beacon-results"
PROOF_LOCK_PARENT = Path.home() / ".cache" / "corelm-proof-runtimes"
PROOF_LOCK = PROOF_LOCK_PARENT / ".proof-run.lock"
MINIMUM_REHEARSAL_FREE_MEMORY_PERCENT = 35
MINIMUM_MODEL_LOADED_FREE_MEMORY_PERCENT = 20
SYNTHETIC_BLOCK_INDEX = 900


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _path_present(path: Path) -> bool:
    return os.path.lexists(path)


def _sanitized_subprocess(
    command: list[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
    )


def _require_ac_power() -> None:
    completed = _sanitized_subprocess(["/usr/bin/pmset", "-g", "batt"])
    if completed.returncode != 0:
        raise ValueError("cannot verify Mac power source")
    if "Now drawing from 'AC Power'" not in completed.stdout:
        raise ValueError(
            "model rehearsal requires AC Power; Battery Power is not allowed"
        )


def _memory_free_percent() -> int:
    completed = _sanitized_subprocess(["/usr/bin/memory_pressure", "-Q"])
    if completed.returncode != 0:
        raise ValueError("cannot read macOS memory pressure")
    prefix = "System-wide memory free percentage:"
    matches = [
        line[len(prefix) :].strip().removesuffix("%")
        for line in completed.stdout.splitlines()
        if line.startswith(prefix)
    ]
    if len(matches) != 1 or not matches[0].isdigit():
        raise ValueError("macOS memory-pressure output is unexpected")
    return int(matches[0])


def _require_resource_headroom() -> None:
    if sys.platform != "darwin":
        raise ValueError("model rehearsal requires macOS")
    machine = _sanitized_subprocess(["/usr/bin/uname", "-m"])
    if machine.returncode != 0 or machine.stdout.strip() != "arm64":
        raise ValueError("model rehearsal requires Apple Silicon")
    physical = _sanitized_subprocess(
        ["/usr/sbin/sysctl", "-n", "hw.memsize"]
    )
    try:
        physical_bytes = int(physical.stdout.strip())
    except ValueError as error:
        raise ValueError("cannot verify physical memory") from error
    if physical.returncode != 0 or physical_bytes < 8 * 1024 * 1024 * 1024:
        raise ValueError("model rehearsal requires at least 8 GiB unified memory")
    free = _memory_free_percent()
    if free < MINIMUM_REHEARSAL_FREE_MEMORY_PERCENT:
        raise ValueError(
            f"model rehearsal requires {MINIMUM_REHEARSAL_FREE_MEMORY_PERCENT}% "
            f"free memory; observed {free}%"
        )


def _require_private_cache(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} must be an existing absolute real directory")
    resolved = path.resolve(strict=True)
    status = resolved.stat()
    if (
        not stat.S_ISDIR(status.st_mode)
        or status.st_uid != os.getuid()
        or status.st_mode & 0o022
    ):
        raise ValueError(f"{label} must be owner-controlled and private")
    return resolved


def _acquire_proof_lock() -> Path:
    PROOF_LOCK_PARENT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if PROOF_LOCK_PARENT.is_symlink() or not PROOF_LOCK_PARENT.is_dir():
        raise ValueError("proof lock parent is unsafe")
    status = PROOF_LOCK_PARENT.stat()
    if status.st_uid != os.getuid() or status.st_mode & 0o022:
        raise ValueError("proof lock parent is not private")
    completed = _sanitized_subprocess(
        ["/usr/bin/shlock", "-p", str(os.getpid()), "-f", str(PROOF_LOCK)]
    )
    if completed.returncode != 0:
        raise ValueError("another Core LM proof or rehearsal is active")
    if PROOF_LOCK.is_symlink() or not PROOF_LOCK.is_file():
        _release_proof_lock(PROOF_LOCK)
        raise ValueError("shared proof lock was not created safely")
    return PROOF_LOCK


def _release_proof_lock(path: Path) -> None:
    if path != PROOF_LOCK or path.is_symlink() or not path.is_file():
        return
    try:
        owner = path.read_text(encoding="ascii").strip()
    except OSError:
        return
    if owner == str(os.getpid()):
        path.unlink()


def _configure_environment(
    registration: dict[str, Any], cache: Path
) -> None:
    for name in (
        "PYTHONHOME",
        "PYTHONINSPECT",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
    ):
        if os.environ.get(name):
            raise ValueError(f"Python injection environment is set: {name}")
    expected = registration.get("runtime", {}).get("processEnvironment")
    if not isinstance(expected, dict):
        raise ValueError("registered process environment is missing")
    allowed_mps = {
        name for name in expected if name.startswith("PYTORCH_MPS_")
    }
    unexpected_mps = sorted(
        name
        for name in os.environ
        if name.startswith("PYTORCH_MPS_") and name not in allowed_mps
    )
    if unexpected_mps:
        raise ValueError(
            "unregistered MPS environment variables are set: "
            + ", ".join(unexpected_mps)
        )
    for name, value in expected.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise ValueError("registered process environment is invalid")
        observed = os.environ.get(name)
        if observed is not None and observed != value:
            raise ValueError(f"ambient {name} differs from the frozen value")
        os.environ[name] = value
    os.environ["HF_HOME"] = str(cache)


def _write_requested(mode: object, flags: object) -> bool:
    return (
        isinstance(mode, str)
        and any(marker in mode for marker in ("w", "a", "x", "+"))
    ) or (
        isinstance(flags, int)
        and bool(
            flags
            & (
                os.O_WRONLY
                | os.O_RDWR
                | os.O_CREAT
                | os.O_TRUNC
                | os.O_APPEND
            )
        )
    )


def _install_model_guard() -> None:
    project_root = PROJECT_ROOT.resolve(strict=True)
    two_path_mutations = {
        "os.link",
        "os.rename",
        "os.symlink",
        "shutil.copyfile",
        "shutil.copymode",
        "shutil.copystat",
        "shutil.move",
    }

    def normalized_path(value: object) -> Path | None:
        if isinstance(value, int):
            return None
        try:
            return Path(os.fsdecode(value)).resolve(strict=False)
        except (OSError, TypeError, ValueError):
            return None

    def forbidden_dataset(path: Path) -> bool:
        lowered = path.as_posix().lower()
        return (
            path.name == "test-00000-of-00001.parquet"
            or "datasets--salesforce--wikitext" in lowered
            or "/salesforce/wikitext/" in lowered
        )

    def inside_project(path: Path) -> bool:
        return path == project_root or project_root in path.parents

    def guard(event: str, arguments: tuple[Any, ...]) -> None:
        if event == "open" and arguments:
            path = normalized_path(arguments[0])
            if path is None:
                return
            if forbidden_dataset(path):
                raise PermissionError(
                    "registered test corpus is forbidden in rehearsal"
                )
            mode = arguments[1] if len(arguments) > 1 else None
            flags = arguments[2] if len(arguments) > 2 else 0
            if inside_project(path) and _write_requested(mode, flags):
                raise PermissionError(
                    "repository writes are forbidden in model rehearsal"
                )
        elif event in {
            "os.chmod",
            "os.chown",
            "os.mkdir",
            "os.remove",
            "os.rename",
            "os.rmdir",
            "os.link",
            "os.mknod",
            "os.symlink",
            "os.truncate",
            "os.utime",
            "os.setxattr",
            "os.removexattr",
            "shutil.copyfile",
            "shutil.copymode",
            "shutil.copystat",
            "shutil.move",
            "shutil.rmtree",
        }:
            paths = (
                arguments[:2]
                if event in two_path_mutations
                else arguments[:1]
            )
            for value in paths:
                path = normalized_path(value)
                if path is not None and inside_project(path):
                    raise PermissionError(
                        "repository mutations are forbidden in model rehearsal"
                    )
        elif event.startswith("socket."):
            raise PermissionError("network is forbidden in model rehearsal")
        elif event == "subprocess.Popen":
            executable = str(arguments[0]) if arguments else ""
            if executable != "/usr/bin/memory_pressure":
                raise PermissionError(
                    "unexpected child process in model rehearsal"
                )

    sys.addaudithook(guard)


def _require_safe_temp_parent() -> Path:
    parent = Path(tempfile.gettempdir()).resolve(strict=True)
    project = PROJECT_ROOT.resolve(strict=True)
    if parent == project or project in parent.parents:
        raise ValueError("model rehearsal TMPDIR resolves inside the repository")
    return parent


def _forbidden_operation(*_arguments: Any, **_keywords: Any) -> Any:
    raise RuntimeError(
        "normative beacon operation is forbidden in model rehearsal"
    )


def _resolve_model_snapshot(runtime: dict[str, Any], cache: Path) -> Path:
    from RealLLM.benchmark_real_llm import (
        MODEL_ASSET_FILES,
        MODEL_REPOSITORY,
        MODEL_REVISION,
        MODEL_WEIGHTS_BYTES,
        MODEL_WEIGHTS_SHA256,
    )

    specifications = {
        "model.safetensors": {
            "bytes": MODEL_WEIGHTS_BYTES,
            "sha256": MODEL_WEIGHTS_SHA256,
        },
        **MODEL_ASSET_FILES,
    }
    downloader = runtime["huggingface_hub"].hf_hub_download
    snapshot: Path | None = None
    for filename, specification in specifications.items():
        path = Path(
            downloader(
                MODEL_REPOSITORY,
                revision=MODEL_REVISION,
                filename=filename,
                cache_dir=cache / "hub",
                local_files_only=True,
                token=False,
            )
        )
        if (
            path.stat().st_size != specification["bytes"]
            or protocol_rehearsal._sha256_file(path)
            != specification["sha256"]
        ):
            raise ValueError(f"cached model asset differs: {filename}")
        if snapshot is None:
            snapshot = path.parent
        elif path.parent != snapshot:
            raise ValueError(
                "cached model assets do not share one frozen snapshot"
            )
    if snapshot is None:
        raise ValueError("no model assets were resolved")
    return snapshot


def _synthetic_token_ids(vocabulary_size: int) -> list[int]:
    if type(vocabulary_size) is not int or vocabulary_size < 2:
        raise ValueError("model vocabulary size is invalid")
    domain = b"CoreLM/beacon-model-rehearsal/v1\0"
    return [
        int.from_bytes(
            hashlib.sha256(
                domain + index.to_bytes(4, "big")
            ).digest()[:8],
            "big",
        )
        % vocabulary_size
        for index in range(512)
    ]


def _run_model_block(cache: Path) -> dict[str, Any]:
    from RealLLM import beacon_evaluation as evaluation
    from RealLLM import beacon_protocol
    from RealLLM import benchmark_real_llm as benchmark
    from security.verify_primary_evidence import _parse_container

    beacon_protocol.fetch_nist_pulse = _forbidden_operation
    beacon_protocol.build_resolution = _forbidden_operation
    beacon_protocol.select_window = _forbidden_operation
    beacon_protocol.durable_exclusive_write = _forbidden_operation
    evaluation.run_selected_window = _forbidden_operation
    evaluation._resolve_model_and_test = _forbidden_operation
    benchmark._token_blocks = _forbidden_operation

    registration = beacon_protocol.load_registration()
    runtime = evaluation.prepare_runtime()
    torch = runtime["torch"]
    tokenizer: Any | None = None
    model: Any | None = None
    total_started = time.monotonic()
    try:
        snapshot = _resolve_model_snapshot(runtime, cache)
        tokenizer = runtime["AutoTokenizer"].from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
        )
        model = runtime["AutoModelForCausalLM"].from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
            dtype=torch.float32,
            attn_implementation="eager",
        ).to("mps")
        model.eval()
        if model.config._attn_implementation != "eager":
            raise RuntimeError("model did not retain eager attention")
        if str(next(model.parameters()).dtype) != "torch.float32":
            raise RuntimeError("model dtype differs from frozen float32")
        if next(model.parameters()).device.type != "mps":
            raise RuntimeError("model did not reach the MPS device")
        if hasattr(torch, "mps") and hasattr(torch.mps, "synchronize"):
            torch.mps.synchronize()
        loaded_free = _memory_free_percent()
        if loaded_free < MINIMUM_MODEL_LOADED_FREE_MEMORY_PERCENT:
            raise RuntimeError(
                "free memory after model load is below the rehearsal minimum: "
                f"{loaded_free}%"
            )
        vocabulary_size = int(model.config.vocab_size)
        if vocabulary_size != 151_936 or len(tokenizer) < 2:
            raise RuntimeError("model or tokenizer vocabulary is unexpected")
        seed = int(registration["execution"]["seed"])
        torch.manual_seed(seed)
        evaluation.np.random.seed(seed)
        if hasattr(torch, "use_deterministic_algorithms"):
            torch.use_deterministic_algorithms(True, warn_only=True)
        configuration = registration["configuration"]
        token_ids = _synthetic_token_ids(min(vocabulary_size, len(tokenizer)))
        block_started = time.monotonic()
        with tempfile.TemporaryDirectory(
            prefix="corelm-beacon-model-rehearsal-"
        ) as temporary:
            temp_root = Path(temporary).resolve(strict=True)
            if PROJECT_ROOT == temp_root or PROJECT_ROOT in temp_root.parents:
                raise RuntimeError(
                    "model rehearsal temp root is inside the repository"
                )
            writer = benchmark.PrimaryEvidenceWriter(
                temp_root / "primary-evidence",
                result_filename="synthetic-rehearsal.json",
            )
            baseline, records = benchmark._evaluate_block(
                token_ids,
                SYNTHETIC_BLOCK_INDEX,
                (configuration,),
                model=model,
                device="mps",
                torch_module=torch,
                primary_evidence_writer=writer,
            )
            if len(records) != 1:
                raise RuntimeError(
                    "model rehearsal produced an unexpected record count"
                )
            record = records[0]
            benchmark.validate_v5_container_manifest(record, configuration)
            descriptor = writer.finalize()
            manifest = record.get("containerManifest")
            if not isinstance(manifest, list) or len(manifest) != 24:
                raise RuntimeError(
                    "model rehearsal did not create 24 layer containers"
                )
            parsed_payload_bytes = 0
            for layer_index, entry in enumerate(manifest):
                container_path = (
                    temp_root
                    / "primary-evidence"
                    / "containers"
                    / f"block-{SYNTHETIC_BLOCK_INDEX:03d}"
                    / f"layer-{layer_index:02d}.vtl5"
                )
                payload_bytes, _ = _parse_container(
                    container_path.read_bytes(),
                    block_index=SYNTHETIC_BLOCK_INDEX,
                    layer_index=layer_index,
                    expected_manifest=entry,
                )
                parsed_payload_bytes += payload_bytes
            if parsed_payload_bytes != record.get("payloadBytes"):
                raise RuntimeError(
                    "independent parser payload accounting differs"
                )
            structural = (
                baseline.get("layers") == 24
                and baseline.get("trajectoryShapePerLayer") == [383, 256]
                and baseline.get("predictionTokens") == 128
                and baseline.get("exactRebuildMaxAbsLogitDifference") == 0.0
                and baseline.get("exactRebuildTop1Identical") is True
                and baseline.get("layoutRebuildMaxAbsLogitDifference") == 0.0
                and baseline.get("layoutRebuildTop1Identical") is True
            )
            if not structural:
                raise RuntimeError("synthetic block structural replay failed")
            if (
                descriptor.get("containerCount") != 24
                or descriptor.get("blocks") != 1
                or descriptor.get("predictionTokens") != 128
                or descriptor.get("containerBytes")
                != record.get("encodedFileBytes")
            ):
                raise RuntimeError(
                    "temporary primary-evidence topology differs"
                )
            block_elapsed = time.monotonic() - block_started
        total_elapsed = time.monotonic() - total_started
        return {
            "schemaVersion": "corelm-beacon-model-rehearsal-v1",
            "status": "PASS",
            "evidenceClass": "synthetic-rehearsal",
            "scientificEvidence": False,
            "countsTowardScientificVerdict": False,
            "selectedWindow": None,
            "targetBeaconFetched": False,
            "testDatasetOpened": False,
            "resultDirectoryWritten": False,
            "model": "Qwen2.5-0.5B",
            "device": "mps",
            "syntheticBlocks": 1,
            "layers": 24,
            "containersVerified": 24,
            "predictionTokens": 128,
            "structuralReplay": True,
            "blockElapsedSeconds": round(block_elapsed, 3),
            "totalElapsedSeconds": round(total_elapsed, 3),
        }
    finally:
        model = None
        tokenizer = None
        gc.collect()
        try:
            if hasattr(torch, "mps") and hasattr(torch.mps, "synchronize"):
                torch.mps.synchronize()
            if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()
        except Exception:
            pass


def _verify_postconditions(
    frozen_before: tuple[tuple[str, int, str], ...],
    results_before: Any,
    proof_before: Any,
) -> None:
    if protocol_rehearsal._frozen_snapshot() != frozen_before:
        raise RuntimeError("frozen files changed during model rehearsal")
    if protocol_rehearsal._snapshot_path(RESULT_DIRECTORY) != results_before:
        raise RuntimeError("normative result tree changed during model rehearsal")
    if protocol_rehearsal._snapshot_path(PROOF_LOCK) != proof_before:
        raise RuntimeError("proof lock survived model rehearsal")


def _execute_model_rehearsal(
    cache: Path,
    frozen_before: tuple[tuple[str, int, str], ...],
    results_before: Any,
    proof_before: Any,
) -> dict[str, Any]:
    lock = _acquire_proof_lock()
    try:
        _install_model_guard()
        return _run_model_block(cache)
    finally:
        try:
            _release_proof_lock(lock)
        finally:
            _verify_postconditions(frozen_before, results_before, proof_before)


def run_rehearsal() -> dict[str, Any]:
    if not sys.flags.isolated or not sys.flags.dont_write_bytecode:
        raise ValueError("model rehearsal requires Python -I -B")
    if _utc_now() >= REHEARSAL_CUTOFF:
        raise ValueError("pre-pulse model rehearsal cutoff has passed")
    present = [
        path.name
        for path in protocol_rehearsal.NORMATIVE_ARTIFACTS
        if _path_present(path)
    ]
    if present:
        raise ValueError("normative beacon artifacts already exist")
    _require_safe_temp_parent()
    _require_ac_power()
    _require_resource_headroom()
    runtime = _require_private_cache(RUNTIME, "locked runtime")
    cache = _require_private_cache(MODEL_CACHE, "model cache")
    verify_environment(
        runtime,
        [
            PROJECT_ROOT / ".github" / "locks" / "pip-bootstrap.txt",
            PROJECT_ROOT / "RealLLM" / "requirements.lock",
        ],
    )
    frozen_before = protocol_rehearsal._frozen_snapshot()
    results_before = protocol_rehearsal._snapshot_path(RESULT_DIRECTORY)
    proof_before = protocol_rehearsal._snapshot_path(PROOF_LOCK)
    if proof_before != {"kind": "absent"}:
        raise ValueError("a Core LM proof lock is already present")
    registration = protocol_rehearsal.protocol.load_registration()
    _configure_environment(registration, cache)
    receipt = _execute_model_rehearsal(
        cache,
        frozen_before,
        results_before,
        proof_before,
    )
    if _memory_free_percent() < 15:
        raise RuntimeError("memory headroom fell below the frozen minimum")
    return receipt


def main() -> int:
    if len(sys.argv) != 1:
        print(
            "MODEL REHEARSAL FAIL: command-line overrides are forbidden",
            file=sys.stderr,
        )
        return 2
    try:
        receipt = run_rehearsal()
    except Exception as error:
        print(f"MODEL REHEARSAL FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    print(
        "MODEL REHEARSAL PASS: real Qwen/MPS codec path passed on one "
        "synthetic block; the test corpus and scientific attempt are untouched."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
