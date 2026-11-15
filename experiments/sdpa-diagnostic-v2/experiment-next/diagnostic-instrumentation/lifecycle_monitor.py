#!/usr/bin/env python3
"""External lifetime NVML sampling with a pre-exec gate and post-exit tail.

This is not an exact continuous physical-memory peak meter. It never enables
accounting mode, changes GPU settings, resets CUDA peaks, or launches CUDA itself.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time
import uuid

from capability_check import plain, safe


def write_json(path, value):
    temporary = Path(str(path) + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_memory(value):
    return isinstance(value, int) and 0 <= value < (1 << 63)


def percentile(values, quantile):
    if not values:
        return None
    return sorted(values)[min(len(values) - 1, math.ceil(quantile * len(values)) - 1)]


def read_events(path):
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"kind": "invalid_json_line", "line": line})
    return events


class Monitor:
    def __init__(self, nv, handle, args, output):
        self.nv, self.handle, self.args, self.output = nv, handle, args, output
        self.aliases = set()
        self.observed_pids = set()
        self.device_peak = None
        self.process_peak = None
        self.target_samples = 0
        self.count = 0
        self.first_ns = self.last_ns = self.previous_ns = None
        self.gaps_ns = []
        self.query_durations_ns = []
        self.query_errors = {}
        self.external_pids = set()
        self.initial_pids = set()
        self.accounting_rows = []
        self.last_accounting_ns = 0
        self.accounting_mode = safe(lambda: int(nv.nvmlDeviceGetAccountingMode(handle)))
        self.accounting_enabled = self.accounting_mode.get("value") == 1
        self.accounting_baseline_pids = safe(lambda: plain(nv.nvmlDeviceGetAccountingPids(handle)))
        self.accounting_baseline_stats = {}
        self.raw = (output / "samples.jsonl").open("w", buffering=1024 * 1024)

    def query(self, label, call):
        start = time.monotonic_ns()
        result = safe(call)
        end = time.monotonic_ns()
        if not result["ok"]:
            key = label + ": " + result["error"]
            self.query_errors[key] = self.query_errors.get(key, 0) + 1
        return {"start_ns": start, "end_ns": end, **result}

    def processes(self, name):
        return [{"pid": int(row.pid), "used_bytes": int(row.usedGpuMemory) if valid_memory(row.usedGpuMemory) else None,
                 **{key: int(getattr(row, key)) for key in ("gpuInstanceId", "computeInstanceId") if hasattr(row, key)}}
                for row in getattr(self.nv, name)(self.handle)]

    def account(self, pids, stage):
        if not self.accounting_enabled:
            return
        for pid in sorted(set(pids)):
            row = {"pid": pid, "stage": stage,
                   **self.query("accounting", lambda pid=pid: plain(self.nv.nvmlDeviceGetAccountingStats(self.handle, pid)))}
            self.accounting_rows.append(row)

    def sample(self, stage):
        start = time.monotonic_ns()
        row = {"sample_index": self.count, "stage": stage, "start_ns": start, "wall_time_ns": time.time_ns()}
        row["device"] = self.query("device", lambda: plain(self.nv.nvmlDeviceGetMemoryInfo(self.handle)))
        # Independent queries are not atomic with one another; retain both times.
        row["compute"] = self.query("compute", lambda: self.processes("nvmlDeviceGetComputeRunningProcesses"))
        row["graphics"] = self.query("graphics", lambda: self.processes("nvmlDeviceGetGraphicsRunningProcesses"))
        rows = row["compute"].get("value", []) + row["graphics"].get("value", [])
        pids = {p["pid"] for p in rows}
        self.observed_pids.update(pids)
        if stage == "prelaunch":
            self.initial_pids.update(pids)
        self.external_pids.update(pids - self.aliases)
        # Matching requires observed namespace PID identity, never guessed offset or singleton inference.
        matched = [p["used_bytes"] for p in rows if p["pid"] in self.aliases and p["used_bytes"] is not None]
        process_used = max(matched) if matched else None
        row["matched_target_used_bytes"] = process_used
        if process_used is not None:
            self.target_samples += 1
            self.process_peak = max(self.process_peak or 0, process_used)
        device_used = row["device"].get("value", {}).get("used")
        if valid_memory(device_used):
            self.device_peak = max(self.device_peak or 0, device_used)
        if self.accounting_enabled and start - self.last_accounting_ns >= int(self.args.accounting_interval_ms * 1e6):
            self.account(self.aliases | pids, stage)
            self.last_accounting_ns = start
        end = time.monotonic_ns()
        row["end_ns"] = end
        row["query_cycle_ns"] = end - start
        self.raw.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
        if self.previous_ns is not None:
            self.gaps_ns.append(start - self.previous_ns)
        self.query_durations_ns.append(end - start)
        self.first_ns = self.first_ns if self.first_ns is not None else start
        self.previous_ns = self.last_ns = start
        self.count += 1
        return row

    def sleep(self, sample):
        # Requested interval is start-to-start, not a delay added to query time.
        left_ns = int(self.args.interval_ms * 1e6) - (time.monotonic_ns() - sample["start_ns"])
        if left_ns > 0:
            time.sleep(left_ns / 1e9)

    def sample_for(self, duration_s, stage):
        end = time.monotonic() + duration_s
        while True:
            row = self.sample(stage)
            if time.monotonic() >= end:
                break
            self.sleep(row)

    def close(self):
        self.raw.flush()
        self.raw.close()

    def summary(self):
        return {"sample_count": self.count, "target_sample_count": self.target_samples,
            "sampled_device_max_bytes": self.device_peak, "sampled_matched_process_max_bytes": self.process_peak,
            "metric_warning": "Sampled maxima are observed NVML lower bounds, not certified continuous physical peaks. NVML accounting is separate.",
            "first_sample_start_ns": self.first_ns, "last_sample_start_ns": self.last_ns,
            "actual_start_gap_ms": {"max": max(self.gaps_ns, default=0) / 1e6,
                "p50": (percentile(self.gaps_ns, .5) or 0) / 1e6,
                "p99": (percentile(self.gaps_ns, .99) or 0) / 1e6,
                "count_above_requested": sum(v > self.args.interval_ms * 1e6 for v in self.gaps_ns)},
            "max_query_cycle_ms": max(self.query_durations_ns, default=0) / 1e6,
            "pid_namespace_aliases": sorted(self.aliases), "initial_gpu_pids": sorted(self.initial_pids),
            "observed_gpu_pids": sorted(self.observed_pids), "observed_external_or_unmapped_pids": sorted(self.external_pids - self.aliases),
            "process_identity_status": "matched_by_namespace_pid" if self.target_samples else "no_verified_nvml_pid_match",
            "query_errors": self.query_errors,
            "contamination_warning": "Absence in finite samples does not rule out short-lived external GPU users; unknown namespace PIDs are not assumed to be the target."}


def accounting_summary(monitor):
    grouped = {}
    for row in monitor.accounting_rows:
        if not row.get("ok"):
            continue
        value = row["value"]
        identity = (row["pid"], value.get("startTime"))
        item = grouped.setdefault(identity, {"pid": row["pid"], "startTime": value.get("startTime"),
            "namespace_pid_matches_worker": row["pid"] in monitor.aliases,
            "maxMemoryUsage": None, "observed_running": False, "observed_terminated": False, "observations": 0})
        item["observations"] += 1
        memory = value.get("maxMemoryUsage")
        if valid_memory(memory):
            item["maxMemoryUsage"] = max(item["maxMemoryUsage"] or 0, memory)
        item["observed_running"] |= bool(value.get("isRunning"))
        item["observed_terminated"] |= value.get("isRunning") == 0
    return {"mode_at_start": monitor.accounting_mode, "settings_changed": False,
        "baseline_accounted_pids": monitor.accounting_baseline_pids,
        "baseline_target_stats": monitor.accounting_baseline_stats,
        "identity_groups": list(grouped.values()),
        "metric_label": "NVML driver-reported lifetime maximum allocated memory (maxMemoryUsage)",
        "warning": "Not independently certified event-complete physical residency. UUID + PID + startTime and terminated record must be audited; pre-existing PID records and buffer eviction are possible.",
        "rows": monitor.accounting_rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uuid", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval-ms", type=float, default=1)
    parser.add_argument("--baseline-ms", type=float, default=50)
    parser.add_argument("--post-exit-ms", type=float, default=250)
    parser.add_argument("--accounting-interval-ms", type=float, default=50)
    parser.add_argument("--timeout-s", type=float, default=7200)
    parser.add_argument("--gate-timeout-s", type=float, default=30)
    parser.add_argument("--allocator-history", action="store_true")
    parser.add_argument("--history-max-entries", type=int, default=1000000)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.interval_ms <= 0 or args.baseline_ms < 0 or args.post_exit_ms <= 0 or args.accounting_interval_ms <= 0:
        parser.error("Command, positive intervals/post-exit tail, and nonnegative baseline required")
    # Fresh output is essential: stale sentinels must never satisfy coverage checks.
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve()
    started_ns = time.monotonic_ns()
    run_id = str(uuid.uuid4())
    report = {"schema": "physical-lifecycle-monitor-v1", "run_id": run_id, "status": "starting",
        "monitor_pid": os.getpid(), "command": command, "gpu_uuid_requested": args.uuid,
        "requested_interval_ms": args.interval_ms, "baseline_ms": args.baseline_ms, "post_exit_ms": args.post_exit_ms,
        "accounting_interval_ms": args.accounting_interval_ms, "timeout_s": args.timeout_s,
        "allocator_history_requested": args.allocator_history, "history_max_entries": args.history_max_entries,
        "monitor_started_ns": started_ns, "wall_started_ns": time.time_ns(), "python": platform.python_version(),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "source_sha256": {p.name: sha256(p) for p in Path(__file__).parent.glob("*.py")},
        "exact_continuous_physical_peak_certified": False, "physical_savings_certified": False,
        "latency_policy": "Use separate fresh unmonitored timing runs with identical workload/backend. Profiled durations are not no-slowdown proof."}
    write_json(output / "run-start.json", report)
    child = monitor = None
    initialized = False
    gate_write = gate_read = None
    child_stdout = child_stderr = None
    try:
        import pynvml as nv
        nv.nvmlInit()
        initialized = True
        handle = nv.nvmlDeviceGetHandleByUUID(args.uuid)
        report.update(gpu_uuid=plain(nv.nvmlDeviceGetUUID(handle)), gpu_name=plain(nv.nvmlDeviceGetName(handle)),
            nvml_version=plain(nv.nvmlSystemGetNVMLVersion()), driver_version=plain(nv.nvmlSystemGetDriverVersion()),
            mig_mode=safe(lambda: plain(nv.nvmlDeviceGetMigMode(handle))),
            mps_processes=safe(lambda: plain(nv.nvmlDeviceGetMPSComputeRunningProcesses(handle))))
        monitor = Monitor(nv, handle, args, output)
        monitor.sample_for(args.baseline_ms / 1000, "prelaunch")
        gate_read, gate_write = os.pipe()
        env = dict(os.environ, PHYSICAL_PEAK_RUN_DIR=str(output), PHYSICAL_PEAK_RUN_ID=run_id)
        env["PHYSICAL_PEAK_ALLOCATOR_HISTORY"] = "1" if args.allocator_history else "0"
        env["PHYSICAL_PEAK_HISTORY_MAX_ENTRIES"] = str(args.history_max_entries)
        env["PYTHONPATH"] = str(Path(__file__).parent) + os.pathsep + env.get("PYTHONPATH", "")
        gate_path = output / "gate-ready.json"
        child_stdout = (output / "worker.stdout.log").open("w")
        child_stderr = (output / "worker.stderr.log").open("w")
        child = subprocess.Popen([sys.executable, str(Path(__file__).with_name("launch_gate.py")),
            "--gate-fd", str(gate_read), "--ready", str(gate_path), "--", *command],
            pass_fds=(gate_read,), env=env, stdout=child_stdout, stderr=child_stderr, start_new_session=True)
        report["child_pid"] = child.pid
        os.close(gate_read)
        gate_read = None
        gate_deadline = time.monotonic() + args.gate_timeout_s
        while not gate_path.exists():
            if child.poll() is not None:
                raise RuntimeError("Gate process exited before ready; target was not executed")
            if time.monotonic() > gate_deadline:
                raise TimeoutError("Pre-exec gate ready timeout")
            monitor.sleep(monitor.sample("gate_wait"))
        gate = json.loads(gate_path.read_text())
        if gate["run_id"] != run_id or gate["pid"] != child.pid:
            raise RuntimeError("Gate run/PID identity mismatch")
        report["gate"] = gate
        monitor.aliases = set(gate["pid_namespace_aliases"]) | {child.pid}
        for pid in monitor.aliases:
            if monitor.accounting_enabled:
                monitor.accounting_baseline_stats[str(pid)] = safe(lambda pid=pid: plain(nv.nvmlDeviceGetAccountingStats(handle, pid)))
        monitor.sample("gate_held")
        report["gate_release_ns"] = time.monotonic_ns()
        os.write(gate_write, b"G")
        os.close(gate_write)
        gate_write = None
        timeout = time.monotonic() + args.timeout_s
        while child.poll() is None:
            row = monitor.sample("running")
            if time.monotonic() > timeout:
                raise TimeoutError("Worker timeout; observer will terminate only its launched process group")
            monitor.sleep(row)
        report["child_exit_observed_ns"] = time.monotonic_ns()
        report["child_returncode"] = child.returncode
        monitor.sample_for(args.post_exit_ms / 1000, "post_exit")
        monitor.account(monitor.aliases | monitor.observed_pids, "final_after_exit")
        report["status"] = "completed" if child.returncode == 0 else "worker_failed"
    except BaseException as exc:
        report["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for descriptor in (gate_write, gate_read):
            if descriptor is not None:
                os.close(descriptor)
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
            report["child_terminated_by_monitor"] = True
        if child is not None:
            report["child_returncode"] = child.returncode
        for stream in (child_stdout, child_stderr):
            if stream is not None:
                stream.close()
        if monitor is not None:
            monitor.close()
            report["sampling"] = monitor.summary()
            write_json(output / "accounting.json", accounting_summary(monitor))
        if initialized:
            nv.nvmlShutdown()
        events = read_events(output / "worker-events.jsonl")
        report["worker_events"] = events
        matching_events = [e for e in events if e.get("run_id") == run_id and e.get("pid") == report.get("child_pid")]
        starts = [e for e in matching_events if e.get("kind") == "worker_start"]
        finished = [e for e in matching_events if e.get("kind") == "worker_finished"]
        report["coverage_checks"] = {
            "observer_sampled_before_target_exec": bool(monitor and report.get("gate_release_ns") and monitor.first_ns < report["gate_release_ns"]),
            "observer_sampled_after_process_exit": bool(monitor and report.get("child_exit_observed_ns") and monitor.last_ns > report["child_exit_observed_ns"]),
            "worker_start_sentinel_before_cuda_init": bool(starts and starts[0].get("torch_state", {}).get("cuda_initialized") is False),
            "worker_normal_finish_sentinel": bool(finished),
            "worker_exit_zero": report.get("child_returncode") == 0,
            "source_contract_no_peak_resets": "Must be source-audited; observer cannot enforce.",
            "atomic_process_device_measurement": False,
            "exact_continuous_physical_peak": False}
        report["monitor_finished_ns"] = time.monotonic_ns()
        report["artifacts"] = {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)} for p in output.iterdir() if p.is_file() and p.name != "summary.json"}
        write_json(output / "summary.json", report)
        print(json.dumps({"status": report["status"], "summary": str(output / "summary.json"),
                          "child_returncode": report.get("child_returncode")}))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
