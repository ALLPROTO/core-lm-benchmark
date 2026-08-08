# Reproducible macOS demo capture

This runbook produces the screenshot and public demo required by portfolio gate
G03. The video and poster are
`HUMAN_REVIEWED_PRESENTATION_NOT_MACHINE_EVIDENCE`: they help a person inspect
the UI, but no machine claim binds pixels to the recorded computation. The
retained receipt, result, raw-token/container evidence, canonical verifier
reports, and hashes are the machine-verifiable record.

The run is a repeatability check on the already-public WikiText validation
blocks 64–71. Call the selected run an
**author-selected public-validation regression**. It is not a blind,
held-out, beacon, generalization, or state-of-the-art result. Do not run a
beacon command, open a frozen holdout, or reuse beacon evidence for this demo.

## What the finished media must show

The final video must be at most 90 seconds and show all of these facts from one
fresh run:

1. the public repository remote, exact commit, exact tree, and a clean checkout;
2. the native SwiftUI application with architecture modules, live progress, and
   the real-Qwen/MPS workload label;
3. the completed compression, delta-NLL, top-1, and KL metrics, regression
   gates, charts, result digest, and verifier verdict;
4. a separate challenge-bound verifier outcome of either `PASS` or
   `VERIFIED — METRIC FAIL`; and
5. an explicit statement that setup and inference time were cut from the video
   and that the result is a public regression, not a blind experiment.

Do not fabricate a result screen, animate progress, replace a metric, splice
together different runs, or use a previously published screenshot as if it
were current. A hard time cut is allowed only when it is labelled on screen and
both sides belong to the same challenge-bound run.

## 1. Prepare a clean, exact source checkout

Use a new Terminal window on an Apple-Silicon Mac. These commands require the
local `main`, its `origin/main`, and the already-signed portfolio tag to name
one exact commit/tree. Do not fetch or pull again during the recording:

```zsh
set -euo pipefail
PROMPT='demo% '
RPROMPT=''
umask 077
DEMO_TAG=corelm-portfolio-v1
printf '%s\n' "$DEMO_TAG" | /usr/bin/grep -Eq \
  '^corelm-portfolio-v[1-9][0-9]*$'
git clone https://github.com/ALLPROTO/core-lm-benchmark.git core-lm-demo-source
cd core-lm-demo-source
git fetch --no-tags origin main
git fetch --no-tags origin \
  "refs/tags/$DEMO_TAG:refs/tags/$DEMO_TAG"
git switch main
git merge --ff-only origin/main
test "$(git rev-parse HEAD^{commit})" = \
  "$(git rev-parse "$DEMO_TAG^{commit}")"

git -c gpg.format=ssh \
  -c gpg.ssh.allowedSignersFile="$PWD/signing/allowed_signers" \
  verify-tag "$DEMO_TAG"

DEMO_COMMIT="$(git rev-parse HEAD^{commit})"
DEMO_TREE="$(git rev-parse HEAD^{tree})"
DEMO_REMOTE="$(git remote get-url origin)"
test "$DEMO_REMOTE" = "https://github.com/ALLPROTO/core-lm-benchmark.git"
test -z "$(git status --porcelain=v1 --untracked-files=all)"
test "$DEMO_COMMIT" = "$(git rev-parse origin/main^{commit})"
test "$(git tag --points-at HEAD)" = "$DEMO_TAG"

DEMO_CAPTURE_DIR="$HOME/Desktop/corelm-demo-capture"
test ! -e "$DEMO_CAPTURE_DIR"
mkdir -m 700 "$DEMO_CAPTURE_DIR"

{
  printf 'repository: %s\n' "$DEMO_REMOTE"
  printf 'tag: %s\n' "$DEMO_TAG"
  printf 'commit: %s\n' "$DEMO_COMMIT"
  printf 'tree: %s\n' "$DEMO_TREE"
  printf '%s\n' 'worktree: CLEAN'
  printf '%s\n' 'claim: AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION'
} | tee "$DEMO_CAPTURE_DIR/source-identity.txt"
```

Set `DEMO_TAG` to the already-created current signed portfolio tag. If any
`test` or `verify-tag` fails, stop. Do not enable `CORELM_ALLOW_DIRTY_SOURCE`,
edit the clone, or record from another checkout. The tag must exist before the
proof because the embedded build provenance records its exact name.

Clear the Terminal, print only the path-free identity card, and record it for
ten seconds. Select only the Terminal content region:

```zsh
clear
cat "$DEMO_CAPTURE_DIR/source-identity.txt"
/usr/sbin/screencapture -i -Jvideo -V10 -k \
  "$DEMO_CAPTURE_DIR/01-source.mov"
```

Run the read-only preflight before recording:

```zsh
./corelm macos doctor
```

If the registered Python is unavailable, run `./corelm macos bootstrap` and
then repeat the doctor. Give Terminal (or the Screenshot application) Screen &
System Audio Recording permission before the real run; testing that permission
must not involve a model invocation.

## 2. Create one selected real application proof

Generate the non-secret freshness challenge in the same shell. Keep the private
operator log outside the repository; it contains local runtime paths and is not
a publication asset.

```zsh
DEMO_CHALLENGE="$(/usr/bin/openssl rand -hex 32)"
test "${#DEMO_CHALLENGE}" -eq 64

set -o pipefail
CORELM_PROOF_CHALLENGE="$DEMO_CHALLENGE" \
  ./corelm macos proof 2>&1 \
  | tee "$DEMO_CAPTURE_DIR/proof-private.log"
```

The command performs a clean committed build, launches the visible app, runs
pinned Qwen2.5-0.5B on Apple MPS and real registered WikiText, creates a fresh
receipt, runs the standard-library verifier, and then performs the separate
heavy model replay. A metric PASS ends with `END-TO-END PROOF PASS`; a fully
executed and verified metric FAIL ends with
`END-TO-END PROOF VERIFIED — METRIC FAIL`. Either outcome belongs in the
recording unchanged. A timeout, memory stop, or verifier failure is an
infrastructure failure; do not edit, rerun selectively, or present any FAIL as
a PASS. In particular, do not rerun a verified metric FAIL to obtain a PASS.
The collector cannot prove that this was the first historical attempt or that
no other run exists; it deliberately classifies the supplied run as
`AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION`.
On either honest terminal outcome, the proof run also retains canonical
`proof-reports/structural-verifier.json`,
`proof-reports/fresh-model-replay.json`, and `proof-reports/terminal.log`.
The replay report is created only after the author-side heavy verifier reruns
all 1,024 pinned-Qwen decisions. Publication verification binds that recorded
report to the retained primary-manifest, token-metrics, and canonical
per-decision digests and recomputes its tolerance envelope. It labels the
outcome `AUTHOR_RECORDED_HEAVY_REPLAY_INTEGRITY_PASS`; the release verifier does
not claim that it independently executed Qwen a second time.

While the proof is running, record the live segment only after the application
window appears. In a second Terminal window use the same fixed capture
directory and macOS's built-in recorder:

```zsh
DEMO_CAPTURE_DIR="$HOME/Desktop/corelm-demo-capture"
test -d "$DEMO_CAPTURE_DIR"
/usr/sbin/screencapture -i -Jvideo -V20 -k \
  "$DEMO_CAPTURE_DIR/02-live-run.mov"
```

Select only the application window or its content region. The 20-second bound
is deliberate. Show the orange/running architecture states, progress bar,
Qwen/MPS label, and live log. Do not wait on camera for the full workload.

## 3. Reopen and independently verify that same run

After the full proof exits successfully, reopen the application. It loads the
newest locally verified result without starting another inference run:

```zsh
open dist/CoreLMBenchmark.app
```

Record the completed UI for at most 30 seconds and capture a still image:

```zsh
DEMO_CAPTURE_DIR="$HOME/Desktop/corelm-demo-capture"
/usr/sbin/screencapture -i -Jvideo -V30 -k \
  "$DEMO_CAPTURE_DIR/04-result.mov"
/usr/sbin/screencapture -i -w \
  "$DEMO_CAPTURE_DIR/corelm-result.png"
```

Show the completed architecture states, all four metric cards, model and
device, blocks and predictions, stored bytes, verifier/integrity status,
regression gate rows, preserved metric verdict, charts, result SHA-256, and the
relative run ID. A valid metric FAIL must remain visible rather than being
replaced by a later PASS. The current application intentionally displays only
a UUID-relative result label; an absolute `/Users/...` path is a privacy defect
and invalidates the capture.

Now close or move the app window, clear the Terminal, and run the independent
verifier again with the original challenge. This does not run the model:

```zsh
DEMO_PROOF_ID="$(/usr/bin/sed -n \
  's/^Fresh proof runtime ID: //p' \
  "$DEMO_CAPTURE_DIR/proof-private.log")"
test "${#DEMO_PROOF_ID}" -eq 36
printf '%s\n' "$DEMO_PROOF_ID" | /usr/bin/grep -Eq \
  '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'

DEMO_RUNTIME="$HOME/.cache/corelm/macos/proof-runtimes/$DEMO_PROOF_ID"
case "$DEMO_RUNTIME" in
  "$HOME/.cache/corelm/macos/proof-runtimes/"*) ;;
  *) printf '%s\n' 'unexpected proof runtime path' >&2; exit 1 ;;
esac
test -d "$DEMO_RUNTIME"
test ! -L "$DEMO_RUNTIME"
DEMO_PYTHON="$DEMO_RUNTIME/bin/python"
test -x "$DEMO_PYTHON"

DEMO_RUN_ID="$(/usr/bin/sed -n \
  's/^Verified run ID: //p' \
  "$DEMO_CAPTURE_DIR/proof-private.log")"
test "${#DEMO_RUN_ID}" -eq 36
printf '%s\n' "$DEMO_RUN_ID" | /usr/bin/grep -Eq \
  '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
DEMO_RUN_DIR="$HOME/Library/Application Support/CoreLMBenchmark/real-llm-results/$DEMO_RUN_ID"
test -d "$DEMO_RUN_DIR"
test ! -L "$DEMO_RUN_DIR"

clear
printf '%s\n' \
  'TIME CUT — setup, inference, and heavy replay omitted from the video.' \
  'SAME RUN — original challenge is checked below.' \
  'CLAIM — public-validation regression; not blind/generalization.'

"$DEMO_PYTHON" -I -B security/verify_local_app_run.py \
  --run-directory "$DEMO_RUN_DIR" \
  --app dist/CoreLMBenchmark.app \
  --challenge "$DEMO_CHALLENGE" \
  | tee "$DEMO_CAPTURE_DIR/verifier.txt"

DEMO_VERIFIER_LINE="$(/usr/bin/sed -n '1p' \
  "$DEMO_CAPTURE_DIR/verifier.txt")"
case "$DEMO_VERIFIER_LINE" in
  'FRESH LOCAL APP PROOF PASS:'*) ;;
  'FRESH LOCAL APP PROOF VERIFIED — METRIC FAIL:'*) ;;
  *) printf '%s\n' 'unexpected verifier outcome' >&2; exit 1 ;;
esac
```

The first line must begin with exactly one of the two accepted prefixes above.
Both mean that the retained evidence was structurally verified; the second
preserves a real metric failure. Do not rerun a verified metric FAIL in pursuit
of the first prefix. The verifier prints only the canonical run UUID, never a
home-directory path.

Bind the app's embedded provenance to the recorded checkout and save the
path-free output:

```zsh
DEMO_PROVENANCE="dist/CoreLMBenchmark.app/Contents/Resources/build-provenance.json"
cp "$DEMO_PROVENANCE" "$DEMO_CAPTURE_DIR/build-provenance.json"

"$DEMO_PYTHON" -I -B -c '
import json, pathlib, sys
document = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
source = document["source"]
if source["mode"] != "git" or source["dirty"] is not False:
    raise SystemExit("app source provenance is not a clean Git checkout")
if source["commit"] != sys.argv[2] or source["tree"] != sys.argv[3]:
    raise SystemExit("app source identity differs from the recorded checkout")
print("embedded source: CLEAN GIT")
print("embedded commit:", source["commit"])
print("embedded tree:", source["tree"])
print("embedded remote:", source["remote"])
' "$DEMO_PROVENANCE" "$DEMO_COMMIT" "$DEMO_TREE" \
  | tee "$DEMO_CAPTURE_DIR/embedded-source-identity.txt"
```

Record the explicit time-cut card for four seconds before the result clip:

```zsh
clear
printf '%s\n' \
  'TIME CUT — setup, inference, and heavy replay omitted from the video.' \
  'SAME RUN — the original challenge is checked in the final clip.' \
  'PUBLIC REGRESSION — not blind/generalization.'
/usr/sbin/screencapture -i -Jvideo -V4 -k \
  "$DEMO_CAPTURE_DIR/03-time-cut.mov"
```

After the result clip, print only the path-free verifier and embedded source
records, then record them for at most 21 seconds:

```zsh
clear
cat "$DEMO_CAPTURE_DIR/verifier.txt"
cat "$DEMO_CAPTURE_DIR/embedded-source-identity.txt"
printf '%s\n' 'PUBLIC REGRESSION — not blind/generalization.'
/usr/sbin/screencapture -i -Jvideo -V21 -k \
  "$DEMO_CAPTURE_DIR/05-verifier.mov"
```

Use a minimal prompt such as `demo%`; never show `pwd`, the private proof log,
shell history, home-directory paths, email, or tokens.

## 4. Exact storyboard (maximum 85 seconds)

| Time | Required picture and narration/caption |
|---:|---|
| 0–10 s | Public remote, exact commit/tree, `worktree: CLEAN`, and `AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION`. |
| 10–30 s | Native app during the same run: architecture list, orange states, real Qwen/MPS label, progress, live log. |
| 30–34 s | Visible card: `TIME CUT — setup, inference, and replay omitted; SAME RUN`. |
| 34–64 s | Reopened app: completed states, four metrics, workload counts, charts, regression gates, preserved metric verdict, result SHA and relative run ID. |
| 64–85 s | Challenge-bound independent verifier `PASS` or `VERIFIED — METRIC FAIL`, embedded commit/tree match, and `not blind/generalization` boundary. |

Silence is preferable to improvised claims. If narration is used, the concise
claim is: “I built a native macOS and Linux benchmark that serializes complete
KV-cache containers, runs pinned real Qwen on registered WikiText, and verifies
the retained evidence through separate code.”

Join only clips from this run in QuickTime Player: open the first clip, choose
**Edit → Add Clip to End**, add the remaining clips in storyboard order, trim
dead time, then choose **File → Export As → 1080p**. Do not use speed-up to make
the progress appear faster; the explicit time cut is clearer and auditable.
Save the exported movie as
`$HOME/Desktop/corelm-demo-capture/corelm-demo-85s.mov`; do not overwrite an
older capture.

## 5. Privacy, integrity, and publication checks

Turn on Do Not Disturb and close chat, mail, password-manager, SSH, browser, and
notification windows before capture. Inspect every frame in QuickTime. If a
private value appears, discard the media and record it again; do not cover
metrics, verdicts, hashes, or failure messages with a blur or overlay.

The following checks are additive. They cannot detect private text rendered
inside video frames, so manual frame-by-frame review remains mandatory.

```zsh
DEMO_VIDEO="$DEMO_CAPTURE_DIR/corelm-demo-85s.mov"
DEMO_SCREENSHOT="$DEMO_CAPTURE_DIR/corelm-result.png"
test -f "$DEMO_VIDEO"
test -f "$DEMO_SCREENSHOT"

/usr/bin/xattr -c "$DEMO_VIDEO" "$DEMO_SCREENSHOT"
DEMO_DURATION="$(/usr/bin/mdls -raw -name kMDItemDurationSeconds "$DEMO_VIDEO")"
/usr/bin/awk -v duration="$DEMO_DURATION" \
  'BEGIN { exit !(duration > 0 && duration <= 90) }'

/usr/bin/mdls \
  -name kMDItemDurationSeconds \
  -name kMDItemAuthors \
  -name kMDItemWhereFroms \
  "$DEMO_VIDEO"
/usr/bin/sips -g pixelWidth -g pixelHeight "$DEMO_SCREENSHOT"

for DEMO_MEDIA in "$DEMO_VIDEO" "$DEMO_SCREENSHOT"; do
  if /usr/bin/strings -a "$DEMO_MEDIA" \
    | /usr/bin/grep -E \
      '/Users/|/home/|gh[pousr]_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+|BEGIN [A-Z ]*PRIVATE KEY'
  then
    printf 'PRIVACY CHECK FAIL: %s\n' "$DEMO_MEDIA" >&2
    exit 1
  fi
done

(
  cd "$DEMO_CAPTURE_DIR"
  /usr/bin/shasum -a 256 \
    "$(/usr/bin/basename "$DEMO_VIDEO")" \
    "$(/usr/bin/basename "$DEMO_SCREENSHOT")" \
    source-identity.txt \
    embedded-source-identity.txt \
    build-provenance.json \
    verifier.txt
) | tee "$DEMO_CAPTURE_DIR/SHA256SUMS"

if /usr/bin/grep -Eq '/Users/|/home/' "$DEMO_CAPTURE_DIR/SHA256SUMS"; then
  printf '%s\n' 'PRIVACY CHECK FAIL: checksum manifest contains a home path' >&2
  exit 1
fi
```

Filesystem extended attributes are not embedded-container metadata. Before the
collector, use the same local FFmpeg installation as the recorded `ffprobe` to
produce a metadata-free delivery copy and derive the poster from its stated
timestamp. Clear format and stream titles, comments, creation time, encoder,
and handler names explicitly. The collector rejects PNG `tEXt`, `zTXt`,
`iTXt`, `eXIf`, and `iCCP` chunks and free-text video/stream tags; it fails if
the export still contains them. Do not weaken that gate for an editor's output.

Also search manually for the account name, legal/private email addresses,
hostnames, Wi-Fi names, calendar events, notification text, API tokens, SSH
material, and browser tabs. The public name “Ivan Tyshchenko”, public ORCID,
public repository URL, commit/tree IDs, run UUID, result SHA-256, and random
challenge are not secrets.

Track the reviewed PNG under `docs/media/` only after it exists. Publish the
reviewed video as the canonical signed release asset (preferred over adding a
large movie to Git), record its SHA-256 in the release notes, and link that one
asset from the first screen of `README.md`. Keep `proof-private.log` local; it
is an operator aid, not a release asset.

## 6. Collect one bounded release input set

After the frame-by-frame privacy review, run the tracked offline collector.
It does not execute a model and does not infer a result. It accepts only the
explicit author-selected app-run UUID parsed above, first copies every run
input into a private stable snapshot, recomputes the structural evidence, checks
the two machine reports, preserves either metric PASS or verified metric FAIL,
and rejects missing, synthetic, private-path, or selection-tainted evidence.

Set every value explicitly. The two Actions URLs must be distinct successful
runs for `DEMO_COMMIT`; live API checking remains a separate release-operator
gate. The poster timestamp must name the actual frame represented by the PNG.

```zsh
: "${DEMO_TAG:?set the exact signed portfolio tag}"
: "${DEMO_RUN_DIR:?derive the exact app run above}"
: "${DEMO_PYTHON:?derive the retained proof Python above}"
: "${DEMO_POSTER_TIMESTAMP_SECONDS:?inspect the exported video timeline}"
: "${DEMO_RELEASE_DATE:?use YYYY-MM-DD matching CITATION.cff}"
: "${DEMO_LINUX_CI_URL:?set the exact successful Actions run URL}"
: "${DEMO_MACOS_CI_URL:?set the distinct successful Actions run URL}"

CROSS_MODEL_LAB=/absolute/core-lm-cross-model-lab
FFPROBE=/absolute/path/to/ffprobe
DEMO_OUTPUT="$HOME/Desktop/corelm-portfolio-inputs-$DEMO_TAG"
test -d "$CROSS_MODEL_LAB"
test -x "$FFPROBE"
test ! -e "$DEMO_OUTPUT"

"$DEMO_PYTHON" -I -B publication/collect_portfolio_demo.py \
  --repository "$(pwd -P)" \
  --cross-model-lab "$CROSS_MODEL_LAB" \
  --run-directory "$DEMO_RUN_DIR" \
  --app "$(pwd -P)/dist/CoreLMBenchmark.app" \
  --video "$DEMO_CAPTURE_DIR/corelm-demo-85s.mov" \
  --poster "$DEMO_CAPTURE_DIR/corelm-result.png" \
  --poster-frame-timestamp-seconds "$DEMO_POSTER_TIMESTAMP_SECONDS" \
  --ffprobe "$FFPROBE" \
  --tag "$DEMO_TAG" \
  --release-date "$DEMO_RELEASE_DATE" \
  --linux-ci-url "$DEMO_LINUX_CI_URL" \
  --macos-ci-url "$DEMO_MACOS_CI_URL" \
  --output "$DEMO_OUTPUT"
```

Success produces the copied video and PNG, canonical
`demo-provenance.json`, canonical `runtime-assets.json`, deterministic
`demo-evidence.tar.gz`, and `release-input.private.json`. The latter contains
local absolute paths solely for the offline release builder: never publish it.
The evidence tar uses one byte-canonical gzip/tar representation: sorted
regular files, mode `0600`, zero uid/gid/mtime, and empty owner names. Public
verification deterministically reserializes it and requires byte equality. Its
public runtime projection binds the private runtime-manifest digest, aggregate
structure, entry-list digest, Python version, and executable hash without
publishing local runtime roots.
The collector records the exact local ffprobe executable hash and version as a
decoder identity; that is not a claim about upstream FFmpeg source signing.

## Acceptance record

G03 is satisfied only when all rows can be filled with public URLs or hashes:

| Item | Required value |
|---|---|
| Source | GitHub commit and tree shown in the media and embedded provenance |
| Build | clean `./corelm macos proof` from that exact commit |
| Workload | pinned Qwen2.5-0.5B, Apple MPS, WikiText validation 64–71 |
| Freshness | verifier accepts the original 64-hex challenge |
| Video | public URL, duration ≤90 s, SHA-256 |
| Screenshot | tracked path, SHA-256 |
| Verdict | app and separate verifier agree on `PASS` or preserved `VERIFIED — METRIC FAIL`; heavy replay succeeds |
| Claim | explicitly labelled public regression, not blind/generalization |

An uncommitted local clip, a clip without exact source identity, or a screenshot
of an older result does not satisfy G03.
