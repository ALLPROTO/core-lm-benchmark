"""Optional worker sentinels. No torch import, CUDA init, peak reset, or sync.

Call start() before importing torch; phase(label) outside timed regions; finish()
at normal completion. All functions are no-ops outside a monitored invocation.
"""
import atexit
import json
import os
from pathlib import Path
import sys
import time

_started = False
_finished = False
_history_started = False
_history_max_entries = 1000000


def _event(kind, **kwargs):
    directory = os.environ.get("PHYSICAL_PEAK_RUN_DIR")
    if not directory:
        return
    event = {"run_id": os.environ.get("PHYSICAL_PEAK_RUN_ID"), "kind": kind,
             "pid": os.getpid(), "monotonic_ns": time.monotonic_ns(), "wall_time_ns": time.time_ns(), **kwargs}
    with (Path(directory) / "worker-events.jsonl").open("a") as stream:
        stream.write(json.dumps(event, allow_nan=False) + "\n")


def _torch_state():
    torch = sys.modules.get("torch")
    result = {"torch_imported": torch is not None, "cuda_initialized": False}
    if torch is None:
        return result
    result["cuda_initialized"] = torch.cuda.is_initialized()
    if not result["cuda_initialized"]:
        return result
    result["devices"] = []
    for device in range(torch.cuda.device_count()):
        stats = torch.cuda.memory_stats(device)
        result["devices"].append({"device": device,
            "uuid": str(getattr(torch.cuda.get_device_properties(device), "uuid", "unavailable")),
            "allocated_peak_bytes": int(torch.cuda.max_memory_allocated(device)),
            "reserved_peak_bytes": int(torch.cuda.max_memory_reserved(device)),
            "allocated_current_bytes": int(torch.cuda.memory_allocated(device)),
            "reserved_current_bytes": int(torch.cuda.memory_reserved(device)),
            "num_alloc_retries": stats.get("num_alloc_retries"), "num_ooms": stats.get("num_ooms"),
            "allocator_backend": torch.cuda.get_allocator_backend()})
    return result


def _state_safe():
    try:
        return _torch_state()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def start():
    global _started
    if _started or not os.environ.get("PHYSICAL_PEAK_RUN_DIR"):
        return
    _started = True
    _event("worker_start", torch_state=_state_safe(), argv=sys.argv)
    atexit.register(_exit)


def phase(label, **metadata):
    if os.environ.get("PHYSICAL_PEAK_RUN_DIR"):
        _event("phase", label=label, metadata=metadata, torch_state=_state_safe())


def enable_allocator_history():
    """Optional profiling only. Call after torch import, before any CUDA operation.

Uses a private PyTorch API with explicit failure reporting. Python allocation/free stacks are collected in this diagnostic-only copy.
Allocator high-water counters remain authoritative even if the trace is truncated.
"""
    global _history_started, _history_max_entries
    if _history_started or os.environ.get("PHYSICAL_PEAK_ALLOCATOR_HISTORY") != "1":
        return
    torch = sys.modules.get("torch")
    if torch is None:
        _event("allocator_history_error", error="Call after importing torch, before CUDA operations")
        return
    already_initialized = torch.cuda.is_initialized()
    try:
        _history_max_entries = int(os.environ.get("PHYSICAL_PEAK_HISTORY_MAX_ENTRIES", "1000000"))
        if not 1 <= _history_max_entries <= 100000:
            raise ValueError("Diagnostic event cap must be between 1 and 100000")
        if already_initialized:
            raise RuntimeError("History must start before CUDA initialization")
        torch.cuda.memory._record_memory_history(enabled="all", context="all", stacks="python", max_entries=_history_max_entries)
        _history_started = True
        _event("allocator_history_enabled", cuda_initialized_before_enable=already_initialized,
               max_entries=_history_max_entries, context="all", stacks="python", warning="PyTorch allocator events only; not all CUDA/driver physical allocations")
    except Exception as exc:
        _event("allocator_history_error", error=f"{type(exc).__name__}: {exc}")


def _save_history():
    if not _history_started:
        return
    try:
        import pickle
        torch = sys.modules["torch"]
        snapshot = torch.cuda.memory._snapshot()
        traces = snapshot.get("device_traces", [])
        counts = [len(trace) for trace in traces]
        output = Path(os.environ["PHYSICAL_PEAK_RUN_DIR"]) / "allocator-snapshot.pickle"
        with output.open("wb") as stream:
            pickle.dump(snapshot, stream, protocol=pickle.HIGHEST_PROTOCOL)
        _event("allocator_history_saved", path=output.name, event_counts=counts,
               configured_max_entries=_history_max_entries,
               possible_ring_truncation=any(count >= _history_max_entries for count in counts),
               warning="Only load this pickle from a trusted run; trace completeness must be audited separately")
    except Exception as exc:
        _event("allocator_history_error", error=f"{type(exc).__name__}: {exc}")


def finish():
    global _finished
    if _finished or not os.environ.get("PHYSICAL_PEAK_RUN_DIR"):
        return
    _finished = True
    _event("worker_finished", torch_state=_state_safe())
    _save_history()


def _exit():
    # This is before interpreter/driver teardown, not a physical process-exit event.
    _event("worker_atexit", normal_finish_called=_finished, torch_state=_state_safe())
