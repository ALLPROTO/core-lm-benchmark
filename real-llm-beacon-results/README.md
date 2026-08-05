# Beacon-selected held-out result artifacts

This directory remains empty of result artifacts on the evolving `main`
branch. The protocol was frozen under immutable release
[`corelm-beacon-heldout-v1`](https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/corelm-beacon-heldout-v1)
at tag commit `0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44`. Its first and only
recorded attempt is published unchanged at evidence commit
`85c2add1799652a818873a04310b75821728da11`, tag and release
`corelm-beacon-heldout-v1-evidence`, with terminal **PASS**. The canonical raw
attempt, resolution, primary-evidence, and outcome bytes remain anchored to
that evidence ref rather than being reconstructed on `main`.

The exact NIST pulse was `2026-08-02T18:00:00.000Z`, and the outcome completed
at `2026-08-02T18:18:20Z`, before the registered
`2026-08-04T18:00:00.000Z` deadline. From a clean detached checkout of the
frozen tag, the normative runner created, in order:

1. `attempt.json` before beacon or data resolution;
2. `resolution.json` after authenticated deterministic beacon selection;
3. `primary-evidence/` during the real 32-block model run; and
4. `outcome.json` with terminal `PASS`, `FAIL_GATES`, or `FAIL_EXECUTION`.

The recorded attempt selected blocks 512--543 and passed all seven registered
gates. The suite is consumed and must not be invoked again as a scientific
attempt. Later runs belong only in `regressions/`, must state that they do not
count toward the scientific verdict, and cannot change the normative outcome.

The published evidence bytes must not be repaired, sanitized, recreated, or
replaced after the attempt. The frozen release body's four high-level entries
are key artifacts; the authoritative complete normative inventory is the 26
entries in `../RealLLM/beacon_freeze.json`.

See `../RealLLM/BEACON_HELDOUT_PROTOCOL.md` for the frozen procedure and claim
boundary. See `../docs/BEACON_EVIDENCE_REPORT.md` for the terminal identities,
metrics, and CI closure. The archived
`../docs/BEACON_LAUNCH_RUNBOOK.md` preserves the predeclared operator procedure
but must not be executed again.
