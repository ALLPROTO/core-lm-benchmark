# Maintained dependencies and historical evidence

This migration separates supported runtime inputs from preserved scientific
records. It does **not** rewrite a release, move a tag, change registered model
or corpus bytes, reopen the beacon, or turn previous numerical results into
proof of a new environment.

## Two explicit contracts

- **Maintained core/publication tools:** `requirements.txt`, `requirements.lock`,
  `.github/locks/core-linux-py312.txt`, and
  `.github/locks/core-macos-arm64-py312.txt`.
- **Maintained model runtime:** `.github/locks/real-llm-maintained.txt` is the
  direct input; `.github/locks/real-llm-portable-py312.txt` is the portable/macOS
  closure. Linux uses `.github/locks/real-llm-linux-cpu-py312.txt` plus the
  separately sourced official `.github/locks/torch-linux-cpu-py312.txt`.
  `.github/locks/pip-maintained.txt` is the maintained installer in both contours.
- **Historical, not supported for new runs:** `RealLLM/requirements.txt`,
  `RealLLM/requirements.lock`, and `.github/locks/pip-bootstrap.txt` retain their
  registered bytes. The immutable beacon audit still reads its exact historical
  source/tag and verifies the original digests. These old packages have known
  vulnerabilities and must not be described as safe.

Offline wheel preparation first creates a disposable private downloader runtime,
updates only its pip from the fixed official PyPI index with wheel/hash checks,
verifies the exact pip closure, and only then contacts any configured mirror.
The bundled base interpreter is not upgraded or used for full dependency downloads.
Its original bundled installer is used only for this one pinned bootstrap step.

The active Linux/macOS builds, offline preparation, policy and direct-dependency
SBOM use the maintained inputs. Linux/macOS default runtime directories now end
in `runtime-maintained-20261110`. Old runtimes are preserved. Explicit paths that
contain a different environment fail exact-lock verification instead of being
upgraded in place. macOS also checks an existing runtime **before** any package
installation; a matching runtime is reused without installation.

Fresh macOS installations are serialized by an owner-private advisory lock.
An unfinished-install marker binds the destination and both maintained lock
hashes before the venv is created. A failed installation is removed only while
that marker still identifies this installation. After abrupt process termination
(including SIGTERM or a hard kill), the next build can safely recreate the marked
unfinished environment once any remaining installer child releases its lock. An active builder,
an unmarked directory, changed lock inputs, or an invalid marker is never
treated as permission to erase a runtime. Older unmarked partial installations
need a fresh `CORELM_REAL_LLM_VENV` path. Completed environments are only verified.
The venv is created at its final path, preserving console-script and activation
paths. The marker is removed only after the full `pip check` and exact-lock
checks succeed; application packaging happens afterward.

The normal macOS builder also upgrades the bundled pip only from the official
PyPI index (or the explicit offline wheelhouse), with hashes, wheels only, and
`--no-deps`. It verifies the patched pip closure before contacting a configured
package mirror, and disables inherited pip configuration for every subprocess.
Native macOS CI exercises this same runtime builder before packaging.

The live maintained OSV gate enumerates **all seven maintained lockfiles**,
including the platform-only torch CPU pin. It contains no advisory suppression.
A separate scheduled/manual `Audit Historical Dependencies (Known Risks)`
workflow reads the frozen pins without installing them and fails when OSV
reports a finding. A green maintained gate does not mean the historical
workflow or a historical release is safe. The original immutable-evidence audit
is unchanged; its optional historical installer remains a disclosed risk.

## Security refresh

The 2026-11-10 candidate changes only these package versions:

| Package | Historical pin | Maintained pin |
| --- | --- | --- |
| pip | 26.1.2 | 26.3 |
| certifi | 2026.7.22 | 2026.10.23 |
| filelock | 3.32.2 | 4.2.10 |
| Pillow | 12.3.0 | 13.0.0 |
| setuptools | 83.0.0 | 84.2.1 |

Replacement hashes were obtained from the exact PyPI release JSON records.
Updated portable entries permit only non-yanked wheels, not source distributions.
The platform core locks retain exactly one compatible wheel hash per package.
Unchanged pins and hashes remain fixed. The Linux CPU torch wheel is still
obtained only from the official PyTorch CPU index.

For review, query the live OSV service again. Availability or an empty advisory
response alone does not prove compatibility. Install the full closures into
fresh Python 3.12.13 environments with `--require-hashes --only-binary=:all:`,
run `pip check`, and compare the complete installed distribution set using
`security/verify_locked_environment.py`. Linux installs the non-torch closure
and the official CPU wheel separately with `--no-deps`, then verifies their
exact union. Never reuse a working evidence runtime for dependency development.

For future resolution, use a disposable Python 3.12 environment and a reviewed
version of pip-tools. Resolve the maintained direct input, retaining the current
closure as constraints and explicitly selecting security updates. Generate
hashes, derive each platform closure from actual compatible wheel metadata,
review the full diff, and repeat installation/OSV/native validation. Do not run
pip-compile against `RealLLM/requirements.lock`; that file is a historical input.

## New publication identity

New runtime-assets manifests use schema version **3** and record all nine
maintained direct/lock inputs, rather than naming the old scientific lock as the
current runtime. Version 2 remains accepted only for source archives/checkouts
without the maintained-runtime marker. Both schemas enforce exact, separate
path sets. The source/archive check rejects a version-2 manifest for a maintained
checkout, preventing a downgrade that omits current dependency hashes.

Old published manifests and results are unchanged. New execution records must
identify the new source commit and runtime hashes. Only the documented public
validation range may be used for regression. No new holdout or beacon execution
is authorized by a dependency refresh.

## Validation status

Local checks on the candidate:

- Live OSV query: PASS for 46 unique maintained package versions across all seven
  maintained closures, including both portable torch and Linux CPU torch.
- Fresh Linux Python 3.12.13 core installation: hash checks, `pip check`, and exact
  installed-distribution verification passed with pip 26.3 and Pillow 13.0.0.
- Fresh Linux CPU model installation: all locked wheels installed; `pip check`
  and exact installed-distribution verification passed with the maintained
  certifi/filelock/setuptools versions and torch 2.13.0+cpu.
- macOS ARM64 cross-download: 41 model/bootstrap wheels and 12 core/bootstrap
  wheels passed hash checks. Their complete dependency metadata was checked
  against a Darwin/ARM64/Python 3.12.13 marker environment. This is **not** a
  native macOS installation, packaging/signing test, or model execution.
  A first resolver attempt evaluated Linux host markers despite `--platform`
  and requested CUDA; it failed closed. Explicit wheel-only downloads plus
  target-marker metadata checks were used instead. Native CI remains required.
- Local Linux doctor refused a scientific regression because this workspace
  has less than the required 8 GiB available RAM. The guard was not bypassed.
  The existing real-Qwen public-validation CI now runs on dependency/runtime
  pull-request changes and records a fresh source/runtime identity.

- Clean local aggregate: 445 tests executed; 442 passed, two host-dependent
  tests skipped, and one artifact-mode test could not pass because this sandbox
  injects an ancestor `.git` mount into temporary directories. The separate
  26-test publication gate initially found one stale schema-version assertion,
  which was corrected to cover the separate v2/v3 runtime contracts. Its
  extracted-archive self-test also hits the same sandbox Git-ancestor
  restriction; the local publication gate is not reported as a full pass.
- Dependency/workflow/secret policy, direct SBOM comparison, and immutable-tag
  verification of the 26 normative Git blobs passed. No frozen input was edited.

Full aggregate test and native CI status must be checked on the final commit.
Until both platform gates and fresh real-Qwen validation pass, this remains a
candidate migration, not a completed reproduction or a release-ready build.
