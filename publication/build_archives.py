#!/usr/bin/env python3
"""Build deterministic arXiv and reproducibility archives."""

from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLICATION = ROOT / "publication"
ARXIV = PUBLICATION / "arxiv"
OUTPUT = ROOT / "output"


def add_tree(archive: tarfile.TarFile, source: Path, arcname: str) -> None:
    archive.add(source, arcname=arcname, recursive=True)


def build_arxiv() -> Path:
    target = OUTPUT / "corelm_arxiv_source.tar.gz"
    include = [
        "main.tex",
        "author.tex",
        "references.bib",
        "main.bbl",
        "results_table.tex",
        "figures/architecture.pdf",
        "figures/tradeoff.pdf",
        "figures/metrics_by_dimension.pdf",
        "figures/error_feedback.pdf",
    ]
    with tarfile.open(target, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for relative in include:
            source = ARXIV / relative
            if not source.is_file():
                raise FileNotFoundError(source)
            archive.add(source, arcname=relative)
    return target


def build_reproducibility() -> Path:
    target = OUTPUT / "corelm_reproducibility.tar.gz"
    aggregate = json.loads((ROOT / "benchmark-results/aggregate.json").read_text())

    with tempfile.TemporaryDirectory(prefix="corelm-repro-") as temporary:
        stage = Path(temporary) / "corelm_reproducibility"
        stage.mkdir()

        files = [
            "ARCHITECTURE.md",
            "CITATION.cff",
            "EVIDENCE.md",
            "KNOWN_LIMITATIONS.md",
            "LICENSE",
            "Package.swift",
            "README.md",
            "requirements.txt",
            "run_tests.sh",
            "run_benchmark.sh",
            "package_app.sh",
        ]
        for relative in files:
            shutil.copy2(ROOT / relative, stage / relative)

        for directory in ["App", "BenchmarkCore", "Tests"]:
            shutil.copytree(
                ROOT / directory,
                stage / directory,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

        results = stage / "benchmark-results"
        results.mkdir()
        shutil.copy2(ROOT / "benchmark-results/aggregate.json", results)
        for run_id in aggregate["runIds"]:
            for suffix in [".json", ".md"]:
                source = ROOT / "benchmark-results" / f"{run_id}{suffix}"
                if not source.is_file():
                    raise FileNotFoundError(source)
                shutil.copy2(source, results)

        publication = stage / "publication"
        publication.mkdir()
        shutil.copy2(PUBLICATION / "reproducibility/README.md", publication / "README.md")
        shutil.copy2(ARXIV / "generate_figures.py", publication)

        with tarfile.open(target, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            add_tree(archive, stage, stage.name)
    return target


if __name__ == "__main__":
    OUTPUT.mkdir(exist_ok=True)
    for artifact in [build_arxiv(), build_reproducibility()]:
        print(artifact)
