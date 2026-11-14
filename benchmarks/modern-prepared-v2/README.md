# Frozen modern-baseline test delivery

This is an unexecuted prepared experiment, not a positive GPU result. The archive
is byte-identical to the prepared-v2 package dated November 12, 2026. Its SHA256 is
`cca62c180509da48436da82a68eb7a9aba3adbb8da6cb72834fde806b40c89d4`.

Pin the Git commit when downloading. From a checkout, run:

```sh
python3 benchmarks/modern-prepared-v2/verify_extract.py \
  --destination /workspace/corelm-modern-study-20261112/prepared-matrix
```

This command verifies all 76 manifest entries and extracts them. It does not
install software, rent hardware, run the benchmark, create credentials, or alter
existing files. The destination must not exist. Follow the extracted protocol and
README, preserving all results including failures and losses. Model licenses and
WikiText attribution are retained inside the archive. Tokenizers are not weights;
pinned public weights download during the separately controlled bootstrap.

## Operational gate before paid execution

The frozen archive contains historical budget metadata, not current spending
authority. Supply current authorization and record the actual GPU, rate, start
balance, start time, overall wall-clock cutoff, and remaining monetary limit in
separate execution metadata. Do not edit the frozen package to hide historical
values. Do not start until both input delivery and external evidence retrieval
are working, and an operator can actively monitor and stop the paid machine.

A shell timeout kills test processes only, NOT RunPod billing. RunPod's deployment
queue expiry also does NOT stop a running pod. `runpodctl --stop-after` was not a
working shutdown method in prior attempts. Stop via the verified console channel
after verified external backup, well before the authorized budget is exhausted.
No persistent credentials or unrelated volume changes are needed.

No new model test ran on November 14, 2026: the temporary GPU was stopped after
input upload authority was cancelled. Do not cite that attempt as evidence.
