"""Source-only adapter for the historical VoidToken comparison backend.

This module deliberately stays outside the macOS application resource list.
The final application evaluates the registered real-model candidate only;
source checkouts retain this adapter so older experiments remain reproducible.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_CORE = PROJECT_ROOT / "BenchmarkCore"


def _codec_types() -> tuple[type[Any], type[Any]]:
    module_path = LEGACY_CORE / "corelm_benchmark.py"
    if not module_path.is_file():
        raise RuntimeError(
            "historical VoidToken codec is unavailable in this real-only package"
        )
    legacy_core = str(LEGACY_CORE)
    if legacy_core not in sys.path:
        sys.path.insert(0, legacy_core)
    try:
        from corelm_benchmark import (  # type: ignore[import-not-found]
            EncodedRepresentation,
            VoidTokenBackend,
        )
    except ImportError as error:
        raise RuntimeError(
            "historical VoidToken codec could not be loaded"
        ) from error
    return EncodedRepresentation, VoidTokenBackend


def encode(
    states: np.ndarray,
    *,
    top_k: int,
    qmax: int,
    keyframe_interval: int,
) -> Any:
    """Encode through the unchanged historical implementation."""
    _, backend = _codec_types()
    return backend.encode(
        states,
        top_k=top_k,
        qmax=qmax,
        keyframe_interval=keyframe_interval,
    )


def from_bytes(container: bytes) -> Any:
    """Parse through the unchanged historical representation type."""
    representation, _ = _codec_types()
    return representation.from_bytes(container)
