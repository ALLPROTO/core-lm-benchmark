#!/usr/bin/env python3
"""Build deterministic arXiv and reproducibility archives."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


ROOT = Path(__file__).resolve().parents[1]
PUBLICATION = ROOT / "publication"
ARXIV = PUBLICATION / "arxiv"
OUTPUT = ROOT / "output"
ARCHIVE_MTIME = 0


def normalized_tarinfo(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Remove host-specific metadata from one archive member."""
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = ARCHIVE_MTIME
    info.pax_headers = {}
    if info.isdir():
        info.mode = 0o755
    elif info.isfile():
        info.mode = 0o755 if info.mode & 0o111 else 0o644
    elif info.issym():
        info.mode = 0o777
    return info


def add_path(archive: tarfile.TarFile, source: Path, arcname: str) -> None:
    """Add one path recursively in a stable order with normalized metadata."""
    info = normalized_tarinfo(archive.gettarinfo(str(source), arcname=arcname))
    if info.isfile():
        with source.open("rb") as handle:
            archive.addfile(info, handle)
        return

    archive.addfile(info)
    if info.isdir():
        for child in sorted(source.iterdir(), key=lambda item: item.name):
            add_path(archive, child, f"{arcname}/{child.name}")


@contextmanager
def deterministic_tar_gz(target: Path) -> Iterator[tarfile.TarFile]:
    """Create a gzip-compressed tar archive without wall-clock metadata."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            mtime=ARCHIVE_MTIME,
        ) as compressed:
            with tarfile.open(
                fileobj=compressed,
                mode="w",
                format=tarfile.PAX_FORMAT,
            ) as archive:
                yield archive


def build_arxiv(output_directory: Path = OUTPUT) -> Path:
    target = output_directory / "corelm_arxiv_source.tar.gz"
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
    with deterministic_tar_gz(target) as archive:
        for relative in sorted(include):
            source = ARXIV / relative
            if not source.is_file():
                raise FileNotFoundError(source)
            add_path(archive, source, relative)
    return target


def build_reproducibility(output_directory: Path = OUTPUT) -> Path:
    target = output_directory / "corelm_reproducibility.tar.gz"
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

        source_files = [
            ".github/workflows/verify.yml",
            "App/Info.plist",
            "App/Sources/BenchmarkStore.swift",
            "App/Sources/ContentView.swift",
            "App/Sources/CoreLMBenchmarkApp.swift",
            "App/Sources/Models.swift",
            "BenchmarkCore/corelm_benchmark.py",
            "BenchmarkCore/run_suite.py",
            "BenchmarkCore/verify_evidence.py",
            "Tests/test_benchmark.py",
            "schemas/benchmark-result.schema.json",
        ]
        for relative in source_files:
            source = ROOT / relative
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        results = stage / "benchmark-results"
        results.mkdir()
        shutil.copy2(ROOT / "benchmark-results/aggregate.json", results)
        shutil.copy2(ROOT / "benchmark-results/README.md", results)
        for run_id in aggregate["runIds"]:
            for suffix in [".json", ".md"]:
                source = ROOT / "benchmark-results" / f"{run_id}{suffix}"
                if not source.is_file():
                    raise FileNotFoundError(source)
                shutil.copy2(source, results)

        publication_arxiv = stage / "publication/arxiv"
        publication_arxiv.mkdir(parents=True)
        shutil.copy2(
            PUBLICATION / "reproducibility/README.md",
            stage / "publication/README.md",
        )
        shutil.copy2(ARXIV / "generate_figures.py", publication_arxiv)

        with deterministic_tar_gz(target) as archive:
            add_path(archive, stage, stage.name)
    return target


def build_all(output_directory: Path = OUTPUT) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    return [
        build_arxiv(output_directory),
        build_reproducibility(output_directory),
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(artifacts: list[Path], output_directory: Path) -> Path:
    target = output_directory / "SHA256SUMS"
    target.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in artifacts),
        encoding="utf-8",
    )
    return target


def verify_determinism() -> bool:
    with tempfile.TemporaryDirectory(prefix="corelm-archive-check-") as temporary:
        root = Path(temporary)
        first = build_all(root / "first")
        second = build_all(root / "second")
        matches = True
        for first_path, second_path in zip(first, second):
            first_digest = sha256(first_path)
            second_digest = sha256(second_path)
            same = first_digest == second_digest
            matches = matches and same
            print(
                f"{first_path.name}: "
                f"{'MATCH' if same else 'MISMATCH'} {first_digest}"
            )
        return matches


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="Directory for generated archives",
    )
    parser.add_argument(
        "--verify-determinism",
        action="store_true",
        help="Build each archive twice in temporary directories and compare SHA-256",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    if arguments.verify_determinism:
        return 0 if verify_determinism() else 1
    artifacts = build_all(arguments.output)
    for artifact in artifacts:
        print(artifact)
    print(write_checksums(artifacts, arguments.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
