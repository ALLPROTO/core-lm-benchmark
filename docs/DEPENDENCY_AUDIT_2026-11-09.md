# Dependency audit: 2026-11-09

The live OSV gate on the reproduction-fix branch found advisories in existing
pinned dependencies. This is a release blocker, not a reason to disable the
scanner or alter historical evidence. The observations below describe the
queried package versions; exploitability depends on the application's use and
platform. They do not claim that a recorded benchmark was compromised.

## Findings and upstream fixes

- `pip==26.1.2`: [GHSA-qwm4-qh6w-59xr](https://osv.dev/vulnerability/GHSA-qwm4-qh6w-59xr),
  doubly encoded URLs from malicious package indexes can write outside the
  intended destination. Fixed in 26.2.0. The current bootstrap lock is updated
  to PyPI's universal **26.3** wheel with its SHA-256, installed and checked
  using Python 3.12.13 with `--require-hashes --only-binary=:all: --no-deps`.
- `certifi==2026.7.22`: [GHSA-6q48-6c7w-9gw2](https://osv.dev/vulnerability/GHSA-6q48-6c7w-9gw2),
  compromised emSign intermediate keys can enable on-path TLS impersonation.
  Fixed in 2026.10.18; the advisory recommends 2026.10.19 or later.
- `filelock==3.32.2`: twelve GHSA findings, including Unix lock-path races
  ([GHSA-69hj-f68j-2879](https://osv.dev/vulnerability/GHSA-69hj-f68j-2879))
  and platform-specific locking/permission problems. The latest fixed boundary
  across these findings is **4.2.1**; 4.2.10 was available when checked.
- `pillow==12.3.0`: 41 GHSA findings covering image/PDF denial of service,
  memory safety and other issues. All queried ranges end at **13.0.0**.
  Examples: [MIC frame loop](https://osv.dev/vulnerability/GHSA-22hg-r758-rrw9),
  [FlashPix heap overflow](https://osv.dev/vulnerability/GHSA-5x8w-8jj5-q52h),
  [Ghostscript argument injection](https://osv.dev/vulnerability/GHSA-w889-685w-c8fh).
- `setuptools==83.0.0`: [GHSA-xmj3-9gf7-h52w](https://osv.dev/vulnerability/GHSA-xmj3-9gf7-h52w),
  Windows path escape during legacy wheel installation, fixed in **84.1.0**.
  Windows is not a supported execution target, but this finding is not waived.

The original scan returned 76 OSV identifiers, including aliases; this is not
76 independent vulnerabilities. Requery OSV before selecting replacement
versions. PyPI availability alone is not proof of compatibility or safety.

## Safe remaining remediation

`RealLLM/requirements.lock` is explicitly bound by the historical beacon
registration and freeze. The Linux dependency policy also requires the active
CPU lock to match that portable closure (except the separate torch wheel).
Changing only a version or hash would break the documented relationship and
could invalidate historical replay. Leave immutable tags, records and their
registered lock bytes unchanged.

A maintained-runtime update needs a separate, reviewed migration:

1. Separate current supported runtime manifests from historical replay inputs,
   explicitly preserving the frozen-source verification path.
2. Generate full hash-checked replacement closures for Linux CPU and macOS
   ARM64, including compatible Pillow/filelock major-version updates.
3. Update runtime manifest/policy checks and test both platforms, package
   installation, media/publication output and offline asset preparation.
4. Run pinned Qwen public-validation regression and fresh evidence verification
   under the new runtime. Record a new source/runtime identity; do not reuse
   old numerical evidence as proof of the updated environment.
5. Keep the OSV gate active and require a clean audit of maintained runtime
   dependencies before declaring the release ready. Disclose any historical
   replay risks separately rather than calling historical dependencies safe.

Updating pip does not repair the remaining four package findings. Existing
managed runtimes are exact-lock environments and must not be upgraded in place;
use a fresh private runtime destination for the new lock and retain any old
runtime needed to audit its associated app/evidence. Do not delete or weaken
runtime receipts to force reuse. This audit did not run a model or change any
historical result.
