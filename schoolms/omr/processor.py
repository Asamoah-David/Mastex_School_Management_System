"""
OMR Image Processor
===================
Accepts a filesystem path to an uploaded image, applies computer-vision
techniques to detect shaded bubbles, and returns a structured result dict.

Falls back gracefully when OpenCV is not installed (import error returns a
clear error message so the teacher can enter answers manually).

Processing pipeline
-------------------
1. Load image → resize to ≤2 000 px on longest edge (speed/memory)
2. Grayscale + Gaussian blur
3. Canny edge detection → find largest 4-point contour (sheet boundary)
4. Perspective-warp to template dimensions  (or plain resize if no contour)
5. For each answer-box region:
   a. Crop the ROI
   b. Otsu binary threshold (inverted)
   c. Fill-ratio = dark_pixels / total_pixels
6. Classify each question: correct option / "blank" / "multiple"
7. Return answers + confidence + flagged questions
"""

from __future__ import annotations

import os
from typing import Any

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _order_points(pts) -> Any:
    """Order 4 points: top-left, top-right, bottom-right, bottom-left."""
    import numpy as np  # noqa: F811
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]   # top-left
    rect[2] = pts[np.argmax(s)]   # bottom-right
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left
    return rect


def _perspective_transform(image, pts, target_w: int, target_h: int):
    import numpy as np  # noqa: F811
    rect = _order_points(pts)
    dst = np.array(
        [[0, 0], [target_w - 1, 0], [target_w - 1, target_h - 1], [0, target_h - 1]],
        dtype="float32",
    )
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, M, (target_w, target_h))


def _detect_sheet_contour(gray):
    """Return the 4-corner contour of the answer sheet, or None."""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 75, 200)
    contours, _ = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    for c in contours[:5]:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype("float32")
    return None


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_omr_image(image_path: str, template_config: dict) -> dict:
    """
    Process one answer-sheet image and return detected answers.

    Returns
    -------
    {
        "success": bool,
        "perspective_corrected": bool,
        "template_id": str,
        "answers": {"1": "A", "2": "blank", ...},
        "confidence": {"1": 0.92, ...},
        "flagged_questions": [3, 7, ...],
        "error": str | None,
    }
    """
    if not CV2_AVAILABLE:
        return {
            "success": False,
            "error": (
                "OpenCV is not installed on this server. "
                "Please install opencv-python-headless and restart the application, "
                "or enter answers manually."
            ),
            "perspective_corrected": False,
            "answers": {},
            "confidence": {},
            "flagged_questions": [],
        }

    if not os.path.exists(image_path):
        return {
            "success": False,
            "error": "Uploaded image file not found.",
            "perspective_corrected": False,
            "answers": {},
            "confidence": {},
            "flagged_questions": [],
        }

    try:
        img = cv2.imread(image_path)
        if img is None:
            return {
                "success": False,
                "error": "Could not read the image. Please check the file format (JPG/PNG supported).",
                "perspective_corrected": False,
                "answers": {},
                "confidence": {},
                "flagged_questions": [],
            }

        target_w: int = template_config["image_width"]
        target_h: int = template_config["image_height"]
        fill_threshold: float = template_config.get("fill_threshold", 0.35)
        uncertain_threshold: float = template_config.get("uncertain_threshold", 0.15)

        # ── Step 1: resize for processing speed ───────────────────────────
        h, w = img.shape[:2]
        max_dim = 2000
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # ── Step 2: perspective correction ────────────────────────────────
        pts = _detect_sheet_contour(gray)
        perspective_corrected = pts is not None

        if perspective_corrected:
            corrected = _perspective_transform(img, pts, target_w, target_h)
        else:
            corrected = cv2.resize(img, (target_w, target_h))

        corrected_gray = cv2.cvtColor(corrected, cv2.COLOR_BGR2GRAY)

        # ── Step 3: detect bubbles ─────────────────────────────────────────
        answers: dict[str, str] = {}
        confidence: dict[str, float] = {}
        flagged_questions: list[int] = []

        for region in template_config["answer_regions"]:
            q_num = str(region["question"])
            opt_ratios: dict[str, float] = {}

            for opt, box in region["boxes"].items():
                x = max(0, int(box["x"]))
                y = max(0, int(box["y"]))
                bw = int(box["w"])
                bh = int(box["h"])
                # Clamp to image dimensions
                x = min(x, corrected_gray.shape[1] - 1)
                y = min(y, corrected_gray.shape[0] - 1)
                bw = min(bw, corrected_gray.shape[1] - x)
                bh = min(bh, corrected_gray.shape[0] - y)

                if bw <= 0 or bh <= 0:
                    opt_ratios[opt] = 0.0
                    continue

                roi = corrected_gray[y : y + bh, x : x + bw]
                _, thresh = cv2.threshold(
                    roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
                )
                ratio = float(np.count_nonzero(thresh)) / thresh.size
                opt_ratios[opt] = round(ratio, 4)

            filled_opts = [o for o, r in opt_ratios.items() if r >= fill_threshold]

            if len(filled_opts) == 0:
                near = [o for o, r in opt_ratios.items() if r >= uncertain_threshold]
                if near:
                    best = max(opt_ratios, key=opt_ratios.get)
                    answers[q_num] = best
                    confidence[q_num] = opt_ratios[best]
                else:
                    answers[q_num] = "blank"
                    confidence[q_num] = 0.0
                flagged_questions.append(int(q_num))

            elif len(filled_opts) == 1:
                opt = filled_opts[0]
                answers[q_num] = opt
                confidence[q_num] = opt_ratios[opt]
                if opt_ratios[opt] < 0.50:
                    flagged_questions.append(int(q_num))

            else:
                answers[q_num] = "multiple"
                confidence[q_num] = round(max(opt_ratios.values()), 4)
                flagged_questions.append(int(q_num))

        return {
            "success": True,
            "perspective_corrected": perspective_corrected,
            "template_id": template_config["template_id"],
            "answers": answers,
            "confidence": confidence,
            "flagged_questions": sorted(set(flagged_questions)),
            "error": None,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"Image processing error: {exc}",
            "perspective_corrected": False,
            "answers": {},
            "confidence": {},
            "flagged_questions": [],
        }


def quality_check(image_path: str) -> dict:
    """
    Quick quality assessment: brightness, contrast, blur score.
    Returns warnings list. Empty list = image quality OK.
    """
    warnings = []
    if not CV2_AVAILABLE:
        return {"warnings": warnings}
    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return {"warnings": ["Could not read image for quality check."]}

        mean_brightness = float(np.mean(img))
        if mean_brightness < 60:
            warnings.append("Image appears very dark. Poor lighting may reduce accuracy.")
        elif mean_brightness > 220:
            warnings.append("Image appears overexposed. Strong glare may reduce accuracy.")

        laplacian_var = float(cv2.Laplacian(img, cv2.CV_64F).var())
        if laplacian_var < 50:
            warnings.append("Image appears blurry. Please retake with better focus.")

    except Exception:
        pass
    return {"warnings": warnings}
