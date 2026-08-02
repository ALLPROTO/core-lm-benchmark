# Frozen compatibility source

`corelm_benchmark.py` remains at this exact path only because its bytes and
path are part of the already published prospective and beacon implementation
manifests. Current v5 macOS/Linux runs do not import or package it, while
evidence verification does not execute it; it hashes the registered path and
bytes. The documented historical-pilot reproduction path and one isolated
compatibility unit test still execute it; neither writes current evidence.

The frozen source also retains a dormant directly invocable historical
synthetic CLI because those bytes cannot be edited. That CLI is unsupported,
is absent from `./corelm` and both platform builds, and cannot create evidence
accepted by the current verifiers.

Its logical owner is the read-only `platforms/beacon/` contour. The physical
legacy path cannot be replaced by a move, copy, or symlink because registered
digests include the path string and the verifier requires a regular file.

The retired complete synthetic suite, supported entrypoint, evidence verifier,
result directory, schema, and paper are intentionally absent from the default
branch. Their exact historical state is recoverable from the immutable
`voidtoken-v5-paper-v5` tag.
