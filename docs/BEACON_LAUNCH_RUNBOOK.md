# Archived beacon held-out launch and publication runbook

> **ARCHIVED — DO NOT EXECUTE.** The first and only normative attempt completed
> with terminal **PASS** and consumed this suite. Every launch, attempt,
> evidence-creation, push, tag, and release command below is retained only as a
> historical record of the published procedure. It must not be used to create
> or publish another scientific attempt. A future experiment requires a new
> suite identity, pulse, preregistration, and deadline. See the
> [evidence and CI report](BEACON_EVIDENCE_REPORT.md).

This is the public, non-normative operator checklist for the already frozen
`corelm-beacon-heldout-v1` experiment. If this checklist and a frozen artifact
ever differ, [`RealLLM/BEACON_HELDOUT_PROTOCOL.md`](../RealLLM/BEACON_HELDOUT_PROTOCOL.md),
[`RealLLM/beacon_registration.json`](../RealLLM/beacon_registration.json), and
[`RealLLM/beacon_freeze.json`](../RealLLM/beacon_freeze.json) are authoritative.
Do not edit the frozen tag or its immutable release to update this checklist.

From an evolving checkout, `./corelm beacon verify-tag` may be used to verify
the exact tag topology and all 26 frozen Git blobs. That read-only command does
not import the runner or access the model, data, NIST service, or result paths;
it cannot replace any tagged launch step below.

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

The frozen protocol permitted execution as soon as the target pulse existed.
As a stricter, non-normative operator rule publicly announced before reveal,
the one-shot was not invoked before 20:15 Prague (`18:15Z`). This did not
change the frozen 18:00 pulse or earliest start. The fixed delay reduces the
observed beacon-publication-lag risk without fetching or polling NIST before
the attempt marker; it cannot guarantee future endpoint availability.

## Execution-build boundary

Only one build is allowed to create the scientific record:

| Build | Role in this experiment | Historical one-shot permission |
|---|---|---|
| Clean detached `corelm-beacon-heldout-v1` checkout on Apple silicon, exact locked Python runtime, MPS device | Frozen normative build | **Consumed by the single recorded attempt** |
| Current macOS application build | Packaging, UI, and regression validation only | No |
| Current Linux CPU build | Cross-platform packaging and regression validation only | No; the frozen experiment requires Apple MPS |

The application UI must remain closed during the normative invocation. It is
useful for inspecting later regression runs, but it is not an alternate beacon
runner and would consume memory on the 8 GiB target Mac. A green current-branch
macOS or Linux build cannot substitute for a failure of the frozen build, and a
failure in a regression-only build cannot change the frozen scientific result.

The frozen tag's historical `Verify` run had a macOS-app failure after a
temporary SwiftPM `.build` directory disappeared; its Python-core and
supply-chain jobs passed. This is a known packaging-CI limitation, not a beacon
result. The evidence commit triggered fresh branch and tag workflows; their
actual statuses are recorded without changing the evidence.

Before the one-shot, maintainers committed and merged this non-normative
runbook and the manual `Audit Immutable Beacon Evidence` workflow to `main`,
then recorded the exact control commit and fresh macOS/Linux CI statuses. That
did not modify the frozen tag; it made the read-only post-publication audit
dispatchable from the default branch before evidence existed.

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

The frozen direct-requirements file retains its historical `recorded
real-model pilot` header. Its bytes and complete lock closure are normative;
no package may be removed or substituted.

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

## Failure map and stop rules

All checks above `attempt.json` creation are preflight checks. A rejection there
does not consume the scientific attempt: stop, correct the condition, and run
the complete launch block again. Once `attempt.json` exists, every failure is
terminal and the runner must never be invoked again.

| Failure class | When it can occur | Prevention or required response |
|---|---|---|
| Wrong checkout, branch, tag, origin, dirty files, bytecode, or pre-existing result | Before marker | Exact detached-tag, clean-tree, artifact, tag, and remote-ref gates; correct and restart only if no marker exists |
| Too early, past deadline, battery power, scheduled sleep/restart, memory pressure, or low disk | Before marker | Fixed UTC gate, AC-only rule, power-schedule check, at least 30% free memory, and at least 6 GiB free on the result volume |
| Wrong Python/package closure, unavailable MPS, unsafe cache, or corrupt/missing assets | Before marker | Exact lock-closure check, dependency/MPS import preflight, private cache checks, and an immediate `--offline-only` hash verification |
| Redirecting cache, proxy, TLS, Python, or dynamic-loader environment | Before or after marker | Reject inherited override variables before invoking the runner; do not improvise a proxy or certificate override |
| GitHub tag/release verification unavailable | Before marker inside the frozen runner | No attempt is created; preserve the checkout and retry only after confirming `attempt.json` is absent |
| Exact NIST pulse/certificate unavailable or invalid | After marker | Irreducible without revealing the target early; publish `FAIL_EXECUTION` or `CONSUMED_INCOMPLETE` unchanged |
| Power loss, MPS/kernel failure, OOM, disk/I/O failure, or checkout mutation | After marker | AC, open lid, closed heavy applications, `caffeinate`, memory/disk headroom, and no concurrent Core LM run reduce but cannot eliminate this risk |
| Branch, tag, release, verifier, or CI failure during publication | After the run | Never rerun or edit evidence; resume idempotently from the first missing publication step and report every status |

There is one known frozen failure edge that cannot be repaired without changing
the preregistered implementation: if resolution verification or its durable
write fails after an in-memory resolution was built, a terminal execution
outcome can reference a resolution hash while `resolution.json` is absent. The
independent verifier will then fail. The correct response is still to publish
all surviving bytes and the verifier failure; never manufacture the missing
file. Disk, filesystem, environment, and network precautions below minimize
the reachable causes but do not turn this into a retryable event.

## Operator timeline for the single attempt

| Prague time | Action |
|---|---|
| Now through 19:30 | Keep the Mac continuously on AC and charging. Finish and publicly record only non-normative runbook/CI changes; do not rebuild or modify the frozen checkout, runtime, or cache after its final verification. |
| 19:30–19:45 | Close the Core LM UI, browsers, Codex/ChatGPT, IDEs, sync clients, and all memory/GPU-heavy programs. Keep the lid open; do not install updates, reboot, switch network, or start another proof/regression. |
| 19:45–20:10 | In an ordinary foreground Terminal, enter only the dedicated detached checkout. Confirm time sync, AC, memory, disk, Wi-Fi/GitHub, clean tree, no proof lock/results, and no evidence refs. Do not contact any NIST beacon endpoint. |
| 20:10–20:15 | Stop all other activity. Keep the terminal visible, cable untouched, Wi-Fi unchanged, and do not open the checkout in Finder or an editor. |
| After 20:15 | Paste the complete block below once. Its time gate, all safety preflights, and exactly one runner invocation are one fail-fast unit. Do not pipe, redirect, background, interrupt, or close the terminal. |
| Immediately after return | Do not invoke the runner again. Classify only from surviving files, run the read-only verifier when an outcome exists, and publish unchanged evidence using the idempotent sequence below. |

The expected model phase is only a few minutes, but no duration is guaranteed.
The registered completion deadline remains 20:00 Prague on 4 August 2026.

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
PATH=/usr/bin:/bin:/usr/sbin:/sbin
LANG=C
LC_ALL=C
export PATH LANG LC_ALL

BEACON_TAG_SHA=0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44
BEACON_TAG=corelm-beacon-heldout-v1
BEACON_PYTHON="$HOME/.cache/corelm-app-runtime/bin/python"
BEACON_CACHE="$HOME/.cache/corelm-model-assets"
BEACON_OPERATOR_NOT_BEFORE=1785694500
BEACON_OPERATOR_DEADLINE=1785866400
BEACON_MIN_FREE_KIB=6291456
BEACON_MIN_FREE_MEMORY_PERCENT=30
BEACON_MAX_CLOCK_OFFSET_SECONDS=1.0
BEACON_EVIDENCE_BRANCH=refs/heads/evidence/corelm-beacon-heldout-v1-outcome
BEACON_EVIDENCE_TAG=refs/tags/corelm-beacon-heldout-v1-evidence

BEACON_GIT_OR_LOADER_ENV="$(
    /usr/bin/env \
    | /usr/bin/awk -F= '$1 ~ /^(GIT_|DYLD_)/ { print $1 }'
)"
test -z "$BEACON_GIT_OR_LOADER_ENV"
GIT_CONFIG_GLOBAL=/dev/null
GIT_CONFIG_NOSYSTEM=1
GIT_TERMINAL_PROMPT=0
export GIT_CONFIG_GLOBAL GIT_CONFIG_NOSYSTEM GIT_TERMINAL_PROMPT

BEACON_ACCOUNT_HOME="$(
    /usr/bin/dscl . -read "/Users/$(/usr/bin/id -un)" NFSHomeDirectory \
    | /usr/bin/awk '{ print $2 }'
)"
test "$HOME" = "$BEACON_ACCOUNT_HOME"
test -d "$HOME"
test ! -L "$HOME"

BEACON_ROOT="$(/usr/bin/git rev-parse --show-toplevel)"
test "$(pwd -P)" = "$(cd "$BEACON_ROOT" && pwd -P)"
test "$(/usr/bin/git rev-parse HEAD)" = "$BEACON_TAG_SHA"
test -z "$(/usr/bin/git symbolic-ref -q --short HEAD || true)"
test "$(/usr/bin/git rev-parse "refs/tags/$BEACON_TAG^{commit}")" = \
    "$BEACON_TAG_SHA"
test "$(/usr/bin/git remote get-url origin)" = \
    https://github.com/ALLPROTO/core-lm-benchmark.git
test -z "$(/usr/bin/git status --porcelain=v1 --untracked-files=all --ignored=no)"
test "$(/bin/date -u +%s)" -ge "$BEACON_OPERATOR_NOT_BEFORE"
test "$(/bin/date -u +%s)" -le "$BEACON_OPERATOR_DEADLINE"
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
test -d real-llm-beacon-results
test ! -L real-llm-beacon-results
test -w real-llm-beacon-results
test -d "$HOME/.cache/corelm-app-runtime"
test ! -L "$HOME/.cache/corelm-app-runtime"
test -x "$BEACON_PYTHON"
test -d "$BEACON_CACHE"
test ! -L "$BEACON_CACHE"

for BEACON_UNSAFE_ENV in \
    PYTHONHOME PYTHONINSPECT PYTHONPATH PYTHONSTARTUP PYTHONUSERBASE \
    HF_HUB_CACHE HUGGINGFACE_HUB_CACHE HF_ASSETS_CACHE \
    TRANSFORMERS_CACHE HF_ENDPOINT HF_TOKEN HUGGING_FACE_HUB_TOKEN \
    HF_HUB_OFFLINE TRANSFORMERS_OFFLINE TOKENIZERS_PARALLELISM \
    HF_HUB_DISABLE_TELEMETRY HF_HUB_DISABLE_PROGRESS_BARS \
    HF_HUB_DISABLE_IMPLICIT_TOKEN \
    PYTORCH_MPS_HIGH_WATERMARK_RATIO PYTORCH_MPS_LOW_WATERMARK_RATIO \
    PYTORCH_MPS_FAST_MATH PYTORCH_ENABLE_MPS_FALLBACK \
    PYTORCH_MPS_PREFER_METAL OMP_NUM_THREADS OPENBLAS_NUM_THREADS \
    MKL_NUM_THREADS VECLIB_MAXIMUM_THREADS NUMEXPR_NUM_THREADS \
    HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY \
    http_proxy https_proxy all_proxy no_proxy \
    SSL_CERT_FILE SSL_CERT_DIR REQUESTS_CA_BUNDLE CURL_CA_BUNDLE \
    DYLD_INSERT_LIBRARIES DYLD_LIBRARY_PATH DYLD_FRAMEWORK_PATH \
    DYLD_FALLBACK_LIBRARY_PATH LD_PRELOAD
do
    if /usr/bin/printenv "$BEACON_UNSAFE_ENV" >/dev/null 2>&1; then
        printf 'Unsafe inherited environment: %s\n' \
            "$BEACON_UNSAFE_ENV" >&2
        exit 1
    fi
done

"$BEACON_PYTHON" -I -B -c '
import urllib.request
if urllib.request.getproxies():
    raise SystemExit("system proxy/PAC/SOCKS configuration is a NO-GO")
print("BEACON NETWORK POLICY PASS: no environment or system proxy is active.")
'

BEACON_REMOTE_BRANCH="$(
    /usr/bin/git ls-remote --heads origin "$BEACON_EVIDENCE_BRANCH"
)"
BEACON_REMOTE_TAG="$(
    /usr/bin/git ls-remote --tags origin "$BEACON_EVIDENCE_TAG"
)"
test -z "$BEACON_REMOTE_BRANCH"
test -z "$BEACON_REMOTE_TAG"

./security/verify_app_bundle.sh dist/CoreLMBenchmark.app
"$BEACON_PYTHON" -I -B -c '
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from security.generate_python_runtime_manifest import validate_manifest_files
manifest_path = Path(
    "dist/CoreLMBenchmark.app/Contents/Resources/python-runtime-manifest.json"
)
if manifest_path.is_symlink() or manifest_path.stat().st_size > 32 * 1024 * 1024:
    raise SystemExit("runtime manifest is unsafe or oversized")
manifest = json.loads(manifest_path.read_bytes())
validate_manifest_files(manifest)
file_count = manifest["fileCount"]
symlink_count = manifest["symlinkCount"]
total_bytes = manifest["totalBytes"]
print(
    "BEACON RUNTIME MANIFEST PASS: "
    f"{file_count} files, {symlink_count} symlinks, {total_bytes} bytes."
)
'
"$BEACON_PYTHON" -I -B -m pip check
"$BEACON_PYTHON" -I -B security/verify_locked_environment.py \
    --runtime "$HOME/.cache/corelm-app-runtime" \
    --lock .github/locks/pip-bootstrap.txt \
    --lock RealLLM/requirements.lock
HF_HOME="$BEACON_CACHE" \
"$BEACON_PYTHON" -I -B RealLLM/prepare_beacon_assets.py \
    --cache "$BEACON_CACHE" --offline-only
HF_HOME="$BEACON_CACHE" \
"$BEACON_PYTHON" -I -B -c '
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from RealLLM.run_beacon_one_shot import _configure_frozen_process_environment
from RealLLM.beacon_evaluation import prepare_runtime
_configure_frozen_process_environment()
runtime = prepare_runtime()
torch = runtime["torch"]
assert torch.backends.mps.is_built()
assert torch.backends.mps.is_available()
assert torch.mps.device_count() >= 1
print("BEACON RUNTIME PASS: exact versions and MPS device are available.")
'

"$BEACON_PYTHON" -I -B -c '
import os
import stat
from pathlib import Path
root = Path("real-llm-beacon-results")
root_status = root.lstat()
if (
    not stat.S_ISDIR(root_status.st_mode)
    or stat.S_ISLNK(root_status.st_mode)
    or root_status.st_uid != os.getuid()
    or root_status.st_mode & 0o022
):
    raise RuntimeError("result directory ownership or mode is unsafe")
probe = root / ".beacon-preflight-write-probe"
descriptor = None
created = False
try:
    descriptor = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    created = True
    payload = b"corelm-beacon-write-probe\n"
    if os.write(descriptor, payload) != len(payload):
        raise RuntimeError("filesystem probe write was incomplete")
    os.fsync(descriptor)
    os.close(descriptor)
    descriptor = None
    if probe.read_bytes() != b"corelm-beacon-write-probe\n":
        raise RuntimeError("filesystem probe readback differs")
finally:
    if descriptor is not None:
        os.close(descriptor)
    if created:
        probe.unlink()
directory = os.open(root, os.O_RDONLY)
try:
    os.fsync(directory)
finally:
    os.close(directory)
print("BEACON FILESYSTEM PASS: exclusive write, fsync, readback, and unlink.")
'

BEACON_FREE_KIB="$(
    /bin/df -Pk real-llm-beacon-results \
    | /usr/bin/awk 'NR == 2 { print $4 }'
)"
case "$BEACON_FREE_KIB" in
    ''|*[!0-9]*) printf 'Cannot read free disk space.\n' >&2; exit 1 ;;
esac
test "$BEACON_FREE_KIB" -ge "$BEACON_MIN_FREE_KIB"

BEACON_FREE_MEMORY_PERCENT="$(
    /usr/bin/memory_pressure -Q \
    | /usr/bin/awk -F ': ' \
        '/^System-wide memory free percentage:/ { gsub(/%/, "", $2); print $2 }'
)"
case "$BEACON_FREE_MEMORY_PERCENT" in
    ''|*[!0-9]*) printf 'Cannot read free memory percentage.\n' >&2; exit 1 ;;
esac
test "$BEACON_FREE_MEMORY_PERCENT" -ge \
    "$BEACON_MIN_FREE_MEMORY_PERCENT"

BEACON_CLOCK_OUTPUT="$(/usr/bin/sntp -d time.apple.com 2>&1)"
BEACON_CLOCK_OFFSET="$(
    printf '%s\n' "$BEACON_CLOCK_OUTPUT" \
    | /usr/bin/awk '/^[[:space:]]*offset:/ { gsub(/[()]/, "", $3); print $3 }'
)"
"$BEACON_PYTHON" -I -B -c '
import math
import sys
offsets = [float(value) for value in sys.argv[1].split()]
limit = float(sys.argv[2])
if not offsets or any(
    not math.isfinite(offset) or abs(offset) > limit for offset in offsets
):
    raise SystemExit("system clock offset exceeds the operator limit")
print(f"BEACON CLOCK PASS: max_abs_offset={max(map(abs, offsets)):.6f}s")
' "$BEACON_CLOCK_OFFSET" "$BEACON_MAX_CLOCK_OFFSET_SECONDS"

BEACON_POWER_SCHEDULE="$(/usr/bin/pmset -g sched)"
if printf '%s\n' "$BEACON_POWER_SCHEDULE" \
    | /usr/bin/grep -Eiq '(shutdown|restart|sleep)'
then
    printf 'Scheduled shutdown, restart, or sleep is a NO-GO.\n' >&2
    exit 1
fi
/usr/sbin/ioreg -r -k AppleClamshellState -d 4 \
    | /usr/bin/grep -Fq '"AppleClamshellState" = No'
/usr/bin/pmset -g batt | /usr/bin/grep -Fq "Now drawing from 'AC Power'"

test -z "$(/usr/bin/git status --porcelain=v1 --untracked-files=all --ignored=no)"

if HF_HOME="$BEACON_CACHE" \
    /usr/bin/caffeinate -dimsu \
    "$BEACON_PYTHON" -I -B \
        RealLLM/run_beacon_one_shot.py --local-files-only; then
    BEACON_EXIT=0
else
    BEACON_EXIT=$?
fi
if ! /bin/sync; then
    printf 'WARNING: post-run filesystem sync failed.\n' >&2
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
| `attempt.json` or `outcome.json` exists but is truncated, unreadable, schema-invalid, or has no recognized terminal verdict | Consumed invalid/incomplete evidence; publish every surviving byte unchanged, claim neither pass nor gate result, and never retry. |
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

For `NOT_STARTED_PREFLIGHT_REJECTION`, do not create the evidence branch, tag,
or release. For every state with an existing `attempt.json`, publication is
mandatory even when JSON parsing or independent verification fails. Record the
verifier exit status and later CI URLs in the evidence pull-request body or a
separate later documentation commit, never in the frozen result directory.

## Exact publication sequence

The evidence branch and evidence tag names below are fixed before reveal. Use
the same procedure for `PASS`, `FAIL_GATES`, `FAIL_EXECUTION`, and
`CONSUMED_INCOMPLETE`. Commit all and only the surviving files below
`real-llm-beacon-results/`; do not add a hand-edited outcome, summary, or
checksum file to that directory.

```sh
(
set -eu
PATH=/usr/bin:/bin:/usr/sbin:/sbin
LANG=C
LC_ALL=C
export PATH LANG LC_ALL

test "$(/usr/bin/git rev-parse HEAD)" = \
    0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44
test -e real-llm-beacon-results/attempt.json \
    || test -L real-llm-beacon-results/attempt.json
/usr/bin/git switch -c evidence/corelm-beacon-heldout-v1-outcome
/usr/bin/git add -A -- real-llm-beacon-results
/usr/bin/git diff --cached --check
test -n "$(/usr/bin/git diff --cached --name-only)"
/usr/bin/git diff --cached --name-status \
| while IFS="$(printf '\t')" read -r BEACON_STATUS BEACON_PATH
do
    test "$BEACON_STATUS" = A
    case "$BEACON_PATH" in
        real-llm-beacon-results/attempt.json \
        |real-llm-beacon-results/resolution.json \
        |real-llm-beacon-results/outcome.json \
        |real-llm-beacon-results/primary-evidence/manifest.json \
        |real-llm-beacon-results/primary-evidence/token-metrics.json \
        |real-llm-beacon-results/primary-evidence/containers/block-[0-9][0-9][0-9]/layer-[0-9][0-9].vtl5) ;;
        *) printf 'Unexpected staged path: %s\n' "$BEACON_PATH" >&2; exit 1 ;;
    esac
    BEACON_INDEX_MODE="$(
        /usr/bin/git ls-files --stage -- "$BEACON_PATH" \
        | /usr/bin/awk '{ print $1 }'
    )"
    test "$BEACON_INDEX_MODE" = 100644
    BEACON_INDEX_SHA="$(/usr/bin/git rev-parse ":$BEACON_PATH")"
    BEACON_DISK_SHA="$(
        /usr/bin/git hash-object --no-filters -- "$BEACON_PATH"
    )"
    test "$BEACON_INDEX_SHA" = "$BEACON_DISK_SHA"
done
/usr/bin/git -c core.hooksPath=/dev/null -c commit.gpgSign=false \
    commit -m "Publish corelm beacon heldout v1 attempt"

BEACON_RESULT_COMMIT=$(/usr/bin/git rev-parse HEAD)
test "$(/usr/bin/git rev-parse HEAD^)" = \
    0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44
/usr/bin/git diff-tree --no-commit-id --name-status -r HEAD \
| while IFS="$(printf '\t')" read -r BEACON_STATUS BEACON_PATH
do
    test "$BEACON_STATUS" = A
    case "$BEACON_PATH" in
        real-llm-beacon-results/attempt.json \
        |real-llm-beacon-results/resolution.json \
        |real-llm-beacon-results/outcome.json \
        |real-llm-beacon-results/primary-evidence/manifest.json \
        |real-llm-beacon-results/primary-evidence/token-metrics.json \
        |real-llm-beacon-results/primary-evidence/containers/block-[0-9][0-9][0-9]/layer-[0-9][0-9].vtl5) ;;
        *) printf 'Unexpected committed path: %s\n' "$BEACON_PATH" >&2; exit 1 ;;
    esac
done
test -z "$(/usr/bin/git ls-remote --heads origin \
    refs/heads/evidence/corelm-beacon-heldout-v1-outcome)"
/usr/bin/git push origin \
    HEAD:refs/heads/evidence/corelm-beacon-heldout-v1-outcome
test "$(/usr/bin/git rev-parse HEAD)" = "$BEACON_RESULT_COMMIT"
/usr/bin/git -c tag.gpgSign=false tag \
    corelm-beacon-heldout-v1-evidence "$BEACON_RESULT_COMMIT"
test -z "$(/usr/bin/git ls-remote --tags origin \
    refs/tags/corelm-beacon-heldout-v1-evidence)"
/usr/bin/git push origin refs/tags/corelm-beacon-heldout-v1-evidence

REMOTE_EVIDENCE_BRANCH_SHA=$(/usr/bin/git ls-remote --heads origin \
    refs/heads/evidence/corelm-beacon-heldout-v1-outcome \
    | /usr/bin/awk '{print $1}')
REMOTE_EVIDENCE_SHA=$(/usr/bin/git ls-remote --tags origin \
    refs/tags/corelm-beacon-heldout-v1-evidence | /usr/bin/awk '{print $1}')
test "$REMOTE_EVIDENCE_BRANCH_SHA" = "$BEACON_RESULT_COMMIT"
test "$REMOTE_EVIDENCE_SHA" = "$BEACON_RESULT_COMMIT"
)
```

Publication is idempotent only when every existing remote ref already points to
`$BEACON_RESULT_COMMIT`. If a network or browser failure interrupts the
sequence, query the branch, tag, and release before doing anything else:

```sh
(
set -eu
BEACON_RESULT_COMMIT=$(/usr/bin/git rev-parse HEAD)
REMOTE_EVIDENCE_BRANCH_SHA=$(/usr/bin/git ls-remote --heads origin \
    refs/heads/evidence/corelm-beacon-heldout-v1-outcome \
    | /usr/bin/awk '{print $1}')
REMOTE_EVIDENCE_TAG_SHA=$(/usr/bin/git ls-remote --tags origin \
    refs/tags/corelm-beacon-heldout-v1-evidence \
    | /usr/bin/awk '{print $1}')

test -z "$REMOTE_EVIDENCE_BRANCH_SHA" \
    || test "$REMOTE_EVIDENCE_BRANCH_SHA" = "$BEACON_RESULT_COMMIT"
test -z "$REMOTE_EVIDENCE_TAG_SHA" \
    || test "$REMOTE_EVIDENCE_TAG_SHA" = "$BEACON_RESULT_COMMIT"
)
```

An absent branch may be pushed, an absent tag may be created at the exact
result commit and pushed, and an existing matching ref is left untouched. Any
different SHA is a hard stop: never force-push, delete, move, or recreate a ref.
If the release already exists, verify it instead of creating another one.

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
- **Description** as one plain-text paragraph: `First and only normative corelm-beacon-heldout-v1 attempt. All surviving runner artifacts are published unchanged. The authoritative state is the verdict in real-llm-beacon-results/outcome.json, or CONSUMED_INCOMPLETE when attempt.json exists without outcome.json, or CONSUMED_INVALID_EVIDENCE when the published artifacts or verifier are invalid. No retry can change this scientific record.`

Before clicking Publish, read back the existing tag, exact title, exact
one-paragraph description, pre-release off, latest off, and an empty asset
list. Publish directly, not as a draft, and do not upload a rebuilt or edited
evidence asset. Then verify the unauthenticated public GitHub API using only
tools included with macOS:

```sh
/usr/bin/curl --fail --silent --show-error --location \
    -H 'Accept: application/vnd.github+json' \
    https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/tags/corelm-beacon-heldout-v1-evidence \
| /usr/bin/python3 -c '
import json, sys
release = json.load(sys.stdin)
expected_body = (
    "First and only normative corelm-beacon-heldout-v1 attempt. "
    "All surviving runner artifacts are published unchanged. "
    "The authoritative state is the verdict in "
    "real-llm-beacon-results/outcome.json, or CONSUMED_INCOMPLETE when "
    "attempt.json exists without outcome.json, or CONSUMED_INVALID_EVIDENCE "
    "when the published artifacts or verifier are invalid. No retry can "
    "change this scientific record."
)
assert release["tag_name"] == "corelm-beacon-heldout-v1-evidence"
assert release["name"] == "CoreLM beacon heldout v1 evidence"
assert release["body"] == expected_body
assert release["html_url"] == (
    "https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/"
    "corelm-beacon-heldout-v1-evidence"
)
assert release["draft"] is False
assert release["prerelease"] is False
assert release["immutable"] is True
assert release["assets"] == []
assert isinstance(release["published_at"], str) and release["published_at"]
print({key: release[key] for key in (
    "tag_name", "name", "draft", "prerelease", "immutable", "published_at"
)})
'

/usr/bin/curl --fail --silent --show-error --location \
    -H 'Accept: application/vnd.github+json' \
    https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/latest \
| /usr/bin/python3 -c '
import json, sys
latest = json.load(sys.stdin)
assert latest["tag_name"] != "corelm-beacon-heldout-v1-evidence"
print({"latest_release_tag": latest["tag_name"]})
'
```

The API check must pass, and the preceding `git ls-remote` check must show that
the public tag resolves to `$BEACON_RESULT_COMMIT`. Never delete, move,
recreate, or replace the evidence tag or release after publication.

If an immutable release field is wrong, disclose the discrepancy. It does not
authorize deletion, recreation, tag movement, evidence editing, or a rerun.

Observe the GitHub Actions `Verify` workflow on that exact result commit and
publish the actual statuses of both branch-push and tag-push runs. The frozen
workflow does not independently verify the newly created evidence files; use
the separate manual evidence-audit workflow from the evolving default branch
for that read-only check. A CI or verifier failure is part of the audit record:
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
