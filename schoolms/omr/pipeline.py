"""
Production OMR scan pipeline
===========================
Perspective correction, optional blank-template subtraction, inner ROI crops,
connected-component mark scoring, and confidence / review-oriented outputs.

Never uses raw darkness alone on the original sheet: detection runs on
difference image (blank-subtracted or high-frequency fallback) with CC analysis.

Coloured print (e.g. magenta) is lightened in Lab space before grayscale so
pencil marks separate better. Per-column **vertical and horizontal** integer shift
search refines bubble alignment on slightly mis-warped phone photos (wrong letter
on the same row is often horizontal drift).

Each question’s decision uses scores from **that question’s bubbles only**:
the quiet baseline is the mean of the two lowest cells; the chosen letter must
clear that baseline by ``min_lift_from_baseline`` as well as beat the runner-up
by ``min_gap``—so we do not infer a shade from global thresholds alone.

Marginal-quality scans optionally get CLAHE + unsharp on warped grayscale before
differencing. Optional bubble ROI PNG export supports QA and future lightweight
models (see ``OMR_EXPORT_BUBBLE_ROIS`` / template ``export_bubble_rois``).
"""

from __future__ import annotations

import io
import os
import uuid
from typing import Any

from django.conf import settings as django_settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


QUALITY_REJECT_MESSAGE = (
    "Image quality is too low for automatic reading (extreme blur, darkness, or tilt). "
    "Please retake the photo with the sheet flat, well-lit, and facing the camera squarely. "
    "If it still fails, use “Enter Manually” on the upload page."
)

CAPTURE_GUIDANCE_LINES = [
    "Place the sheet flat on a plain background.",
    "Use bright, even light; avoid shadows.",
    "Hold the phone parallel to the paper.",
    "Fill the frame with the paper; keep all four corners visible.",
    "Avoid folded, curved, or wrinkled sheets.",
    "Use a dark pen or firm pencil; light marks are harder to detect.",
    "After upload, always review yellow-flagged questions before saving.",
]


def _deprint_lighten_bgr(bgr: np.ndarray, strength: float = 0.42) -> np.ndarray:
    """Lighten high-chroma (magenta/red) print in Lab space; graphite stays mostly neutral.

    Phone photos of coloured OMR sheets often confuse printed ink with pencil in
    grayscale differencing. Boosting L where chroma is high makes print cancel
    better in blank-subtracted images while low-chroma pencil marks remain.
    """
    if bgr is None or bgr.size == 0 or strength <= 0:
        return bgr
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    L, a, b = cv2.split(lab)
    af = a.astype(np.float32) - 128.0
    bf = b.astype(np.float32) - 128.0
    chroma = np.sqrt(af * af + bf * bf)
    lift = float(strength) * np.clip(chroma / 38.0, 0.0, 2.8)
    L2 = np.clip(L.astype(np.float32) + lift, 0, 255).astype(np.uint8)
    out = cv2.merge([L2, a, b])
    return cv2.cvtColor(out, cv2.COLOR_LAB2BGR)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def _order_points(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _perspective_transform(
    image: np.ndarray, pts: np.ndarray, target_w: int, target_h: int
) -> np.ndarray:
    rect = _order_points(pts)
    dst = np.array(
        [[0, 0], [target_w - 1, 0], [target_w - 1, target_h - 1], [0, target_h - 1]],
        dtype="float32",
    )
    m = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(
        image, m, (target_w, target_h), borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255)
    )


def _detect_document_contour(gray: np.ndarray) -> tuple[np.ndarray | None, dict]:
    debug = {"method": "contour", "success": False}
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edged = cv2.dilate(edged, kernel, iterations=2)
    edged = cv2.erode(edged, kernel, iterations=1)
    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, debug
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:8]
    h, w = gray.shape
    image_area = float(h * w)
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            area = cv2.contourArea(approx)
            ratio = area / image_area
            if 0.22 < ratio < 0.96:
                pts = approx.reshape(4, 2).astype("float32")
                debug["success"] = True
                debug["area_ratio"] = ratio
                return pts, debug
    return None, debug


def _refine_corners_from_markers(
    gray: np.ndarray, margin_ratio: float = 0.12
) -> np.ndarray | None:
    """
    Find four corner fiducials as the largest dark blob in each corner patch.
    Returns 4x2 float32 points in image coordinates, or None.
    """
    h, w = gray.shape[:2]
    mx = int(max(8, margin_ratio * w))
    my = int(max(8, margin_ratio * h))
    patches = [
        gray[0:my, 0:mx],
        gray[0:my, w - mx : w],
        gray[h - my : h, w - mx : w],
        gray[h - my : h, 0:mx],
    ]
    corners = []
    for pi, patch in enumerate(patches):
        if patch.size < 50:
            return None
        _, th = cv2.threshold(patch, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        c = max(contours, key=cv2.contourArea)
        if cv2.contourArea(c) < 20:
            return None
        m = cv2.moments(c)
        if m["m00"] == 0:
            return None
        cx = m["m10"] / m["m00"]
        cy = m["m01"] / m["m00"]
        if pi == 0:
            corners.append((cx, cy))
        elif pi == 1:
            corners.append((w - mx + cx, cy))
        elif pi == 2:
            corners.append((w - mx + cx, h - my + cy))
        else:
            corners.append((cx, h - my + cy))
    return np.array(corners, dtype="float32")


def _corner_markers_plausible(pts: np.ndarray, w: int, h: int) -> bool:
    """True if ordered fiducial centers sit in the expected quadrants (inset from edges)."""
    if pts is None or pts.shape != (4, 2):
        return False
    tl, tr, br, bl = _order_points(pts)
    return bool(
        tl[0] < w * 0.4
        and tl[1] < h * 0.4
        and tr[0] > w * 0.6
        and tr[1] < h * 0.4
        and br[0] > w * 0.6
        and br[1] > h * 0.6
        and bl[0] < w * 0.4
        and bl[1] > h * 0.6
    )


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

def assess_capture_quality(
    gray: np.ndarray,
    contour_pts: np.ndarray | None,
    template_config: dict | None = None,
) -> dict[str, Any]:
    """Return metrics, warnings, ``reject`` (hard block only), ``marginal`` (process but review harder)."""
    metrics: dict[str, float] = {}
    warnings: list[str] = []
    reject_hard = False
    marginal = False
    h, w = gray.shape[:2]
    template_config = template_config or {}

    lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    metrics["laplacian_variance"] = lap
    mean_b = float(np.mean(gray))
    metrics["mean_brightness"] = mean_b
    std_b = float(np.std(gray))
    metrics["contrast"] = std_b

    if lap < 38.0:
        warnings.append("Image is extremely blurry; automatic reading may fail.")
        reject_hard = True
    elif lap < 68.0:
        marginal = True
        warnings.append("Image appears soft (typical for some phone cameras); review flagged answers.")

    if mean_b < 40.0:
        warnings.append("Image is very dark.")
        reject_hard = True
    elif mean_b < 52.0:
        marginal = True
        warnings.append("Image is somewhat dark; marks may be harder to separate from print.")
    elif mean_b > 249.0:
        marginal = True
        warnings.append("Image may be overexposed; glare can hide pencil marks.")

    blur_bg = cv2.GaussianBlur(gray.astype(np.float32), (101, 101), 0)
    residual = np.abs(gray.astype(np.float32) - blur_bg)
    shadow_score = float(np.mean(residual))
    metrics["shadow_level"] = shadow_score
    if shadow_score > 38.0:
        warnings.append("Uneven lighting or strong shadows detected.")
        marginal = True

    coverage = 0.0
    tilt = 0.0
    if contour_pts is not None:
        coverage = float(cv2.contourArea(contour_pts) / (h * w))
        rect = cv2.minAreaRect(contour_pts)
        tilt = float(rect[2])
        metrics["paper_coverage_ratio"] = coverage
        metrics["tilt_angle_deg"] = tilt
        if coverage < 0.24:
            warnings.append("The sheet fills very little of the frame.")
            reject_hard = True
        elif coverage < 0.36:
            marginal = True
            warnings.append("The sheet does not fill much of the frame; alignment may be off.")
        if abs(tilt) > 16.0:
            warnings.append("The sheet appears tilted; keep the camera parallel to the paper.")
        if abs(tilt) > 44.0:
            reject_hard = True
        elif abs(tilt) > 22.0:
            marginal = True
    else:
        warnings.append(
            "Could not detect paper borders; using a centered crop — check results carefully."
        )
        marginal = True
        metrics["paper_coverage_ratio"] = 0.0

    markers_ok = True
    if template_config.get("require_corner_markers"):
        refined = _refine_corners_from_markers(gray)
        markers_ok = refined is not None
        if not markers_ok:
            warnings.append("Not all four corner markers are clearly visible.")
            if template_config.get("sheet_design") == "generated":
                reject_hard = True

    return {
        "metrics": metrics,
        "warnings": warnings,
        "reject": reject_hard,
        "marginal": marginal,
        "markers_ok": markers_ok,
        "pass_soft": not reject_hard and not marginal,
    }


# ---------------------------------------------------------------------------
# Template grid
# ---------------------------------------------------------------------------

def build_answer_regions(template_config: dict) -> list[dict]:
    """Build answer regions from column_configs + grid params (matches v2 layout)."""
    cols = template_config.get("column_configs") or []
    qpc = int(template_config.get("questions_per_column", 20))
    options = template_config.get("options", ["A", "B", "C", "D"])
    box_w = int(template_config.get("box_width", template_config.get("option_box_width", 36)))
    box_h = int(template_config.get("box_height", template_config.get("option_box_height", 26)))
    opt_w = float(template_config.get("option_width", 43))
    opt_gap = float(template_config.get("option_gap", 7))
    box_y_off = int(template_config.get("box_y_offset", 2))

    if template_config.get("answer_regions") and not template_config.get("force_rebuild_grid"):
        return template_config["answer_regions"]

    regions = []
    for col_idx, col in enumerate(cols):
        x0 = int(col["x_start"])
        y0 = int(col["y_start"])
        rh = int(col["row_height"])
        for row in range(qpc):
            qn = col_idx * qpc + row + 1
            y = y0 + row * rh + box_y_off
            boxes = {}
            for oi, opt in enumerate(options):
                x = int(round(x0 + oi * (opt_w + opt_gap)))
                boxes[opt] = {"x": x, "y": y, "w": box_w, "h": box_h}
            regions.append({"question": qn, "boxes": boxes})
    regions.sort(key=lambda r: r["question"])
    return regions


def _inner_roi_rect(
    x: int, y: int, w: int, h: int, inner_ratio: float, im_w: int, im_h: int
) -> tuple[int, int, int, int]:
    """Crop a smaller inner zone (fraction of min side retained)."""
    r = float(inner_ratio)
    r = max(0.25, min(0.75, r))
    nw = max(4, int(w * r))
    nh = max(4, int(h * r))
    cx = x + w // 2
    cy = y + h // 2
    nx = cx - nw // 2
    ny = cy - nh // 2
    nx = max(0, min(nx, im_w - nw))
    ny = max(0, min(ny, im_h - nh))
    return nx, ny, nw, nh


def _infer_questions_per_column(cfg: dict, regions: list) -> int:
    qpc = cfg.get("questions_per_column")
    if qpc is not None:
        qpc_i = int(qpc)
        if qpc_i > 0:
            return qpc_i
    n = len(regions)
    if n <= 0:
        return 20
    tid = str(cfg.get("template_id", ""))
    if "30" in tid or n == 30:
        return 15
    return 20


def _partition_regions_by_column(regions: list, qpc: int) -> dict[int, list]:
    """Map column index -> list of region dicts (same order as regions)."""
    cols: dict[int, list] = {}
    for region in regions:
        qn = int(region["question"])
        c = (qn - 1) // max(1, qpc)
        cols.setdefault(c, []).append(region)
    return cols


def _refine_column_vertical_shifts(
    diff_gray: np.ndarray,
    regions_by_column: dict[int, list],
    inner_ratio: float,
    im_w: int,
    im_h: int,
    dy_max: int = 5,
) -> dict[int, int]:
    """Pick integer dy per column that maximizes separation between strongest bubbles."""
    shifts: dict[int, int] = {}
    for col_idx, col_regions in regions_by_column.items():
        best_dy = 0
        best_score = -1e9
        for dy in range(-dy_max, dy_max + 1):
            col_score = 0.0
            for region in col_regions:
                scores: list[float] = []
                for _opt, box in region["boxes"].items():
                    x, y, bw, bh = int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"])
                    y = y + dy
                    x = max(0, min(x, im_w - 1))
                    y = max(0, min(y, im_h - 1))
                    bw = max(1, min(bw, im_w - x))
                    bh = max(1, min(bh, im_h - y))
                    ix, iy, iw, ih = _inner_roi_rect(x, y, bw, bh, inner_ratio, im_w, im_h)
                    roi = diff_gray[iy : iy + ih, ix : ix + iw]
                    scores.append(_score_mark_in_diff_roi(roi)["mark_score"])
                scores.sort(reverse=True)
                if len(scores) >= 2:
                    col_score += scores[0] - scores[1]
                elif scores:
                    col_score += scores[0]
            if col_score > best_score:
                best_score = col_score
                best_dy = dy
        shifts[col_idx] = best_dy
    return shifts


def _refine_column_horizontal_shifts(
    diff_gray: np.ndarray,
    regions_by_column: dict[int, list],
    inner_ratio: float,
    im_w: int,
    im_h: int,
    col_dy: dict[int, int],
    dx_max: int = 4,
) -> dict[int, int]:
    """Pick integer dx per column after vertical dy — reduces wrong-letter (e.g. B vs E) drift."""
    shifts: dict[int, int] = {}
    for col_idx, col_regions in regions_by_column.items():
        row_dy = int(col_dy.get(col_idx, 0))
        best_dx = 0
        best_score = -1e9
        for dx in range(-dx_max, dx_max + 1):
            col_score = 0.0
            for region in col_regions:
                scores: list[float] = []
                for _opt, box in region["boxes"].items():
                    x, y, bw, bh = int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"])
                    x, y = x + dx, y + row_dy
                    x = max(0, min(x, im_w - 1))
                    y = max(0, min(y, im_h - 1))
                    bw = max(1, min(bw, im_w - x))
                    bh = max(1, min(bh, im_h - y))
                    ix, iy, iw, ih = _inner_roi_rect(x, y, bw, bh, inner_ratio, im_w, im_h)
                    roi = diff_gray[iy : iy + ih, ix : ix + iw]
                    scores.append(_score_mark_in_diff_roi(roi)["mark_score"])
                scores.sort(reverse=True)
                if len(scores) >= 2:
                    col_score += scores[0] - scores[1]
                elif scores:
                    col_score += scores[0]
            if col_score > best_score:
                best_score = col_score
                best_dx = dx
        shifts[col_idx] = best_dx
    return shifts


# ---------------------------------------------------------------------------
# Blank subtraction & alignment
# ---------------------------------------------------------------------------

def _align_gray_ecc(moving: np.ndarray, fixed: np.ndarray) -> np.ndarray:
    """Affine-align moving to fixed using ECC; returns same shape as moving."""
    if moving.shape != fixed.shape:
        moving = cv2.resize(moving, (fixed.shape[1], fixed.shape[0]))
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5)
        _, warp = cv2.findTransformECC(
            fixed.astype(np.float32),
            moving.astype(np.float32),
            warp,
            cv2.MOTION_AFFINE,
            criteria,
            None,
            5,
        )
        aligned = cv2.warpAffine(
            moving,
            warp,
            (fixed.shape[1], fixed.shape[0]),
            flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return aligned
    except cv2.error:
        return moving


def _difference_image(marked_gray: np.ndarray, blank_gray: np.ndarray | None) -> tuple[np.ndarray, bool]:
    """
    Build a non-negative difference image where **new marks** (darker than blank)
    show as **bright** pixels: max(0, blank - marked), aligned to marked.
    Returns (diff_u8, used_blank).
    """
    if blank_gray is not None:
        if blank_gray.shape != marked_gray.shape:
            blank_gray = cv2.resize(blank_gray, (marked_gray.shape[1], marked_gray.shape[0]))
        blank_a = _align_gray_ecc(blank_gray, marked_gray)
        d = blank_a.astype(np.float32) - marked_gray.astype(np.float32)
        d = np.clip(d, 0, 255).astype(np.uint8)
        d = cv2.normalize(d, None, 0, 255, cv2.NORM_MINMAX)
        return d, True
    # Fallback: high-frequency residual — not as reliable as blank subtraction
    bg = cv2.GaussianBlur(marked_gray, (0, 0), sigmaX=2.2, sigmaY=2.2)
    hi = cv2.absdiff(marked_gray, bg.astype(np.uint8))
    hi = cv2.normalize(hi, None, 0, 255, cv2.NORM_MINMAX)
    return hi, False


# ---------------------------------------------------------------------------
# Connected-component mark scoring (on difference ROI)
# ---------------------------------------------------------------------------

def _score_mark_in_diff_roi(diff_roi: np.ndarray, min_area_px: int = 8) -> dict[str, float]:
    """
    Score a single option cell using connected components on the difference ROI.
    Ignores long thin components (table lines).
    """
    if diff_roi.size == 0:
        return {"mark_score": 0.0, "area_ratio": 0.0, "mean_diff": 0.0, "shape": 0.0}

    roi_area = float(diff_roi.shape[0] * diff_roi.shape[1])
    _, binary = cv2.threshold(diff_roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

    num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    best_score = 0.0
    best_meta = {"area_ratio": 0.0, "mean_diff": 0.0, "shape": 0.0}

    for i in range(1, num):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < min_area_px:
            continue
        w = int(stats[i, cv2.CC_STAT_WIDTH])
        h = int(stats[i, cv2.CC_STAT_HEIGHT])
        if w <= 0 or h <= 0:
            continue
        ar = max(w / float(h), h / float(w))
        if ar > 14.0:
            continue
        extent = area / float(w * h)
        if extent < 0.08:
            continue
        mask = (labels == i).astype(np.uint8)
        comp_pts = cv2.findNonZero(mask)
        if comp_pts is None:
            continue
        hull = cv2.convexHull(comp_pts)
        hull_area = float(cv2.contourArea(hull)) if hull is not None else area
        solidity = area / hull_area if hull_area > 1e-6 else 0.0
        if solidity < 0.35:
            continue
        mean_d = float(np.mean(diff_roi[mask.astype(bool)])) / 255.0
        area_ratio = area / roi_area
        shape = min(1.0, solidity) * min(1.0, extent * 1.8)
        mark = 0.48 * area_ratio + 0.34 * mean_d + 0.18 * shape
        if mark > best_score:
            best_score = mark
            best_meta = {"area_ratio": area_ratio, "mean_diff": mean_d, "shape": shape}

    return {
        "mark_score": float(round(best_score, 5)),
        "area_ratio": float(best_meta["area_ratio"]),
        "mean_diff": float(best_meta["mean_diff"]),
        "shape": float(best_meta["shape"]),
    }


def _decide_option_scores(
    option_scores: dict[str, float],
    min_mark: float,
    strong_mark: float,
    min_gap: float,
    *,
    min_lift_from_baseline: float = 0.032,
) -> tuple[str, str, str, float, float, float]:
    """
    Returns (answer, status, confidence_level, confidence_scalar, baseline, lift).

    ``baseline`` is the mean of the two lowest option scores on this question only
    (empirical “unmarked” level for that row). ``lift`` is top score minus baseline.
    A detection requires sufficient lift so we are not guessing from global
    thresholds alone.
    """
    items = sorted(option_scores.items(), key=lambda t: t[1], reverse=True)
    if not items:
        return "blank", "blank", "low", 0.0, 0.0, 0.0
    vals_asc = sorted(option_scores.values())
    if len(vals_asc) >= 2:
        baseline = float(vals_asc[0] + vals_asc[1]) / 2.0
    else:
        baseline = float(vals_asc[0])
    top_l, top_s = items[0]
    second_s = items[1][1] if len(items) > 1 else 0.0
    gap = top_s - second_s
    lift = top_s - baseline
    strong_opts = [k for k, v in items if v >= strong_mark]

    if len(strong_opts) >= 2:
        return "multiple", "multiple", "low", round(top_s, 4), baseline, lift
    if top_s < min_mark:
        return "blank", "blank", "high" if top_s < min_mark * 0.5 else "medium", round(top_s, 4), baseline, lift
    if min_lift_from_baseline > 0 and lift < min_lift_from_baseline:
        return "uncertain", "uncertain", "low", round(top_s, 4), baseline, lift
    if gap < min_gap:
        return "uncertain", "uncertain", "low", round(top_s, 4), baseline, lift
    conf = "high" if top_s >= strong_mark and gap >= min_gap * 1.35 else "medium"
    return top_l, "detected", conf, round(top_s, 4), baseline, lift


def _enhance_gray_marginal_capture(gray: np.ndarray, cfg: dict) -> np.ndarray:
    """CLAHE + mild unsharp on warped grayscale for marginal phone captures only.

    Improves faint pencil vs paper separation before blank subtraction. Not applied
    to the blank template so differencing still cancels print geometry.
    """
    if not CV2_AVAILABLE or gray is None or gray.size == 0:
        return gray
    clip = float(cfg.get("marginal_clahe_clip_limit", 2.35))
    tile = int(cfg.get("marginal_clahe_tile_size", 24))
    tile = max(8, min(64, tile))
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(tile, tile))
    g = clahe.apply(gray)
    blur = cv2.GaussianBlur(g, (0, 0), sigmaX=0.95, sigmaY=0.95)
    amount = float(cfg.get("marginal_unsharp_amount", 0.52))
    out = cv2.addWeighted(g, 1.0 + amount, blur, -amount, 0.0)
    return np.clip(out, 0, 255).astype(np.uint8)


def _should_export_bubble_rois(cfg: dict, save_debug: bool) -> bool:
    """Template can force export; otherwise settings + debug scan only."""
    if cfg.get("export_bubble_rois"):
        return True
    return bool(getattr(django_settings, "OMR_EXPORT_BUBBLE_ROIS", False) and save_debug)


def _export_bubble_rois_debug(
    diff_gray: np.ndarray,
    regions: list,
    *,
    qpc_used: int,
    col_dy: dict[int, int],
    col_dx: dict[int, int],
    inner_ratio: float,
    im_w: int,
    im_h: int,
    flagged: list[int],
    cfg: dict,
) -> dict[str, Any]:
    """Save capped PNG crops of inner bubble zones (difference image) for QA / training."""
    if not CV2_AVAILABLE or diff_gray is None or diff_gray.size == 0:
        return {}
    max_files = int(cfg.get("export_bubble_roi_max", 96))
    if max_files <= 0:
        return {}
    flagged_set = set(int(x) for x in flagged)
    only_flagged = bool(cfg.get("export_bubble_rois_flagged_only", True))
    if only_flagged and not flagged_set:
        return {}
    run_id = uuid.uuid4().hex[:10]
    rel_prefix = f"omr/debug/rois/{run_id}"
    urls: list[str] = []
    n = 0
    for region in regions:
        qn = int(region["question"])
        if only_flagged and flagged_set and qn not in flagged_set:
            continue
        cidx = (qn - 1) // max(1, qpc_used)
        row_dy = int(col_dy.get(cidx, 0))
        row_dx = int(col_dx.get(cidx, 0))
        for opt, box in region["boxes"].items():
            if n >= max_files:
                break
            x, y, bw, bh = int(box["x"]) + row_dx, int(box["y"]) + row_dy, int(box["w"]), int(box["h"])
            x = max(0, min(x, im_w - 1))
            y = max(0, min(y, im_h - 1))
            bw = max(1, min(bw, im_w - x))
            bh = max(1, min(bh, im_h - y))
            ix, iy, iw, ih = _inner_roi_rect(x, y, bw, bh, inner_ratio, im_w, im_h)
            crop = diff_gray[iy : iy + ih, ix : ix + iw]
            if crop.size == 0:
                continue
            name = f"q{qn}_{opt}"
            rel = f"{rel_prefix}/{name}.png"
            ok, buf = cv2.imencode(".png", crop)
            if not ok:
                continue
            path = default_storage.save(rel, ContentFile(buf.tobytes()))
            urls.append(path)
            n += 1
        if n >= max_files:
            break
    if not urls:
        return {}
    return {"prefix": rel_prefix, "count": len(urls), "urls": urls[:32]}


def _save_debug_png(arr_bgr_or_gray: np.ndarray, name: str) -> str:
    rel = f"omr/debug/{uuid.uuid4().hex}_{name}.png"
    if arr_bgr_or_gray.ndim == 2:
        ok, buf = cv2.imencode(".png", arr_bgr_or_gray)
    else:
        ok, buf = cv2.imencode(".png", arr_bgr_or_gray)
    if not ok:
        return ""
    path = default_storage.save(rel, ContentFile(buf.tobytes()))
    return path


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def process_omr_scan(
    image_path: str,
    template_config: dict,
    *,
    skip_quality_reject: bool = False,
    save_debug: bool = False,
) -> dict[str, Any]:
    """
    Full production scan. See module docstring.
    """
    if not CV2_AVAILABLE:
        return _fail("OpenCV is not installed. Install opencv-python-headless.")

    if not os.path.isfile(image_path):
        return _fail("Image file not found.")

    cfg = dict(template_config)
    target_w = int(cfg.get("image_width", 1000))
    target_h = int(cfg.get("image_height", 1400))
    inner_ratio = float(cfg.get("inner_zone_ratio", cfg.get("inner_answer_ratio", 0.42)))
    min_mark = float(cfg.get("min_mark_area_ratio", cfg.get("min_fill_ratio", 0.08)))
    strong_mark = float(
        cfg.get("strong_mark_area_ratio", cfg.get("strong_fill_ratio", 0.16))
    )
    min_gap = float(
        cfg.get("min_gap_from_second", cfg.get("min_difference_from_second", 0.05))
    )
    uncertainty_gap = float(cfg.get("uncertainty_gap", min_gap * 0.85))
    legacy_mode = bool(cfg.get("legacy_mode", cfg.get("sheet_design") == "legacy"))
    min_lift_fb = float(cfg.get("min_lift_from_baseline", 0.032))
    if cfg.get("disable_per_question_baseline"):
        min_lift_fb = 0.0

    img = cv2.imread(image_path)
    if img is None:
        return _fail("Could not read image (use JPG/PNG).")

    orig = img.copy()
    h0, w0 = img.shape[:2]
    scale = 1.0
    if max(h0, w0) > 2200:
        scale = 2200 / max(h0, w0)
        img = cv2.resize(img, (int(w0 * scale), int(h0 * scale)))
    gray0 = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Heavy denoising smears pencil marks; scale strength to sharpness of the original crop.
    _lap_pre = float(cv2.Laplacian(gray0, cv2.CV_64F).var())
    if _lap_pre >= 110.0:
        gray0 = cv2.fastNlMeansDenoising(gray0, h=5, templateWindowSize=7, searchWindowSize=21)
    elif _lap_pre >= 72.0:
        gray0 = cv2.fastNlMeansDenoising(gray0, h=3, templateWindowSize=7, searchWindowSize=15)

    contour, _ = _detect_document_contour(gray0)
    gh, gw = gray0.shape[:2]
    marker_pts = _refine_corners_from_markers(gray0)
    use_markers = marker_pts is not None and (
        cfg.get("prefer_corner_markers")
        or cfg.get("sheet_design") == "generated"
    )
    if use_markers and not _corner_markers_plausible(marker_pts, gw, gh):
        marker_pts = None
        use_markers = False

    if use_markers:
        pts = marker_pts
        if scale != 1.0:
            pts = pts / scale
        warped_bgr = _perspective_transform(orig, pts, target_w, target_h)
        perspective_corrected = True
    elif contour is not None:
        pts = contour.copy()
        if scale != 1.0:
            pts = pts / scale
        warped_bgr = _perspective_transform(orig, pts, target_w, target_h)
        perspective_corrected = True
    else:
        warped_bgr = cv2.resize(orig, (target_w, target_h))
        perspective_corrected = False

    deprint = float(cfg.get("deprint_strength", 0.42))
    if cfg.get("disable_deprint"):
        deprint = 0.0
    warped_bgr = _deprint_lighten_bgr(warped_bgr, deprint)
    warped_gray = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2GRAY)

    quality = assess_capture_quality(gray0, contour, cfg)
    if quality["reject"] and not skip_quality_reject:
        return {
            "success": False,
            "error": QUALITY_REJECT_MESSAGE,
            "quality_rejected": True,
            "quality": quality,
            "capture_guidance": CAPTURE_GUIDANCE_LINES,
            "perspective_corrected": perspective_corrected,
            "answers": {},
            "per_question": {},
            "flagged_questions": [],
        }

    marginal_enhancement_applied = False
    if (
        bool(quality.get("marginal"))
        and cfg.get("enable_marginal_enhancement", True)
        and not cfg.get("disable_marginal_enhancement")
    ):
        warped_gray = _enhance_gray_marginal_capture(warped_gray, cfg)
        marginal_enhancement_applied = True

    blank_path = cfg.get("blank_template_path") or cfg.get("blank_template_image_path")
    blank_gray = None
    if blank_path and os.path.isfile(str(blank_path)):
        blank_bgr = cv2.imread(str(blank_path), cv2.IMREAD_COLOR)
        if blank_bgr is not None:
            blank_bgr = _deprint_lighten_bgr(blank_bgr, deprint)
            bg = cv2.cvtColor(blank_bgr, cv2.COLOR_BGR2GRAY)
            if bg.shape != warped_gray.shape:
                bg = cv2.resize(bg, (warped_gray.shape[1], warped_gray.shape[0]))
            blank_gray = bg

    diff_gray, used_blank = _difference_image(warped_gray, blank_gray)
    if legacy_mode and not used_blank:
        min_mark = min_mark * 0.85
        min_gap = min_gap * 0.85
    # Blank subtraction yields cleaner “mark signal” — allow slightly lower thresholds to reduce false blanks.
    elif used_blank:
        min_mark = min_mark * 0.90
        strong_mark = strong_mark * 0.94
        min_gap = min_gap * 0.93

    marginal_q = bool(quality.get("marginal"))
    if marginal_q:
        min_gap = min_gap * 0.90
        uncertainty_gap = uncertainty_gap * 0.88

    regions = build_answer_regions(cfg)
    total_q = int(cfg.get("total_questions", len(regions)))
    qpc_used = _infer_questions_per_column(cfg, regions)
    col_dy: dict[int, int] = {}
    col_dx: dict[int, int] = {}
    im_h, im_w = diff_gray.shape[:2]
    if cfg.get("enable_column_dy_refine", True):
        col_shift_max = int(cfg.get("column_dy_search_range", 5))
        if col_shift_max > 0 and regions:
            by_col = _partition_regions_by_column(regions, qpc_used)
            col_dy = _refine_column_vertical_shifts(
                diff_gray, by_col, inner_ratio, im_w, im_h, dy_max=max(1, col_shift_max)
            )
    if cfg.get("enable_column_dx_refine", True):
        dx_max = int(cfg.get("column_dx_search_range", 4))
        if dx_max > 0 and regions:
            by_col = _partition_regions_by_column(regions, qpc_used)
            col_dx = _refine_column_horizontal_shifts(
                diff_gray, by_col, inner_ratio, im_w, im_h, col_dy, dx_max=max(1, dx_max)
            )

    answers: dict[str, str] = {}
    per_question: dict[str, dict[str, Any]] = {}
    flagged: list[int] = []

    for region in regions:
        qn = int(region["question"])
        if qn > total_q:
            continue
        qk = str(qn)
        cidx = (qn - 1) // max(1, qpc_used)
        row_dy = int(col_dy.get(cidx, 0))
        row_dx = int(col_dx.get(cidx, 0))
        opt_scores: dict[str, float] = {}
        for opt, box in region["boxes"].items():
            x, y, bw, bh = int(box["x"]) + row_dx, int(box["y"]) + row_dy, int(box["w"]), int(box["h"])
            x = max(0, min(x, im_w - 1))
            y = max(0, min(y, im_h - 1))
            bw = max(1, min(bw, im_w - x))
            bh = max(1, min(bh, im_h - y))
            ix, iy, iw, ih = _inner_roi_rect(x, y, bw, bh, inner_ratio, im_w, im_h)
            roi = diff_gray[iy : iy + ih, ix : ix + iw]
            meta = _score_mark_in_diff_roi(roi)
            opt_scores[opt] = meta["mark_score"]

        ans, status, conf_level, conf_val, baseline, lift = _decide_option_scores(
            opt_scores,
            min_mark,
            strong_mark,
            min_gap,
            min_lift_from_baseline=min_lift_fb,
        )
        if uncertainty_gap and status == "detected":
            items = sorted(opt_scores.items(), key=lambda t: t[1], reverse=True)
            if items:
                gap = items[0][1] - (items[1][1] if len(items) > 1 else 0.0)
                if gap < uncertainty_gap:
                    conf_level = "low"

        answers[qk] = ans
        per_question[qk] = {
            "question_number": qn,
            "answer": ans,
            "status": status,
            "confidence": conf_val,
            "confidence_level": conf_level,
            "option_scores": opt_scores,
            "local_baseline": round(baseline, 5),
            "lift_vs_baseline": round(lift, 5),
            "crop_debug_urls": {},
        }

        if status in ("uncertain", "multiple", "blank") or conf_level == "low":
            flagged.append(qn)
        if legacy_mode and status == "detected" and conf_level != "high":
            flagged.append(qn)
        if marginal_q and status == "detected" and conf_level != "high":
            flagged.append(qn)

    flagged = sorted(set(flagged))

    uncertain_n = sum(1 for q, pq in per_question.items() if pq["status"] == "uncertain")
    blank_n = sum(1 for q, pq in per_question.items() if pq["status"] == "blank")
    mult_n = sum(1 for q, pq in per_question.items() if pq["status"] == "multiple")

    review_fraction = (uncertain_n + blank_n + mult_n) / max(1, len(per_question))
    review_cut = 0.08 if marginal_q else 0.10
    answer_key_review = review_fraction > review_cut

    bubble_roi_export: dict[str, Any] = {}
    if _should_export_bubble_rois(cfg, save_debug):
        bubble_roi_export = _export_bubble_rois_debug(
            diff_gray,
            regions,
            qpc_used=qpc_used,
            col_dy=col_dy,
            col_dx=col_dx,
            inner_ratio=inner_ratio,
            im_w=im_w,
            im_h=im_h,
            flagged=flagged,
            cfg=cfg,
        ) or {}

    debug_urls: dict[str, str] = {}
    overlay_bgr = cv2.cvtColor(warped_gray, cv2.COLOR_GRAY2BGR)
    overlays_allowed = getattr(django_settings, "ENABLE_DEBUG_OVERLAYS", django_settings.DEBUG)
    if save_debug and overlays_allowed:
        for region in regions:
            qn_o = int(region["question"])
            dyo = int(col_dy.get((qn_o - 1) // max(1, qpc_used), 0))
            dxo = int(col_dx.get((qn_o - 1) // max(1, qpc_used), 0))
            for opt, box in region["boxes"].items():
                x, y, bw, bh = int(box["x"]) + dxo, int(box["y"]) + dyo, int(box["w"]), int(box["h"])
                ix, iy, iw, ih = _inner_roi_rect(x, y, bw, bh, inner_ratio, im_w, im_h)
                color = (180, 180, 180)
                if answers.get(str(region["question"])) == opt:
                    color = (0, 200, 0)
                cv2.rectangle(overlay_bgr, (ix, iy), (ix + iw, iy + ih), color, 1)
        minimal = getattr(
            django_settings, "OMR_SAVE_MINIMAL_DEBUG", not django_settings.DEBUG
        )
        if minimal:
            debug_urls["overlay_inner_zones"] = _save_debug_png(overlay_bgr, "overlay")
        else:
            debug_urls["normalized_gray"] = _save_debug_png(warped_gray, "normalized")
            debug_urls["difference"] = _save_debug_png(diff_gray, "diff")
            if blank_gray is not None:
                debug_urls["blank_aligned"] = _save_debug_png(blank_gray, "blank")
            debug_urls["overlay_inner_zones"] = _save_debug_png(overlay_bgr, "overlay")

    confidences = {k: float(v["confidence"]) for k, v in per_question.items()}
    option_details = {k: v["option_scores"] for k, v in per_question.items()}

    detected_high = sum(
        1 for v in per_question.values() if v["status"] == "detected" and v["confidence_level"] == "high"
    )
    coverage_ratio = detected_high / max(1, len(per_question))

    return {
        "success": True,
        "error": None,
        "quality_rejected": False,
        "quality": quality,
        "capture_guidance": CAPTURE_GUIDANCE_LINES,
        "perspective_corrected": perspective_corrected,
        "perspective_quality": {"metrics": quality.get("metrics", {}), "valid": not quality.get("reject")},
        "registration_marks_found": 0,
        "used_blank_subtraction": used_blank,
        "legacy_mode": legacy_mode,
        "template_id": cfg.get("template_id", "unknown"),
        "answers": answers,
        "confidence": confidences,
        "option_details": option_details,
        "per_question": per_question,
        "flagged_questions": flagged,
        "uncertain_count": uncertain_n,
        "blank_detection_count": blank_n,
        "multiple_count": mult_n,
        "answer_key_needs_review": answer_key_review,
        "review_fraction": round(review_fraction, 4),
        "coverage_ratio": round(coverage_ratio, 4),
        # High-confidence detections only; phone scans often land 0.55–0.70 with valid sheets.
        "coverage_warning": coverage_ratio < 0.52,
        "quality_marginal": bool(quality.get("marginal")),
        "marginal_enhancement_applied": marginal_enhancement_applied,
        "column_vertical_shift_px": {str(k): int(v) for k, v in col_dy.items()},
        "column_horizontal_shift_px": {str(k): int(v) for k, v in col_dx.items()},
        "bubble_roi_export": bubble_roi_export if bubble_roi_export else None,
        "debug_urls": debug_urls,
        "debug_image_path": debug_urls.get("overlay_inner_zones", ""),
    }


def _fail(msg: str) -> dict[str, Any]:
    return {
        "success": False,
        "error": msg,
        "quality_rejected": False,
        "answers": {},
        "per_question": {},
        "flagged_questions": [],
        "option_details": {},
        "confidence": {},
    }


# Backwards-compatible aliases
def process_omr_image_v2(
    image_path: str,
    template_config: dict,
    thresholds: Any = None,
    generate_debug_image: bool = False,
) -> dict[str, Any]:
    """Adapter: map legacy v2 call signature to process_omr_scan."""
    cfg = dict(template_config)
    if thresholds is not None:
        cfg["min_mark_area_ratio"] = getattr(thresholds, "min_fill_ratio", cfg.get("min_fill_ratio"))
        cfg["strong_mark_area_ratio"] = getattr(thresholds, "strong_fill_ratio", cfg.get("strong_fill_ratio"))
        cfg["min_gap_from_second"] = getattr(
            thresholds, "min_difference_from_second", cfg.get("min_difference_from_second")
        )
    return process_omr_scan(image_path, cfg, save_debug=generate_debug_image)


def enhanced_quality_check(image_path: str, template_config: dict | None = None) -> dict[str, Any]:
    if not CV2_AVAILABLE or not os.path.isfile(image_path):
        return {"warnings": [], "metrics": {}, "pass": True, "marginal": False}
    img = cv2.imread(image_path)
    if img is None:
        return {"warnings": ["Could not read image"], "metrics": {}, "pass": False, "marginal": False}
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    contour, _ = _detect_document_contour(gray)
    q = assess_capture_quality(gray, contour, template_config or {})
    return {
        "warnings": q["warnings"],
        "metrics": q["metrics"],
        "pass": not q["reject"],
        "reject": q["reject"],
        "marginal": bool(q.get("marginal")),
    }
