"""
OMR template resolution: built-in registry + per-school calibration overlay.
"""

from __future__ import annotations

import copy
from typing import Any

from .models import OmrTemplateCalibration
from .omr_templates_v2 import get_template, get_template_with_regions


def normalize_template_dict(tmpl: dict) -> dict:
    """Ensure pipeline keys exist (aliases from legacy v2 names)."""
    out = copy.deepcopy(tmpl)
    out.setdefault("min_mark_area_ratio", out.get("min_fill_ratio", 0.08))
    out.setdefault("strong_mark_area_ratio", out.get("strong_fill_ratio", 0.16))
    out.setdefault("min_gap_from_second", out.get("min_difference_from_second", 0.05))
    out.setdefault("uncertainty_gap", out.get("min_gap_from_second", 0.05) * 0.85)
    out.setdefault("inner_zone_ratio", 0.42)
    out.setdefault("option_box_width", out.get("box_width", 36))
    out.setdefault("option_box_height", out.get("box_height", 26))
    out.setdefault("row_start_y", (out.get("column_configs") or [{}])[0].get("y_start"))
    return out


def get_processing_template(school: Any, template_id: str) -> dict | None:
    """
    Merge built-in template with optional school calibration and blank image path.
    """
    base = get_template_with_regions(template_id) or get_template(template_id)
    if not base:
        return None
    merged = normalize_template_dict(base)
    cal = (
        OmrTemplateCalibration.objects.filter(school=school, template_id=template_id)
        .order_by("-updated_at")
        .first()
    )
    if not cal:
        return merged

    cfg = cal.calibrated_config or {}
    if cfg:
        merged.update(cfg)
    if cal.blank_sheet:
        try:
            merged["blank_template_path"] = cal.blank_sheet.path
        except Exception:
            merged["blank_template_image_url"] = cal.blank_sheet.url
    merged = normalize_template_dict(merged)
    if cfg.get("answer_regions"):
        merged["answer_regions"] = cfg["answer_regions"]
    elif cfg.get("column_configs"):
        merged["force_rebuild_grid"] = True
        from .pipeline import build_answer_regions

        merged["answer_regions"] = build_answer_regions(merged)
    return merged
