# SDPA follow-up status — 2026-11-14

No new GPU evidence produced. No GPU is running as a result of this task.

Implemented inference-only in-place MLP SiLU/product candidate preserving native
SDPA and linear-layer shapes, weights, full KV and BF16. No quantization,
offload, context cropping or output omission. Twelve isolated CPU/protocol controls
pass; these do not establish GPU correctness, performance or memory savings.

The new separate benchmark_inplace.py retains original measurement lifecycle,
six fresh pairs, independent quality gate and unsampled latency, fixed primary
Qwen0.5B/4096. Native SDPA is the reference. Original prepared package sources
remain byte-identical. Candidate published separately for reproducibility; no new GPU result claimed.

Analytical caution: previous SDPA Qwen0.5B/4096 weights 988,065,792 bytes,
full KV 50,319,360, peak allocated1,224,387,072, reserved1,314,914,304.
Target23% of observed NVML2207.6875MiB requires507.768MiB reduction.
The MLP buffer reuse candidate removes at most around74MiB of simultaneous
intermediates in this shape; it cannot credibly promise the requested target.
A larger reduction requires reducing model/runtime residency or a different
explicitly registered workload, not silently changing the comparison baseline.

## Follow-up without GPU
Added standalone in-place RMSNorm buffer reuse ablation and combined harness.
12 isolated CPU/protocol unit controls pass. Real registered Qwen0.5B CPU
regression ran with all asset SHA256 checked, public WikiText512 and4096,
full128x151936 logits: MLP and MLP+RMSNorm both byte-identical to stock SDPA,
max absolute difference0. This is CPU accuracy-only evidence, not CUDA quality
or speed/memory proof. No performance time was used as an advantage claim.

Actual prior CUDA backend audit: all9 stock SDPA probe cells executed Flash
attention operators for prefill and efficient-attention operators for the
rectangular128-token continuation. The lower-right control used Flash for
both phases. Operator records belong to diagnostic probes, not forced-backend
settings. Codec README remains CPU/MPS-only; these adapters are independent
experimental CUDA runtime changes.

Independent review follow-up: four preflight issues fixed (separate combo
runner/protocol, RMSNorm invocation counts, observer-hook guard, deterministic
harness generation). Twelve isolated tests now pass. New GPU run should begin
with short allocation attribution, not a full matrix expecting23%.

Offline diagnostic audit found original context=None disabled stacks. Fixed in
separate diagnostic-only copy, bounded100000 events, pre-CUDA start guard,
metadata-aware trace completeness and stack coverage reports.17 unit/API mock
tests pass; latency remains separate and unprofiled. No paid GPU launch.
