# Restore into a fresh GPU workspace
1. Fetch the previously verified public original prepared package at
   ALLPROTO/core-lm-benchmark commit9205529d6fc9c4f61dd4639b646410fab8a25d71.
   Verify original ZIP and manifest using that branch's verify_extract.py.
2. Place it at /workspace/corelm-modern-study-20261112/prepared-matrix.
3. Place benchmark_inplace.py, benchmark_combined.py, inplace_mlp.py and
   inplace_norm.py from this packet under prepared-matrix/implementation.
   Verify this packet's manifest separately; do not alter the original manifest.
4. Run the original pinned official bootstrap, optionally downloading only
   Qwen0.5B for the preregistered pilot and recording this scope explicitly.
5. Run diagnose-memory.sh. Inspect allocator-history errors/ring truncation,
   actual backend operators and physical sampling gaps. Not a performance run.
6. If a credible avenue remains, run either run.sh (MLP) or run-combined.sh
   (MLP+norm), retaining both outcomes and all failed gates. Use a whole-session
   timeout and active supervision. These timeout commands stop processes, not
   billing: verify external export then explicitly stop RunPod.
7. The original analyzer expects old mode names; do not pass this experiment to
   it unmodified. Audit new SDPA/inplace pairs using their actual mode names,
   six process-level samples and original declared statistical rules. No result
   claim is authorized merely by a zero exit code.
8. Keep diagnostic-instrumentation beside diagnose-memory.sh. It is deliberately
   separate from frozen originals and from performance instrumentation. Snapshot
   analysis now requires --worker-events <physical/worker-events.jsonl>.
