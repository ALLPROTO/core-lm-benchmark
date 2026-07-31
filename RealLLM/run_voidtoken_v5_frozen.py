#!/usr/bin/env python3
"""Run the frozen VoidToken v5 selection or prospective holdout phase."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_BOOTSTRAP_PUBLIC_ORIGIN = "https://github.com/ALLPROTO/core-lm-benchmark"
_BOOTSTRAP_TAGS = {
    "selection": "voidtoken-v5-selection-protocol-v1",
    "holdout": "voidtoken-v5-pretest-v1",
}
_BOOTSTRAP_ATTESTATION: dict[str, str] | None = None
_GIT_TIMEOUT_SECONDS = 90


def _git_executable() -> str:
    candidates = (
        Path("/usr/bin/git"),
        Path("/usr/local/bin/git"),
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    discovered = shutil.which("git")
    if discovered is None:
        raise ValueError("cannot locate a Git executable")
    resolved = Path(discovered).resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("resolved Git executable is not a regular file")
    return str(resolved)


def _sanitized_git_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in tuple(environment):
        if (
            name.startswith("GIT_")
            or name.startswith("DYLD_")
            or name == "LD_PRELOAD"
        ):
            environment.pop(name, None)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            "PATH": os.defpath,
        }
    )
    return environment


def _run_git_process(
    arguments: list[str] | tuple[str, ...],
    *,
    text: bool = False,
) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(
            [_git_executable(), *arguments],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=text,
            env=_sanitized_git_environment(),
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"cannot execute bounded Git command: {error}") from error


def _bootstrap_command(*arguments: str) -> str:
    if not arguments or arguments[0] != "git":
        raise RuntimeError("bootstrap permits only Git commands")
    completed = _run_git_process(list(arguments[1:]), text=True)
    if completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"bootstrap command {' '.join(arguments)} failed: {message}"
        )
    return completed.stdout.strip()


def _bootstrap_before_repository_imports(phase: str) -> dict[str, str]:
    if phase not in _BOOTSTRAP_TAGS:
        raise RuntimeError("bootstrap phase must be selection or holdout")
    problems: list[str] = []
    if not sys.flags.isolated:
        problems.append("Python isolated mode is disabled")
    if not sys.flags.dont_write_bytecode:
        problems.append("Python bytecode writes are enabled")
    scan_roots = (
        PROJECT_ROOT,
        PROJECT_ROOT / "RealLLM",
        PROJECT_ROOT / "BenchmarkCore",
    )
    suspicious: set[str] = set()
    for root in scan_roots:
        if root == PROJECT_ROOT:
            candidates = list(root.glob("*.py[co]")) + list(
                root.glob("__pycache__")
            )
        else:
            candidates = list(root.rglob("*.py[co]")) + list(
                root.rglob("__pycache__")
            )
        suspicious.update(
            path.relative_to(PROJECT_ROOT).as_posix()
            for path in candidates
        )
    if suspicious:
        problems.append(
            "local Python bytecode/cache exists: "
            + ", ".join(sorted(suspicious))
        )
    if problems:
        raise RuntimeError("; ".join(problems))

    status = _bootstrap_command(
        "git",
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignored=no",
    )
    if status:
        raise RuntimeError(
            "bootstrap requires a completely clean checkout: "
            + ", ".join(status.splitlines())
        )
    commit = _bootstrap_command("git", "rev-parse", "HEAD")
    if (
        len(commit) != 40
        or any(character not in "0123456789abcdef" for character in commit)
    ):
        raise RuntimeError("bootstrap cannot resolve a full Git commit")
    tag = _BOOTSTRAP_TAGS[phase]
    tag_commit = _bootstrap_command(
        "git", "rev-parse", f"refs/tags/{tag}^{{commit}}"
    )
    if tag_commit != commit:
        raise RuntimeError(f"bootstrap HEAD is not the frozen tag {tag}")
    origin = _bootstrap_command(
        "git", "remote", "get-url", "origin"
    ).removesuffix(".git")
    if origin != _BOOTSTRAP_PUBLIC_ORIGIN:
        raise RuntimeError("bootstrap origin is not the public registration")
    remote = _bootstrap_command(
        "git",
        "ls-remote",
        "--tags",
        "origin",
        f"refs/tags/{tag}",
    )
    remote_lines = [
        line.split() for line in remote.splitlines() if line.strip()
    ]
    if [line[0] for line in remote_lines if len(line) == 2] != [commit]:
        raise RuntimeError(f"bootstrap tag {tag} is not public on origin")
    return {"phase": phase, "gitCommit": commit, "gitTag": tag}


if __name__ == "__main__":
    requested_phase = next(
        (
            argument
            for argument in sys.argv[1:]
            if argument in _BOOTSTRAP_TAGS
        ),
        None,
    )
    if requested_phase is not None:
        try:
            _BOOTSTRAP_ATTESTATION = _bootstrap_before_repository_imports(
                requested_phase
            )
        except Exception as error:
            print(
                "FROZEN VOIDTOKEN V5 BOOTSTRAP FAILED: invoke from a clean "
                f"publicly tagged checkout with `python -I -B`: {error}",
                file=sys.stderr,
            )
            raise SystemExit(1)

sys.dont_write_bytecode = True
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np


from RealLLM.benchmark_real_llm import (  # noqa: E402
    DATASET_FILES,
    DATASET_REPOSITORY,
    DATASET_REVISION,
    MODEL_ASSET_FILES,
    MODEL_REPOSITORY,
    MODEL_REVISION,
    MODEL_WEIGHTS_BYTES,
    MODEL_WEIGHTS_SHA256,
    _aggregate_phase,
    _evaluate_block,
    _resolve_device,
    _token_blocks,
    aggregate_candidate_records,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    validate_v5_container_manifest,
)


SCHEMA_VERSION = "corelm-voidtoken-v5-phase-result-v2"
LEGACY_PHASE_SCHEMA_VERSION = "corelm-voidtoken-v5-phase-result-v1"
ATTEMPT_SCHEMA_VERSION = "corelm-voidtoken-v5-attempt-v1"
SUITE_ID = "qwen2.5-0.5b-kv-voidtoken-v5-prospective-v1"
REGISTERED_LEGACY_PHASE_RESULTS = {
    "selection": {
        "artifactSHA256": (
            "72bd149903ac84edb4d56ac7e066fa5640278845bbb5961264ae1b34854dd247"
        ),
        "resultSHA256": (
            "11329a941051073bae9e2aec3f483f5fc6acf7449ed18457d020f4693c1b1876"
        ),
        "gitCommitAtExecution": "467538875402265b2ca915768376e2a5548f3069",
        "implementationSHA256": (
            "55b2f589aae027e4353cf8011547d821a7d885d1fde8b9c3d9dd7af3cd90d783"
        ),
        "registrationSHA256": (
            "ad5b75791f5385740bcdd472bf81ec546fa17fa59a0715a343ed91a193c1af32"
        ),
    },
    "holdout": {
        "artifactSHA256": (
            "499c067d6ccff4bf1ac4a9f98436a52fa6c414ccced495719532347b89b46167"
        ),
        "resultSHA256": (
            "d1c16e88655c1fbc9884324742dee3f0b9b4bc86d973c2bf38df3a02cc090eaa"
        ),
        "gitCommitAtExecution": "34fbd0556bd4e8fb889e628ae35175ff596818af",
        "implementationSHA256": (
            "55b2f589aae027e4353cf8011547d821a7d885d1fde8b9c3d9dd7af3cd90d783"
        ),
        "registrationSHA256": (
            "ad5b75791f5385740bcdd472bf81ec546fa17fa59a0715a343ed91a193c1af32"
        ),
    },
}
REGISTRATION_PATH = PROJECT_ROOT / "RealLLM" / "v5_registration.json"
RESULT_SCHEMA_PATH = (
    PROJECT_ROOT / "schemas" / "voidtoken-v5-phase-result.schema.json"
)
ATTEMPT_SCHEMA_PATH = (
    PROJECT_ROOT / "schemas" / "voidtoken-v5-attempt.schema.json"
)
SELECTION_PATH = PROJECT_ROOT / "real-llm-v5-results" / "selection.json"
HOLDOUT_PATH = PROJECT_ROOT / "real-llm-v5-results" / "holdout.json"
SELECTION_ATTEMPT_PATH = (
    PROJECT_ROOT / "real-llm-v5-results" / "selection.attempt.json"
)
HOLDOUT_ATTEMPT_PATH = (
    PROJECT_ROOT / "real-llm-v5-results" / "holdout.attempt.json"
)
SELECTION_PROTOCOL_TAG = _BOOTSTRAP_TAGS["selection"]
PRETEST_TAG = _BOOTSTRAP_TAGS["holdout"]
PUBLIC_ORIGIN = _BOOTSTRAP_PUBLIC_ORIGIN

PHASES: dict[str, dict[str, Any]] = {
    "selection": {
        "split": "validation",
        "startBlock": 32,
        "blocks": 32,
        "output": SELECTION_PATH,
        "attempt": SELECTION_ATTEMPT_PATH,
    },
    "holdout": {
        "split": "test",
        "startBlock": 384,
        "blocks": 32,
        "output": HOLDOUT_PATH,
        "attempt": HOLDOUT_ATTEMPT_PATH,
    },
}

FROZEN_CONFIGURATION: dict[str, Any] = {
    "backend": "voidtoken-v5",
    "bitsByLayer": [
        9,
        8,
        8,
        8,
        8,
        8,
        8,
        8,
        9,
        8,
        8,
        8,
        8,
        8,
        8,
        8,
        8,
        8,
        8,
        8,
        8,
        8,
        8,
        8,
    ],
    "codeCompression": "zlib-9",
    "groupSize": 128,
    "scaleCompression": "zlib-9",
    "schedule": "group-kl-top-2-9bit-rest-8bit",
    "signMode": "none",
    "transformBlockSize": 128,
}

GATES = {
    "minimumCompressionRatioVsBF16": 2.0,
    "maximumDeltaNLLNatPerToken": 0.01,
    "maximumBlockwiseDeltaNLLUpperOneSided95": 0.01,
    "minimumTop1Agreement": 0.99,
    "minimumBlockwiseTop1LowerOneSided95": 0.99,
    "minimumWilsonLowerOneSided95": 0.99,
    "requireStructuralReplay": True,
}
FROZEN_CONFIGURATION_SHA256 = (
    "4c7be8c836aa725722b51f66dce78af7a5094e887432e622b5322f7ca2cf0af8"
)
DEVELOPMENT_MANIFEST = {
    "path": "real-llm-v5-development/manifest.json",
    "sizeBytes": 2383,
    "manifestSHA256": (
        "09926e921f288e144f9bece3c656eeb4c50a736aedcb69ed682a75da952e599f"
    ),
    "fileSHA256": (
        "ee0d4b64efaa961e7abb32c2f2571e5f81e9dbead1d4d83fc19ca594241874de"
    ),
}
DEVELOPMENT_ARTIFACTS = [
    {
        "path": "real-llm-v5-development/validation-000-007.json",
        "split": "validation",
        "startBlock": 0,
        "blocks": 8,
        "sizeBytes": 40_867,
        "resultSHA256": (
            "a2cd9d2e4ca62427f608f7e2bfef2076979698db4d158a51c84d1c9c19785bf5"
        ),
        "fileSHA256": (
            "f8c900246c8dafe50ffea309ce86793822cf6fb93e438e3f16b7450bd1f9f224"
        ),
    },
    {
        "path": "real-llm-v5-development/validation-008-015.json",
        "split": "validation",
        "startBlock": 8,
        "blocks": 8,
        "sizeBytes": 40_921,
        "resultSHA256": (
            "3e5c3ecbf517768c003951efee3c516ea0f8bcb67c6306d132a255a6d38da3e7"
        ),
        "fileSHA256": (
            "04ef609cf32f0828de70e6adc47eefc717b6c7c67240035d856f047450860d34"
        ),
    },
    {
        "path": "real-llm-v5-development/validation-016-023.json",
        "split": "validation",
        "startBlock": 16,
        "blocks": 8,
        "sizeBytes": 40_893,
        "resultSHA256": (
            "542b67278955420a1d6b84a18715980fe79fb6033c3133d03201783b9aea283e"
        ),
        "fileSHA256": (
            "65ac4c9bbb1e3d3821d08c9a2f11aa970b0390582388f6ffdbb8ff6f235ad827"
        ),
    },
    {
        "path": "real-llm-v5-development/validation-024-031.json",
        "split": "validation",
        "startBlock": 24,
        "blocks": 8,
        "sizeBytes": 40_912,
        "resultSHA256": (
            "c72d433eea71e3bb60cd5cfab0b30bd25b12a6b7ba5bb9c1e0411bd7f89f2773"
        ),
        "fileSHA256": (
            "ab3a981349e5d2bfcda51d5c32235499fc35af396e827b2f916ed64af769ce1e"
        ),
    },
]
DEVELOPMENT_OBSERVATION = {
    "blocks": 32,
    "predictionTokens": 4096,
    "denseBF16Bytes": 150_601_728,
    "encodedFileBytes": 73_255_705,
    "compressionRatioVsBF16": 2.0558361700293513,
    "deltaNLLNatPerToken": 0.0008044950664043427,
    "blockwiseDeltaNLLUpperOneSided95": 0.001378464012472557,
    "top1AgreementCount": 4078,
    "top1Agreement": 0.99560546875,
    "blockwiseTop1LowerOneSided95": 0.9936384394443587,
    "wilsonLowerOneSided95": 0.99354768675646,
    "meanKLDivergenceNat": 0.00013694787391482777,
}
PROTOCOL_SOURCE_FILES = [
    "BenchmarkCore/corelm_benchmark.py",
    "RealLLM/__init__.py",
    "RealLLM/V5_PROTOCOL.md",
    "RealLLM/benchmark_real_llm.py",
    "RealLLM/codecs.py",
    "RealLLM/develop_voidtoken_v5.py",
    "RealLLM/requirements.txt",
    "RealLLM/run_voidtoken_v5_frozen.py",
    "RealLLM/v5_registration.json",
    "RealLLM/verify_voidtoken_v5_development.py",
    "RealLLM/verify_voidtoken_v5_evidence.py",
    "RealLLM/voidtoken_v5.py",
    "Tests/test_voidtoken_v5.py",
    "Tests/test_voidtoken_v5_development.py",
    "Tests/test_voidtoken_v5_frozen.py",
    "real-llm-v5-development/manifest.json",
    "schemas/voidtoken-v5-attempt.schema.json",
    "schemas/voidtoken-v5-phase-result.schema.json",
]
WILSON_Z_ONE_SIDED_95 = 1.6448536269514715
STUDENT_T_ONE_SIDED_95_DF31 = 1.6955187825458675
FROZEN_RUNTIME = {
    "huggingfaceHub": "1.25.1",
    "python": "3.12.13",
    "numpy": "2.5.1",
    "pyarrow": "23.0.1",
    "safetensors": "0.8.0",
    "tokenizers": "0.22.2",
    "torch": "2.13.0",
    "transformers": "5.14.1",
    "zlibCompileVersion": "1.2.12",
    "zlibRuntimeVersion": "1.2.12",
}


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key is forbidden: {key}")
        result[key] = value
    return result


def _require_finite_json_numbers(value: Any) -> None:
    if type(value) is float and not math.isfinite(value):
        raise ValueError("non-finite JSON number is forbidden")
    if isinstance(value, dict):
        for child in value.values():
            _require_finite_json_numbers(child)
    elif isinstance(value, list):
        for child in value:
            _require_finite_json_numbers(child)


def _load_registration() -> dict[str, Any]:
    try:
        value = json.loads(
            REGISTRATION_PATH.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_json,
            object_pairs_hook=_object_without_duplicate_keys,
        )
        _require_finite_json_numbers(value)
    except (OSError, ValueError) as error:
        raise ValueError(
            f"cannot read the frozen v5 registration: {error}"
        ) from error
    if not isinstance(value, dict):
        raise ValueError("the frozen v5 registration must be an object")
    return value


def registration_sha256() -> str:
    return sha256_bytes(canonical_json_bytes(_load_registration()))


def validate_frozen_registration() -> None:
    registration = _load_registration()
    if registration.get("schemaVersion") != (
        "corelm-voidtoken-v5-registration-v1"
    ):
        raise ValueError("unexpected v5 registration schema")
    if registration.get("suiteId") != SUITE_ID:
        raise ValueError("v5 suite ID differs from the frozen runner")
    if registration.get("protocolSourceFiles") != PROTOCOL_SOURCE_FILES:
        raise ValueError(
            "protocol source-file manifest differs from the frozen runner"
        )
    if registration.get("configuration") != FROZEN_CONFIGURATION:
        raise ValueError("v5 configuration differs from the frozen runner")
    computed_configuration_sha256 = sha256_bytes(
        canonical_json_bytes(FROZEN_CONFIGURATION)
    )
    if (
        computed_configuration_sha256 != FROZEN_CONFIGURATION_SHA256
        or registration.get("configurationSHA256")
        != FROZEN_CONFIGURATION_SHA256
    ):
        raise ValueError("full v5 configuration digest is inconsistent")
    expected_phases = {
        name: {
            "split": phase["split"],
            "startBlock": phase["startBlock"],
            "blocks": phase["blocks"],
            "countsTowardProspectiveVerdict": name == "holdout",
        }
        for name, phase in PHASES.items()
    }
    registered_phases = registration.get("evidencePhases", {})
    for name, expected in expected_phases.items():
        observed = registered_phases.get(name, {})
        for key, value in expected.items():
            if observed.get(key) != value:
                raise ValueError(
                    f"registered {name}.{key} differs from the frozen runner"
                )
    fixed_nonexecution_phases = {
        "development": {
            "split": "validation",
            "startBlock": 0,
            "blocks": 32,
            "countsTowardProspectiveVerdict": False,
        },
        "reserve": {
            "split": "test",
            "startBlock": 416,
            "blocks": 32,
            "countsTowardProspectiveVerdict": False,
            "runnerAccess": "disabled",
        },
    }
    for name, expected in fixed_nonexecution_phases.items():
        observed = registered_phases.get(name, {})
        for key, value in expected.items():
            if observed.get(key) != value:
                raise ValueError(
                    f"registered {name}.{key} differs from the frozen protocol"
                )
    pretest = registration.get("pretestFreeze", {})
    if pretest.get("requiredLightweightTag") != PRETEST_TAG:
        raise ValueError("pretest tag differs from the frozen runner")
    if pretest.get("publicRepository") != PUBLIC_ORIGIN:
        raise ValueError("public origin differs from the frozen runner")
    if (
        pretest.get("requiredGitRemote") != "origin"
        or pretest.get("selectionArtifact")
        != "real-llm-v5-results/selection.json"
        or pretest.get("selectionAttemptArtifact")
        != "real-llm-v5-results/selection.attempt.json"
    ):
        raise ValueError("pretest artifact location differs from the runner")
    selection_freeze = registration.get("selectionFreeze", {})
    if selection_freeze != {
        "publicRepository": PUBLIC_ORIGIN,
        "requiredGitRemote": "origin",
        "requiredLightweightTag": SELECTION_PROTOCOL_TAG,
    }:
        raise ValueError("selection protocol freeze differs from the runner")
    attempt_policy = registration.get("attemptPolicy", {})
    if attempt_policy != {
        "crashConsumesPhase": True,
        "createdBeforeSplitResolution": True,
        "exclusiveCreation": True,
        "firstPublicAttemptIsNormative": True,
        "markers": {
            "holdout": "real-llm-v5-results/holdout.attempt.json",
            "selection": "real-llm-v5-results/selection.attempt.json",
        },
        "rerunAfterMarker": False,
    }:
        raise ValueError("attempt policy differs from the frozen runner")
    development_disclosure = registration.get("developmentDisclosure")
    if development_disclosure != {
        "adaptiveEngineering": True,
        "candidateIndex": 32,
        "configurationChosenAfterDevelopment": True,
        "developmentManifest": DEVELOPMENT_MANIFEST,
        "developmentArtifacts": DEVELOPMENT_ARTIFACTS,
        "developmentSourceBlocks": {
            "count": 32,
            "split": "validation",
            "start": 0,
        },
        "observedDevelopmentAggregate": DEVELOPMENT_OBSERVATION,
        "statement": (
            "Blocks validation-000 through validation-031 were used "
            "adaptively for engineering and are not prospective evidence."
        ),
    }:
        raise ValueError(
            "development evidence disclosure differs from the frozen runner"
        )
    model = registration.get("model", {})
    if (
        model.get("architecture") != "Qwen2ForCausalLM"
        or model.get("attentionHeads") != 14
        or model.get("headDimension") != 64
        or model.get("hiddenSize") != 896
        or model.get("kvHeads") != 2
        or model.get("layers") != 24
        or model.get("license") != "Apache-2.0"
        or model.get("repository") != MODEL_REPOSITORY
        or model.get("revision") != MODEL_REVISION
        or model.get("trustRemoteCode") is not False
        or model.get("weightFile") != "model.safetensors"
        or model.get("weightSha256") != MODEL_WEIGHTS_SHA256
        or model.get("weightSizeBytes") != MODEL_WEIGHTS_BYTES
    ):
        raise ValueError("model pins differ from the frozen runner")
    registered_assets = {
        item.get("path"): {
            "bytes": item.get("sizeBytes"),
            "sha256": item.get("sha256"),
        }
        for item in model.get("verifiedFiles", [])
        if isinstance(item, dict)
    }
    if registered_assets != MODEL_ASSET_FILES:
        raise ValueError("model asset pins differ from the frozen runner")
    corpus = registration.get("corpus", {})
    if (
        corpus.get("blockTokens") != 512
        or corpus.get("configuration") != "wikitext-2-raw-v1"
        or corpus.get("joinSeparator") != "\n\n"
        or corpus.get("normalization") != "none"
        or corpus.get("overlapTokens") != 0
        or corpus.get("repository") != DATASET_REPOSITORY
        or corpus.get("revision") != DATASET_REVISION
        or corpus.get("rowOrder") != "stored-order"
    ):
        raise ValueError("dataset pins differ from the frozen runner")
    if corpus.get("tokenization") != {
        "addSpecialTokens": False,
        "tokenizerRevision": MODEL_REVISION,
    }:
        raise ValueError("tokenization pins differ from the frozen runner")
    registered_splits = corpus.get("splits", {})
    for split, specification in DATASET_FILES.items():
        registered_split = registered_splits.get(split, {})
        if registered_split != {
            "file": specification["path"],
            "fileBytes": specification["bytes"],
            "fileSha256": specification["sha256"],
        }:
            raise ValueError(
                f"registered {split} file differs from the frozen runner"
            )
    expected_statistics = registration.get("statisticalGates", {})
    if (
        expected_statistics.get("compressionRatioVsBF16", {}).get("minimum")
        != GATES["minimumCompressionRatioVsBF16"]
        or expected_statistics.get("deltaNllNatPerToken", {}).get("maximum")
        != GATES["maximumDeltaNLLNatPerToken"]
        or expected_statistics.get("top1Agreement", {}).get("minimum")
        != GATES["minimumTop1Agreement"]
        or expected_statistics.get(
            "blockwiseTop1LowerOneSided95", {}
        ).get("minimum")
        != GATES["minimumBlockwiseTop1LowerOneSided95"]
        or expected_statistics.get(
            "blockwiseTop1LowerOneSided95", {}
        ).get("criticalValue")
        != STUDENT_T_ONE_SIDED_95_DF31
        or expected_statistics.get(
            "wilsonLowerOneSided95", {}
        ).get("minimum")
        != GATES["minimumWilsonLowerOneSided95"]
        or expected_statistics.get(
            "blockwiseDeltaNllUpperOneSided95", {}
        ).get("maximum")
        != GATES["maximumBlockwiseDeltaNLLUpperOneSided95"]
        or expected_statistics.get(
            "blockwiseDeltaNllUpperOneSided95", {}
        ).get("criticalValue")
        != STUDENT_T_ONE_SIDED_95_DF31
        or expected_statistics.get(
            "wilsonLowerOneSided95", {}
        ).get("criticalValue")
        != WILSON_Z_ONE_SIDED_95
        or expected_statistics.get("structuralReplay", {}).get("required")
        is not True
    ):
        raise ValueError("statistical gates differ from the frozen runner")
    protocol = registration.get("protocol", {})
    if protocol != {
        "cacheCanonicalization": "native-float32-to-bfloat16-to-float32",
        "continuationInputTokens": 128,
        "continuationTargets": "block[384:512]",
        "denseReferenceBytesPerScalar": 2,
        "flattening": "per-layer token-major concat(K,V)",
        "freshContainerParseRequired": True,
        "layerTrajectoryShape": [383, 256],
        "predictionTokensPerBlock": 128,
        "prefillTokens": 383,
        "structuralReplayExactnessRequired": True,
        "teacherForcedContinuationInputs": "block[383:511]",
        "uncompressedBytesPerBlock": 4_706_304,
    }:
        raise ValueError("cache replay protocol differs from the runner")
    registered_runtime = registration.get("runtime", {})
    for name, value in FROZEN_RUNTIME.items():
        if registered_runtime.get(name) != value:
            raise ValueError(
                f"registered runtime {name} differs from the frozen runner"
            )
    if (
        registered_runtime.get("attentionImplementation") != "eager"
        or registered_runtime.get("device") != "mps"
        or registered_runtime.get("modelDtype") != "float32"
        or registered_runtime.get("localPythonBytecode") != "forbidden"
        or registered_runtime.get("pythonBytecodeWrites") is not False
        or registered_runtime.get("pythonIsolatedMode") is not True
        or registered_runtime.get("torchDeterministicAlgorithms")
        != "warn-only"
    ):
        raise ValueError("model execution runtime differs from the runner")


def _validate_runtime_versions(
    torch_module: Any,
    transformers_module: Any,
    pyarrow_module: Any,
    huggingface_hub_module: Any,
    tokenizers_module: Any,
    safetensors_module: Any,
) -> None:
    observed = {
        "huggingfaceHub": huggingface_hub_module.__version__,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pyarrow": pyarrow_module.__version__,
        "safetensors": safetensors_module.__version__,
        "tokenizers": tokenizers_module.__version__,
        "torch": torch_module.__version__,
        "transformers": transformers_module.__version__,
        "zlibCompileVersion": zlib.ZLIB_VERSION,
        "zlibRuntimeVersion": zlib.ZLIB_RUNTIME_VERSION,
    }
    if observed != FROZEN_RUNTIME:
        raise ValueError(
            "runtime differs from the frozen registration: "
            + json.dumps(observed, sort_keys=True)
        )


def implementation_sha256() -> str:
    registration = _load_registration()
    paths = registration.get("protocolSourceFiles")
    if paths != PROTOCOL_SOURCE_FILES:
        raise ValueError(
            "registration has a non-frozen protocol source-file manifest"
        )
    digest = hashlib.sha256()
    for raw_path in paths:
        if not isinstance(raw_path, str):
            raise ValueError("protocol source paths must be strings")
        path = PROJECT_ROOT / raw_path
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ValueError(
                f"cannot read normative source {raw_path}: {error}"
            ) from error
        encoded_path = raw_path.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(4, "little"))
        digest.update(encoded_path)
        digest.update(len(content).to_bytes(8, "little"))
        digest.update(content)
    return digest.hexdigest()


def _registration_at_commit(commit: str) -> dict[str, Any]:
    if (
        len(commit) != 40
        or any(character not in "0123456789abcdef" for character in commit)
    ):
        raise ValueError("implementation commit must be a full Git SHA-1")
    relative_registration = REGISTRATION_PATH.relative_to(
        PROJECT_ROOT
    ).as_posix()
    completed = _run_git_process(
        ["show", f"{commit}:{relative_registration}"]
    )
    if completed.returncode:
        raise ValueError(
            f"commit {commit} does not contain the frozen registration"
        )
    try:
        value = json.loads(
            completed.stdout,
            parse_constant=_reject_nonfinite_json,
            object_pairs_hook=_object_without_duplicate_keys,
        )
        _require_finite_json_numbers(value)
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError(
            f"commit {commit} contains an invalid registration: {error}"
        ) from error
    if not isinstance(value, dict):
        raise ValueError(f"commit {commit} registration is not an object")
    return value


def registration_sha256_at_commit(commit: str) -> str:
    return sha256_bytes(canonical_json_bytes(_registration_at_commit(commit)))


def implementation_sha256_at_commit(commit: str) -> str:
    paths = _registration_at_commit(commit).get("protocolSourceFiles")
    if paths != PROTOCOL_SOURCE_FILES:
        raise ValueError(
            "commit has a non-frozen protocol source-file manifest"
        )
    digest = hashlib.sha256()
    for raw_path in paths:
        if not isinstance(raw_path, str):
            raise ValueError("protocol source paths must be strings")
        completed = _run_git_process(["show", f"{commit}:{raw_path}"])
        if completed.returncode:
            raise ValueError(
                f"commit {commit} does not contain normative source {raw_path}"
            )
        encoded_path = raw_path.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(4, "little"))
        digest.update(encoded_path)
        digest.update(len(completed.stdout).to_bytes(8, "little"))
        digest.update(completed.stdout)
    return digest.hexdigest()


def _git(*arguments: str) -> str:
    completed = _run_git_process(list(arguments), text=True)
    if completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"git {' '.join(arguments)} failed: {message}")
    return completed.stdout.strip()


def _repository_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"path is outside the repository: {path}") from error


def _require_clean_head(
    *, allowed_untracked: tuple[Path, ...] = ()
) -> str:
    allowed = {_repository_relative(path) for path in allowed_untracked}
    unexpected: list[str] = []
    status = _git(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignored=no",
    )
    for line in status.splitlines():
        if line.startswith("?? ") and line[3:] in allowed:
            continue
        unexpected.append(line)
    if unexpected:
        raise ValueError(
            "worktree differs from HEAD; frozen execution permits only its "
            "exact attempt marker, but found: "
            + ", ".join(unexpected)
        )
    commit = _git("rev-parse", "HEAD")
    if (
        len(commit) != 40
        or any(character not in "0123456789abcdef" for character in commit)
    ):
        raise ValueError("cannot resolve the current Git commit")
    return commit


def _require_isolated_python() -> None:
    if not sys.flags.isolated:
        raise ValueError(
            "frozen execution requires Python isolated mode; invoke the "
            "runner with `python -I -B`"
        )
    if not sys.flags.dont_write_bytecode:
        raise ValueError(
            "frozen execution requires bytecode writes disabled; invoke the "
            "runner with `python -I -B`"
        )
    forbidden = [
        name
        for name in (
            "PYTHONHOME",
            "PYTHONINSPECT",
            "PYTHONPATH",
            "PYTHONSTARTUP",
        )
        if os.environ.get(name)
    ]
    if forbidden:
        raise ValueError(
            "frozen execution rejects Python injection variables: "
            + ", ".join(forbidden)
        )
    bytecode = sorted(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in PROJECT_ROOT.rglob("*.py[co]")
    )
    if bytecode:
        raise ValueError(
            "frozen execution requires a disposable checkout without local "
            "Python bytecode: "
            + ", ".join(bytecode)
        )


def _require_bootstrap_attestation(phase_name: str) -> dict[str, str]:
    expected_tag = _BOOTSTRAP_TAGS[phase_name]
    attestation = _BOOTSTRAP_ATTESTATION
    if (
        not isinstance(attestation, dict)
        or attestation.get("phase") != phase_name
        or attestation.get("gitTag") != expected_tag
        or not isinstance(attestation.get("gitCommit"), str)
    ):
        raise ValueError(
            "frozen phases cannot be called through an imported module; use "
            "`python -I -B RealLLM/run_voidtoken_v5_frozen.py <phase>`"
        )
    return attestation


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_json,
            object_pairs_hook=_object_without_duplicate_keys,
        )
        _require_finite_json_numbers(value)
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _schema_errors(
    value: dict[str, Any],
    schema_path: Path,
    label: str,
) -> list[str]:
    try:
        import jsonschema
    except ImportError as error:
        return [f"{label} JSON Schema validation could not start: {error}"]
    try:
        schema = _load_json_object(schema_path)
        validator = jsonschema.Draft202012Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        )
        jsonschema.Draft202012Validator.check_schema(schema)
    except (ValueError, jsonschema.exceptions.SchemaError) as error:
        return [f"{label} JSON Schema validation could not start: {error}"]
    errors: list[str] = []
    for problem in sorted(
        validator.iter_errors(value),
        key=lambda error: tuple(str(item) for item in error.absolute_path),
    ):
        location = ".".join(str(item) for item in problem.absolute_path)
        errors.append(
            f"{label} schema {location or '<root>'}: {problem.message}"
        )
    return errors


def phase_schema_errors(result: dict[str, Any]) -> list[str]:
    return _schema_errors(result, RESULT_SCHEMA_PATH, "phase-result")


def attempt_schema_errors(attempt: dict[str, Any]) -> list[str]:
    return _schema_errors(attempt, ATTEMPT_SCHEMA_PATH, "attempt")


def _wilson_lower(successes: int, trials: int) -> float:
    if trials <= 0 or successes < 0 or successes > trials:
        raise ValueError("invalid Bernoulli counts")
    probability = successes / trials
    z = WILSON_Z_ONE_SIDED_95
    denominator = 1.0 + z * z / trials
    center = probability + z * z / (2.0 * trials)
    radius = z * math.sqrt(
        probability * (1.0 - probability) / trials
        + z * z / (4.0 * trials * trials)
    )
    return (center - radius) / denominator


def _structural_replay_passed(baselines: list[dict[str, Any]]) -> bool:
    return bool(baselines) and all(
        baseline.get("exactRebuildMaxAbsLogitDifference") == 0.0
        and baseline.get("exactRebuildTop1Identical") is True
        and baseline.get("layoutRebuildMaxAbsLogitDifference") == 0.0
        and baseline.get("layoutRebuildTop1Identical") is True
        for baseline in baselines
    )


def compute_confidence_and_verdict(
    records: list[dict[str, Any]],
    baselines: list[dict[str, Any]],
    aggregate: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, bool], bool]:
    if len(records) != 32:
        raise ValueError("a frozen phase must contain exactly 32 block records")
    delta_values = [
        float(record["deltaNLLNatPerToken"]) for record in records
    ]
    delta_mean = statistics.fmean(delta_values)
    delta_standard_deviation = statistics.stdev(delta_values)
    delta_upper = delta_mean + (
        STUDENT_T_ONE_SIDED_95_DF31
        * delta_standard_deviation
        / math.sqrt(len(delta_values))
    )
    prediction_tokens = sum(
        int(record["predictionTokens"]) for record in records
    )
    agreement_count = sum(
        int(record["top1AgreementCount"]) for record in records
    )
    block_top1_values = [
        int(record["top1AgreementCount"])
        / int(record["predictionTokens"])
        for record in records
    ]
    block_top1_mean = statistics.fmean(block_top1_values)
    block_top1_standard_deviation = statistics.stdev(block_top1_values)
    block_top1_lower = block_top1_mean - (
        STUDENT_T_ONE_SIDED_95_DF31
        * block_top1_standard_deviation
        / math.sqrt(len(block_top1_values))
    )
    wilson_lower = _wilson_lower(agreement_count, prediction_tokens)
    confidence = {
        "blockDeltaNLLMean": delta_mean,
        "blockDeltaNLLSampleStandardDeviation": delta_standard_deviation,
        "blockwiseDeltaNLLUpperOneSided95": delta_upper,
        "blockTop1Mean": block_top1_mean,
        "blockTop1SampleStandardDeviation": (
            block_top1_standard_deviation
        ),
        "blockwiseTop1LowerOneSided95": block_top1_lower,
        "predictionTokens": prediction_tokens,
        "top1AgreementCount": agreement_count,
        "wilsonLowerOneSided95": wilson_lower,
    }
    gates = {
        "compressionRatioVsBF16": (
            float(aggregate["compressionRatioVsBF16"])
            >= GATES["minimumCompressionRatioVsBF16"]
        ),
        "deltaNLLNatPerToken": (
            float(aggregate["deltaNLLNatPerToken"])
            <= GATES["maximumDeltaNLLNatPerToken"]
        ),
        "blockwiseDeltaNLLUpperOneSided95": (
            delta_upper
            <= GATES["maximumBlockwiseDeltaNLLUpperOneSided95"]
        ),
        "top1Agreement": (
            float(aggregate["top1Agreement"])
            >= GATES["minimumTop1Agreement"]
        ),
        "blockwiseTop1LowerOneSided95": (
            block_top1_lower
            >= GATES["minimumBlockwiseTop1LowerOneSided95"]
        ),
        "wilsonLowerOneSided95": (
            wilson_lower >= GATES["minimumWilsonLowerOneSided95"]
        ),
        "structuralReplay": _structural_replay_passed(baselines),
    }
    return confidence, gates, all(gates.values())


def _close(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(
            float(left), float(right), rel_tol=1e-12, abs_tol=1e-12
        )
    return left == right


def _less_than_or_close(left: float, right: float) -> bool:
    tolerance = max(
        1e-12,
        1e-12 * max(abs(left), abs(right)),
    )
    return left <= right + tolerance


def _phase_specification(phase_name: str) -> dict[str, Any]:
    phase = PHASES[phase_name]
    return {
        "split": phase["split"],
        "startBlock": phase["startBlock"],
        "blocks": phase["blocks"],
    }


def _attempt_path(phase_name: str) -> Path:
    return Path(PHASES[phase_name]["attempt"])


def _canonical_object_digest(
    value: dict[str, Any], digest_field: str
) -> str:
    digest_input = dict(value)
    digest_input.pop(digest_field, None)
    return sha256_bytes(canonical_json_bytes(digest_input))


def _serialized_json(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _exclusive_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as error:
        # Some filesystems do not support directory fsync. The exclusive file
        # creation and file fsync above remain mandatory.
        unsupported = {
            errno.EINVAL,
            getattr(errno, "ENOTSUP", errno.EINVAL),
            getattr(errno, "EOPNOTSUPP", errno.EINVAL),
        }
        if error.errno not in unsupported:
            raise


def _verify_attempt_document_core(
    attempt: dict[str, Any],
    expected_phase: str,
    *,
    verify_git_provenance: bool,
) -> list[str]:
    errors: list[str] = []
    errors.extend(attempt_schema_errors(attempt))
    recorded_attempt_digest = attempt.get("attemptSHA256")
    try:
        expected_attempt_digest = _canonical_object_digest(
            attempt, "attemptSHA256"
        )
    except (TypeError, ValueError) as error:
        errors.append(f"cannot canonicalize attempt marker: {error}")
    else:
        if recorded_attempt_digest != expected_attempt_digest:
            errors.append("attemptSHA256 does not cover the canonical marker")
    if attempt.get("suiteId") != SUITE_ID:
        errors.append("attempt marker has a different suite ID")
    if attempt.get("phase") != expected_phase:
        errors.append("attempt marker has a different phase")
    if attempt.get("phaseSpec") != _phase_specification(expected_phase):
        errors.append("attempt marker has a different phase specification")
    if attempt.get("testSplitWillBeResolved") is not (
        expected_phase == "holdout"
    ):
        errors.append("attempt split-access disclosure is inconsistent")
    if attempt.get("configurationSHA256") != FROZEN_CONFIGURATION_SHA256:
        errors.append("attempt configuration digest is inconsistent")
    commit = attempt.get("gitCommitAtExecution")
    if (
        verify_git_provenance
        and isinstance(commit, str)
        and len(commit) == 40
    ):
        try:
            if registration_sha256_at_commit(commit) != attempt.get(
                "registrationSHA256"
            ):
                errors.append(
                    "attempt commit has a different registration digest"
                )
            if implementation_sha256_at_commit(commit) != attempt.get(
                "implementationSHA256"
            ):
                errors.append(
                    "attempt commit has a different implementation digest"
                )
        except ValueError as error:
            errors.append(f"cannot verify attempt execution commit: {error}")
    freeze = attempt.get("executionFreeze")
    if expected_phase == "selection":
        if (
            not isinstance(freeze, dict)
            or freeze.get("freezeGitTag") != SELECTION_PROTOCOL_TAG
            or freeze.get("freezeGitCommit") != commit
            or freeze.get("publicRepository") != PUBLIC_ORIGIN
        ):
            errors.append("selection attempt has no valid public protocol freeze")
    elif (
        not isinstance(freeze, dict)
        or freeze.get("pretestGitTag") != PRETEST_TAG
        or freeze.get("pretestGitCommit") != commit
        or freeze.get("publicRepository") != PUBLIC_ORIGIN
    ):
        errors.append("holdout attempt has no valid public pretest freeze")
    return errors


def verify_attempt_document(
    attempt: dict[str, Any],
    expected_phase: str,
) -> list[str]:
    """Verify a marker, including its execution commit in the Git object DB."""
    return _verify_attempt_document_core(
        attempt,
        expected_phase,
        verify_git_provenance=True,
    )


def verify_attempt_artifact_self_consistency(
    attempt: dict[str, Any],
    expected_phase: str,
) -> list[str]:
    """Verify marker bytes and invariants when Git objects are unavailable."""
    return _verify_attempt_document_core(
        attempt,
        expected_phase,
        verify_git_provenance=False,
    )


def _verify_attempt_marker_core(
    result: dict[str, Any],
    expected_phase: str,
    *,
    verify_git_provenance: bool,
) -> list[str]:
    errors: list[str] = []
    attempt_path = _attempt_path(expected_phase)
    try:
        attempt = _load_json_object(attempt_path)
    except ValueError as error:
        return [f"attempt marker is missing or invalid: {error}"]
    errors.extend(
        _verify_attempt_document_core(
            attempt,
            expected_phase,
            verify_git_provenance=verify_git_provenance,
        )
    )
    recorded_attempt_digest = attempt.get("attemptSHA256")
    if result.get("attemptMarkerSHA256") != recorded_attempt_digest:
        errors.append("result references a different canonical attempt marker")
    try:
        attempt_file_digest = sha256_file(attempt_path)
    except OSError as error:
        errors.append(f"cannot hash attempt marker: {error}")
    else:
        if result.get("attemptArtifactSHA256") != attempt_file_digest:
            errors.append("result references a different attempt-marker file")
    expected_pairs = {
        "suiteId": "suiteId",
        "phase": "phase",
        "registrationSHA256": "registrationSHA256",
        "implementationSHA256": "implementationSHA256",
        "gitCommitAtExecution": "gitCommitAtExecution",
        "configurationSHA256": "configurationSHA256",
    }
    for attempt_key, result_key in expected_pairs.items():
        if attempt.get(attempt_key) != result.get(result_key):
            errors.append(
                f"attempt/result field {attempt_key} is inconsistent"
            )
    if attempt.get("phaseSpec") != result.get("phaseSpec"):
        errors.append("attempt/result phase specification is inconsistent")
    if expected_phase == "holdout":
        if attempt.get("executionFreeze") != result.get("pretestFreeze"):
            errors.append("holdout attempt/result freeze records differ")
    try:
        started = datetime.fromisoformat(str(attempt["startedAt"]))
        created = datetime.fromisoformat(str(result["createdAt"]))
        if started > created:
            errors.append("result predates its attempt marker")
    except (KeyError, TypeError, ValueError):
        errors.append("attempt/result timestamps are invalid")
    return errors


def verify_attempt_marker(
    result: dict[str, Any],
    expected_phase: str,
) -> list[str]:
    """Verify the linked marker with full execution-commit provenance."""
    return _verify_attempt_marker_core(
        result,
        expected_phase,
        verify_git_provenance=True,
    )


def _verify_phase_result_core(
    result: dict[str, Any],
    expected_phase: str,
    *,
    verify_git_provenance: bool,
) -> list[str]:
    errors: list[str] = []
    if expected_phase not in PHASES:
        return [f"unknown frozen phase {expected_phase!r}"]
    legacy_result = result.get("schemaVersion") == LEGACY_PHASE_SCHEMA_VERSION
    if legacy_result:
        registered = REGISTERED_LEGACY_PHASE_RESULTS[expected_phase]
        for field in (
            "resultSHA256",
            "gitCommitAtExecution",
            "implementationSHA256",
            "registrationSHA256",
        ):
            if result.get(field) != registered[field]:
                errors.append(
                    f"legacy {expected_phase} {field} differs from the "
                    "immutable registered historical result"
                )
        digest_input = dict(result)
        digest_input.pop("resultSHA256", None)
        try:
            computed_legacy_digest = sha256_bytes(
                canonical_json_bytes(digest_input)
            )
        except (TypeError, ValueError) as error:
            errors.append(
                f"legacy {expected_phase} result cannot be canonicalized: "
                f"{error}"
            )
        else:
            if computed_legacy_digest != registered["resultSHA256"]:
                errors.append(
                    f"legacy {expected_phase} canonical result digest differs "
                    "from the immutable registered historical result"
                )
        if errors:
            return errors
    else:
        errors.extend(phase_schema_errors(result))
    try:
        validate_frozen_registration()
    except ValueError as error:
        errors.append(str(error))
    if not legacy_result and result.get("schemaVersion") != SCHEMA_VERSION:
        errors.append("unexpected phase-result schema")
    if result.get("suiteId") != SUITE_ID:
        errors.append("unexpected v5 suite ID")
    if result.get("phase") != expected_phase:
        errors.append("result phase differs from the expected phase")
    if result.get("registrationSHA256") != registration_sha256():
        errors.append("result registration digest is stale")
    if result.get("configuration") != FROZEN_CONFIGURATION:
        errors.append("result configuration is not frozen")
    if result.get("configurationSHA256") != FROZEN_CONFIGURATION_SHA256:
        errors.append("result full configuration digest is inconsistent")
    if result.get("gatesDefinition") != GATES:
        errors.append("result gate definitions are not frozen")
    expected_status = (
        "prospective-holdout"
        if expected_phase == "holdout"
        else "one-shot-frozen-selection"
    )
    if result.get("status") != expected_status:
        errors.append("result status is inconsistent with its phase")
    git_commit = result.get("gitCommitAtExecution")
    if (
        not isinstance(git_commit, str)
        or len(git_commit) != 40
        or any(
            character not in "0123456789abcdef"
            for character in git_commit
        )
    ):
        errors.append("result execution commit is not a full Git SHA-1")
    elif verify_git_provenance:
        try:
            commit_implementation = implementation_sha256_at_commit(
                git_commit
            )
        except ValueError as error:
            errors.append(
                "cannot verify the implementation at the execution commit: "
                + str(error)
            )
        else:
            if commit_implementation != result.get("implementationSHA256"):
                errors.append(
                    "execution commit has a different implementation digest"
                )
        try:
            commit_registration = registration_sha256_at_commit(git_commit)
        except ValueError as error:
            errors.append(
                "cannot verify the registration at the execution commit: "
                + str(error)
            )
        else:
            if commit_registration != result.get("registrationSHA256"):
                errors.append(
                    "execution commit has a different registration digest"
                )
    if expected_phase == "selection":
        if result.get("pretestFreeze") is not None:
            errors.append("selection cannot contain a pretest freeze record")
    elif not isinstance(result.get("pretestFreeze"), dict):
        errors.append("holdout must contain a pretest freeze record")
    elif result["pretestFreeze"].get("pretestGitCommit") != git_commit:
        errors.append(
            "holdout execution commit differs from the pretest commit"
        )
    phase = PHASES[expected_phase]
    expected_phase_spec = _phase_specification(expected_phase)
    if result.get("phaseSpec") != expected_phase_spec:
        errors.append("result source-block specification is not frozen")
    if result.get("testSplitResolvedThisRun") is not (
        expected_phase == "holdout"
    ):
        errors.append("test split access disclosure is inconsistent")
    errors.extend(
        _verify_attempt_marker_core(
            result,
            expected_phase,
            verify_git_provenance=verify_git_provenance,
        )
    )

    records = result.get("records")
    baselines = result.get("baselines")
    aggregate = result.get("aggregate")
    if (
        not isinstance(records, list)
        or not isinstance(baselines, list)
        or not isinstance(aggregate, dict)
    ):
        return errors + ["records, baselines, and aggregate are required"]
    if any(not isinstance(record, dict) for record in records):
        return errors + ["every candidate record must be an object"]
    if any(not isinstance(baseline, dict) for baseline in baselines):
        return errors + ["every baseline record must be an object"]
    expected_indices = list(
        range(phase["startBlock"], phase["startBlock"] + phase["blocks"])
    )
    if [record.get("blockIndex") for record in records] != expected_indices:
        errors.append("candidate record indices differ from registration")
    if [baseline.get("blockIndex") for baseline in baselines] != expected_indices:
        errors.append("baseline record indices differ from registration")
    for field in (
        "tokenIdsSHA256",
        "canonicalCacheBF16SHA256",
        "payloadSHA256",
    ):
        values = [record.get(field) for record in records]
        if (
            any(not isinstance(value, str) for value in values)
            or len(values) != len(set(values))
        ):
            errors.append(f"candidate {field} values are not unique")
    expected_configuration_id = sha256_bytes(
        canonical_json_bytes(FROZEN_CONFIGURATION)
    )[:16]
    for record, baseline in zip(records, baselines):
        block_index = record.get("blockIndex")
        if record.get("configurationId") != expected_configuration_id:
            errors.append(
                f"block {block_index} has a foreign configuration ID"
            )
        if record.get("tokenIdsSHA256") != baseline.get("tokenIdsSHA256"):
            errors.append(
                f"block {block_index} candidate/baseline token digests differ"
            )
        if record.get("canonicalCacheBF16SHA256") != baseline.get(
            "canonicalCacheBF16SHA256"
        ):
            errors.append(
                f"block {block_index} candidate/baseline cache digests differ"
            )
        prediction_tokens = record.get("predictionTokens")
        agreement_count = record.get("top1AgreementCount")
        if (
            prediction_tokens != 128
            or baseline.get("predictionTokens") != 128
            or record.get("denseBF16Bytes") != 4_706_304
            or baseline.get("denseBF16Bytes") != 4_706_304
        ):
            errors.append(f"block {block_index} has an invalid fixed size")
        try:
            layers = baseline["layers"]
            trajectory_shape = baseline["trajectoryShapePerLayer"]
            if (
                type(layers) is not int
                or layers <= 0
                or not isinstance(trajectory_shape, list)
                or len(trajectory_shape) != 2
                or any(
                    type(value) is not int or value <= 0
                    for value in trajectory_shape
                )
            ):
                raise ValueError("invalid cache shape")
            scalar_count = layers * trajectory_shape[0] * trajectory_shape[1]
            expected_dense_bytes = scalar_count * 2
            if (
                baseline.get("denseBF16Bytes") != expected_dense_bytes
                or record.get("denseBF16Bytes") != expected_dense_bytes
            ):
                errors.append(
                    f"block {block_index} cache scalar count is inconsistent"
                )
        except (KeyError, TypeError, ValueError, OverflowError):
            scalar_count = 0
            errors.append(f"block {block_index} cache scalar count is invalid")
        if (
            type(agreement_count) is not int
            or agreement_count < 0
            or agreement_count > 128
            or not _close(
                record.get("top1Agreement"),
                agreement_count / 128,
            )
        ):
            errors.append(f"block {block_index} top-1 fields are inconsistent")
        if not _close(
            record.get("baselineNLLNatPerToken"),
            baseline.get("canonicalBF16NLLNatPerToken"),
        ):
            errors.append(
                f"block {block_index} candidate/baseline NLL fields differ"
            )
        try:
            expected_native_delta = (
                float(baseline["canonicalBF16NLLNatPerToken"])
                - float(baseline["originalFP32NLLNatPerToken"])
            )
            if not _close(
                baseline.get("nativeBF16DeltaNLLNatPerToken"),
                expected_native_delta,
            ):
                errors.append(
                    f"block {block_index} native BF16 delta is inconsistent"
                )
        except (KeyError, TypeError, ValueError):
            errors.append(
                f"block {block_index} has invalid baseline NLL fields"
            )
        native_agreement = baseline.get("nativeBF16Top1Agreement")
        if (
            type(native_agreement) not in {int, float}
            or not math.isfinite(float(native_agreement))
            or not 0.0 <= float(native_agreement) <= 1.0
            or not _close(
                float(native_agreement) * 128.0,
                round(float(native_agreement) * 128.0),
            )
        ):
            errors.append(
                f"block {block_index} native BF16 top-1 agreement is not k/128"
            )
        if (
            type(record.get("payloadBytes")) is not int
            or type(record.get("encodedFileBytes")) is not int
            or record["payloadBytes"] <= 0
            or record["encodedFileBytes"] < record["payloadBytes"] + (24 * 8)
        ):
            errors.append(
                f"block {block_index} container byte accounting is invalid"
            )
        if not legacy_result:
            try:
                validate_v5_container_manifest(record, FROZEN_CONFIGURATION)
            except (IndexError, KeyError, TypeError, ValueError) as error:
                errors.append(
                    f"block {block_index} container byte accounting is "
                    f"invalid: {error}"
                )
        try:
            expected_delta = (
                float(record["candidateNLLNatPerToken"])
                - float(record["baselineNLLNatPerToken"])
            )
            if not _close(
                record.get("deltaNLLNatPerToken"), expected_delta
            ):
                errors.append(
                    f"block {block_index} delta NLL is inconsistent"
                )
            if not _close(
                record.get("perplexityRatio"), math.exp(expected_delta)
            ):
                errors.append(
                    f"block {block_index} perplexity ratio is inconsistent"
                )
        except (KeyError, TypeError, ValueError, OverflowError):
            errors.append(f"block {block_index} has invalid NLL fields")
        try:
            reference_sum_squares = float(
                record["cacheReferenceSumSquares"]
            )
            candidate_sum_squares = float(
                record["cacheCandidateSumSquares"]
            )
            dot_product = float(record["cacheDotProduct"])
            difference_sum_squares = float(
                record["cacheDifferenceSumSquares"]
            )
            maximum_absolute_error = float(
                record["cacheMaximumAbsoluteError"]
            )
            if (
                not all(
                    math.isfinite(value)
                    for value in (
                        reference_sum_squares,
                        candidate_sum_squares,
                        dot_product,
                        difference_sum_squares,
                        maximum_absolute_error,
                    )
                )
                or min(
                    reference_sum_squares,
                    candidate_sum_squares,
                    difference_sum_squares,
                    maximum_absolute_error,
                )
                < 0.0
            ):
                raise ValueError("invalid cache accumulator")
            cache_identity = (
                reference_sum_squares
                + candidate_sum_squares
                - (2.0 * dot_product)
            )
            if (
                not math.isfinite(cache_identity)
                or not math.isclose(
                    difference_sum_squares,
                    cache_identity,
                    rel_tol=1e-9,
                    abs_tol=1e-6,
                )
            ):
                errors.append(
                    f"block {block_index} cache accumulators are inconsistent"
                )
            norm_product = math.sqrt(reference_sum_squares) * math.sqrt(
                candidate_sum_squares
            )
            if not _less_than_or_close(abs(dot_product), norm_product):
                errors.append(
                    f"block {block_index} cache Cauchy-Schwarz bound is violated"
                )
            maximum_error_squared = maximum_absolute_error**2
            maximum_error_sum_bound = scalar_count * maximum_error_squared
            if (
                scalar_count <= 0
                or not math.isfinite(maximum_error_squared)
                or not math.isfinite(maximum_error_sum_bound)
                or not _less_than_or_close(
                    maximum_error_squared,
                    difference_sum_squares,
                )
                or not _less_than_or_close(
                    difference_sum_squares,
                    maximum_error_sum_bound,
                )
            ):
                errors.append(
                    f"block {block_index} cache maximum-error bounds are violated"
                )
        except (KeyError, TypeError, ValueError, OverflowError):
            errors.append(
                f"block {block_index} has invalid cache accumulators"
            )
    try:
        recomputed_aggregate = aggregate_candidate_records(
            FROZEN_CONFIGURATION, records
        )
        cache_cosine = recomputed_aggregate.get("cacheCosineSimilarity")
        if (
            type(cache_cosine) not in {int, float}
            or not math.isfinite(float(cache_cosine))
            or not -1.0 <= float(cache_cosine) <= 1.0
        ):
            errors.append("aggregate cache cosine is outside [-1, 1]")
        for key, value in recomputed_aggregate.items():
            if key not in aggregate or not _close(aggregate[key], value):
                errors.append(f"aggregate field {key} is inconsistent")
        confidence, gates, passed = compute_confidence_and_verdict(
            records, baselines, recomputed_aggregate
        )
        for name, value in confidence.items():
            if (
                name not in result.get("confidence", {})
                or not _close(result["confidence"][name], value)
            ):
                errors.append(f"confidence field {name} is inconsistent")
        if result.get("gates") != gates:
            errors.append("recorded gates are inconsistent")
        if result.get("pass") is not passed:
            errors.append("recorded phase verdict is inconsistent")
    except (
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
        statistics.StatisticsError,
    ) as error:
        errors.append(f"cannot recompute frozen metrics: {error}")

    digest_input = dict(result)
    recorded_digest = digest_input.pop("resultSHA256", None)
    try:
        computed_digest = sha256_bytes(canonical_json_bytes(digest_input))
    except (TypeError, ValueError) as error:
        errors.append(f"cannot canonicalize phase result: {error}")
    else:
        if recorded_digest != computed_digest:
            errors.append(
                "resultSHA256 does not cover the canonical phase result"
            )
    return errors


def verify_phase_result(
    result: dict[str, Any],
    expected_phase: str,
) -> list[str]:
    """Verify a frozen phase, including its execution commit in Git."""
    return _verify_phase_result_core(
        result,
        expected_phase,
        verify_git_provenance=True,
    )


def verify_phase_artifact_self_consistency(
    result: dict[str, Any],
    expected_phase: str,
) -> list[str]:
    """Verify phase artifacts without claiming Git commit/tag provenance."""
    return _verify_phase_result_core(
        result,
        expected_phase,
        verify_git_provenance=False,
    )


def _resolve_model_and_split(
    split: str, local_files_only: bool
) -> tuple[Path, Path]:
    if split not in {"validation", "test"}:
        raise ValueError("frozen runner requested an unsupported split")
    from huggingface_hub import hf_hub_download

    model_path = Path(
        hf_hub_download(
            MODEL_REPOSITORY,
            revision=MODEL_REVISION,
            filename="model.safetensors",
            local_files_only=local_files_only,
        )
    )
    if model_path.stat().st_size != MODEL_WEIGHTS_BYTES:
        raise RuntimeError("pinned model weight size mismatch")
    if sha256_file(model_path) != MODEL_WEIGHTS_SHA256:
        raise RuntimeError("pinned model weight digest mismatch")
    for filename, asset in MODEL_ASSET_FILES.items():
        asset_path = Path(
            hf_hub_download(
                MODEL_REPOSITORY,
                revision=MODEL_REVISION,
                filename=filename,
                local_files_only=local_files_only,
            )
        )
        if asset_path.stat().st_size != asset["bytes"]:
            raise RuntimeError(f"pinned model asset size mismatch: {filename}")
        if sha256_file(asset_path) != asset["sha256"]:
            raise RuntimeError(
                f"pinned model asset digest mismatch: {filename}"
            )

    specification = DATASET_FILES[split]
    split_path = Path(
        hf_hub_download(
            DATASET_REPOSITORY,
            repo_type="dataset",
            revision=DATASET_REVISION,
            filename=specification["path"],
            local_files_only=local_files_only,
        )
    )
    if split_path.stat().st_size != specification["bytes"]:
        raise RuntimeError(f"pinned {split} dataset size mismatch")
    if sha256_file(split_path) != specification["sha256"]:
        raise RuntimeError(f"pinned {split} dataset digest mismatch")
    return model_path, split_path


def _require_public_tag(tag: str, expected_commit: str) -> None:
    local_commit = _git("rev-parse", f"refs/tags/{tag}^{{commit}}")
    if local_commit != expected_commit:
        raise ValueError(f"current HEAD is not the frozen tag {tag}")
    origin = _git("remote", "get-url", "origin").removesuffix(".git")
    if origin != PUBLIC_ORIGIN:
        raise ValueError("origin is not the registered public repository")
    remote_tag = _git(
        "ls-remote",
        "--tags",
        "origin",
        f"refs/tags/{tag}",
    )
    remote_lines = [
        line.split() for line in remote_tag.splitlines() if line.strip()
    ]
    if [line[0] for line in remote_lines if len(line) == 2] != [
        expected_commit
    ]:
        raise ValueError(f"the frozen lightweight tag {tag} is not public")


def _require_public_selection_freeze(head: str) -> dict[str, str]:
    _require_public_tag(SELECTION_PROTOCOL_TAG, head)
    return {
        "freezeGitCommit": head,
        "freezeGitTag": SELECTION_PROTOCOL_TAG,
        "publicRepository": PUBLIC_ORIGIN,
    }


def _require_public_pretest_freeze(
    head: str | None = None,
) -> dict[str, str]:
    try:
        selection = _load_json_object(SELECTION_PATH)
    except ValueError as error:
        raise ValueError(
            f"cannot read the frozen selection artifact: {error}"
        ) from error
    errors = verify_phase_result(selection, "selection")
    if errors:
        raise ValueError("selection artifact is invalid: " + "; ".join(errors))
    if selection.get("pass") is not True:
        raise ValueError("selection phase did not pass every frozen gate")

    head = head or _require_clean_head()
    _require_public_tag(PRETEST_TAG, head)
    selection_commit = str(selection.get("gitCommitAtExecution", ""))
    try:
        _git("merge-base", "--is-ancestor", selection_commit, head)
    except ValueError as error:
        raise ValueError(
            "selection execution commit is not an ancestor of the pretest tag"
        ) from error
    if implementation_sha256_at_commit(selection_commit) != selection.get(
        "implementationSHA256"
    ):
        raise ValueError(
            "selection execution commit has a different implementation"
        )
    relative_selection = SELECTION_PATH.relative_to(PROJECT_ROOT).as_posix()
    committed_selection = _run_git_process(
        ["show", f"{PRETEST_TAG}:{relative_selection}"]
    )
    if (
        committed_selection.returncode
        or committed_selection.stdout != SELECTION_PATH.read_bytes()
    ):
        raise ValueError("pretest tag does not contain this selection artifact")
    selection_attempt_path = _attempt_path("selection")
    relative_attempt = selection_attempt_path.relative_to(
        PROJECT_ROOT
    ).as_posix()
    committed_attempt = _run_git_process(
        ["show", f"{PRETEST_TAG}:{relative_attempt}"]
    )
    if (
        committed_attempt.returncode
        or committed_attempt.stdout != selection_attempt_path.read_bytes()
    ):
        raise ValueError(
            "pretest tag does not contain this selection attempt marker"
        )
    return {
        "pretestGitCommit": head,
        "pretestGitTag": PRETEST_TAG,
        "publicRepository": PUBLIC_ORIGIN,
        "selectionResultSHA256": str(selection["resultSHA256"]),
        "selectionArtifactSHA256": sha256_file(SELECTION_PATH),
        "selectionAttemptArtifactSHA256": sha256_file(
            selection_attempt_path
        ),
    }


def _create_attempt_marker(
    phase_name: str,
    *,
    git_commit: str,
    registration_digest: str,
    implementation_digest: str,
    execution_freeze: dict[str, str],
) -> tuple[dict[str, Any], str]:
    marker: dict[str, Any] = {
        "schemaVersion": ATTEMPT_SCHEMA_VERSION,
        "suiteId": SUITE_ID,
        "phase": phase_name,
        "status": "attempt-started-split-not-yet-resolved",
        "startedAt": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "registrationSHA256": registration_digest,
        "implementationSHA256": implementation_digest,
        "gitCommitAtExecution": git_commit,
        "phaseSpec": _phase_specification(phase_name),
        "testSplitWillBeResolved": phase_name == "holdout",
        "configurationSHA256": FROZEN_CONFIGURATION_SHA256,
        "executionFreeze": execution_freeze,
    }
    marker["attemptSHA256"] = sha256_bytes(canonical_json_bytes(marker))
    schema_problems = attempt_schema_errors(marker)
    if schema_problems:
        raise ValueError(
            "attempt marker is invalid before creation: "
            + "; ".join(schema_problems)
        )
    serialized = _serialized_json(marker)
    path = _attempt_path(phase_name)
    _exclusive_write(path, serialized)
    artifact_digest = sha256_bytes(serialized)
    if sha256_file(path) != artifact_digest:
        raise RuntimeError("attempt marker changed during durable creation")
    return marker, artifact_digest


def _path_present(path: Path) -> bool:
    return os.path.lexists(path)


def _assert_execution_unchanged(
    phase_name: str,
    *,
    git_commit: str,
    registration_digest: str,
    implementation_digest: str,
    attempt_marker: dict[str, Any],
    attempt_artifact_digest: str,
) -> None:
    attempt_path = _attempt_path(phase_name)
    current_commit = _require_clean_head(
        allowed_untracked=(attempt_path,)
    )
    if current_commit != git_commit:
        raise RuntimeError("HEAD changed after the attempt marker was created")
    if registration_sha256() != registration_digest:
        raise RuntimeError(
            "registration changed after the attempt marker was created"
        )
    if implementation_sha256() != implementation_digest:
        raise RuntimeError(
            "implementation changed after the attempt marker was created"
        )
    if implementation_sha256_at_commit(git_commit) != implementation_digest:
        raise RuntimeError(
            "execution commit no longer matches the implementation digest"
        )
    if registration_sha256_at_commit(git_commit) != registration_digest:
        raise RuntimeError(
            "execution commit no longer matches the registration digest"
        )
    observed_marker = _load_json_object(attempt_path)
    if observed_marker != attempt_marker:
        raise RuntimeError("attempt marker changed during execution")
    if sha256_file(attempt_path) != attempt_artifact_digest:
        raise RuntimeError("attempt-marker bytes changed during execution")
    output_path = Path(PHASES[phase_name]["output"])
    if _path_present(output_path):
        raise RuntimeError("phase output appeared during execution")


def _write_verified_result(
    phase_name: str,
    result: dict[str, Any],
    *,
    git_commit: str,
    registration_digest: str,
    implementation_digest: str,
    attempt_marker: dict[str, Any],
    attempt_artifact_digest: str,
) -> None:
    result_errors = verify_phase_result(result, phase_name)
    if result_errors:
        raise RuntimeError(
            "computed result failed frozen verification: "
            + "; ".join(result_errors)
        )
    serialized = _serialized_json(result)
    _assert_execution_unchanged(
        phase_name,
        git_commit=git_commit,
        registration_digest=registration_digest,
        implementation_digest=implementation_digest,
        attempt_marker=attempt_marker,
        attempt_artifact_digest=attempt_artifact_digest,
    )
    _exclusive_write(Path(PHASES[phase_name]["output"]), serialized)


def _load_runtime_dependencies() -> tuple[Any, ...]:
    """Load the heavyweight execution stack only when a phase reaches runtime."""
    import pyarrow
    import huggingface_hub
    import safetensors
    import tokenizers
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    return (
        pyarrow,
        huggingface_hub,
        safetensors,
        tokenizers,
        torch,
        transformers,
        AutoModelForCausalLM,
        AutoTokenizer,
    )


def run_phase(phase_name: str, local_files_only: bool) -> dict[str, Any]:
    if phase_name not in PHASES:
        raise ValueError("phase must be selection or holdout")
    validate_frozen_registration()
    output_path = Path(PHASES[phase_name]["output"])
    attempt_path = _attempt_path(phase_name)
    if _path_present(output_path):
        raise ValueError(
            f"refusing to overwrite one-shot artifact {output_path}"
        )
    if _path_present(attempt_path):
        raise ValueError(
            "phase attempt is already consumed; refusing to reuse marker "
            f"{attempt_path}"
        )
    bootstrap = _require_bootstrap_attestation(phase_name)
    _require_isolated_python()
    git_commit = _require_clean_head()
    if bootstrap["gitCommit"] != git_commit:
        raise ValueError("HEAD changed after the stdlib-only bootstrap")
    initial_registration_digest = registration_sha256()
    initial_implementation_digest = implementation_sha256()
    if (
        registration_sha256_at_commit(git_commit)
        != initial_registration_digest
    ):
        raise ValueError("HEAD does not contain the active registration")
    if (
        implementation_sha256_at_commit(git_commit)
        != initial_implementation_digest
    ):
        raise ValueError("HEAD does not contain the active implementation")
    execution_freeze = (
        _require_public_pretest_freeze(git_commit)
        if phase_name == "holdout"
        else _require_public_selection_freeze(git_commit)
    )
    freeze = execution_freeze if phase_name == "holdout" else None
    phase = PHASES[phase_name]

    (
        pyarrow,
        huggingface_hub,
        safetensors,
        tokenizers,
        torch,
        transformers,
        AutoModelForCausalLM,
        AutoTokenizer,
    ) = _load_runtime_dependencies()

    _validate_runtime_versions(
        torch,
        transformers,
        pyarrow,
        huggingface_hub,
        tokenizers,
        safetensors,
    )
    seed = 20260729
    torch.manual_seed(seed)
    np.random.seed(seed)
    if hasattr(torch, "use_deterministic_algorithms"):
        torch.use_deterministic_algorithms(True, warn_only=True)
    device = _resolve_device("mps", torch)
    attempt_marker, attempt_artifact_digest = _create_attempt_marker(
        phase_name,
        git_commit=git_commit,
        registration_digest=initial_registration_digest,
        implementation_digest=initial_implementation_digest,
        execution_freeze=execution_freeze,
    )
    model_path, split_path = _resolve_model_and_split(
        str(phase["split"]), local_files_only
    )
    verified_snapshot = model_path.parent
    tokenizer = AutoTokenizer.from_pretrained(
        verified_snapshot,
        local_files_only=True,
        trust_remote_code=False,
    )
    model = AutoModelForCausalLM.from_pretrained(
        verified_snapshot,
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.float32,
        attn_implementation="eager",
    ).to(device)
    model.eval()
    if model.config._attn_implementation != "eager":
        raise RuntimeError("model did not retain eager attention")
    if str(next(model.parameters()).dtype) != "torch.float32":
        raise RuntimeError("model dtype differs from frozen float32")

    blocks, token_digest = _token_blocks(
        tokenizer,
        split_path,
        int(phase["blocks"]),
        start_block=int(phase["startBlock"]),
    )
    baselines: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    grid = (FROZEN_CONFIGURATION,)
    for relative_index, block in enumerate(blocks):
        source_index = int(phase["startBlock"]) + relative_index
        print(
            f"{phase_name} block {relative_index + 1}/{len(blocks)} "
            f"(source {source_index})",
            flush=True,
        )
        baseline, candidates = _evaluate_block(
            block,
            source_index,
            grid,
            model=model,
            device=device,
            torch_module=torch,
        )
        baselines.append(baseline)
        records.extend(candidates)

    aggregate = _aggregate_phase(grid, records)[0]
    confidence, gates, passed = compute_confidence_and_verdict(
        records, baselines, aggregate
    )
    _assert_execution_unchanged(
        phase_name,
        git_commit=git_commit,
        registration_digest=initial_registration_digest,
        implementation_digest=initial_implementation_digest,
        attempt_marker=attempt_marker,
        attempt_artifact_digest=attempt_artifact_digest,
    )
    result: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "suiteId": SUITE_ID,
        "phase": phase_name,
        "status": "prospective-holdout" if phase_name == "holdout" else (
            "one-shot-frozen-selection"
        ),
        "createdAt": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "registrationSHA256": initial_registration_digest,
        "implementationSHA256": initial_implementation_digest,
        "gitCommitAtExecution": git_commit,
        "phaseSpec": _phase_specification(phase_name),
        "testSplitResolvedThisRun": phase_name == "holdout",
        "attemptMarkerSHA256": str(attempt_marker["attemptSHA256"]),
        "attemptArtifactSHA256": attempt_artifact_digest,
        "configuration": FROZEN_CONFIGURATION,
        "configurationSHA256": FROZEN_CONFIGURATION_SHA256,
        "gatesDefinition": GATES,
        "environment": {
            "device": device,
            "hfHome": (
                "configured" if os.environ.get("HF_HOME") else None
            ),
            "huggingfaceHub": huggingface_hub.__version__,
            "attentionImplementation": model.config._attn_implementation,
            "localPythonBytecode": "absent",
            "machine": platform.machine(),
            "modelDtype": str(next(model.parameters()).dtype),
            "numpy": np.__version__,
            "platform": platform.platform(),
            "pyarrow": pyarrow.__version__,
            "python": platform.python_version(),
            "pythonBytecodeWrites": False,
            "pythonIsolatedMode": bool(sys.flags.isolated),
            "safetensors": safetensors.__version__,
            "seed": seed,
            "tokenizers": tokenizers.__version__,
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "zlibCompileVersion": zlib.ZLIB_VERSION,
            "zlibRuntimeVersion": zlib.ZLIB_RUNTIME_VERSION,
        },
        "selectedTokenIdsSHA256": token_digest,
        "baselines": baselines,
        "records": records,
        "aggregate": aggregate,
        "confidence": confidence,
        "gates": gates,
        "pass": passed,
        "pretestFreeze": freeze,
    }
    result["resultSHA256"] = sha256_bytes(canonical_json_bytes(result))
    _write_verified_result(
        phase_name,
        result,
        git_commit=git_commit,
        registration_digest=initial_registration_digest,
        implementation_digest=initial_implementation_digest,
        attempt_marker=attempt_marker,
        attempt_artifact_digest=attempt_artifact_digest,
    )
    return result


def parse_arguments(
    arguments: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=tuple(PHASES))
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="use only already verified Hugging Face cache files",
    )
    return parser.parse_args(arguments)


def main() -> int:
    arguments = parse_arguments()
    try:
        result = run_phase(arguments.phase, arguments.local_files_only)
    except Exception as error:
        print(f"FROZEN VOIDTOKEN V5 RUN FAILED: {error}", file=sys.stderr)
        return 1
    aggregate = result["aggregate"]
    confidence = result["confidence"]
    print(
        f"{arguments.phase.upper()} {'PASS' if result['pass'] else 'FAIL'}: "
        f"{aggregate['compressionRatioVsBF16']:.6f}x, "
        f"delta NLL {aggregate['deltaNLLNatPerToken']:+.6f}, "
        f"upper95 {confidence['blockwiseDeltaNLLUpperOneSided95']:+.6f}, "
        f"top-1 {aggregate['top1Agreement']:.6%}, "
        f"Wilson lower95 {confidence['wilsonLowerOneSided95']:.6%}."
    )
    print(f"Result SHA-256: {result['resultSHA256']}")
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
