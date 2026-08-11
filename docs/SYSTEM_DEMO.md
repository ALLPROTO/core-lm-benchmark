# Interactive full-system demo

The interactive demo has two deliberately separate windows:

- `CoreLMBenchmark.app` shows the real Qwen compression run, a strict live
  event trail, layer-container progress, measured block values, and the
  verified source excerpt for the most recently confirmed stage. It does not
  claim to expose a synthetic instruction-by-instruction program counter.
- `Core LM Operator` provides manual repository **Verify**, application
  **Build**, **Full System Proof**, and **Open Built App** controls.

This separation is a safety boundary. The signed benchmark application can
run and verify the pinned scientific workload, but it cannot execute arbitrary
repository commands. The source-only Operator maps four fixed buttons to
fixed commands; it has no shell editor, command field, arbitrary path picker,
or inherited credential environment.

## Run it

On Apple Silicon macOS 14 or newer, from a clean checkout:

```sh
./corelm macos doctor
./corelm macos operator
```

In the Operator window:

1. Select **Verify Repository** to run the normal repository gate.
2. Select **Build App** to build, sign, and verify
   `dist/CoreLMBenchmark.app`.
3. Select **Open Built App**, then choose **Run Compression Proof** in the
   benchmark window for the live in-app view.
4. Select **Full System Proof** when the complete outer proof, independent
   replay, and terminal result are required in one command log.

Only one Operator action may run at a time. Its output is bounded and
sanitized. The buttons map exactly to:

| Button | Fixed command |
|---|---|
| Verify Repository | `./corelm verify` |
| Build App | `./corelm macos build` |
| Full System Proof | `./corelm macos proof` |
| Open Built App | canonical `dist/CoreLMBenchmark.app` |

## What “real LLM connected” means here

The benchmark does not connect to a remote model API. It resolves and
full-hash-checks the pinned `Qwen/Qwen2.5-0.5B` revision and WikiText
validation parquet from the owner-local cache with network access disabled,
then loads the actual Qwen parameters onto Apple MPS in evaluation mode. The
live dashboard distinguishes these facts:

- pinned model and dataset bytes verified;
- real Qwen load started and completed on MPS;
- registered token slice selected and hashed;
- each validation block entered real prefill/KV-cache work;
- each of 24 layer containers per block completed codec roundtrip and
  canonical write;
- each block produced 128 batched continuation decisions and measured values;
- primary evidence and the canonical result were sealed; and
- Swift re-read the retained containers and reconciled the live stream with
  the sealed result.

There is no timer-based animation, simulated token stream, fake layer sweep,
or network “connected” badge. Qwen evaluates all 128 continuation positions
for a block in a batched call, so the UI does not invent token-by-token
progress.

## Live-channel contract

Machine events use canonical JSON Lines on the worker's stdout. Human logs go
only to stderr. Every event binds a canonical UUID, a strictly increasing
sequence, the SHA-256 of the previous canonical event, an exact event type,
and an exact facts object. A standard eight-block run contains 216 events:

```text
5 setup events
+ 8 × (block start + 24 written layer containers + block metrics)
+ primary-evidence seal + result seal + worker terminal
```

The Swift consumer accepts no unknown keys or event types. It pins the model,
dataset, geometry, block/layer order, and terminal filename. At process exit it
replays the complete bounded transcript from a single EOF drain, then
reconciles block metrics, container sizes/digests, totals, manifest digest, and
result digest against the independently parsed result. An invalid channel is
shown as `LIVE CHANNEL INVALID`; missing progress is never synthesized. The
scientific result verifier remains a separate gate.

The code pane is also read-only. It shows line-numbered excerpts from the
actual `app_proof_runner.py` and generated `app_proof_core.py` bytes bundled
with the application, together with their source SHA-256. Stage changes only
select a verified excerpt; the UI is not a code editor.

## Evidence boundary

Both windows state their classification explicitly. This interactive surface
is a manual developer demonstration, not independent replication and not
portfolio machine evidence. It does not modify the frozen V15 tag, immutable
GitHub Release, automated presentation-v2 state machine, collector, release
builder, or the published exact-14 asset set. Publishing a recording of this
new surface would require a new versioned media contract and a future release
identity.
