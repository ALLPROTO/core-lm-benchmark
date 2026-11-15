# Exploratory MLP buffer reuse, 2026-11-14
Fixed primary: Qwen2.5-0.5B revision in original registry, real public WikiText
validation suffix4096, same BF16 weights, full GPU KV and outputs. Stock HF SDPA
vs stock SDPA with inference-only in-place SiLU and elementwise product in MLP.
No attention changes. No quantization/offload/cropping. Inputs/old code immutable.
Quality: native SDPA logits must match byte-for-byte, including independent
1024-scored-token sweep, before candidate latency. Six balanced fresh processes
per arm for memory and latency, original lifecycle monitor; no peak reset/cache
clearing. Nine warmed inner rounds are one process sample, not independent tests.
Report all outcomes. Success is >=23% observed NVML maximum reduction and no
slowdown in every pair plus one-sided95% bounds below1. Results are exploratory
because same public data has been used for development; no holdout generalization.
Observed NVML sample maximum is not continuous physical max. No claim of Core LM
codec gain. Analytical expectation: small improvement, likely below target.

## Additional predefined ablation
`sdpa_inplace_combo` adds RMSNorm scratch reuse to the MLP candidate, preserving
FP32 variance arithmetic, BF16 output rounding and unchanged native SDPA. It is
not a KV codec. Both candidates must be reported, not only a favourable one.
CPU public validation at512 and4096 passed byte-exact comparisons; these CPU
checks are not transferable evidence of CUDA quality/performance.

Before any measurement, run diagnose-memory.sh once on stock SDPA to gather
PyTorch allocator history. That instrumented run is diagnostic only, excluded
from speed/memory advantage estimates. Detect snapshot ring truncation and
unmatched frees. NVML driver/context allocations remain outside the snapshot.
Do not change allocator environment or force a worse SDPA kernel in one arm.
Actual operator diagnostics must be recorded for both arms, not inferred from
`attn_implementation='sdpa'`.

Stop escalating a weak candidate if a cheap pilot plainly misses the target;
preserve and report that failure rather than retesting until a noisy win.

## Corrected allocation diagnostic (offline review)
The original monitor used context=None and therefore did NOT record stacks.
Only the new isolated diagnostic-instrumentation copy uses context='all',
stacks='python', enabled='all', with a hard maximum of100000 history events.
It rejects late attachment after CUDA initialization. The CPU API contract is
mock-tested; CUDA compatibility still needs a smoke test. Ring-full traces,
missing metadata, recording errors, unmatched frees, or missing allocation
stacks prevent complete attribution. The analyzer requires worker-events.jsonl;
no unmatched frees alone is NOT proof of complete history.

Compare the snapshot to the SAME diagnostic process's physical/samples.jsonl
and physical/worker-events.jsonl: check GPU UUID/PID, prelaunch device usage,
other GPU processes, sampling intervals/gaps and phase timestamps. Report
allocator allocated/reserved maxima alongside sampled device/process NVML
maxima, not as equivalent measures. Do NOT subtract independently occurring
peaks to claim an exact non-PyTorch allocation amount. Use near-time phase
allocator counters with the surrounding NVML samples and disclose time skew.
Snapshots exclude CUDA context, driver/library/non-PyTorch and other-process
allocations. NVML is sampled and cannot prove a continuous physical peak.

Latency remains a separate fresh unmonitored process: orchestration strips
PHYSICAL_PEAK_* environment, attaches monitor only for purpose=memory, and
constructs torch.profiler only for purpose=probe. Allocation-diagnostic timings
must never enter the six-pair no-slowdown analysis.
Source checked: https://docs.pytorch.org/docs/main/torch_cuda_memory
and installed pinned torch2.13.0 memory._record_memory_history docstring.
