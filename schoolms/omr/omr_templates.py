"""
OMR Template Configuration
==========================
Each template defines the layout of a printable answer sheet.
To add a new template:
  1. Define a function _build_<template_id>() returning the config dict.
  2. Register it in TEMPLATE_REGISTRY.
  3. Add a choice entry in models.TEMPLATE_CHOICES.

Coordinate system: (0, 0) is top-left of the normalised image.
image_width × image_height is the standard size the image is resized to
before bubble detection.  Coordinates must match the printed sheet.
"""

from __future__ import annotations


def _build_basic_30_ad() -> dict:
    """30 Questions, options A–D. Two columns of 15."""
    ROWS_PER_COL = 15
    ROW_H = 76
    START_Y = 218
    BOX_W, BOX_H = 42, 32
    BOX_Y_OFFSET = 2

    col_configs = [
        {"A": 95, "B": 145, "C": 195, "D": 245},  # Column 1 (Q1–Q15)
        {"A": 585, "B": 635, "C": 685, "D": 735},  # Column 2 (Q16–Q30)
    ]

    regions = []
    for col_idx, col_opts in enumerate(col_configs):
        for row in range(ROWS_PER_COL):
            q_num = col_idx * ROWS_PER_COL + row + 1
            y = START_Y + row * ROW_H
            boxes = {
                opt: {"x": x, "y": y + BOX_Y_OFFSET, "w": BOX_W, "h": BOX_H}
                for opt, x in col_opts.items()
            }
            regions.append({"question": q_num, "boxes": boxes})

    regions.sort(key=lambda r: r["question"])
    return {
        "template_id": "basic_30_ad",
        "name": "30 Questions (A–D)",
        "total_questions": 30,
        "options": ["A", "B", "C", "D"],
        "image_width": 1000,
        "image_height": 1400,
        "fill_threshold": 0.35,
        "uncertain_threshold": 0.15,
        "answer_regions": regions,
    }


def _build_bece_60_ae() -> dict:
    """60 Questions, options A–E. Three columns of 20."""
    ROWS_PER_COL = 20
    ROW_H = 58
    START_Y = 215
    BOX_W, BOX_H = 36, 26
    BOX_Y_OFFSET = 2

    col_configs = [
        {"A": 55,  "B": 98,  "C": 141, "D": 184, "E": 227},   # Column 1 (Q1–Q20)
        {"A": 385, "B": 428, "C": 471, "D": 514, "E": 557},   # Column 2 (Q21–Q40)
        {"A": 715, "B": 758, "C": 801, "D": 844, "E": 887},   # Column 3 (Q41–Q60)
    ]

    regions = []
    for col_idx, col_opts in enumerate(col_configs):
        for row in range(ROWS_PER_COL):
            q_num = col_idx * ROWS_PER_COL + row + 1
            y = START_Y + row * ROW_H
            boxes = {
                opt: {"x": x, "y": y + BOX_Y_OFFSET, "w": BOX_W, "h": BOX_H}
                for opt, x in col_opts.items()
            }
            regions.append({"question": q_num, "boxes": boxes})

    regions.sort(key=lambda r: r["question"])
    return {
        "template_id": "bece_60_ae",
        "name": "60 Questions (A–E)",
        "total_questions": 60,
        "options": ["A", "B", "C", "D", "E"],
        "image_width": 1000,
        "image_height": 1400,
        "fill_threshold": 0.35,
        "uncertain_threshold": 0.15,
        "answer_regions": regions,
    }


TEMPLATE_REGISTRY: dict[str, dict] = {
    "basic_30_ad": _build_basic_30_ad(),
    "bece_60_ae": _build_bece_60_ae(),
}


def get_template(template_id: str) -> dict | None:
    return TEMPLATE_REGISTRY.get(template_id)


def get_template_choices() -> list[tuple[str, str]]:
    return [(k, v["name"]) for k, v in TEMPLATE_REGISTRY.items()]


def list_templates() -> list[dict]:
    return [
        {
            "template_id": k,
            "name": v["name"],
            "total_questions": v["total_questions"],
            "options": v["options"],
        }
        for k, v in TEMPLATE_REGISTRY.items()
    ]
