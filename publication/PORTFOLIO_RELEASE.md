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
  for a non-synthetic `PUBLIC_VALIDATION_REGRESSION`.

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
poster hash, dimensions and frame timestamp; macOS arm64 capture; executable,
result, receipt and evidence hashes; classification; and
`synthetic_data:false`. The canonical runtime-assets object binds source/tag,
macOS arm64, Python 3.12.13, literal macOS/Swift/Xcode versions, exact tracked
lockfile and verifier/dependency-source hashes, the exact ffprobe executable
SHA-256 and first `ffprobe -version` line used by the builder, pinned Qwen
repository/revision/file hashes,
pinned WikiText repository/revision/file hash/license/source URL, executable
hash, and proof hashes. The builder verifies tracked lockfile/verifier hashes
against the clean source.

Before build, fetch the related refs into the exact local names
`refs/remotes/origin/main` and `refs/remotes/origin/pull/5/head`. The builder
requires the recorded lab and Blind commits/trees to equal those refs.

The evidence gzip tar has exact regular members
`run/app-run-receipt.json`, `run/validation-064-071.json`,
`run/build-provenance.json`, `run/runtime-provenance.json`,
`reports/structural-verifier.json`, `reports/fresh-model-replay.json`, and
`logs/terminal.log`, plus only raw files below `run/primary-evidence/`.
Receipt/result bytes are bound to demo provenance; canonical reports bind their
hashes, source commit/tree, PASS integrity verdict, metric outcome, pinned
model and fresh replay. The tracked product verifier rechecks the complete run
with metric PASS or preserved verified metric FAIL. Every member is streamed
through secret/path scanning regardless of size. Links, special entries,
traversal, duplicate paths, secrets, model weights, and private paths fail.

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
