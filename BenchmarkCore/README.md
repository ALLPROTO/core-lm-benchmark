# Frozen compatibility source

`corelm_benchmark.py` remains at this exact path only because its bytes and
path are part of the already published prospective and beacon implementation
manifests. It is not exposed by `./corelm`, included in either platform build,
or executed by current CI.

The retired synthetic suite, runner, evidence verifier, result directory,
schema, and paper are intentionally absent from the default branch. Their exact
historical state is recoverable from the immutable `voidtoken-v5-paper-v5` tag.
