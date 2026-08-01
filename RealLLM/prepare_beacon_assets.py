#!/usr/bin/env python3
"""Pre-cache pinned bytes for the one-shot run without tokenizing or scoring."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RealLLM.benchmark_real_llm import (  # noqa: E402
    DATASET_FILES,
    DATASET_REPOSITORY,
    DATASET_REVISION,
    MODEL_ASSET_FILES,
    MODEL_REPOSITORY,
    MODEL_REVISION,
    MODEL_WEIGHTS_BYTES,
    MODEL_WEIGHTS_SHA256,
    sha256_file,
)


def _safe_cache(path: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise ValueError("cache path must be absolute")
    expanded.mkdir(mode=0o700, parents=True, exist_ok=True)
    if expanded.is_symlink() or not expanded.is_dir():
        raise ValueError("cache path must be a real directory, not a symlink")
    resolved = expanded.resolve(strict=True)
    status = resolved.stat()
    if not stat.S_ISDIR(status.st_mode) or status.st_uid != os.getuid():
        raise ValueError("cache directory must be owned by the current user")
    if status.st_mode & 0o022:
        raise ValueError("cache directory must not be group/world writable")
    return resolved


def prepare_assets(cache: Path, *, local_files_only: bool) -> list[Path]:
    cache = _safe_cache(cache)
    os.environ["HF_HOME"] = str(cache)
    from huggingface_hub import hf_hub_download

    verified: list[Path] = []
    model_files = {
        "model.safetensors": {
            "bytes": MODEL_WEIGHTS_BYTES,
            "sha256": MODEL_WEIGHTS_SHA256,
        },
        **MODEL_ASSET_FILES,
    }
    for filename, specification in model_files.items():
        path = Path(
            hf_hub_download(
                MODEL_REPOSITORY,
                revision=MODEL_REVISION,
                filename=filename,
                cache_dir=cache / "hub",
                local_files_only=local_files_only,
                token=False,
            )
        )
        if (
            path.stat().st_size != specification["bytes"]
            or sha256_file(path) != specification["sha256"]
        ):
            raise RuntimeError(f"pinned model asset failed verification: {filename}")
        verified.append(path)
    test = DATASET_FILES["test"]
    test_path = Path(
        hf_hub_download(
            DATASET_REPOSITORY,
            repo_type="dataset",
            revision=DATASET_REVISION,
            filename=test["path"],
            cache_dir=cache / "hub",
            local_files_only=local_files_only,
            token=False,
        )
    )
    if (
        test_path.stat().st_size != test["bytes"]
        or sha256_file(test_path) != test["sha256"]
    ):
        raise RuntimeError("pinned test parquet failed verification")
    verified.append(test_path)
    return verified


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path.home() / ".cache" / "corelm-model-assets",
    )
    parser.add_argument("--offline-only", action="store_true")
    return parser.parse_args(arguments)


def main() -> int:
    arguments = parse_arguments()
    try:
        verified = prepare_assets(
            arguments.cache,
            local_files_only=arguments.offline_only,
        )
    except Exception as error:
        print(f"BEACON ASSET PREPARATION FAILED: {error}", file=sys.stderr)
        return 1
    print(
        "BEACON ASSET PREPARATION PASS: verified model assets and the pinned "
        f"test parquet ({len(verified)} files)."
    )
    print("No tokenizer, model inference, codec, or metric was executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
