# Exploratory real-LLM pilot result

This directory is separate from `benchmark-results/`. The synthetic 115-run
evidence remains unchanged.

The pilot used the pinned pretrained `Qwen/Qwen2.5-0.5B` model, canonical
BF16-rounded KV cache from all 24 layers, WikiText-2 test source blocks 8–15,
and 1,024 teacher-forced next-token predictions. Every decoded cache was built
from a freshly parsed binary container and fed back into the model.

| Family | BF16 ratio | ΔNLL (nat/token) | PPL ratio | Top-1 agreement | Cache NRMSE | Verdict |
|---|---:|---:|---:|---:|---:|---|
| VoidToken v4 | 2.4184× | +0.203580 | 1.225783 | 79.88% | 0.07157 | **FAIL** |
| Mixed packed group quant | 2.0214× | +0.001356 | 1.001357 | 97.95% | 0.00861 | **FAIL** |

The runner's fixed gates were compression ≥2×, ΔNLL ≤0.01 nat/token, and top-1
agreement ≥99%. They were not independently preregistered or externally
timestamped before first test execution. VoidToken failed the NLL and top-1
gates. The strong
mixed-precision baseline passed compression and NLL but missed the top-1 gate,
so it is also recorded as FAIL. Its small NLL change is promising, but it is not
relabeled as a success after observing test.

Direct `DynamicCache` continuation and flatten/rebuild continuation had exactly
zero maximum logit difference on all validation and test blocks. Two independent
rebuilds of the canonical BF16 cache also had zero maximum logit difference.

- Result SHA-256:
  `8922108d749b0680fd1d8cd6b307b9e1cc1cb3294a6d9ac8723c0ed093a755a9`
- Model revision:
  `060db6499f32faf8b98477b0a26969ef7d8b9987`
- Model weight SHA-256:
  `88c142557820ccad55bb59756bfcfcf891de9cc6202816bd346445188a0ed342`
- Dataset revision:
  `b08601e04326c79dfdd32d625aee71d232d685c3`
- Recorded runtime: macOS 26.3, arm64, MPS, Python 3.12.13, PyTorch 2.13.0,
  Transformers 5.14.1.

Verify the checked-in evidence without downloading the model:

```sh
python -m pip install numpy==2.5.1 jsonschema==4.25.1
python RealLLM/verify_real_llm_evidence.py
```

The verifier checks the JSON schema, source pins, validation-only selection,
aggregations, independent family verdicts, structural replay gates, and the
canonical result digest.
