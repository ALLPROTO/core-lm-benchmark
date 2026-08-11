# Recorded real-Qwen regression on RunPod, 2026-08-11

This report records one author-operated execution of the complete Linux
real-Qwen regression in a RunPod Secure Cloud managed Docker container. The
model execution and retained-evidence checks passed. This is a transparent
public-validation regression record; it is not an independent replication, a
GPU result, a booted-VM result, or new V15 scientific evidence.

For ordinary-user commands, use the [RunPod guide](RUNPOD.md).

## Source identity

- Source commit:
  `9b68055502e81efe6c9aa164632d2fa6de780c4b`.
- Source tree: `e07617638be98c95a158f8241a4ca095f6c70858`.
- The commit object carried an ED25519 SSH signature whose recorded key
  fingerprint was
  `SHA256:8A4y/GkoFglweSfg3rP21BtWWqIBOeQAUoAJDQM8sMM`.

## Container and resource boundary

- Provider/location: RunPod Secure Cloud, `CA-MTL-1`.
- Runtime boundary: managed Docker container, Ubuntu 24.04, x86_64. It was not a
  booted hardware VM.
- Selected pod accelerator: NVIDIA A40 48 GB. The registered model process did
  not use it: the result recorded device `cpu` and the isolated runtime used
  Torch `2.13.0+cpu`.
- Cgroup CPU quota: 7.65 CPUs.
- Cgroup memory limit: 49,999,998,976 bytes.
- RunPod image reference:
  `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`.
- The image digest was not captured. The tag therefore does not establish an
  immutable or hermetic base-image identity.
- Storage for this run was container/pod disk; no network volume was attached.
  The evidence was retrieved before termination.
- Pod uptime observed for the session: 15 minutes 26 seconds. The recorded
  price display was $0.44/h compute + $0.004/h container disk + $0.014/h
  volume, shown by RunPod as $0.46/h total.
- The pod was terminated after evidence retrieval and its access key was
  removed.

The selected A40 and CUDA-oriented image name are environment facts only. They
must not be interpreted as GPU execution: this repository's Linux contour
installs CPU-only PyTorch wheels and fixes the model runner to `--device cpu`.

## Registered workload

- Model: `Qwen/Qwen2.5-0.5B`, exact revision
  `060db6499f32faf8b98477b0a26969ef7d8b9987`.
- Dataset: `Salesforce/wikitext`, exact revision
  `b08601e04326c79dfdd32d625aee71d232d685c3`, configuration
  `wikitext-2-raw-v1`, validation split, public blocks 64–71.
- Validation parquet SHA-256:
  `204929b7ff9d6184953f867dedb860e40aa69c078fc1e54b3baaa8fb28511c4c`.
- Evaluated candidate index: 32.
- Selected-token SHA-256:
  `1bb36c91d441379596361ae779ca0542c85457e9902a290a6ab6945cb2513453`.
- Model weights SHA-256:
  `88c142557820ccad55bb59756bfcfcf891de9cc6202816bd346445188a0ed342`.

The real-model interval was 2026-08-11T21:27:19Z through
2026-08-11T21:28:23Z, 64 seconds by the recorded UTC endpoints.

## Result

- `modelExecuted`: `true`.
- Retained evidence: 192 containers and 1,024 token decisions.
- Compression ratio versus BF16: `2.052389237121773`.
- Delta NLL in natural units per token: `2.2321861713692215e-05`.
- Top-1 agreement: `0.99609375`.
- Metric verdict: `PASS`.
- Result SHA-256:
  `70dd06e8b7c7c4c53b4c86f0ba393fc667577563f146a23652f7c0ec9c29842f`.
- `validation-064-071.json` file SHA-256:
  `bcc2d30fe1d26cc1bce93e99c361a88df2903848d1ec4d9732dae2a714104319`.
- `run-manifest.json` file SHA-256:
  `3c44a2adc4b2c19c1ceb7e854fdeb3748b36ec9bc39542ca581c7cdd4a5bd110`.
- `primary-evidence/manifest.json` SHA-256:
  `28a1605a74e9f967d6e54cc96cca991d6e0ceaa050a211228839b7110e7c609c`.
- `primary-evidence/token-metrics.json` SHA-256:
  `5807ae7b236ef45962608d9c1a9c16bd02135b4b60eb4619ab0fb0c56986aaeb`.
- `SHA256SUMS` file SHA-256:
  `d5390403b10b8ca1584d5cdfcebebce2f13fa5173de403d1f2b2ed76cf965621`.

The repository's separate primary-evidence verifier and `sha256sum -c` passed
inside the pod. Both checks passed again on the author-controlled local copy
after transport. That demonstrates consistency of the retrieved bytes with
the recorded run; it does not make the author-operated execution independent.

The author-held transport tar was 18,508,840 bytes with SHA-256
`c14e165c80a1ab4aa1b5c17cb984f22838617cf23884f580a99ff5b787fecb88`.
It has no public download location, so this report does not claim that a reader
can independently retrieve or reverify that tar.

## Full-repository gate finding

The full repository test gate inside the container overlay passed 463 of 464
tests. The sole failure was
`test_inode_ctime_seal_detects_modify_execute_restore_attack`: the overlay
filesystem did not expose the ctime transition that this safety test requires
after modifying and restoring the fixture. The available tmpfs was mounted
`noexec` and was not a valid substitute for the complete gate.

This finding is disclosed rather than relabelled as a full-suite PASS. It is
separate from the successful real-Qwen process, the 192-container/1,024-token
evidence verification, and the complete checksum verification. It also means
this one container run does not replace the repository's booted-VM portability
matrix.
