#!/usr/bin/env python3
"""Generate vector figures and derived tables for the Core LM paper."""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from reportlab.lib.colors import Color, HexColor, black, white
from reportlab.pdfgen import canvas


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
RESULTS = PROJECT / "benchmark-results"
FIGURES = HERE / "figures"
CORE = PROJECT / "BenchmarkCore"
sys.path.insert(0, str(CORE))

from corelm_benchmark import (  # noqa: E402
    CoreLMAdapter,
    DenseBackend,
    DeterministicInputGenerator,
    ExperimentConfiguration,
    VoidTokenBackend,
    method_metrics,
)


COLORS = {
    "zero": HexColor("#7B8794"),
    "gaussian_bounded": HexColor("#2563EB"),
    "uniform_bounded": HexColor("#0D9488"),
    "impulse": HexColor("#DC2626"),
    "repeating_structured": HexColor("#7C3AED"),
}


def authoritative_results() -> tuple[dict, list[dict]]:
    aggregate = json.loads((RESULTS / "aggregate.json").read_text())
    runs = [
        json.loads((RESULTS / f"{run_id}.json").read_text())
        for run_id in aggregate["runIds"]
    ]
    return aggregate, runs


def label(c: canvas.Canvas, x: float, y: float, text: str, size: float = 9,
          color=black, font: str = "Helvetica") -> None:
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawString(x, y, text)


def architecture_figure() -> None:
    path = FIGURES / "architecture.pdf"
    width, height = 520, 225
    c = canvas.Canvas(str(path), pagesize=(width, height), invariant=1)
    c.setTitle("Core LM compression benchmark architecture")
    boxes = [
        (18, 135, 105, 42, "Configuration", "#E8F0FE"),
        (148, 135, 110, 42, "Deterministic U_t", "#E8F0FE"),
        (283, 135, 96, 42, "Core LM F", "#E8F0FE"),
        (404, 135, 98, 42, "Dense S_t", "#E8F0FE"),
        (96, 58, 92, 42, "Dense", "#EEF2F7"),
        (214, 58, 92, 42, "PCA", "#EEF2F7"),
        (332, 58, 92, 42, "VoidToken v3", "#DCFCE7"),
    ]
    for x, y, w, h, text, fill in boxes:
        c.setFillColor(HexColor(fill))
        c.setStrokeColor(HexColor("#52606D"))
        c.roundRect(x, y, w, h, 6, fill=1, stroke=1)
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(x + w / 2, y + 17, text)

    def arrow(x1, y1, x2, y2):
        c.setStrokeColor(HexColor("#52606D"))
        c.setLineWidth(1.2)
        c.line(x1, y1, x2, y2)
        angle = math.atan2(y2 - y1, x2 - x1)
        for delta in (-0.45, 0.45):
            c.line(x2, y2, x2 - 7 * math.cos(angle + delta),
                   y2 - 7 * math.sin(angle + delta))

    arrow(123, 156, 148, 156)
    arrow(258, 156, 283, 156)
    arrow(379, 156, 404, 156)
    c.line(453, 135, 453, 119)
    c.line(142, 119, 378, 119)
    arrow(142, 119, 142, 100)
    arrow(260, 119, 260, 100)
    arrow(378, 119, 378, 100)
    c.setFillColor(HexColor("#F8FAFC"))
    c.setStrokeColor(HexColor("#94A3B8"))
    c.roundRect(92, 12, 336, 24, 5, fill=1, stroke=1)
    c.setFillColor(black)
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(
        260, 21,
        "Metrics, invariants, byte accounting, verdict, JSON and Markdown evidence",
    )
    arrow(142, 58, 181, 36)
    arrow(260, 58, 260, 36)
    arrow(378, 58, 339, 36)
    c.showPage()
    c.save()


def axes(c, left, bottom, width, height, xmin, xmax, ymin, ymax,
         xlabel, ylabel):
    c.setStrokeColor(HexColor("#475569"))
    c.setLineWidth(0.8)
    c.line(left, bottom, left + width, bottom)
    c.line(left, bottom, left, bottom + height)
    c.setFillColor(black)
    c.setFont("Helvetica", 8)
    c.drawCentredString(left + width / 2, bottom - 26, xlabel)
    c.saveState()
    c.translate(left - 38, bottom + height / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, ylabel)
    c.restoreState()
    return (
        lambda x: left + (x - xmin) / (xmax - xmin) * width,
        lambda y: bottom + (y - ymin) / (ymax - ymin) * height,
    )


def tradeoff_figure(runs: list[dict]) -> None:
    path = FIGURES / "tradeoff.pdf"
    width, height = 430, 290
    c = canvas.Canvas(str(path), pagesize=(width, height), invariant=1)
    c.setTitle("Compression-quality tradeoff")
    points = []
    for run in runs:
        method = next(m for m in run["methods"] if m["name"] == "voidtoken")
        points.append((
            method["compressionRatio"],
            method["normalizedRMSE"],
            run["configuration"]["inputScenario"],
        ))
    max_x = max(p[0] for p in points)
    tx, ty = axes(c, 60, 54, 330, 195, 0, max_x * 1.05, 0, 0.11,
                  "Actual compression ratio (dense bytes / payload bytes)",
                  "Normalized RMSE")
    c.setDash(4, 3)
    c.setStrokeColor(HexColor("#DC2626"))
    c.line(tx(4), 54, tx(4), 249)
    c.line(60, ty(0.10), 390, ty(0.10))
    c.setDash()
    label(c, tx(4) + 4, 239, "4x", 7.5, HexColor("#DC2626"))
    label(c, 285, ty(0.10) + 4, "NRMSE threshold", 7.5, HexColor("#DC2626"))
    for x, y, scenario in points:
        c.setFillColor(COLORS[scenario])
        c.circle(tx(x), ty(y), 2.4, fill=1, stroke=0)
    legend_y = 270
    x = 58
    for scenario in COLORS:
        c.setFillColor(COLORS[scenario])
        c.circle(x, legend_y, 3, fill=1, stroke=0)
        label(c, x + 6, legend_y - 3, scenario.replace("_", " "), 7.2)
        x += 73
    c.showPage()
    c.save()


def metrics_by_dimension(runs: list[dict]) -> None:
    grouped = defaultdict(list)
    for run in runs:
        method = next(m for m in run["methods"] if m["name"] == "voidtoken")
        grouped[run["configuration"]["dimension"]].append(method)
    path = FIGURES / "metrics_by_dimension.pdf"
    width, height = 430, 270
    c = canvas.Canvas(str(path), pagesize=(width, height), invariant=1)
    c.setTitle("Worst-case metrics by state dimension")
    dimensions = sorted(grouped)
    values = {
        n: {
            "ratio": min(x["compressionRatio"] for x in grouped[n]),
            "nrmse": max(x["normalizedRMSE"] for x in grouped[n]),
            "energy": max(x["meanEnergyRelativeDrift"] for x in grouped[n]),
        }
        for n in dimensions
    }
    colors = [HexColor("#2563EB"), HexColor("#0D9488"), HexColor("#7C3AED")]
    panel_specs = [
        (48, 56, 98, 165, "Min. ratio", 0, 6.2, "ratio"),
        (171, 56, 98, 165, "Worst NRMSE", 0, 0.07, "nrmse"),
        (294, 56, 98, 165, "Worst energy drift", 0, 0.055, "energy"),
    ]
    for left, bottom, pw, ph, title, ymin, ymax, key in panel_specs:
        c.setStrokeColor(HexColor("#CBD5E1"))
        c.rect(left, bottom, pw, ph, fill=0, stroke=1)
        label(c, left, bottom + ph + 10, title, 8, font="Helvetica-Bold")
        bar_w = 20
        gap = 10
        for i, n in enumerate(dimensions):
            value = values[n][key]
            x = left + 10 + i * (bar_w + gap)
            h = value / ymax * (ph - 20)
            c.setFillColor(colors[i])
            c.rect(x, bottom, bar_w, h, fill=1, stroke=0)
            label(c, x + 2, bottom - 14, str(n), 7)
            label(c, x, bottom + h + 4, f"{value:.3f}", 6.5)
        if key == "ratio":
            y = bottom + 4 / ymax * (ph - 20)
        elif key == "nrmse":
            y = bottom + 0.10 / ymax * (ph - 20)
        else:
            y = bottom + 0.05 / ymax * (ph - 20)
        if bottom <= y <= bottom + ph:
            c.setStrokeColor(HexColor("#DC2626"))
            c.setDash(3, 2)
            c.line(left, y, left + pw, y)
            c.setDash()
    label(c, 170, 22, "State dimension n", 8)
    c.showPage()
    c.save()


def legacy_reconstruction(states: np.ndarray, top_k: int, qmax: int) -> np.ndarray:
    reconstructed = np.empty_like(states)
    reconstructed[0] = states[0]
    for row, delta in enumerate(np.diff(states, axis=0), 1):
        norm = float(np.linalg.norm(delta))
        decoded = np.zeros(states.shape[1], dtype=np.float32)
        if norm > 1e-12:
            indices = np.argpartition(np.abs(delta), -top_k)[-top_k:]
            quantized = np.clip(
                np.rint(delta[indices] / norm * qmax), -qmax, qmax
            )
            decoded[indices] = quantized.astype(np.float32) / qmax * norm
        reconstructed[row] = reconstructed[row - 1] + decoded
    return reconstructed


def error_feedback_figure() -> None:
    config = ExperimentConfiguration(
        dimension=96,
        steps=200,
        seed=42,
        input_scenario="gaussian_bounded",
        pca_components=8,
        top_k=8,
        qmax=127,
        keyframe_interval=0,
    )
    inputs = DeterministicInputGenerator.generate(config)
    states = CoreLMAdapter(config.dimension).run(inputs)
    legacy = legacy_reconstruction(states, config.top_k, config.qmax)
    corrected = VoidTokenBackend.encode(
        states, config.top_k, config.qmax, config.keyframe_interval
    ).reconstructed
    legacy_error = np.sqrt(np.mean((legacy - states) ** 2, axis=1))
    corrected_error = np.sqrt(np.mean((corrected - states) ** 2, axis=1))
    ymax = float(max(legacy_error.max(), corrected_error.max())) * 1.08
    path = FIGURES / "error_feedback.pdf"
    width, height = 430, 275
    c = canvas.Canvas(str(path), pagesize=(width, height), invariant=1)
    c.setTitle("Accumulated reconstruction error")
    tx, ty = axes(c, 58, 48, 335, 190, 0, config.steps, 0, ymax,
                  "Time step", "Per-step RMSE")

    def draw_line(values, color):
        c.setStrokeColor(color)
        c.setLineWidth(1.4)
        path_obj = c.beginPath()
        path_obj.moveTo(tx(0), ty(float(values[0])))
        for index, value in enumerate(values[1:], 1):
            path_obj.lineTo(tx(index), ty(float(value)))
        c.drawPath(path_obj, stroke=1, fill=0)

    draw_line(legacy_error, HexColor("#DC2626"))
    draw_line(corrected_error, HexColor("#0D9488"))
    c.setStrokeColor(HexColor("#DC2626"))
    c.line(215, 255, 235, 255)
    label(c, 241, 252, "open-loop delta v1", 8)
    c.setStrokeColor(HexColor("#0D9488"))
    c.line(315, 255, 335, 255)
    label(c, 341, 252, "closed-loop residual v3", 8)
    c.showPage()
    c.save()


def derived_table(aggregate: dict, runs: list[dict]) -> None:
    grouped = defaultdict(list)
    for run in runs:
        method = next(m for m in run["methods"] if m["name"] == "voidtoken")
        grouped[run["configuration"]["inputScenario"]].append(method)
    order = [
        "zero", "gaussian_bounded", "uniform_bounded",
        "impulse", "repeating_structured",
    ]
    rows = []
    for scenario in order:
        methods = grouped[scenario]
        rows.append(
            f"{scenario.replace('_', ' ')} & {len(methods)} & "
            f"{min(m['compressionRatio'] for m in methods):.4f} & "
            f"{max(m['normalizedRMSE'] for m in methods):.5f} & "
            f"{min(m['cosineSimilarity'] for m in methods):.5f} & "
            f"{max(m['meanEnergyRelativeDrift'] for m in methods):.5f} \\\\"
        )
    content = "\n".join([
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Scenario & Runs & Min. ratio & Max. NRMSE & Min. cosine & Max. energy drift \\",
        r"\midrule",
        *rows,
        r"\midrule",
        f"All & {aggregate['runs']} & "
        f"{aggregate['voidToken']['minimumCompressionRatio']:.4f} & "
        f"{aggregate['voidToken']['maximumNormalizedRMSE']:.5f} & "
        f"{aggregate['voidToken']['minimumCosineSimilarity']:.5f} & "
        f"{aggregate['voidToken']['maximumMeanEnergyRelativeDrift']:.5f} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        "",
    ])
    (HERE / "results_table.tex").write_text(content)


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    aggregate, runs = authoritative_results()
    architecture_figure()
    tradeoff_figure(runs)
    metrics_by_dimension(runs)
    error_feedback_figure()
    derived_table(aggregate, runs)
    print(f"Generated {len(list(FIGURES.glob('*.pdf')))} figures for {len(runs)} runs")


if __name__ == "__main__":
    main()
