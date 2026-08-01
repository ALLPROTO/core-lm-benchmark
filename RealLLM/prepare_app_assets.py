#!/usr/bin/env python3
"""Download and independently verify the inputs used by the macOS app."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path
from urllib.parse import urlsplit


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
)
from RealLLM.develop_voidtoken_v5 import (  # noqa: E402
    _download_validation_only,
)


def _private_cache_directory(path: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise ValueError("Hugging Face cache path must be absolute")
    resolved_home = Path.home().resolve()
    if expanded in {Path("/"), resolved_home}:
        raise ValueError(f"refusing unsafe cache path: {expanded}")
    expanded.mkdir(mode=0o700, parents=True, exist_ok=True)
    status = expanded.lstat()
    if (
        not stat.S_ISDIR(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_uid != os.getuid()
        or status.st_mode & 0o022
    ):
        raise ValueError(
            "Hugging Face cache must be an owner-controlled directory "
            f"(chmod go-w {expanded})"
        )
    os.chmod(expanded, 0o700, follow_symlinks=False)
    status = expanded.lstat()
    if stat.S_IMODE(status.st_mode) != 0o700:
        raise ValueError(
            f"Hugging Face cache could not be made private: {expanded}"
        )
    return expanded.resolve(strict=True)


def _validated_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    try:
        parsed.port
    except ValueError as error:
        raise ValueError("Hugging Face endpoint has an invalid port") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "\\" in value
        or any(ord(character) <= 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(
            "Hugging Face endpoint must be an HTTPS base URL without "
            "credentials, query, or fragment"
        )
    return value.rstrip("/")


def prepare_assets(
    cache_directory: Path,
    *,
    offline_only: bool = False,
    endpoint: str | None = None,
) -> dict[str, Path]:
    """Resolve pinned validation inputs, then prove that offline reuse works."""

    cache = _private_cache_directory(cache_directory)
    for variable in (
        "HF_ASSETS_CACHE",
        "HF_ENDPOINT",
        "HF_HUB_CACHE",
        "HF_TOKEN",
        "HF_TOKEN_PATH",
        "HF_HUB_OFFLINE",
        "HF_XET_CACHE",
        "HUGGING_FACE_HUB_TOKEN",
        "HUGGINGFACE_HUB_CACHE",
        "TRANSFORMERS_CACHE",
        "TRANSFORMERS_OFFLINE",
    ):
        os.environ.pop(variable, None)
    os.environ["HF_HOME"] = str(cache)
    os.environ["HF_HUB_CACHE"] = str(cache / "hub")
    os.environ["HF_XET_CACHE"] = str(cache / "xet")
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    if offline_only:
        os.environ["HF_HUB_OFFLINE"] = "1"
    elif endpoint is not None:
        os.environ["HF_ENDPOINT"] = _validated_endpoint(endpoint)
    resolved = _download_validation_only(local_files_only=offline_only)
    offline_resolved = _download_validation_only(local_files_only=True)
    if {
        key: value.resolve(strict=True)
        for key, value in resolved.items()
    } != {
        key: value.resolve(strict=True)
        for key, value in offline_resolved.items()
    }:
        raise RuntimeError("online and offline asset resolution differ")
    cache_prefix = str(cache) + os.sep
    if any(
        not str(path.resolve(strict=True)).startswith(cache_prefix)
        for path in offline_resolved.values()
    ):
        raise RuntimeError("resolved asset escaped the dedicated app cache")
    return offline_resolved


def _registered_download_bytes() -> int:
    return (
        MODEL_WEIGHTS_BYTES
        + sum(int(asset["bytes"]) for asset in MODEL_ASSET_FILES.values())
        + int(DATASET_FILES["validation"]["bytes"])
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "prepare the exact Qwen and WikiText validation files used by "
            "CoreLMBenchmark.app"
        )
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path(
            os.environ.get(
                "HF_HOME",
                str(Path.home() / ".cache" / "corelm-model-assets"),
            )
        ),
        help="private Hugging Face cache directory",
    )
    parser.add_argument(
        "--offline-only",
        action="store_true",
        help="verify an existing cache without network access",
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("CORELM_HF_ENDPOINT"),
        help=(
            "HTTPS Hugging Face-compatible base URL; downloaded files still "
            "must match the registered sizes and SHA-256 digests"
        ),
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    mode = "Verifying cached" if arguments.offline_only else "Downloading"
    print(
        f"{mode} pinned inputs ({_registered_download_bytes() / 1_000_000:.1f} MB).",
        flush=True,
    )
    try:
        prepare_assets(
            arguments.cache,
            offline_only=arguments.offline_only,
            endpoint=arguments.endpoint,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"APP ASSET PREPARATION FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "APP ASSET PREPARATION PASS: "
        f"{MODEL_REPOSITORY}@{MODEL_REVISION} "
        f"({MODEL_WEIGHTS_SHA256}) and "
        f"{DATASET_REPOSITORY}@{DATASET_REVISION} validation are "
        "digest-verified and available offline."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
