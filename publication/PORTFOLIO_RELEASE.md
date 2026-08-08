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
- real H.264/AAC-or-silent demo bytes, a PNG frame, and a safe evidence archive
  for a non-synthetic `AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION`.

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

## Mandatory CI API preflight

Online CI validation is deliberately outside this offline tool. This remains
a release-time blocker, not a builder claim. Immediately before build, query
both run IDs named in the input through the GitHub Actions API and confirm all
of the following:

1. each URL resolves in `ALLPROTO/core-lm-benchmark`;
2. each run's `head_sha` equals the input source commit;
3. conclusion is `success` and no required job is skipped or cancelled;
4. one run is the required Linux x86-64 gate and the other is the required
   macOS arm64 gate; and
5. the tag object/target still equals the signed tag-object SHA and source
   commit/tree; and
6. cross-model-lab `main` and PR #5 head still equal the recorded related
   commit/tree identities.

Retain the API responses with the release operator log. Only after this check
may `--ci-api-preflight-confirmed` be supplied. The flag records operator
acknowledgement; it does not turn a declaration into online verification.
Public verify mode checks only a signed operator assertion containing canonical
URLs and commit binding; it does not prove GitHub state without network access.
The source identity labels this exact boundary
`SIGNED_OPERATOR_ASSERTION_REQUIRES_LIVE_API_RECHECK`. Downloaded-run API
validation must therefore be repeated as a separate logged-out release audit.

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
lifecycle, and absolute paths to five local recorded-demo assets. Absolute
paths are input-only and never enter an output asset.

The canonical demo-provenance object has the exact keys documented by the
builder: source/tag; video hash, duration, dimensions, H.264 and AAC/silent;
poster hash, dimensions and frame timestamp; both media objects classified
`HUMAN_REVIEWED_PRESENTATION_NOT_MACHINE_EVIDENCE`; macOS arm64 capture; executable,
result, receipt and evidence hashes; classification; and
`synthetic_data:false`. The canonical runtime-assets object binds source/tag,
macOS arm64, Python 3.12.13, and the complete canonical Apple toolchain object
copied from the run's validated `build-provenance.json`. That object records
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
`reports/structural-verifier.json`, `reports/fresh-model-replay.json`, and
`logs/terminal.log`, plus only raw files below `run/primary-evidence/`.
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

## Collect one completed demo proof

`publication/collect_portfolio_demo.py` is the bounded offline bridge from one
completed macOS proof and reviewed presentation media to the five release
assets. It does not run a model or infer the newest result. The operator must
pass the exact author-selected run UUID directory, exact app, one H.264 MOV/MP4,
one PNG, signed portfolio tag,
two exact CI URLs, and local lab checkout. It recomputes product evidence,
requires both reports retained by `./corelm macos proof`, preserves an honest
metric FAIL, checks privacy and archive topology, and writes canonical
provenance/runtime manifests, a deterministic evidence gzip tar, and a private
release-input draft. See `docs/DEMO.md` for the exact capture and collector
commands. Before verification/archiving it seals all run inputs into a private
stable snapshot; later changes to the original run cannot alter the collected
bytes. This classification makes no global first-attempt or no-rerun claim.
Never publish `release-input.private.json`, because its local asset paths are
input-only.

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
"$PORTFOLIO_PYTHON" -I -B publication/build_portfolio_release.py \
  --input /absolute/release-input.json \
  --repository /absolute/core-lm-benchmark \
  --cross-model-lab /absolute/core-lm-cross-model-lab \
  --ffprobe "$FFPROBE" \
  --output /absolute/corelm-portfolio-vN-assets \
  --ci-api-preflight-confirmed
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
"$PORTFOLIO_PYTHON" -I -B publication/build_portfolio_release.py \
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
TAG=corelm-portfolio-v1
ASSET_DIR=/absolute/corelm-portfolio-v1-assets
CREATE_REQUEST=/absolute/corelm-portfolio-v1-create-release.json
PORTFOLIO_PYTHON=/absolute/locked/python
FFPROBE=/absolute/caller-selected/ffprobe
"$PORTFOLIO_PYTHON" -I -B \
  publication/verify_portfolio_github_release.py prepare \
  --assets "$ASSET_DIR" \
  --ffprobe "$FFPROBE" \
  --output "$CREATE_REQUEST"
```

The canonical request has exactly these seven keys and values:

```json
{
  "tag_name": "corelm-portfolio-v1",
  "target_commitish": "main",
  "name": "Core LM Portfolio v1 — reproducible real-model KV-cache benchmark",
  "body": "generated exactly from the signed source identity and SHA256SUMS digest",
  "draft": false,
  "prerelease": false,
  "make_latest": "true"
}
```

The on-disk JSON is compact canonical JSON; the expanded object above is only
a readable field contract. The exact body contains the supported engineering
claim, scientific exclusions, source commit/tree/tag object, both CI URLs,
demo hashes, `SHA256SUMS` hash, the fourteen-asset verification instruction,
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
TAG=corelm-portfolio-v1
ASSET_DIR=/absolute/corelm-portfolio-v1-assets
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
RECEIPT="$RECEIPT_DIRECTORY/corelm-portfolio-v1-github-release-receipt.json"
"$PORTFOLIO_PYTHON" -I -B \
  publication/verify_portfolio_github_release.py verify \
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
time boundaries. Confirm the release page in a private/logged-out browser as a
separate human check. Keep the receipt and API files in the operator/design or
Zenodo evidence bundle. Do not upload them back into the same fourteen-asset
release, edit its body after verification, or move its tag; doing so would
create a self-reference and invalidate the recorded snapshot.

Create request output and receipts must live in new directories disjoint from
the asset directory and saved-API input directories. The tool rejects an
output path that is equal to, inside, or an ancestor of any protected input
directory; this prevents generated output from contaminating a verified input
set.

## Presentation successor after publication

Call the tagged release-source commit C0. The presentation successor C1 is
optional for G12 artifact integrity, but it is mandatory for G03 and
`CV_READY` while the public README has no current poster/video. It is allowed
only after the saved release and latest APIs both report
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

This presentation was recorded from SSH-signed release source [`$SOURCE_COMMIT`](https://github.com/ALLPROTO/core-lm-benchmark/commit/$SOURCE_COMMIT) at annotated tag [`$TAG`](https://github.com/ALLPROTO/core-lm-benchmark/releases/tag/$TAG). It is an `AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION` on pinned public data. This presentation-only successor does not alter the released source or evidence and is **not** a blind/generalization result, model-weight-compression result, or independent human replication.
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

"$PORTFOLIO_PYTHON" -I -B \
  publication/verify_portfolio_github_release.py verify-successor \
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
avoids a source-to-release-to-source self-reference.
