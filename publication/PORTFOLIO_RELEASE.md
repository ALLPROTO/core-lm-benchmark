# Portfolio release contract

`publication/build_portfolio_release.py` is the offline, fail-closed builder
and public verifier for the stable engineering release family
`corelm-portfolio-vN`. It does not create, move, publish, or fetch a tag. It
does not call GitHub. Do not use it for the historical
`voidtoken-v5-paper-vN` contour.

The builder accepts only:

- the exact clean `main` worktree at its canonical HTTPS origin;
- input commit/tree equal to `HEAD`, annotated tag-object SHA equal to the exact
  tag ref, upstream exactly `origin/main`, and local `origin/main` equal to
  `HEAD`;
- an existing local annotated tag with the exact `corelm-portfolio-vN` name,
  targeting that `HEAD`, with one valid SSH signature under the tracked
  `signing/allowed_signers` policy;
- locally available lab and Blind V1 commit/tree objects matching the
  canonical cross-model-lab origin;
- release-exact `CITATION.cff` version, date, Ivan Tyshchenko author identity,
  ORCID, MIT license, and repository URL;
- canonical input, demo-provenance, and runtime-assets JSON with no unknown
  keys or unresolved `@PLACEHOLDER@` values; and
- real silent H.264 demo bytes, a PNG frame, a canonical automation receipt,
  and a safe evidence archive for a non-synthetic
  `AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION`. The media classification is
  exactly `AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`; signed result and
  evidence bytes, not pixels, support the metric.

It produces exactly 14 regular files. `SHA256SUMS` covers exactly the first 12
in bytewise filename order; both it and the canonical source identity receive
detached SSH signatures in namespace `file`:

```text
REPRODUCE-corelm-portfolio-vN.md
allowed_signers
corelm-portfolio-signing.pub
corelm-portfolio-vN-demo-evidence.tar.gz
corelm-portfolio-vN-demo-poster.png
corelm-portfolio-vN-demo-provenance.json
corelm-portfolio-vN-demo.mp4
corelm-portfolio-vN-direct-dependencies.cdx.json
corelm-portfolio-vN-runtime-assets.json
corelm-portfolio-vN-source-identity.json
corelm-portfolio-vN-source-identity.json.sig
corelm-portfolio-vN-source.tar.gz
SHA256SUMS
SHA256SUMS.sig
```

`publication/verify_portfolio_github_release.py` is the separate, network-free
publication-boundary tool. Its `prepare` mode writes the exact GitHub REST
create-release request; its `verify` mode checks saved public API responses
against the exact fourteen downloaded bytes and writes a canonical receipt.
It does not call GitHub, upload an asset, create a tag, or publish a release.

Missing, extra, linked, special, tampered, credential-like, private-key, cache,
or model-weight entries are rejected. Generated manifests, instructions, and
demo evidence also reject author-only absolute paths. The exact source archive
may retain only the hardcoded `(relative path, SHA-256)` allowlist of
already-public historical evidence fields and security-test string fixtures
from the signed Git tree; a new path or byte drift fails. They are not demo
runtime provenance and cannot be silently rewritten by a packager. The source archive uses prefix
`core-lm-benchmark/`, is compressed twice in memory with gzip level 9,
filename empty, and timestamp zero; unequal bytes fail the build. The
direct-dependency CycloneDX 1.5 SBOM is generated twice by
`security/generate_direct_sbom.py`; it must be byte-identical and retain scope
`direct-python-dependencies-only`.

This V8 contract does not reopen a failed historical candidate. V3 remains
frozen at its first tag-push assertion failure. V4 remains frozen after its
automation stopped in pre-model FFprobe frame-PTS field validation, before
`AttemptLog.reserve`; no V4 model attempt was invoked or consumed. V5 passed
first-attempt tag CI. Its first local contour received a safely retryable
anonymous GitHub API HTTP 403 before the marker; after reset, its normative
contour fetched the exact responses but rejected real GitHub run/job IDs above
the tag-CI receipt validator's old signed 32-bit ceiling. That rejection also
preceded `AttemptLog.reserve`; no V5 model attempt was invoked or consumed.
The signed `corelm-portfolio-v6` candidate passed first-attempt tag CI and its
one scientific proof honestly passed at 2.052384x compression, delta NLL
-0.00000846, 99.5117% top-1
agreement, and all 1,024 heavy-replay decisions with zero maximum loss error.
Its durable state then ended `ATTEMPT_FAILED` after `REPLAY_VERIFIED` because
the preflight-built explanatory-window executable differed from the
proof-rebuilt verified app, before same-run result capture, media sealing, or
collection. Never rerun or move V3, V4, V5, or V6, and never relabel their bytes
or partial evidence as a later identity.

The signed `corelm-portfolio-v7` candidate is also frozen. Its exact source
commit is `8d53e43208f76141a01bb2c0914459fbc101e7d5`, tree
`ea82aa490c008d8560a6d44a70407d8d5e33bdbc`, and annotated tag object
`2c82497617173e3dfd965502860082ab5bf98130`. Its first-attempt tag CI passed in
Linux run `31328178519` and macOS run `31328178525`. The three V7 runner
invocations all stopped strictly before `AttemptLog.reserve`: two failed the
>=50% available-memory admission after the parallel Swift preflight build left
less than 50% available memory, and one transient pre-marker public tag-CI
admission failure had an unretained nested cause; the exact same 8-response validation
subsequently passed. The durable state and session remained absent after all
three; no proof or model attempt was consumed. Never rerun or move V7, and never
relabel it as V8. The distinct V8 single-job/low-peak-memory pre-marker build
scheduling avoids the V7 parallel-build admission pressure without weakening
the 50% available-memory threshold. Receipts bind the exact produced app SHA;
this does not claim byte-deterministic executable builds across scratch roots.
V8 retains `corelm-automated-presentation-v2`.

## Automated public tag-CI admission

Before the retained attempt is reserved or any model is loaded, the automation
runner performs one bounded online admission against anonymous
`api.github.com` endpoints. This is the sole network exception to the otherwise
offline proof: model weights, corpus assets, app execution, replay, capture,
collection, and release construction remain offline. Proxy, authentication,
redirect, ambiguous response, timeout, or API failure stops before the durable
attempt marker and is safely retryable. The admission verifies all of the
following:

1. each URL resolves in `ALLPROTO/core-lm-benchmark`;
2. each run's `head_sha` equals the input source commit;
3. conclusion is `success` and no required job is skipped or cancelled;
4. one run is the required Linux x86-64 gate and the other is the required
   macOS arm64 gate; and
5. the tag object/target still equals the signed tag-object SHA and source
   commit/tree.

The runner retains the exact eight bounded API responses, a canonical public
admission receipt, and a separately hard-pinned local SSH trust receipt. The
collector and release builder parse those raw bytes again, recompute the
receipt, bind its exact Linux/macOS URLs and annotated tag-object identity, and
archive the complete response bundle. There is no operator-confirmation
Boolean. Retained responses prove what the public API returned at admission
time; they are not a GitHub-signed attestation or a substitute for a later live
current-state recheck.
Cross-model-lab `main` and PR #5 are a separate local exact-ref boundary
checked by collector and builder; these eight benchmark-repository responses
do not claim current public lab state.

## Canonical input

The input must validate against
`schemas/portfolio-release-input.schema.json` and be serialized as compact
UTF-8, sorted keys, no ASCII escaping requirement, and exactly one final LF:

```python
target.write_bytes(
    (json.dumps(value, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False) + "\n").encode()
)
```

It binds the tag/date, source commit/tree, two distinct successful Actions run
URLs plus the same commit, lab main commit/tree, Blind V1 draft commit/tree and
lifecycle, the exact automation-only presentation contract, and absolute paths
to five local automatically collected demo assets. Absolute paths are
input-only and never enter an output asset.

The canonical V8 demo-provenance object has the exact keys documented by the
builder: source/tag; video hash, duration, dimensions, silent H.264;
poster hash, dimensions and fixed frame timestamp; both media objects
classified `AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`; macOS arm64
single-window capture; automation-receipt, executable, result, receipt and
evidence hashes; workload classification; and `synthetic_data:false`. Its
capture contract is `corelm-automated-presentation-v2` with
`automation_only:true`, `human_reviewed:false`, `manual_edits:false`,
`machine_evidence:false`, and `pixel_semantics_verified:false`. The canonical
runtime-assets object binds source/tag, macOS arm64, Python 3.12.13, the exact
window-helper, `screencapture`, FFmpeg, and ffprobe identities, and the complete
canonical Apple toolchain object copied from the run's validated
`build-provenance.json`. That object records
either `developerTools.kind:command-line-tools` with the exact CLT package
identifier/version and a null `buildVersion`, or `developerTools.kind:xcode`
with the exact Xcode identifier/version/build. It never invents a separate
`xcode_version` when only Command Line Tools were used. The manifest also binds
exact tracked lockfile and verifier/dependency-source hashes, the exact
ffprobe executable SHA-256 and first `ffprobe -version` line used by the
builder, pinned Qwen repository/revision/license and the exact seven
path/size/SHA-256 assets, pinned WikiText validation
repository/revision/path/size/SHA-256/license/source URL, executable
hash, and proof hashes. The builder verifies tracked lockfile/verifier hashes
against the clean source.

`AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION` is the exact workload enum for
the public validation range fixed before this V8 execution. It is not a media
selection or human-review state: the tagged proof-driver attempt and its first
honest terminal outcome are retained once by the owner-local automation state.
The proof driver also performs the required pinned-Qwen heavy replay; the
contour does not describe that as zero additional model execution or claim
global historical uniqueness.

The evidence archive contains a canonical public runtime projection, not the
private manifest's owner-specific absolute roots. The projection binds the
source runtime-manifest SHA-256 and schema, entry-list SHA-256, file/symlink/
byte totals, Python version, and executable SHA-256. Verification requires that
Python identity to equal `runtime-assets.json`, the receipt worker identity,
and the result environment exactly.

Before build, fetch the related refs into the exact local names
`refs/remotes/origin/main` and `refs/remotes/origin/pull/5/head`. The builder
requires the recorded lab and Blind commits/trees to equal those refs.

The evidence gzip tar has exact regular members
`run/app-run-receipt.json`, `run/validation-064-071.json`,
`run/build-provenance.json`, `run/runtime-provenance.json`,
`reports/structural-verifier.json`, `reports/fresh-model-replay.json`,
`reports/automated-media.json`, `reports/result-readiness.json`,
`reports/tag-ci-receipt.json`, `reports/local-tag-trust-receipt.json`,
`session/attempt-state.jsonl`, `session/preflight-window.mov`,
`session/post-proof-presentation.mov`, `session/same-run-result.mov`,
`session/find-proof-window`, `logs/terminal.log`, all nine exact files under
`tag-ci-responses/` (eight raw API responses plus the recomputed public
receipt), and only raw files below `run/primary-evidence/`.
Receipt/result bytes are bound to demo provenance; canonical reports bind their
hashes, source commit/tree, metric outcome, pinned model, raw-token digests and
the author-recorded replay. The replay report is labelled
`AUTHOR_RECORDED_HEAVY_REPLAY_INTEGRITY_PASS`, not independently re-executed
proof. It retains the author-side 1,024-decision maxima; the public verifier
recomputes the primary-manifest/token-metrics/per-decision digests and finite
mathematical tolerance envelope before accepting those values. The tracked
product verifier rechecks the complete retained run with metric
PASS or preserved verified metric FAIL. Every member is streamed
through secret/path scanning regardless of size. Links, special entries,
traversal, duplicate paths, secrets, model weights, and private paths fail. The
terminal log is one exact PASS-or-verified-metric-FAIL byte string. The archive
must equal the deterministic reserialization of its sorted regular members
with mode `0600`, zero uid/gid/mtime, and empty owner names.

## Run and collect one automated tagged proof

`platforms/macos/scripts/run-automated-portfolio-demo.py` is the only current
V8 capture entry point. Invoke it through `./corelm macos portfolio-demo` from
the exact clean, signed tagged checkout. It checks the tag/main/source binding,
AC power, offline runtime and assets, capture authorization, exact app/window,
and tool identities before invoking the model. It then reserves one durable
exclusive attempt for the tag, invokes the proof once, preserves its first
honest terminal PASS or verified metric FAIL, then records a fixed 12-second,
model-free `--portfolio-capture-presentation` explanatory overview from the
exact verified proof app and an
18-second capture-safe view of the exact retained result,
creates one fixed silent H.264 composition, and derives the poster at exactly
15.000000 seconds. The normal proof UI, worker log, and free-form error surface
are never captured.

```sh
DEMO_TAG=corelm-portfolio-v8
FFMPEG=/absolute/path/to/ffmpeg
FFPROBE=/absolute/path/to/ffprobe
DEMO_SESSION=/absolute/absent/corelm-portfolio-v8-automated-demo

CORELM_OFFLINE=1 \
CORELM_WHEELHOUSE="$HOME/.cache/corelm/macos/wheelhouse" \
./corelm macos portfolio-demo \
  --tag "$DEMO_TAG" \
  --output "$DEMO_SESSION" \
  --ffmpeg "$FFMPEG" \
  --ffprobe "$FFPROBE"
```

The output used by collection is the final video/poster plus the fixed bounded
session evidence: automation and readiness receipts, the nine-event state log,
three raw window segments, compiled window helper, public/local tag trust
receipts, and eight-response tag-CI bundle. The receipt binds the exact source,
run UUID and challenge, result/receipt/app hashes, two window identities,
capture tools, media bytes, decoded-frame and PTS digests, fixed poster,
privacy boundary, and durable attempt-state digest. A capture or media failure
after proof invocation consumes the tag attempt and cannot be retried to seek
a preferred result.

The exact V8 state order is
`ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL → REPLAY_VERIFIED → POST_PROOF_PRESENTATION_SURFACE_READY → POST_PROOF_PRESENTATION_CAPTURED → SAME_RUN_REOPENED → RESULT_CAPTURED → MEDIA_SEALED_FOR_COLLECTION`.
The first composed raw role is exactly `post_proof_presentation`; legacy
live-role names, paths, and command-line options are not accepted by this
contour.

The same session may contain private driver/UI logs. Do not upload or publish
the session directory as a whole. Only the explicitly named bounded inputs
below enter collection; the collector revalidates them and embeds their exact
public-safe subset into the signed evidence archive.

`publication/collect_portfolio_demo.py` is the bounded offline bridge from
that exact retained proof, media, and automation receipt to the five release
assets. It does not run a model, choose a result, or infer the newest run. Pass
the run UUID named by the receipt, the exact app, silent H.264 video, fixed PNG,
receipts, raw segments, helper, tag-CI response bundle, FFmpeg/ffprobe, signed
tag, and local lab checkout:

```sh
PORTFOLIO_PYTHON="$HOME/.cache/corelm/macos/runtime/bin/python"
LAB=/absolute/clean/core-lm-cross-model-lab
RUN_DIRECTORY=/absolute/exact/run-directory-from-automation-receipt
INPUTS=/absolute/absent/corelm-portfolio-v8-inputs

publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" collect_portfolio_demo.py \
  --repository "$PWD" \
  --cross-model-lab "$LAB" \
  --run-directory "$RUN_DIRECTORY" \
  --app "$PWD/dist/CoreLMBenchmark.app" \
  --video "$DEMO_SESSION/$DEMO_TAG-demo.mp4" \
  --poster "$DEMO_SESSION/$DEMO_TAG-demo-poster.png" \
  --automation-receipt "$DEMO_SESSION/automation-receipt.json" \
  --result-readiness "$DEMO_SESSION/result-readiness.json" \
  --attempt-state "$DEMO_SESSION/attempt-state.jsonl" \
  --preflight-segment "$DEMO_SESSION/preflight-window.mov" \
  --post-proof-presentation-segment "$DEMO_SESSION/post-proof-presentation.mov" \
  --result-segment "$DEMO_SESSION/same-run-result.mov" \
  --window-helper "$DEMO_SESSION/find-proof-window" \
  --tag-ci-receipt "$DEMO_SESSION/tag-ci-receipt.json" \
  --local-tag-trust-receipt "$DEMO_SESSION/local-tag-trust-receipt.json" \
  --tag-ci-bundle "$DEMO_SESSION/tag-ci-bundle" \
  --ffmpeg "$FFMPEG" \
  --ffprobe "$FFPROBE" \
  --tag "$DEMO_TAG" \
  --release-date 2026-08-09 \
  --output "$INPUTS"
```

The collector recomputes product evidence, fixed-poster and decoded-video
identity, requires all proof and automation reports, preserves an honest metric
FAIL, checks privacy and exact archive topology, and writes canonical
provenance/runtime manifests, a deterministic evidence gzip tar, and a private
release-input draft. Before verification and archiving it seals all run inputs
into a private stable snapshot; later changes to the original run cannot alter
the collected bytes. Never publish `release-input.private.json`, because its
local asset paths are input-only. See `docs/DEMO.md` for the complete preflight
and failure semantics.
The live run has one additional non-evidence entry: the app-created
`python-cache/`. It is mandatory, must be an empty owner-controlled mode-`0700`
directory, is held open and rechecked throughout sealing, and is never copied
into the snapshot or evidence archive. Any contents, link, replacement, missing
directory, or unsafe mode fail closed. Temporary evidence extraction uses the
canonical resolved directory, so the macOS `/var` to `/private/var` alias cannot
invalidate an otherwise canonical extracted run.

## Build locally

Do not place the private key in the repository or input JSON. Use an absolute
0600 path through the environment; the tool verifies that its public half
matches the hard-pinned tracked ED25519 key and never emits or copies the key
path:

Install a local `ffprobe` first (for example from the platform FFmpeg package).
The Core LM bootstrap intentionally does not install it. Build mode binds its
exact executable SHA-256 and version; public verify uses the reproducer's
local binary only as a caller-side decoder check.

```sh
./corelm macos bootstrap
./corelm macos build
PORTFOLIO_PYTHON="$HOME/.cache/corelm/macos/runtime/bin/python"
test "$("$PORTFOLIO_PYTHON" -I -B -c \
  'import platform; print(platform.python_version())')" = 3.12.13
FFPROBE=$(command -v ffprobe)
test -x "$FFPROBE"
export CORELM_PORTFOLIO_SIGNING_KEY=/absolute/private/path
publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" build_portfolio_release.py \
  --input /absolute/release-input.json \
  --repository /absolute/core-lm-benchmark \
  --cross-model-lab /absolute/core-lm-cross-model-lab \
  --ffprobe "$FFPROBE" \
  --output /absolute/corelm-portfolio-vN-assets
```

The output path must not exist. Build occurs in a private sibling staging
directory, performs a full public verification, then renames the directory
only after every gate passes. No release is published by this command.

## Public offline verification

Use the verifier from the exact signed source tag and point it at a directory
containing all downloaded release files:

```sh
case "$(uname -s):$(uname -m)" in
  Darwin:arm64)
    ./corelm macos bootstrap
    ./corelm macos build
    PORTFOLIO_PYTHON="$HOME/.cache/corelm/macos/runtime/bin/python" ;;
  Linux:x86_64)
    ./corelm linux bootstrap
    ./corelm linux build
    PORTFOLIO_PYTHON="$HOME/.cache/corelm/linux/runtime/bin/python" ;;
  *) exit 2 ;;
esac
FFPROBE=$(command -v ffprobe)
test -x "$FFPROBE"
publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" build_portfolio_release.py \
  --verify /absolute/downloaded-assets \
  --ffprobe "$FFPROBE"
```

This checks the exact 14-file set, public-key hard pins, both detached
signatures, the sorted checksum manifest, canonical identities, all internal
hash bindings, archive safety, source commit PAX identity, SBOM scope,
reproduction document, complete PNG structure/CRC, MP4 `avc1`/`avcC` sample
description, nonempty media payload, and the Git tree reconstructed from every
source-archive blob and executable bit. Required local `ffprobe` rechecks
codec, audio, dimensions, and duration as a **caller-side decoder check**; it
is not a release trust root, and without it the tool refuses to print PASS.
Build mode additionally requires its executable hash and version to equal the
runtime-assets record. The success message is explicitly **offline signed-
artifact PASS — caller-side decoder check only — live CI API recheck
required**. A source tar proves archive-to-tree identity; its PAX commit field
alone does not independently prove commit-to-tree identity without the signed
identity/tag or a canonical Git object database. Offline verification also
does not regenerate GitHub API receipts, the recorded real-model replay, or
the SBOM from a fresh environment. It does not establish current GitHub state,
human-independent replication, or a Blind/generalization result.

## Exact GitHub publication contract

Publication uses the existing, publicly visible signed annotated tag. The tag
must never be created implicitly by the release API. From the exact signed tag
checkout and the already verified fourteen-asset directory, generate the
request into a new absolute path:

```sh
TAG=corelm-portfolio-v8
ASSET_DIR=/absolute/corelm-portfolio-v8-assets
CREATE_REQUEST=/absolute/corelm-portfolio-v8-create-release.json
PORTFOLIO_PYTHON=/absolute/locked/python
FFPROBE=/absolute/caller-selected/ffprobe
publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" verify_portfolio_github_release.py prepare \
  --assets "$ASSET_DIR" \
  --ffprobe "$FFPROBE" \
  --output "$CREATE_REQUEST"
```

The canonical request has exactly these seven keys and values:

```json
{
  "tag_name": "corelm-portfolio-v8",
  "target_commitish": "main",
  "name": "Core LM Portfolio v8 — reproducible real-model KV-cache benchmark",
  "body": "generated exactly from the signed source identity and SHA256SUMS digest",
  "draft": false,
  "prerelease": false,
  "make_latest": "true"
}
```

The on-disk JSON is compact canonical JSON; the expanded object above is only
a readable field contract. The exact body contains the supported engineering
claim, scientific exclusions, source commit/tree/tag object, both CI URLs,
demo hashes, exact `AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`
classification, the pixels-versus-evidence and semantic-privacy boundaries,
`SHA256SUMS` hash, the fourteen-asset verification instruction,
caller-decoder boundary, preservation policy, and the explicit warning that
policy is not GitHub's `immutable` API value.

After a final tag/ref and CI API recheck, the maintainer may create the release
with that request and upload the already verified directory. A representative
operator sequence is:

```sh
test -z "$(git status --short)"
test "$(git rev-parse HEAD)" = "$(git rev-parse "$TAG^{commit}")"
gh api --method POST \
  "repos/ALLPROTO/core-lm-benchmark/releases" \
  --input "$CREATE_REQUEST" \
  > /absolute/operator-log/release-create-response.json
gh release upload "$TAG" "$ASSET_DIR"/* \
  --repo ALLPROTO/core-lm-benchmark
```

Do not use `--clobber`; an existing name is a hard stop. The prepare tool has
already rejected any extra or missing local asset, but the operator must also
retain the exact command, response, and exit status. The `make_latest` input is
the caller-side publication request; `/releases/latest` is checked separately
after upload rather than inferred from that input.

## Logged-out post-upload verification

Fetch five API views and all fourteen assets without a GitHub token, cookie,
`.netrc`, or curl configuration. Use a new directory and a scrubbed environment;
the exact commit and tag-object SHA come from the signed source identity:

```sh
TAG=corelm-portfolio-v8
ASSET_DIR=/absolute/corelm-portfolio-v8-assets
PORTFOLIO_PYTHON=/absolute/locked/python
FFPROBE=/absolute/caller-selected/ffprobe
PUBLIC_AUDIT=/absolute/new-public-audit
API_SNAPSHOTS="$PUBLIC_AUDIT/api"
DOWNLOADED="$PUBLIC_AUDIT/assets"
RECEIPT_DIRECTORY=/absolute/new-public-receipts
test ! -e "$PUBLIC_AUDIT"
test ! -e "$RECEIPT_DIRECTORY"
mkdir -m 700 "$PUBLIC_AUDIT"
mkdir -m 700 "$API_SNAPSHOTS"
mkdir -m 700 "$DOWNLOADED"
mkdir -m 700 "$RECEIPT_DIRECTORY"

PUBLIC_CURL=(/usr/bin/env -i \
  HOME=/nonexistent LANG=C LC_ALL=C \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  /usr/bin/curl -q --fail --silent --show-error --location \
  --proto '=https' --tlsv1.2 \
  -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2022-11-28')

TAG_OBJECT=$("$PORTFOLIO_PYTHON" -I -B - \
  "$ASSET_DIR/$TAG-source-identity.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["source"]["tag_object"])
PY
)
SOURCE_COMMIT=$("$PORTFOLIO_PYTHON" -I -B - \
  "$ASSET_DIR/$TAG-source-identity.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["source"]["commit"])
PY
)

"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/tags/$TAG" \
  > "$API_SNAPSHOTS/release.json"
"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/latest" \
  > "$API_SNAPSHOTS/latest.json"
"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/git/ref/tags/$TAG" \
  > "$API_SNAPSHOTS/tag-ref.json"
"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/git/tags/$TAG_OBJECT" \
  > "$API_SNAPSHOTS/tag-object.json"
"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/git/commits/$SOURCE_COMMIT" \
  > "$API_SNAPSHOTS/commit-object.json"

for name in \
  "REPRODUCE-$TAG.md" \
  allowed_signers \
  corelm-portfolio-signing.pub \
  "$TAG-demo-evidence.tar.gz" \
  "$TAG-demo-poster.png" \
  "$TAG-demo-provenance.json" \
  "$TAG-demo.mp4" \
  "$TAG-direct-dependencies.cdx.json" \
  "$TAG-runtime-assets.json" \
  "$TAG-source-identity.json" \
  "$TAG-source-identity.json.sig" \
  "$TAG-source.tar.gz" \
  SHA256SUMS \
  SHA256SUMS.sig
do
  "${PUBLIC_CURL[@]}" \
    "https://github.com/ALLPROTO/core-lm-benchmark/releases/download/$TAG/$name" \
    --output "$DOWNLOADED/$name"
done
```

The GitHub-boundary verifier creates one private exact-fourteen-asset snapshot,
runs the complete offline signed-artifact verifier on that snapshot, and
derives all API size/hash records from the same snapshot. It refuses PASS if
either detached SSH signature, any artifact gate, or the required caller-side
decoder check fails. Retain the caller-selected `ffprobe` executable SHA-256
and exact first version line written to the receipt; that identity describes
the invocation and is not a release-signing, GitHub, or CI trust root.

```sh
RECEIPT="$RECEIPT_DIRECTORY/corelm-portfolio-v8-github-release-receipt.json"
publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" verify_portfolio_github_release.py verify \
  --assets "$DOWNLOADED" \
  --ffprobe "$FFPROBE" \
  --release-json "$API_SNAPSHOTS/release.json" \
  --latest-json "$API_SNAPSHOTS/latest.json" \
  --tag-ref-json "$API_SNAPSHOTS/tag-ref.json" \
  --tag-object-json "$API_SNAPSHOTS/tag-object.json" \
  --commit-object-json "$API_SNAPSHOTS/commit-object.json" \
  --receipt "$RECEIPT"
```

The verifier requires exact tag, title, body, target branch, `draft:false`,
`prerelease:false`, the same complete body/target/published/asset contract in
`/releases/latest`, annotated tag-object/commit binding, commit-to-tree binding,
fourteen uploaded names, sizes, download URLs, and a mandatory exact
`sha256:<local-hash>` API digest for every asset. A missing/null digest fails.
GitHub's tag `verified` value remains informational; the SSH signature from its
API payload must independently verify in namespace `git` under the attached
`allowed_signers`. The receipt records `immutable:true` or `immutable:false`
exactly as returned. Either boolean may coexist with a metadata-consistency
PASS; only `GITHUB_API_REPORTED_TRUE` permits the narrower statement that the
saved API response reported true at that moment. Neither value changes the
project rule that tags and assets are never moved or replaced.

The receipt binds the saved-response hashes but cannot prove that the fetch was
logged out or that GitHub is still in the same state; those are transport and
time boundaries. The V8 acceptance contour uses the scrubbed logged-out API
fetches and verifier receipt and has no browser inspection or human-review
gate. A later viewer may inspect the public page, but that observation is not
an input to V8 acceptance and cannot retroactively close independent-
replication gate G10. Keep the receipt and API files in the operator/design or
Zenodo evidence bundle. Do not upload them back into the same fourteen-asset
release, edit its body after verification, or move its tag; doing so would
create a self-reference and invalidate the recorded snapshot.

Create request output and receipts must live in new directories disjoint from
the asset directory and saved-API input directories. The tool rejects an
output path that is equal to, inside, or an ancestor of any protected input
directory; this prevents generated output from contaminating a verified input
set.

## Presentation successor after publication

Call the automation-capable tagged release-source commit C0. C0 owns the
signed source/evidence identity and the immutable fourteen-asset release. The
presentation successor C1 is optional for G12 artifact integrity, but it is
mandatory for G03 and `CV_READY` while the public README has no current
poster/video. C1 adds no evidence and requires no human-review acceptance. It
is allowed only after the saved release and latest APIs both report
`immutable:true`, the signed tag still resolves to C0, and the full C0 artifact
verification passes. C1 must be exactly one signed child of C0 and its public
compare response must contain exactly these changes:

```text
README.md                              modified
docs/media/corelm-result.png           added
```

An ordinary GitHub merge commit would give C1 two parents, while squash or
rebase would replace the locally SSH-signed object. Neither is allowed. Run
the required checks on the exact signed C1 commit, then publish that same
object to `main` only by an explicitly authorized fast-forward from C0. Never
force-push or rewrite C1. The saved GitHub commit response and the verifier
below must still validate its local SSH signature and sole parent C0.

The PNG bytes must equal the released `$TAG-demo-poster.png`. README must
contain exactly once each of the immutable tagged poster and video download
URLs; `/releases/latest/download/`, branch/raw links, additional release-media
URLs, renames, or any third changed path fail. Fetch the public compare and C1
commit responses logged out, retain the existing five C0 API snapshots, and
run:

The verifier does not trust `files[].sha` from that saved compare response as
the source of truth. `SUCCESSOR_ROOT` must be a clean canonical-origin Git
checkout whose exact `HEAD`, `HEAD^{tree}`, sole parent, index, tracked blobs,
modes, and local two-path diff reconstruct the signed C1 object chain. The C1
query disables and rejects replacement refs and legacy grafts, parses the raw
commit object's tree/parent headers, and pins `/usr/bin/ssh-keygen` instead of
trusting repo-local signature-program configuration. The C1
README is deterministic: it is the byte-exact C0 README with only this block
inserted immediately after `# Core LM Benchmark` and its blank line (replace
the shell variables with their exact values; do not edit the wording):

```markdown
<!-- corelm-portfolio-presentation-v1:start -->
## Verified real-model demo

![Core LM benchmark result](https://github.com/ALLPROTO/core-lm-benchmark/releases/download/$TAG/$TAG-demo-poster.png)

[Watch the complete demo video](https://github.com/ALLPROTO/core-lm-benchmark/releases/download/$TAG/$TAG-demo.mp4)

This presentation was recorded from SSH-signed release source [`$SOURCE_COMMIT`](https://github.com/ALLPROTO/core-lm-benchmark/commit/$SOURCE_COMMIT) at annotated tag [`$TAG`](https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/$TAG). It is an `AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION` on pinned public data, classified as `AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE`. Signed result and evidence files—not the pixels—support the metrics. Automated checks found no configured violation; semantic pixel privacy and independent review are not claimed. This presentation-only successor does not alter the released source or evidence and is **not** a blind/generalization result, model-weight-compression result, or independent human replication.
<!-- corelm-portfolio-presentation-v1:end -->
```

Any other README edit—including a stronger scientific claim—fails even if a
saved compare response is changed to match those bytes.

```sh
C0="$SOURCE_COMMIT"
: "${C1:?set the exact 40-hex signed successor commit}"
printf '%s\n' "$C1" | grep -Eq '^[0-9a-f]{40}$' || exit 2
SUCCESSOR_ROOT=/absolute/clean-c1-checkout
SUCCESSOR_RECEIPT=/absolute/new-successor-receipts/presentation-successor.json

"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/compare/$C0...$C1" \
  > "$API_SNAPSHOTS/compare-c0-c1.json"
"${PUBLIC_CURL[@]}" \
  "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/commits/$C1" \
  > "$API_SNAPSHOTS/successor-commit.json"

publication/run_portfolio_python.sh \
  "$PORTFOLIO_PYTHON" verify_portfolio_github_release.py verify-successor \
  --assets "$DOWNLOADED" \
  --ffprobe "$FFPROBE" \
  --release-json "$API_SNAPSHOTS/release.json" \
  --latest-json "$API_SNAPSHOTS/latest.json" \
  --tag-ref-json "$API_SNAPSHOTS/tag-ref.json" \
  --tag-object-json "$API_SNAPSHOTS/tag-object.json" \
  --commit-object-json "$API_SNAPSHOTS/commit-object.json" \
  --compare-json "$API_SNAPSHOTS/compare-c0-c1.json" \
  --successor-commit-json "$API_SNAPSHOTS/successor-commit.json" \
  --successor-root "$SUCCESSOR_ROOT" \
  --receipt "$SUCCESSOR_RECEIPT"
```

The verifier checks C1's API signature payload locally with `ssh-keygen -Y
verify -n git`; GitHub's own `verified` boolean is recorded but does not replace
that cryptographic check. C1 is presentation only, never release source or
evidence. The C0 tag must remain unchanged. Keeping media links out of C0
avoids a source-to-release-to-source self-reference. Neither the automated C0
release nor C1 closes G10; that requires a later published clean-clone
replication by a non-author, non-agent person.
