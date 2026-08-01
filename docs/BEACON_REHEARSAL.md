# Safe synthetic rehearsal before the beacon

This non-normative rehearsal reduces operational risk without using the one
scientific attempt. It is deliberately separate from
`RealLLM/run_beacon_one_shot.py`; the frozen runner has no dry-run, synthetic,
source, pulse, window, gate, or output override.

Run it only from the current default branch, before
`2026-08-02T17:00:00Z` (19:00 in Prague):

```sh
./security/run_beacon_rehearsal.sh
```

The command installs or downloads nothing. It uses macOS system tools, the
runtime at `~/.cache/corelm-app-runtime` whose installed-distribution closure
matches the hash-locked requirements, and the already verified model cache at
`~/.cache/corelm-model-assets`.

The first contour is stdlib-only and hermetic. It disables network and child
processes, permits writes only below a private temporary directory, validates
all 26 frozen file hashes, verifies the historical signed NIST fixture, checks
a deterministic selection over dummy window IDs, and exercises exclusive
durable temporary state transitions. It never resolves an eligible window.

The second contour requires AC power and at least 35% free memory. It loads the
exact cached Qwen2.5-0.5B model as FP32/eager on MPS and evaluates one 512-token
block generated from a fixed SHA-256 rule. It exercises the same 24-layer
cache extraction, BF16 canonicalization, VoidToken v5 codec, continuation,
structural replay, 24 VTL5 files, token metrics, and an independent container
parser. All generated rehearsal evidence files live in a temporary directory
and are deleted. The audit guard denies the WikiText test parquet, its Hugging
Face dataset cache, network access, and Python writes anywhere in the
repository, including `real-llm-beacon-results`.

The audit hook is a Python guard, not an operating-system sandbox for arbitrary
native-extension I/O. The no-corpus property also relies on poisoning every
frozen dataset resolver before model work and never calling a PyArrow read or
tokenization path. Repository-wide Python writes are denied. A stdlib parent
supervisor bounds the model contour to 300 seconds, stops it after two
consecutive samples below 15% free memory, kills its process group on failure,
and removes a surviving shared proof lock only after proving that the recorded
PID belonged to the now-dead rehearsal group. The shared lock is transient;
all rehearsal evidence remains private temporary data.

Both contours refuse to start if a normative artifact or shared proof lock is
present. They snapshot the frozen files and normative result tree before and
after execution. No receipt is retained; stdout is operational evidence only.

## What PASS means

PASS establishes that, on this Mac at rehearsal time:

- frozen protocol bytes and historical NIST cryptography are intact;
- a synthetic selection and exclusive state transition behave deterministically;
- the installed-distribution closure, exact cached Qwen model, MPS path,
  registered codec, structural replay, temporary evidence writer, and
  independent VTL5 parser work together;
- no registered test data, target beacon, eligible window, or normative result
  path was used.

It does **not** establish a scientific metric, a gate verdict, blind
generalization, availability of the future NIST pulse, or readiness to launch
on battery power. Synthetic compression, NLL, and top-1 values are intentionally
not published because they have no scientific meaning.

## Fixed launch delay

The scientific pulse remains frozen at `2026-08-02T18:00:00Z`. The operator
will not invoke the one-shot before the separate non-normative time publicly
announced before reveal: `2026-08-02T18:15:00Z` (20:15 in Prague). This fixed
15-minute delay reduces the observed NIST publication-lag risk without polling
or fetching any beacon pulse before the attempt marker. It does not establish
future endpoint availability; a post-marker fetch failure still consumes the
attempt. The delay leaves 47 hours 45 minutes before the frozen deadline.
Generic connectivity, the GitHub freeze, AC power, memory, a clean detached
frozen tag, absent artifacts, and the model cache must still be rechecked
immediately before the single invocation.
