#!/usr/bin/env python3
"""Generate all VoidToken v5 paper figures and the main results table."""

from __future__ import annotations

import json
import math
from pathlib import Path

from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen import canvas


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIGURES = HERE / "figures"
SELECTION_PATH = ROOT / "real-llm-v5-results" / "selection.json"
HOLDOUT_PATH = ROOT / "real-llm-v5-results" / "holdout.json"
DEVELOPMENT_PATH = ROOT / "real-llm-v5-development" / "manifest.json"

BLUE = HexColor("#2563EB")
ORANGE = HexColor("#EA580C")
GREEN = HexColor("#15803D")
RED = HexColor("#DC2626")
SLATE = HexColor("#475569")
LIGHT = HexColor("#F8FAFC")
GRID = HexColor("#CBD5E1")


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def text(
    drawing: canvas.Canvas,
    x: float,
    y: float,
    value: str,
    *,
    size: float = 8,
    color=black,
    font: str = "Helvetica",
    centered: bool = False,
) -> None:
    drawing.setFillColor(color)
    drawing.setFont(font, size)
    if centered:
        drawing.drawCentredString(x, y, value)
    else:
        drawing.drawString(x, y, value)


def arrow(
    drawing: canvas.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    color=SLATE,
) -> None:
    drawing.setStrokeColor(color)
    drawing.setLineWidth(1.2)
    drawing.line(x1, y1, x2, y2)
    angle = math.atan2(y2 - y1, x2 - x1)
    for delta in (-0.48, 0.48):
        drawing.line(
            x2,
            y2,
            x2 - 6 * math.cos(angle + delta),
            y2 - 6 * math.sin(angle + delta),
        )


def rounded_box(
    drawing: canvas.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    lines: list[str],
    *,
    fill: str,
    border: str = "#64748B",
) -> None:
    drawing.setFillColor(HexColor(fill))
    drawing.setStrokeColor(HexColor(border))
    drawing.setLineWidth(0.8)
    drawing.roundRect(x, y, width, height, 6, fill=1, stroke=1)
    text(
        drawing,
        x + width / 2,
        y + height - 16,
        title,
        size=8,
        font="Helvetica-Bold",
        centered=True,
    )
    for index, line in enumerate(lines):
        text(
            drawing,
            x + width / 2,
            y + height - 29 - 11 * index,
            line,
            size=6.8,
            color=SLATE,
            centered=True,
        )


def protocol_timeline() -> None:
    path = FIGURES / "protocol_timeline.pdf"
    width, height = 690, 146
    drawing = canvas.Canvas(str(path), pagesize=(width, height), invariant=1)
    drawing.setTitle("VoidToken v5 public-freeze evaluation timeline")
    text(
        drawing,
        18,
        127,
        "Data partition and public-freeze chronology",
        size=10,
        font="Helvetica-Bold",
    )
    boxes = [
        (
            14,
            40,
            96,
            70,
            "Development",
            ["validation 0--31", "adaptive", "not prospective"],
            "#F1F5F9",
        ),
        (
            126,
            40,
            96,
            70,
            "Protocol tag",
            ["selection-protocol-v1", "commit 4675388", "config frozen"],
            "#DBEAFE",
        ),
        (
            238,
            40,
            96,
            70,
            "Selection",
            ["validation 32--63", "one-shot acceptance", "PASS"],
            "#DCFCE7",
        ),
        (
            350,
            40,
            96,
            70,
            "Pretest tag",
            ["pretest-v1", "commit 34fbd055", "result public"],
            "#DBEAFE",
        ),
        (
            462,
            40,
            96,
            70,
            "Holdout",
            ["test 384--415", "one-shot execution", "PASS"],
            "#DCFCE7",
        ),
        (
            574,
            40,
            102,
            70,
            "Evidence tag",
            ["evidence-v1", "commit 531e4ab8", "artifacts verified"],
            "#FEF3C7",
        ),
    ]
    for x, y, box_width, box_height, title, lines, fill in boxes:
        rounded_box(
            drawing,
            x,
            y,
            box_width,
            box_height,
            title,
            lines,
            fill=fill,
        )
    for left, right in zip(boxes, boxes[1:]):
        arrow(
            drawing,
            left[0] + left[2] + 2,
            75,
            right[0] - 3,
            75,
        )
    text(
        drawing,
        345,
        18,
        "Reserve test blocks 416--447 were unscored; the runner exposes no reserve mode.",
        size=7.3,
        color=SLATE,
        centered=True,
    )
    drawing.showPage()
    drawing.save()


def codec_pipeline() -> None:
    path = FIGURES / "codec_pipeline.pdf"
    width, height = 690, 168
    drawing = canvas.Canvas(str(path), pagesize=(width, height), invariant=1)
    drawing.setTitle("VoidToken v5 codec and replay pipeline")
    text(
        drawing,
        18,
        149,
        "Complete-container codec and measured replay path",
        size=10,
        font="Helvetica-Bold",
    )
    boxes = [
        (
            15,
            55,
            96,
            70,
            "Canonical cache",
            ["FP32 -> BF16 -> FP32", "24 x [383, 256]", "4,706,304 B/block"],
            "#E2E8F0",
        ),
        (
            128,
            55,
            96,
            70,
            "Rotation",
            ["K and V separate", "normalized WHT", "128-wide groups"],
            "#DBEAFE",
        ),
        (
            241,
            55,
            96,
            70,
            "Quantization",
            ["float16 max-abs scale", "layers 0,8: 9 bit", "others: 8 bit"],
            "#EDE9FE",
        ),
        (
            354,
            55,
            96,
            70,
            "Wire format",
            ["zigzag integers", "canonical zlib-9", "full VTL5 containers"],
            "#FEF3C7",
        ),
        (
            467,
            55,
            96,
            70,
            "Strict parse",
            ["fresh byte entry", "shape/length checks", "all framing counted"],
            "#FFEDD5",
        ),
        (
            580,
            55,
            96,
            70,
            "Model replay",
            ["lossy decoded cache", "128 teacher-forced", "NLL and top-1"],
            "#DCFCE7",
        ),
    ]
    for x, y, box_width, box_height, title, lines, fill in boxes:
        rounded_box(
            drawing,
            x,
            y,
            box_width,
            box_height,
            title,
            lines,
            fill=fill,
        )
    for left, right in zip(boxes, boxes[1:]):
        arrow(
            drawing,
            left[0] + left[2] + 2,
            90,
            right[0] - 3,
            90,
        )
    text(
        drawing,
        345,
        26,
        "Compression ratio = canonical BF16 cache bytes / all serialized VTL5 bytes.",
        size=7.5,
        color=SLATE,
        centered=True,
    )
    drawing.showPage()
    drawing.save()


def axes(
    drawing: canvas.Canvas,
    left: float,
    bottom: float,
    width: float,
    height: float,
    ymin: float,
    ymax: float,
    title: str,
    ylabel: str,
):
    drawing.setStrokeColor(GRID)
    drawing.setLineWidth(0.5)
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = bottom + height * fraction
        drawing.line(left, y, left + width, y)
        value = ymin + (ymax - ymin) * fraction
        text(
            drawing,
            left - 5,
            y - 2,
            f"{value:.3f}",
            size=6.2,
            color=SLATE,
            centered=False,
        )
    drawing.setStrokeColor(SLATE)
    drawing.setLineWidth(0.8)
    drawing.line(left, bottom, left + width, bottom)
    drawing.line(left, bottom, left, bottom + height)
    text(
        drawing,
        left + width / 2,
        bottom + height + 13,
        title,
        size=8.2,
        font="Helvetica-Bold",
        centered=True,
    )
    text(
        drawing,
        left + width / 2,
        bottom - 22,
        "relative block index (1--32)",
        size=6.5,
        color=SLATE,
        centered=True,
    )
    drawing.saveState()
    drawing.translate(left - 34, bottom + height / 2)
    drawing.rotate(90)
    text(
        drawing,
        0,
        0,
        ylabel,
        size=6.5,
        color=SLATE,
        centered=True,
    )
    drawing.restoreState()

    def map_x(index: int, offset: float = 0.0) -> float:
        return left + ((index - 1 + offset) / 31.0) * width

    def map_y(value: float) -> float:
        return bottom + ((value - ymin) / (ymax - ymin)) * height

    return map_x, map_y


def block_metrics(selection: dict, holdout: dict) -> None:
    path = FIGURES / "block_metrics.pdf"
    width, height = 690, 285
    drawing = canvas.Canvas(str(path), pagesize=(width, height), invariant=1)
    drawing.setTitle("Per-block VoidToken v5 evidence")
    text(
        drawing,
        18,
        264,
        "Per-block variability in the two frozen phases",
        size=10,
        font="Helvetica-Bold",
    )
    text(drawing, 482, 264, "selection", size=7.4, color=BLUE)
    drawing.setFillColor(BLUE)
    drawing.circle(472, 267, 2.5, fill=1, stroke=0)
    text(drawing, 575, 264, "holdout", size=7.4, color=ORANGE)
    drawing.setFillColor(ORANGE)
    drawing.circle(565, 267, 2.5, fill=1, stroke=0)

    specs = [
        (54, 52, 164, 175, -0.007, 0.011, "Delta NLL by block", "nat/token"),
        (276, 52, 164, 175, 0.965, 1.001, "Top-1 agreement by block", "agreement"),
        (498, 52, 164, 175, 1.99, 2.065, "Complete-container ratio", "ratio"),
    ]
    fields = [
        "deltaNLLNatPerToken",
        "top1Agreement",
        None,
    ]
    thresholds = [0.01, 0.99, 2.0]

    for spec, field, threshold in zip(specs, fields, thresholds):
        left, bottom, panel_width, panel_height, ymin, ymax, title, ylabel = spec
        map_x, map_y = axes(
            drawing,
            left,
            bottom,
            panel_width,
            panel_height,
            ymin,
            ymax,
            title,
            ylabel,
        )
        drawing.setStrokeColor(RED)
        drawing.setDash(3, 2)
        drawing.line(
            left,
            map_y(threshold),
            left + panel_width,
            map_y(threshold),
        )
        drawing.setDash()
        text(
            drawing,
            left + panel_width - 36,
            map_y(threshold) + 4,
            "gate",
            size=6.2,
            color=RED,
        )
        for phase, color, offset in (
            (selection, BLUE, -0.10),
            (holdout, ORANGE, 0.10),
        ):
            for index, record in enumerate(phase["records"], start=1):
                value = (
                    record[field]
                    if field is not None
                    else record["denseBF16Bytes"] / record["encodedFileBytes"]
                )
                drawing.setFillColor(color)
                drawing.circle(
                    map_x(index, offset),
                    map_y(float(value)),
                    2.0,
                    fill=1,
                    stroke=0,
                )
    text(
        drawing,
        345,
        15,
        "Gate lines are aggregate decision thresholds; individual blocks are shown to expose dispersion.",
        size=7,
        color=SLATE,
        centered=True,
    )
    drawing.showPage()
    drawing.save()


def tex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(character, character) for character in value)


def phase_row(
    name: str,
    role: str,
    values: dict,
    verdict: str,
) -> str:
    return (
        f"{tex_escape(name)} & {tex_escape(role)} & "
        f"{values['compressionRatioVsBF16']:.6f} & "
        f"{values['deltaNLLNatPerToken']:+.7f} & "
        f"{values['blockwiseDeltaNLLUpperOneSided95']:.7f} & "
        f"{100 * values['top1Agreement']:.4f}\\% & "
        f"{100 * values['blockwiseTop1LowerOneSided95']:.4f}\\% & "
        f"{100 * values['wilsonLowerOneSided95']:.4f}\\% & "
        f"{values['meanKLDivergenceNat']:.7f} & "
        f"{tex_escape(verdict)} \\\\"
    )


def results_table(
    development: dict,
    selection: dict,
    holdout: dict,
) -> None:
    development_values = development["combinedObservation"]
    selection_values = {
        **selection["aggregate"],
        **selection["confidence"],
    }
    holdout_values = {
        **holdout["aggregate"],
        **holdout["confidence"],
    }
    rows = [
        phase_row(
            "Development",
            "adaptive; val. 0--31",
            development_values,
            "not prospective",
        ),
        phase_row(
            "Selection",
            "one-shot; val. 32--63",
            selection_values,
            "PASS",
        ),
        phase_row(
            "Holdout",
            "prospective; test 384--415",
            holdout_values,
            "PASS",
        ),
    ]
    output = "\n".join(
        [
            r"\begin{table*}[t]",
            r"\centering",
            r"\caption{Registered phase results. Each phase has 32 blocks and 4,096 teacher-forced predictions. Development was adaptive and is shown only for disclosure; it does not contribute to the prospective verdict. Ratios count every serialized container byte.}",
            r"\label{tab:phase-results}",
            r"\scriptsize",
            r"\setlength{\tabcolsep}{3.1pt}",
            r"\resizebox{\textwidth}{!}{%",
            r"\begin{tabular}{llrrrrrrrrl}",
            r"\toprule",
            r"Phase & Role / blocks & Ratio & $\Delta$NLL & $\Delta$NLL U95 & Top-1 & Block L95 & Wilson L95 & Mean KL & Verdict \\",
            r"\midrule",
            *rows,
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"\end{table*}",
            "",
        ]
    )
    (HERE / "results_table.tex").write_text(output, encoding="ascii")


def main() -> int:
    FIGURES.mkdir(parents=True, exist_ok=True)
    selection = load_json(SELECTION_PATH)
    holdout = load_json(HOLDOUT_PATH)
    development = load_json(DEVELOPMENT_PATH)
    if selection.get("phase") != "selection" or selection.get("pass") is not True:
        raise ValueError("registered selection PASS is missing")
    if holdout.get("phase") != "holdout" or holdout.get("pass") is not True:
        raise ValueError("registered holdout PASS is missing")
    if development.get("status") != "adaptive-development-not-prospective-evidence":
        raise ValueError("development disclosure is missing")
    protocol_timeline()
    codec_pipeline()
    block_metrics(selection, holdout)
    results_table(development, selection, holdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
