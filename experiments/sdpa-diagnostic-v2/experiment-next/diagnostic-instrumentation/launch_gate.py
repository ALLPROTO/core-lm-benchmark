#!/usr/bin/env python3
"""Hold fresh Python process before target exec, without importing CUDA libraries."""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate-fd", type=int, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    aliases = [os.getpid()]
    status = Path("/proc/self/status").read_text()
    for line in status.splitlines():
        if line.startswith("NSpid:"):
            aliases.extend(int(x) for x in line.split()[1:])
    temporary = Path(str(args.ready) + ".tmp")
    temporary.write_text(json.dumps({"pid": os.getpid(), "pid_namespace_aliases": sorted(set(aliases)),
        "monotonic_ns": time.monotonic_ns(), "wall_time_ns": time.time_ns(),
        "run_id": os.environ.get("PHYSICAL_PEAK_RUN_ID"), "target_not_executed_yet": True}))
    temporary.replace(args.ready)
    try:
        token = os.read(args.gate_fd, 1)
    finally:
        os.close(args.gate_fd)
    if token != b"G":
        raise SystemExit("Observer did not release gate; target never started")
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    main()
