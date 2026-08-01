# Beacon-selected held-out result artifacts

This directory is intentionally empty of result artifacts before the registered
one-shot execution.

The public protocol freeze must exist before the NIST pulse at
`2026-08-02T18:00:00.000Z`. The normative runner then creates, in order:

1. `attempt.json` before beacon or data resolution;
2. `resolution.json` after authenticated deterministic beacon selection;
3. `primary-evidence/` during the real 32-block model run; and
4. `outcome.json` with terminal `PASS`, `FAIL_GATES`, or `FAIL_EXECUTION`.

An `attempt.json` without an outcome is `CONSUMED_INCOMPLETE`; it must be
published and must not be rerun. `FAIL_EXECUTION` is likewise terminal and
forbids a repeat. Regression runs are allowed only after `PASS` or `FAIL_GATES`,
belong only in `regressions/`, and cannot change the normative verdict.

See `../RealLLM/BEACON_HELDOUT_PROTOCOL.md` for the frozen procedure and claim
boundary.
