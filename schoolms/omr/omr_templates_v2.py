"""
OMR Template Configuration V2
=============================
Grid-based dynamic template generation with calibration support.

Key improvements:
- Dynamic coordinate generation from grid parameters
- Calibration mode for custom sheet layouts
- Separate configs for BECE 60 and Basic 30
- Detection thresholds per template
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Detection Thresholds (per template type)
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "min_fill_ratio": 0.12,
    "strong_fill_ratio": 0.22,
    "min_difference_from_second": 0.06,
    "blank_threshold": 0.08,
    "adaptive_block_size": 21,
    "adaptive_c": 8,
    "roi_shrink_percent": 0.15,
}

BECE_60_THRESHOLDS = {
    "min_fill_ratio": 0.10,  # Slightly more sensitive for BECE
    "strong_fill_ratio": 0.20,
    "min_difference_from_second": 0.05,
    "blank_threshold": 0.06,
    "adaptive_block_size": 21,
    "adaptive_c": 8,
    "roi_shrink_percent": 0.12,  # Smaller shrink for smaller bubbles
}

BASIC_30_THRESHOLDS = {
    "min_fill_ratio": 0.15,  # Higher threshold for larger bubbles
    "strong_fill_ratio": 0.25,
    "min_difference_from_second": 0.08,
    "blank_threshold": 0.10,
    "adaptive_block_size": 21,
    "adaptive_c": 8,
    "roi_shrink_percent": 0.18,
}


# ---------------------------------------------------------------------------
# Template Builders
# ---------------------------------------------------------------------------

def _build_basic_30_ad() -> dict:
    """
    30 Questions, options A–D. Two columns of 15.
    Standard layout for basic assessments.
    """
    ROWS_PER_COL = 15
    ROW_H = 76
    START_Y = 218
    BOX_W, BOX_H = 42, 32
    BOX_Y_OFFSET = 2
    
    # Column configurations with x positions for each option
    col_configs = [
        {
            "x_start": 95,  # First option (A) x position
            "y_start": START_Y,
            "row_height": ROW_H,
            "options_x": {"A": 95, "B": 145, "C": 195, "D": 245}
        },  # Column 1 (Q1–Q15)
        {
            "x_start": 585,
            "y_start": START_Y,
            "row_height": ROW_H,
            "options_x": {"A": 585, "B": 635, "C": 685, "D": 735}
        },  # Column 2 (Q16–Q30)
    ]
    
    # Calculate option width/gap from positions
    opt_positions = list(col_configs[0]["options_x"].values())
    option_width = opt_positions[1] - opt_positions[0] if len(opt_positions) > 1 else 50
    option_gap = option_width - BOX_W
    
    # Generate regions using grid
    regions = _generate_regions_from_grid(
        col_configs=col_configs,
        rows_per_col=ROWS_PER_COL,
        box_w=BOX_W,
        box_h=BOX_H,
        box_y_offset=BOX_Y_OFFSET,
        options=["A", "B", "C", "D"]
    )
    
    return {
        "template_id": "basic_30_ad",
        "name": "30 Questions (A–D)",
        "description": "Basic 30-question sheet with 2 columns (15 questions each), options A-D",
        "total_questions": 30,
        "questions_per_column": ROWS_PER_COL,
        "options": ["A", "B", "C", "D"],
        "columns": 2,
        "image_width": 1000,
        "image_height": 1400,
        
        # Grid parameters
        "column_configs": [
            {"x_start": 95, "y_start": START_Y, "row_height": ROW_H},
            {"x_start": 585, "y_start": START_Y, "row_height": ROW_H},
        ],
        "option_width": option_width,
        "option_gap": option_gap,
        "box_width": BOX_W,
        "box_height": BOX_H,
        
        # Detection thresholds
        **BASIC_30_THRESHOLDS,
        
        # Registration marks (none for basic template)
        "expected_registration_marks": 0,
        
        # Answer regions (for backward compatibility)
        "answer_regions": regions,
        
        # Calibration reference points (for calibration UI)
        "calibration_points": {
            "top_left_answer_area": {"x": 50, "y": 180},
            "bottom_right_answer_area": {"x": 780, "y": 1350},
            "first_row_y": START_Y,
            "last_row_y": START_Y + (ROWS_PER_COL - 1) * ROW_H,
            "option_positions": {"A": 95, "B": 145, "C": 195, "D": 245},
        },
        
        # Camera capture guidance
        "capture_guidance": [
            "Place sheet flat on a dark surface",
            "Ensure all four corners are visible",
            "Fill the camera frame with the sheet",
            "Hold phone parallel to the paper",
            "Use good, even lighting (avoid shadows)",
            "Make sure answer bubbles are clearly visible",
        ],
    }


def _build_bece_60_ae() -> dict:
    """
    60 Questions, options A–E. Three columns of 20.
    BECE (Basic Education Certificate Examination) standard layout.
    Includes timing marks on the right side for alignment.
    """
    ROWS_PER_COL = 20
    ROW_H = 58
    START_Y = 215
    BOX_W, BOX_H = 36, 26
    BOX_Y_OFFSET = 2
    
    # Column configurations
    col_configs = [
        {
            "x_start": 55,
            "y_start": START_Y,
            "row_height": ROW_H,
            "options_x": {"A": 55, "B": 98, "C": 141, "D": 184, "E": 227}
        },   # Column 1 (Q1–Q20)
        {
            "x_start": 385,
            "y_start": START_Y,
            "row_height": ROW_H,
            "options_x": {"A": 385, "B": 428, "C": 471, "D": 514, "E": 557}
        },   # Column 2 (Q21–Q40)
        {
            "x_start": 715,
            "y_start": START_Y,
            "row_height": ROW_H,
            "options_x": {"A": 715, "B": 758, "C": 801, "D": 844, "E": 887}
        },   # Column 3 (Q41–Q60)
    ]
    
    # Calculate option width/gap
    opt_positions = list(col_configs[0]["options_x"].values())
    option_width = opt_positions[1] - opt_positions[0] if len(opt_positions) > 1 else 43
    option_gap = option_width - BOX_W
    
    # Generate regions
    regions = _generate_regions_from_grid(
        col_configs=col_configs,
        rows_per_col=ROWS_PER_COL,
        box_w=BOX_W,
        box_h=BOX_H,
        box_y_offset=BOX_Y_OFFSET,
        options=["A", "B", "C", "D", "E"]
    )
    
    return {
        "template_id": "bece_60_ae",
        "name": "60 Questions (A–E) - BECE",
        "description": "BECE standard 60-question sheet with 3 columns (20 questions each), options A-E, includes timing marks",
        "total_questions": 60,
        "questions_per_column": ROWS_PER_COL,
        "options": ["A", "B", "C", "D", "E"],
        "columns": 3,
        "image_width": 1000,
        "image_height": 1400,
        
        # Grid parameters
        "column_configs": [
            {"x_start": 55, "y_start": START_Y, "row_height": ROW_H},
            {"x_start": 385, "y_start": START_Y, "row_height": ROW_H},
            {"x_start": 715, "y_start": START_Y, "row_height": ROW_H},
        ],
        "option_width": option_width,
        "option_gap": option_gap,
        "box_width": BOX_W,
        "box_height": BOX_H,
        
        # Detection thresholds optimized for BECE sheets
        **BECE_60_THRESHOLDS,
        
        # Registration marks (timing marks on right side)
        "expected_registration_marks": 20,  # One per row typically
        "registration_marks_region": {"x_start": 0.80, "x_end": 0.98, "y_start": 0.15, "y_end": 0.95},
        
        # Answer regions
        "answer_regions": regions,
        
        # Calibration reference points
        "calibration_points": {
            "top_left_answer_area": {"x": 20, "y": 180},
            "bottom_right_answer_area": {"x": 940, "y": 1380},
            "first_row_y": START_Y,
            "last_row_y": START_Y + (ROWS_PER_COL - 1) * ROW_H,
            "option_positions": {"A": 55, "B": 98, "C": 141, "D": 184, "E": 227},
        },
        
        # Camera capture guidance specific to BECE
        "capture_guidance": [
            "Place BECE sheet flat on a dark surface",
            "Ensure timing marks (right side) are clearly visible",
            "All four corners of the sheet must be in frame",
            "Hold phone directly above, parallel to the paper",
            "Use bright, even lighting (avoid shadows on bubbles)",
            "Check that pink/black timing bars on right are visible",
            "Avoid folded, curled, or wrinkled sheets",
            "For best results, use a dark background",
        ],
        
        # Quality requirements
        "min_coverage_ratio": 0.70,  # Require at least 70% confident detections
        "min_registration_marks": 14,  # At least 14 of 20 timing marks should be visible
    }


def _generate_regions_from_grid(
    col_configs: list,
    rows_per_col: int,
    box_w: int,
    box_h: int,
    box_y_offset: int,
    options: list[str]
) -> list[dict]:
    """Generate answer region coordinates from column configurations."""
    regions = []
    
    for col_idx, col in enumerate(col_configs):
        options_x = col.get("options_x", {})
        
        for row in range(rows_per_col):
            q_num = col_idx * rows_per_col + row + 1
            y = col["y_start"] + row * col["row_height"] + box_y_offset
            
            boxes = {}
            for opt in options:
                x = options_x.get(opt, col["x_start"])
                boxes[opt] = {"x": x, "y": y, "w": box_w, "h": box_h}
            
            regions.append({"question": q_num, "boxes": boxes})
    
    regions.sort(key=lambda r: r["question"])
    return regions


# ---------------------------------------------------------------------------
# Template Registry
# ---------------------------------------------------------------------------

TEMPLATE_REGISTRY: dict[str, dict] = {
    "basic_30_ad": _build_basic_30_ad(),
    "bece_60_ae": _build_bece_60_ae(),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_template(template_id: str) -> dict | None:
    """Get template configuration by ID."""
    return TEMPLATE_REGISTRY.get(template_id)


def get_template_choices() -> list[tuple[str, str]]:
    """Get template choices for form dropdowns."""
    return [(k, v["name"]) for k, v in TEMPLATE_REGISTRY.items()]


def list_templates() -> list[dict]:
    """List all templates with basic info."""
    return [
        {
            "template_id": k,
            "name": v["name"],
            "description": v.get("description", ""),
            "total_questions": v["total_questions"],
            "options": v["options"],
            "columns": v.get("columns", 1),
            "capture_guidance": v.get("capture_guidance", []),
        }
        for k, v in TEMPLATE_REGISTRY.items()
    ]


def get_template_with_regions(template_id: str) -> dict | None:
    """Get template with dynamically generated answer regions."""
    template = TEMPLATE_REGISTRY.get(template_id)
    if not template:
        return None
    
    # Regenerate regions from grid (ensures consistency)
    from .omr_processor_v2 import generate_answer_regions_from_grid, build_grid_config_from_template
    
    grid = build_grid_config_from_template(template)
    regions = generate_answer_regions_from_grid(grid)
    
    # Return copy with updated regions
    result = template.copy()
    result["answer_regions"] = regions
    return result


def get_detection_thresholds(template_id: str) -> dict:
    """Get detection thresholds for a template."""
    template = TEMPLATE_REGISTRY.get(template_id)
    if not template:
        return DEFAULT_THRESHOLDS.copy()
    
    return {
        "min_fill_ratio": template.get("min_fill_ratio", DEFAULT_THRESHOLDS["min_fill_ratio"]),
        "strong_fill_ratio": template.get("strong_fill_ratio", DEFAULT_THRESHOLDS["strong_fill_ratio"]),
        "min_difference_from_second": template.get("min_difference_from_second", DEFAULT_THRESHOLDS["min_difference_from_second"]),
        "blank_threshold": template.get("blank_threshold", DEFAULT_THRESHOLDS["blank_threshold"]),
        "adaptive_block_size": template.get("adaptive_block_size", DEFAULT_THRESHOLDS["adaptive_block_size"]),
        "adaptive_c": template.get("adaptive_c", DEFAULT_THRESHOLDS["adaptive_c"]),
        "roi_shrink_percent": template.get("roi_shrink_percent", DEFAULT_THRESHOLDS["roi_shrink_percent"]),
    }


def get_calibration_points(template_id: str) -> dict | None:
    """Get calibration reference points for a template."""
    template = TEMPLATE_REGISTRY.get(template_id)
    if template:
        return template.get("calibration_points")
    return None


def get_capture_guidance(template_id: str) -> list[str]:
    """Get camera capture guidance for a template."""
    template = TEMPLATE_REGISTRY.get(template_id)
    if template:
        return template.get("capture_guidance", [])
    return [
        "Place sheet flat on a dark surface",
        "Ensure all corners are visible",
        "Hold camera parallel to the paper",
        "Use good, even lighting",
    ]


# ---------------------------------------------------------------------------
# Template Calibration
# ---------------------------------------------------------------------------

def build_template_from_calibration(
    template_id: str,
    reference_image_size: tuple[int, int],
    calibration_data: dict
) -> dict:
    """
    Build a custom template configuration from calibration data.
    
    calibration_data format:
    {
        "columns": [
            {
                "x_start": int,
                "y_start": int,
                "row_height": int,
                "options_x": {"A": int, "B": int, ...}
            },
            ...
        ],
        "questions_per_column": int,
        "options": ["A", "B", "C", "D", "E"],
        "box_width": int,
        "box_height": int,
    }
    """
    base_template = TEMPLATE_REGISTRY.get(template_id)
    
    width, height = reference_image_size
    questions_per_col = calibration_data.get("questions_per_column", 20)
    options = calibration_data.get("options", ["A", "B", "C", "D", "E"])
    box_w = calibration_data.get("box_width", 36)
    box_h = calibration_data.get("box_height", 26)
    
    col_configs = calibration_data.get("columns", [])
    
    # Generate regions from calibrated columns
    regions = []
    for col_idx, col in enumerate(col_configs):
        options_x = col.get("options_x", {})
        
        for row in range(questions_per_col):
            q_num = col_idx * questions_per_col + row + 1
            y = col["y_start"] + row * col["row_height"]
            
            boxes = {}
            for opt in options:
                x = options_x.get(opt, col["x_start"])
                boxes[opt] = {"x": x, "y": y, "w": box_w, "h": box_h}
            
            regions.append({"question": q_num, "boxes": boxes})
    
    regions.sort(key=lambda r: r["question"])
    
    # Calculate grid parameters
    column_configs = [
        {
            "x_start": col["x_start"],
            "y_start": col["y_start"],
            "row_height": col["row_height"],
        }
        for col in col_configs
    ]
    
    # Calculate option width/gap
    if col_configs and options:
        first_col = col_configs[0]
        options_x = first_col.get("options_x", {})
        if len(options) >= 2 and options[0] in options_x and options[1] in options_x:
            option_width = options_x[options[1]] - options_x[options[0]]
            option_gap = option_width - box_w
        else:
            option_width = 43
            option_gap = 7
    else:
        option_width = 43
        option_gap = 7
    
    total_questions = len(col_configs) * questions_per_col
    
    return {
        "template_id": f"{template_id}_custom",
        "name": f"Custom {base_template['name'] if base_template else 'Template'}",
        "description": "User-calibrated custom template",
        "total_questions": total_questions,
        "questions_per_column": questions_per_col,
        "options": options,
        "columns": len(col_configs),
        "image_width": width,
        "image_height": height,
        "column_configs": column_configs,
        "option_width": option_width,
        "option_gap": option_gap,
        "box_width": box_w,
        "box_height": box_h,
        "answer_regions": regions,
        "calibrated": True,
        "calibration_source": template_id,
    }
    
    # Merge threshold config based on number of options
    threshold_config = BECE_60_THRESHOLDS if len(options) == 5 else BASIC_30_THRESHOLDS
    result.update(threshold_config)
