# Recorded real-Qwen regression on Linux

This report preserves a public GitHub-hosted execution of the real pinned
`Qwen/Qwen2.5-0.5B` model on registered WikiText validation data. It is an
environmental regression on already-public blocks, not a blind, held-out, or
prospective result. For current build instructions, use the
[Linux platform guide](README.md).

## Successful execution

The first complete public Linux CPU execution finished on 2026-08-01:

- [workflow run 30710142923](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30710142923)
  and [job 91396042691](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30710142923/job/91396042691);
- workflow commit
  `177cd53b595f15614b40c724c74ce8da0630e06b`;
- exact benchmark source commit
  `aaae33c744fe1b384877079c600fe4833966e74a`, tree
  `ec7087bb88a024a65ea90ec6171d8e48e7fd00ed`;
- Python 3.12.13, Torch 2.13.0+cpu, x86_64 Ubuntu 24.04 runner;
- eight real blocks, 1,024 predictions, and 192 retained containers;
- compression `2.052389237x`, delta NLL `+0.0000223219`, top-1 agreement
  `99.609375%`, all three registered gates `PASS`;
- result SHA-256
  `9575998655ba2dc728f0856ba16d34fa9cbe23f918d3cc4155c5f898cebc5ada`;
- selected-token SHA-256
  `1bb36c91d441379596361ae779ca0542c85457e9902a290a6ab6945cb2513453`;
- [Actions artifact 8821614426](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30710142923/artifacts/8821614426),
  ZIP SHA-256
  `d618ee6addad3d62d2d9db479d6c7f2f737fa30ba9491322b1f17f7a0172c4ef`.

The model execution took 54.08 seconds and reached 3,380,064 KiB maximum
resident memory. The independent verifier recomputed the result from the raw
artifact and reported `PRIMARY EVIDENCE PASS: 192 raw containers and 1024 token
decisions independently agree.` The run manifest records
`countsTowardScientificVerdict: false`, `testDataOpened: false`, and
`beaconExecuted: false`.

Three preceding workflow attempts are retained rather than hidden:

- [30709855291](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30709855291)
  failed workflow validation before a VM job existed;
- [30709905602](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30709905602)
  stopped at hash-locked dependency resolution before model/data preparation;
- [30710067688](https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/30710067688)
  stopped because the separate Linux locks were not present in the exact
  source checkout, again before model/data preparation.

None of those three setup attempts executed Qwen or opened model-evaluation
data. They are engineering failures, not model results and not scientific
attempts.
