# Independent clean-clone replication

This procedure creates the evidence required for portfolio gate G10. It is for
one **human who is not Ivan Tyshchenko and is not an AI/agent**, working on a
different machine from a fresh clone of the public repository. The run uses
pinned Qwen on public WikiText validation data. It is a regression; it is not
a blind/generalization result and cannot be cited as one.

## What the bundle proves—and what it does not

The standard-library recorder binds a clean exact commit and tree, an
allowlisted host description, a sanitized terminal stream, the app/Linux run
receipt, result digests, a manifest of every retained run file, and output from
the separate product verifier. Before execution it makes a second fresh clone
of the exact signed tag from the hard-coded canonical GitHub URL, rejects every
ignored/untracked file (including valid bytecode), and runs only from that
isolated checkout. It neither runs a synthetic benchmark nor accepts an
arbitrary command.

The recorder cannot determine whether a person is real or independent. It
therefore labels the attestation
`DECLARED_ONLY_NOT_VERIFIED_BY_SOFTWARE`. An AI review, an author-run clone, or
the recorder's own PASS does **not** close G10. The public submission account
must match the attested GitHub profile, and a maintainer must review that link.

The public bundle includes the canonical result and roughly 18 MiB of raw
containers/token evidence. `verify` reruns the standard-library primary-
evidence verifier over Linux evidence. For macOS it reruns the full existing
portable receipt/result verifier: application identity fields, the worker
digest against the signed source, runtime-identity receipt fields, build
provenance, and retained primary-evidence contracts. It also requires the saved
terminal and product-verifier report to show that the original run validated
the live app/runtime and reached the heavy replay's final marker; it does not
merely trust a saved PASS line. The app bundle and external Python runtime are
not copied, so a later portable verification cannot rehash those live bytes.
Host-specific environment files and caches are not copied.

## 1. Choose the exact public source

Use the current signed portfolio release named by the project README. If no
such release exists yet, stop: a branch tip or draft PR is not a stable G10
target. Clone the canonical repository directly, then detach the exact release
tag:

```sh
git clone https://github.com/ALLPROTO/core-lm-benchmark.git
cd core-lm-benchmark
git checkout --detach <SIGNED-PORTFOLIO-TAG>
git status --porcelain=v1 --untracked-files=all
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
```

The status command must print nothing. Do not edit the attestation inside the
clone because the recorder rejects any tracked or untracked change.
Both `record` and `verify` require network access to compare the local tag
object and peeled commit with the exact tag advertised by the hard-coded
canonical GitHub repository. Merely changing a local `origin` string is not
accepted. The signer policy digest and SSH principal are hard-pinned.
The signing public-key digest and the exact `object`, `type`, and embedded `tag`
headers of the annotated tag are checked as well. HTTPS and SSH spellings of
the one accepted origin are normalized to the same canonical identity; Git URL
rewrite configuration is not used for remote inspection.

This `corelm-portfolio-vN` SSH-signed annotated portfolio tag is a separate
release contour from the lightweight historical paper archive tags named
`voidtoken-v5-paper-vN`. It must not be passed to
`publication/build_archives.py --release-tag`; that builder intentionally
rejects portfolio tags. Conversely, a lightweight paper tag does not satisfy
this recorder's signed-source requirement and cannot be used for G10.

## 2. Create the human attestation outside the clone

```sh
cp docs/independent-replication-attestation.template.json \
  ../corelm-human-attestation.json
```

Replace only `attestedAt` and `publicProfileURL`. Use the same GitHub account
that will publish the bundle. Read every fixed statement; if any is false, do
not set it to true and do not claim an independent replication.

Do not add an email address, local username, hostname, token, SSH key, home
path, or free-form notes. The bundle scanner fails closed on common credentials
and `/Users/<name>`, `/home/<name>`, and Windows user paths.

## 3. Prepare the selected platform

Run the platform doctor and install the owner-local pinned Python without
`sudo`. Model downloads happen during the proof unless the documented offline
cache was prepared beforehand.

macOS (Apple Silicon):

```sh
./corelm macos doctor
./corelm macos bootstrap
PYTHON312="$HOME/.local/share/corelm/python-3.12.13/bin/python3.12"
```

Linux (Ubuntu 24.04 x86-64):

```sh
./corelm linux bootstrap
./corelm linux doctor
PYTHON312="$HOME/.local/share/corelm/linux-x86_64/python-3.12.13+20260718/bin/python3.12"
```

Confirm the exact interpreter before continuing:

```sh
"$PYTHON312" -VV
```

It must report Python 3.12.13.

## 4. Make one recorded real-model run

Choose exactly one command. The output must be outside the clone and must not
already exist.

macOS:

```sh
"$PYTHON312" -I -B tools/independent_replication.py record \
  --platform macos \
  --expected-tag <SIGNED-PORTFOLIO-TAG> \
  --attestation ../corelm-human-attestation.json \
  --output ../corelm-replication-macos
```

Linux:

```sh
"$PYTHON312" -I -B tools/independent_replication.py record \
  --platform linux \
  --expected-tag <SIGNED-PORTFOLIO-TAG> \
  --attestation ../corelm-human-attestation.json \
  --output ../corelm-replication-linux
```

The recorder executes only `./corelm macos proof` or `./corelm linux run`. It
first rejects a lightweight, unsigned, invalid, or non-HEAD release tag by
checking the annotated tag object with `signing/allowed_signers`; a merely
clean arbitrary commit is not accepted. The accepted release identity is
strictly `corelm-portfolio-vN`, where `N` is a positive integer. On macOS it
supplies a fresh 256-bit challenge and requires the receipt to bind that
challenge. On Linux it supplies a new private run directory. Both paths
require a clean source tree, retain real-model evidence, run the existing
separate verifier, and preserve a behavioral metric FAIL if one occurs. A
verified macOS metric FAIL is accepted only when the public proof command exits
zero after the local app verifier and independent heavy replay have reached
their final marker. **Every non-zero public-command or verifier exit is an
infrastructure failure**, even if a receipt was already written, and cannot
produce a completed bundle. The isolated checkout's tracked bytes/modes and
untracked topology are checked again after execution (with only the generated
macOS `dist` tree allowed).
The recorder also seals inode and ctime metadata for every tracked file and
ancestor directory before launch, then compares that seal after the proof and
after the verifier. This detects persistent drift and ordinary same-user
modify/restore attempts, but it is not a cryptographic read-only mount. The
procedure's threat model excludes a concurrent same-user or root attacker who
can actively manipulate the execution checkout while the proof is running;
the independent operator should use an otherwise idle, independently
controlled machine.

The recorder does not dump the process environment, local username, or
hostname. It allowlists child environment variables, normalizes private paths
in terminal output, strips terminal control sequences, and rejects secrets or
private home paths before finalizing the bundle. The same high-confidence scan
applies to binary `.vtl5` containers; encrypted private-key headers, bearer or
query credentials, and configured package/model endpoint values cannot leak
into the public bundle.

## 5. Verify and publish without editing

```sh
"$PYTHON312" -I -B tools/independent_replication.py verify \
  ../corelm-replication-macos
```

Use the Linux directory name if applicable. A valid command prints two
different conclusions:

- `INDEPENDENT REPLICATION BUNDLE INTEGRITY PASS` for automated byte/contract
  checks;
- `METRIC VERDICT PASS` or `METRIC VERDICT FAIL`, explicitly and independently
  of bundle integrity; and
- `DECLARED_ONLY_NOT_VERIFIED_BY_SOFTWARE` for the human identity statement.

Archive the directory without changing its contents and publish it from the
GitHub account in `publicProfileURL`, preferably as a pull request or issue
attachment against the exact release. Publish the following beside it:

- exact commit and platform;
- whether the metric verdict was PASS or FAIL;
- the output of the bundle verifier; and
- a statement that this is a public-validation regression, not a blind result.

The bundle already contains the bounded result/primary-evidence subset needed
for verification. Do not publish the remaining local cache/run directory
unless you have audited it separately. Never publish `.ssh`, access tokens,
Hugging Face credentials, environment dumps, or private keys.

## Maintainer acceptance checklist

G10 is complete only after all items below are visible publicly:

1. The bundle verifier passes without model execution.
2. `replication.json.source.commit` is the exact canonical signed portfolio
   release commit, and its tree matches the release.
3. The submission account matches `human-attestation.json.publicProfileURL`.
4. The declarant is not the author, an AI agent, or an author-controlled bot.
5. The environment is a different physical or independently controlled
   machine and matches the declared platform.
6. Terminal output, receipt, result digest, raw-file digest manifest, and
   product-verifier output are all present—even if the metric verdict is FAIL.
7. The result is described only as a reproducible public-data regression.

Author self-verification and Codex/agent review remain useful engineering
checks, but neither may be renamed or counted as independent human
replication.
