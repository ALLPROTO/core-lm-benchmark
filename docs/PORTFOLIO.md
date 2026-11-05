# Core LM Benchmark — portfolio brief

## One-line summary

Core LM Benchmark is an open-source engineering project for reproducibly
evaluating complete-container KV-cache compression on pinned real-model
workloads.

## What the project does

The benchmark loads a pinned Qwen model and registered WikiText input, creates
complete compressed KV-cache containers, parses the produced bytes again,
replays the cache through the model, retains evidence, and independently
verifies the resulting record.

The engineering unit is the complete serialized container, including framing
and metadata—not a payload-only estimate. The project documents macOS and
Linux paths and separates the producer of evidence from the verifier.

## What I learned from building it

- A model-efficiency claim must be narrow enough that another person can
  inspect the model revision, input, bytes, replay, metrics, and failure state.
- A passing regression does not prove generalization. A verified negative
  result is useful evidence and should remain visible.
- A reproducibility workflow needs explicit limits, source identity, retained
  artifacts, and checks that fail closed rather than silently accepting an
  ambiguous result.

## Current evidence and limits

The project supports a model- and workload-scoped statement: I built and
reproducibly evaluated complete-container KV-cache compression on pinned
real-model workloads.

It does **not** support claims of universal LLM compression, weight
compression, arbitrary-model transfer, latency or serving improvements,
production readiness, state-of-the-art performance, independent scientific
review, or completed blind generalization evidence.

The public project remains below its own full `CV_READY` boundary because an
independent human clean-clone replication, a current public demo, and a single
stable portfolio release are not yet complete. That status is intentional: the
project records the remaining evidence rather than hiding it.

## Why I am sharing it

I am an early-stage, self-taught applicant building formal Python and ML
foundations. I use AI-assisted tools transparently and am seeking rigorous
feedback and mentorship in AI evaluation, reproducibility, model efficiency,
developer tools, or research operations.

## Contact

Ivan Tyshchenko — ivantyschenko777@gmail.com  
LinkedIn: <https://www.linkedin.com/in/ivan-t-758595380/>
