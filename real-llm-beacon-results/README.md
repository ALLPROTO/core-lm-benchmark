# Beacon-selected held-out result artifacts

This directory is intentionally empty of result artifacts before the registered
one-shot execution. The protocol is already frozen under immutable release
[`corelm-beacon-heldout-v1`](https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/corelm-beacon-heldout-v1)
at tag commit `0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44`; the suite has no
result yet.

The exact NIST pulse is `2026-08-02T18:00:00.000Z`, and the scientific outcome
must complete by `2026-08-04T18:00:00.000Z`. From a clean detached checkout of
the frozen tag, the normative runner creates, in order:

1. `attempt.json` before beacon or data resolution;
2. `resolution.json` after authenticated deterministic beacon selection;
3. `primary-evidence/` during the real 32-block model run; and
4. `outcome.json` with terminal `PASS`, `FAIL_GATES`, or `FAIL_EXECUTION`.

An `attempt.json` without an outcome is `CONSUMED_INCOMPLETE`; it must be
published and must not be rerun. `FAIL_EXECUTION` is likewise terminal and
forbids a repeat. Regression runs are allowed only after `PASS` or `FAIL_GATES`,
belong only in `regressions/`, and cannot change the normative verdict.

For every terminal state, publish all surviving files in this directory
byte-for-byte unchanged. Do not repair, sanitize, recreate, or replace an
artifact after the attempt. The frozen release body's four high-level entries
are key artifacts; the authoritative complete normative inventory is the 26
entries in `../RealLLM/beacon_freeze.json`.

See `../RealLLM/BEACON_HELDOUT_PROTOCOL.md` for the frozen procedure and claim
boundary. See `../docs/BEACON_LAUNCH_RUNBOOK.md` for the predeclared AC-power,
`caffeinate`, one-shot, commit, evidence-tag, immutable-release, and pull-request
sequence.
