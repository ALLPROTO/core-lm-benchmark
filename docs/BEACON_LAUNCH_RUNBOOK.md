# Beacon held-out launch and publication runbook

This is the public, non-normative operator checklist for the already frozen
`corelm-beacon-heldout-v1` experiment. If this checklist and a frozen artifact
ever differ, [`RealLLM/BEACON_HELDOUT_PROTOCOL.md`](../RealLLM/BEACON_HELDOUT_PROTOCOL.md),
[`RealLLM/beacon_registration.json`](../RealLLM/beacon_registration.json), and
[`RealLLM/beacon_freeze.json`](../RealLLM/beacon_freeze.json) are authoritative.
Do not edit the frozen tag or its immutable release to update this checklist.

## Frozen public record

| Item | Frozen value |
|---|---|
| Suite | `qwen2.5-0.5b-kv-voidtoken-v5-beacon-heldout-v1` |
| Protocol commit | `b34bc4d06c00c86b99076b117049e2d590d73bcd` |
| Required tag | `corelm-beacon-heldout-v1` |
| Tagged freeze commit | `0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44` |
| Immutable release | [`corelm-beacon-heldout-v1`](https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/corelm-beacon-heldout-v1) |
| Release publication time | `2026-08-01T01:18:09Z` |
| Release-notes correction time | `2026-08-01T10:08:12Z` |
| Exact NIST pulse / earliest start | `2026-08-02T18:00:00.000Z` |
| Completion deadline | `2026-08-04T18:00:00.000Z` |
| Fixed evidence tag after the attempt | `corelm-beacon-heldout-v1-evidence` |

The initial release body used the heading `Normative files` above four
high-level entries. Before the pulse, at `2026-08-01T10:08:12Z`, a notes-only
correction renamed that heading to `Key normative artifacts` and explicitly
pointed to the complete 26-entry inventory in `RealLLM/beacon_freeze.json`.
GitHub continues to report `immutable: true`; the tag, assets, frozen manifest,
protocol, and original `published_at` value were unchanged. The notes update is
recorded here for timestamp transparency.

The target is 20:00 on 2 August 2026 in Europe/Prague while daylight-saving
time is in effect. Use UTC as the authority. A scientific `PASS` or
`FAIL_GATES` must be written no later than 20:00 on 4 August 2026 in
Europe/Prague. The runner enforces the UTC timestamps.

The frozen protocol permits execution as soon as the target pulse exists. As
a stricter, non-normative operator rule publicly announced before reveal, the
one-shot will not be invoked before 20:15 Prague (`18:15Z`). This does not
change the frozen 18:00 pulse or earliest start. The fixed delay reduces the
observed beacon-publication-lag risk without fetching or polling NIST before
the attempt marker; it cannot guarantee future endpoint availability.

## Rules that do not change after reveal

- Do not move, delete, recreate, or edit the frozen tag or release.
- Do not modify any of the 26 normative paths listed by
  `RealLLM/beacon_freeze.json`.
- Do not resolve a candidate window manually and do not run model inference on
  an eligible window before the registered runner resolves it.
- Do not add source, parameter, configuration, range, seed, or gate overrides.
- Invoke the scientific launch command only from the clean detached frozen tag.
- Once `attempt.json` exists, the suite is consumed. Never invoke the one-shot
  runner again after success, gate failure, execution failure, interruption,
  crash, power loss, or a marker with no outcome.
- Publish every surviving runner artifact byte-for-byte unchanged. This applies
  to `PASS`, `FAIL_GATES`, `FAIL_EXECUTION`, and `CONSUMED_INCOMPLETE`.
- A later run is allowed only after a published `PASS` or `FAIL_GATES`, must use
  `run_beacon_regression.py`, and cannot change the scientific verdict.

Do not put credentials or other secrets in usernames, filesystem paths, cache
paths, terminal arguments, or environment values. A terminal
`FAIL_EXECUTION.error.message` is part of the evidence and must not be sanitized
or rewritten after the attempt.

## Preparation before the pulse

Use a new clone dedicated to the one-shot. Do not execute these commands inside
a working copy containing documentation or development changes.

```sh
git clone https://github.com/ALLPROTO/core-lm-benchmark.git core-lm-beacon-one-shot
cd core-lm-beacon-one-shot
git fetch --tags origin
git switch --detach corelm-beacon-heldout-v1

BEACON_TAG_SHA=0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44
test "$(git rev-parse HEAD)" = "$BEACON_TAG_SHA"
test -z "$(git status --porcelain=v1 --untracked-files=all --ignored=no)"
test -z "$(git ls-remote --heads origin \
    refs/heads/evidence/corelm-beacon-heldout-v1-outcome)"
test -z "$(git ls-remote --tags origin \
    refs/tags/corelm-beacon-heldout-v1-evidence)"
```

Prepare the exact runtime without launching the application, then
download and verify the registered bytes. The second asset command is the
required offline resolution check. These preparation commands do not tokenize
the test corpus, select a window, load the model for inference, run the codec,
or calculate a metric.

The immutable tag retains both the historical root script path and the
environment-variable name published with that tag. The command below is run
only after the detached-tag checkout above; it is intentionally different from
the current default branch's `./corelm macos build` command. The variable
disables only the application launch check.

```sh
CORELM_SKIP_SMOKE_TEST=1 ./build_local_app.sh

BEACON_PYTHON="$HOME/.cache/corelm-app-runtime/bin/python"
BEACON_CACHE="$HOME/.cache/corelm-model-assets"
test -x "$BEACON_PYTHON"

HF_HOME="$BEACON_CACHE" \
"$BEACON_PYTHON" -I -B RealLLM/prepare_beacon_assets.py \
    --cache "$BEACON_CACHE"

HF_HOME="$BEACON_CACHE" \
"$BEACON_PYTHON" -I -B RealLLM/prepare_beacon_assets.py \
    --cache "$BEACON_CACHE" --offline-only

test -z "$(git status --porcelain=v1 --untracked-files=all --ignored=no)"
test ! -e real-llm-beacon-results/attempt.json
test ! -e real-llm-beacon-results/resolution.json
test ! -e real-llm-beacon-results/outcome.json
test ! -e real-llm-beacon-results/primary-evidence
```

Before the pulse, close memory-heavy applications, connect the Mac to reliable
AC power, keep the lid open, and disable any scheduled shutdown or restart. The
one-shot runner checks memory but does not itself acquire the application's
idle-sleep assertion. Confirm AC power before proceeding:

```sh
/usr/bin/pmset -g batt
/usr/bin/pmset -g batt | /usr/bin/grep -Fq "Now drawing from 'AC Power'"
```

The second command must exit successfully. Do not begin on battery power. Keep
the network available for the exact NIST pulse and GitHub freeze checks; the
model and dataset remain offline-only.

## One scientific invocation

Do not paste this block before the precommitted operator safety time
`2026-08-02T18:15:00.000Z`, and do not run it
after `2026-08-04T18:00:00.000Z`. Reconfirm the detached commit, clean tree,
absent artifacts, AC power, open lid, free memory, cache, generic connectivity,
and the GitHub freeze immediately before the command.

Do not poll `/pulse/last`, fetch the exact target, or resolve a candidate before
the runner creates `attempt.json`. The fixed 15-minute delay is the entire
pre-marker NIST-availability precaution.
It does not prove that the target endpoint is available. A target fetch failure
after marker creation still consumes the attempt.

`caffeinate` is an external macOS power assertion; it does not change the frozen
Python runner, selected data, model, codec, parameters, gates, or evidence. Its
exit status is the runner's exit status: 0 for `PASS`, 2 for `FAIL_GATES`, and 1
for execution or integrity failure.

```sh
(
set -eu

BEACON_TAG_SHA=0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44
BEACON_PYTHON="$HOME/.cache/corelm-app-runtime/bin/python"
BEACON_CACHE="$HOME/.cache/corelm-model-assets"
BEACON_OPERATOR_NOT_BEFORE=1785694500

test "$(git rev-parse HEAD)" = "$BEACON_TAG_SHA"
test -z "$(git status --porcelain=v1 --untracked-files=all --ignored=no)"
test "$(/bin/date -u +%s)" -ge "$BEACON_OPERATOR_NOT_BEFORE"
test ! -e real-llm-beacon-results/attempt.json
test ! -L real-llm-beacon-results/attempt.json
test ! -e real-llm-beacon-results/resolution.json
test ! -L real-llm-beacon-results/resolution.json
test ! -e real-llm-beacon-results/outcome.json
test ! -L real-llm-beacon-results/outcome.json
test ! -e real-llm-beacon-results/primary-evidence
test ! -L real-llm-beacon-results/primary-evidence
test ! -e "$HOME/.cache/corelm-proof-runtimes/.proof-run.lock"
test ! -L "$HOME/.cache/corelm-proof-runtimes/.proof-run.lock"
/usr/bin/pmset -g batt | /usr/bin/grep -Fq "Now drawing from 'AC Power'"

if HF_HOME="$BEACON_CACHE" \
    /usr/bin/caffeinate -dimsu \
    "$BEACON_PYTHON" -I -B \
        RealLLM/run_beacon_one_shot.py --local-files-only; then
    BEACON_EXIT=0
else
    BEACON_EXIT=$?
fi
printf 'Beacon runner exit code: %s\n' "$BEACON_EXIT"
exit "$BEACON_EXIT"
)
```

Do not invoke `run_beacon_one_shot.py` a second time. The files on disk, not a
terminal screenshot or expected verdict, are the publication source.

## Classify without changing files

Inspect only; do not open and save the JSON in an editor.

```sh
git status --short --untracked-files=all
find real-llm-beacon-results -type f -print | LC_ALL=C sort
```

Classify the first invocation as follows:

| Files present | Public state |
|---|---|
| No `attempt.json` | `NOT_STARTED_PREFLIGHT_REJECTION`; no scientific attempt was created. Stop and publish the operator status separately; do not claim a result. |
| `attempt.json`, no `outcome.json` | `CONSUMED_INCOMPLETE`; publish every surviving file and never retry. |
| `outcome.json` verdict `FAIL_EXECUTION` | Terminal execution failure; publish every surviving file and never retry. |
| `outcome.json` verdict `FAIL_GATES` | Terminal scientific gate failure; publish unchanged. Only later regression-labelled runs are permitted. |
| `outcome.json` verdict `PASS` | Terminal scientific pass; publish unchanged. Only later regression-labelled runs are permitted. |

When `outcome.json` exists, run the read-only independent verifier. It verifies
`PASS`, `FAIL_GATES`, and well-formed `FAIL_EXECUTION` outcomes. A missing outcome
is intentionally not converted into a fabricated outcome.

```sh
"$HOME/.cache/corelm-app-runtime/bin/python" -I -B \
    RealLLM/verify_beacon_evidence.py
```

Publish the verifier's actual exit status. A verification failure does not
authorize editing an artifact or running the experiment again.

## Exact publication sequence

The evidence branch and evidence tag names below are fixed before reveal. Use
the same procedure for `PASS`, `FAIL_GATES`, `FAIL_EXECUTION`, and
`CONSUMED_INCOMPLETE`. Commit all and only the surviving files below
`real-llm-beacon-results/`; do not add a hand-edited outcome, summary, or
checksum file to that directory.

```sh
test "$(git rev-parse HEAD)" = \
    0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44
git switch -c evidence/corelm-beacon-heldout-v1-outcome
git add -A -- real-llm-beacon-results
git diff --cached --check
test -n "$(git diff --cached --name-only)"
git commit -m "Publish corelm beacon heldout v1 attempt"

BEACON_RESULT_COMMIT=$(git rev-parse HEAD)
git push origin \
    HEAD:refs/heads/evidence/corelm-beacon-heldout-v1-outcome
test "$(git rev-parse HEAD)" = "$BEACON_RESULT_COMMIT"
git tag corelm-beacon-heldout-v1-evidence "$BEACON_RESULT_COMMIT"
git push origin refs/tags/corelm-beacon-heldout-v1-evidence

REMOTE_EVIDENCE_SHA=$(git ls-remote --tags origin \
    refs/tags/corelm-beacon-heldout-v1-evidence | /usr/bin/awk '{print $1}')
test "$REMOTE_EVIDENCE_SHA" = "$BEACON_RESULT_COMMIT"
```

No GitHub CLI or Homebrew installation is required. In the authenticated GitHub
web interface, open
`https://github.com/ALLPROTO/core-lm-benchmark/releases/new?tag=corelm-beacon-heldout-v1-evidence`
and use these exact fields:

- **Choose a tag:** existing `corelm-beacon-heldout-v1-evidence`;
- **Release title:** `CoreLM beacon heldout v1 evidence`;
- **Previous tag:** `corelm-beacon-heldout-v1` if GitHub displays that optional
  field;
- **Pre-release:** off;
- **Latest release:** off if GitHub offers the choice; and
- **Description:** `First and only normative corelm-beacon-heldout-v1 attempt.
  All surviving runner artifacts are published unchanged. The authoritative
  state is the verdict in real-llm-beacon-results/outcome.json, or
  CONSUMED_INCOMPLETE when attempt.json exists without outcome.json. No retry
  can change this scientific record.`

Publish the release directly, not as a draft, and do not upload a rebuilt or
edited evidence asset. Then verify the unauthenticated public GitHub API using
only tools included with macOS:

```sh
/usr/bin/curl --fail --silent --show-error --location \
    -H 'Accept: application/vnd.github+json' \
    https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/tags/corelm-beacon-heldout-v1-evidence \
| /usr/bin/python3 -c '
import json, sys
release = json.load(sys.stdin)
assert release["tag_name"] == "corelm-beacon-heldout-v1-evidence"
assert release["draft"] is False
assert release["prerelease"] is False
assert release["immutable"] is True
assert isinstance(release["published_at"], str) and release["published_at"]
print({key: release[key] for key in (
    "tag_name", "draft", "prerelease", "immutable", "published_at"
)})
'
```

The API check must pass, and the preceding `git ls-remote` check must show that
the public tag resolves to `$BEACON_RESULT_COMMIT`. Never delete, move,
recreate, or replace the evidence tag or release after publication.

Observe the GitHub Actions `Verify` workflow on that exact result commit and
publish its actual status. A CI or verifier failure is part of the audit record:
it may be investigated, but it does not permit withholding, amending, or
replacing the first-attempt artifacts, tag, or release.

Finally, open a pull request from
`evidence/corelm-beacon-heldout-v1-outcome` to `main` so the default branch also
contains the exact same evidence bytes. The immutable evidence tag and release,
not a later merge commit, remain the canonical first-attempt record. Any
explanation or documentation update belongs in a separate later commit and must
not replace or rewrite the evidence artifacts.

## Regression boundary

Do not run a regression as part of the launch or publication sequence. After a
published terminal `PASS` or `FAIL_GATES`, the only permitted later executable
is `RealLLM/run_beacon_regression.py`; its output belongs below
`real-llm-beacon-results/regressions/` and must state
`countsTowardScientificVerdict = false`. There is no regression permission
after `FAIL_EXECUTION` or `CONSUMED_INCOMPLETE`.
