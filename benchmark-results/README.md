# Registered benchmark evidence

`aggregate.json` is the authoritative index for the paper result. Its `runIds`
array names exactly 115 JSON records. Each JSON file contains the complete
configuration, environment, input digest, method metrics, invariants,
deterministic replay state, verdict, and bounded chart series for one run. The
matching Markdown file is a human-readable rendering of the same result.

Exploratory runs are intentionally excluded from version control. Consumers
should resolve evidence through `aggregate.json`, not by enumerating every file
that happens to be present in a working directory.
