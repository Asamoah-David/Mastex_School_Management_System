"""
OMR Processor V2 - Enhanced Detection Pipeline
==============================================
A comprehensive rewrite with:
- Advanced perspective correction with document detection
- Registration mark alignment (timing marks for BECE sheets)
- Dynamic grid-based coordinate generation
- Adaptive thresholding with local background comparison
- Relative darkness scoring with confidence calculation
- Debug overlay generation
- Enhanced image quality checks
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration Classes
# ---------------------------------------------------------------------------

@dataclass
class DetectionThresholds:
    """Configurable thresholds for OMR detection."""
    min_fill_ratio: float = 0.12
    strong_fill_ratio: float = 0.22
    min_difference_from_second: float = 0.06
    blank_threshold: float = 0.08
    adaptive_block_size: int = 21
    adaptive_c: int = 8
    roi_shrink_percent: float = 0.15  # Shrink ROI to avoid printed brackets


@dataclass
class GridConfig:
    """Configuration for dynamic grid generation."""
    columns: list[dict] = field(default_factory=list)  # Each column: x_start, y_start, row_height
    option_width: float = 36
    option_gap: float = 8
    questions_per_column: int = 20
    options: list[str] = field(default_factory=lambda: ["A", "B", "C", "D", "E"])
    box_width: int = 36
    box_height: int = 26


@dataclass
class ProcessingResult:
    """Result of OMR processing for a single question option."""
    fill_score: float = 0.0
    is_filled: bool = False
    status: str = "blank"  # detected, blank, multiple, uncertain


@dataclass
class QuestionResult:
    """Complete result for one question."""
    question_num: int = 0
    detected_answer: str = "blank"
    confidence: float = 0.0
    option_scores: dict[str, float] = field(default_factory=dict)
    status: str = "blank"  # detected, blank, multiple, uncertain


# ---------------------------------------------------------------------------
# Geometry & Perspective Correction
# ---------------------------------------------------------------------------

def _order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]   # top-left
    rect[2] = pts[np.argmax(s)]   # bottom-right
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left
    return rect


def _perspective_transform(image: np.ndarray, pts: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """Apply four-point perspective transform."""
    rect = _order_points(pts)
    dst = np.array(
        [[0, 0], [target_w - 1, 0], [target_w - 1, target_h - 1], [0, target_h - 1]],
        dtype="float32",
    )
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, M, (target_w, target_h), borderMode=cv2.BORDER_CONSTANT, borderValue=255)


def _detect_document_contour(gray: np.ndarray) -> tuple[np.ndarray | None, dict]:
    """
    Detect the largest rectangular contour that looks like a document.
    Returns (contour_points, debug_info).
    """
    debug_info = {"method": "contour_detection", "success": False}
    
    # Preprocessing pipeline
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Edge detection with Canny
    edged = cv2.Canny(blurred, 50, 150)
    
    # Dilate to connect edges
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edged = cv2.dilate(edged, kernel, iterations=2)
    edged = cv2.erode(edged, kernel, iterations=1)
    
    # Find contours
    contours, _ = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None, debug_info
    
    # Sort by area, take top 5
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    
    height, width = gray.shape
    image_area = height * width
    
    for c in contours:
        peri = cv2.arcLength(c, True)
        # More lenient epsilon for better detection of slightly curved sheets
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        
        if len(approx) == 4:
            contour_area = cv2.contourArea(approx)
            area_ratio = contour_area / image_area
            
            # Document should be at least 25% of image and at most 95%
            if 0.25 < area_ratio < 0.95:
                pts = approx.reshape(4, 2).astype("float32")
                debug_info["success"] = True
                debug_info["area_ratio"] = area_ratio
                debug_info["contour_area"] = contour_area
                return pts, debug_info
    
    return None, debug_info


def _detect_registration_marks(gray: np.ndarray, template_config: dict) -> list[tuple[int, int]] | None:
    """
    Detect timing/registration marks on BECE-style sheets.
    These are typically vertical bars on the right side of the sheet.
    Returns list of (x, y) coordinates of detected marks or None.
    """
    height, width = gray.shape
    
    # Look for vertical registration marks on the right side (typically last 20% of width)
    right_region_start = int(width * 0.80)
    right_region = gray[:, right_region_start:]
    
    # Threshold to find dark marks
    _, thresh = cv2.threshold(right_region, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Look for vertical line segments
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15))
    vertical_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
    
    # Find contours of potential registration marks
    contours, _ = cv2.findContours(vertical_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    marks = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        aspect_ratio = h / float(w) if w > 0 else 0
        
        # Registration marks are tall and narrow (aspect ratio > 3)
        if aspect_ratio > 3 and h > 20:
            marks.append((right_region_start + x + w//2, y + h//2))
    
    # Sort by y position (top to bottom)
    marks.sort(key=lambda p: p[1])
    
    # We expect a certain number of marks based on the template
    expected_marks = template_config.get("expected_registration_marks", 0)
    if expected_marks > 0 and len(marks) >= expected_marks * 0.7:  # At least 70% found
        return marks
    
    return None


def _validate_perspective_quality(warped: np.ndarray, original: np.ndarray) -> dict:
    """Check quality of perspective-corrected image."""
    height, width = warped.shape[:2]
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY) if len(warped.shape) == 3 else warped
    
    quality = {
        "valid": True,
        "warnings": [],
        "mean_brightness": float(np.mean(gray)),
        "contrast": float(np.std(gray)),
    }
    
    # Check if the warped image has reasonable brightness
    if quality["mean_brightness"] < 40:
        quality["warnings"].append("Warped image is very dark - sheet may be poorly lit")
        quality["valid"] = False
    elif quality["mean_brightness"] > 250:
        quality["warnings"].append("Warped image is overexposed - may have glare issues")
    
    # Check contrast
    if quality["contrast"] < 20:
        quality["warnings"].append("Low contrast in warped image - answers may be hard to detect")
        quality["valid"] = False
    
    return quality


# ---------------------------------------------------------------------------
# Grid Generation
# ---------------------------------------------------------------------------

def generate_answer_regions_from_grid(grid_config: GridConfig) -> list[dict]:
    """
    Generate answer region coordinates from grid configuration.
    This creates coordinates dynamically based on column/row parameters.
    """
    regions = []
    
    for col_idx, col in enumerate(grid_config.columns):
        x_start = col["x_start"]
        y_start = col["y_start"]
        row_height = col["row_height"]
        
        for row in range(grid_config.questions_per_column):
            q_num = col_idx * grid_config.questions_per_column + row + 1
            y = y_start + row * row_height
            
            boxes = {}
            for opt_idx, opt in enumerate(grid_config.options):
                x = x_start + opt_idx * (grid_config.option_width + grid_config.option_gap)
                boxes[opt] = {
                    "x": int(x),
                    "y": int(y),
                    "w": grid_config.box_width,
                    "h": grid_config.box_height,
                }
            
            regions.append({"question": q_num, "boxes": boxes})
    
    regions.sort(key=lambda r: r["question"])
    return regions


def build_grid_config_from_template(template_config: dict) -> GridConfig:
    """Build grid configuration from template parameters."""
    grid = GridConfig(
        questions_per_column=template_config.get("questions_per_column", 20),
        options=template_config.get("options", ["A", "B", "C", "D", "E"]),
        option_width=template_config.get("option_width", 36),
        option_gap=template_config.get("option_gap", 8),
        box_width=template_config.get("box_width", 36),
        box_height=template_config.get("box_height", 26),
    )
    
    # Build columns from template column config
    col_configs = template_config.get("column_configs", [])
    for col_cfg in col_configs:
        grid.columns.append({
            "x_start": col_cfg["x_start"],
            "y_start": col_cfg["y_start"],
            "row_height": col_cfg["row_height"],
        })
    
    return grid


# ---------------------------------------------------------------------------
# Bubble Detection with Adaptive Thresholding
# ---------------------------------------------------------------------------

def _detect_bubble_fill(
    roi: np.ndarray,
    thresholds: DetectionThresholds,
    local_background: float | None = None
) -> ProcessingResult:
    """
    Detect if a bubble is filled using adaptive thresholding.
    
    Args:
        roi: Region of interest (grayscale)
        thresholds: Detection thresholds
        local_background: Optional local background level for relative comparison
    
    Returns:
        ProcessingResult with fill score and status
    """
    result = ProcessingResult()
    
    if roi.size == 0:
        return result
    
    # Shrink ROI to avoid printed brackets/text at edges
    h, w = roi.shape
    shrink_x = int(w * thresholds.roi_shrink_percent)
    shrink_y = int(h * thresholds.roi_shrink_percent)
    
    if shrink_x > 0 and shrink_y > 0:
        roi = roi[shrink_y:h-shrink_y, shrink_x:w-shrink_x]
    
    if roi.size == 0:
        return result
    
    # Calculate statistics
    mean_val = float(np.mean(roi))
    min_val = float(np.min(roi))
    
    # Use adaptive thresholding for better results under varying lighting
    # First try Otsu
    _, otsu_thresh = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    otsu_fill = np.count_nonzero(otsu_thresh) / otsu_thresh.size
    
    # Also try adaptive Gaussian
    if roi.shape[0] >= thresholds.adaptive_block_size and roi.shape[1] >= thresholds.adaptive_block_size:
        adaptive_thresh = cv2.adaptiveThreshold(
            roi, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV,
            thresholds.adaptive_block_size,
            thresholds.adaptive_c
        )
        adaptive_fill = np.count_nonzero(adaptive_thresh) / adaptive_thresh.size
    else:
        adaptive_fill = otsu_fill
    
    # Use the more conservative (lower) fill estimate
    fill_ratio = min(otsu_fill, adaptive_fill)
    
    # Calculate relative darkness if we have local background
    if local_background is not None and local_background > 0:
        darkness = (local_background - mean_val) / local_background
        # Combine fill ratio with darkness measure
        fill_score = max(fill_ratio, darkness * 0.5)
    else:
        fill_score = fill_ratio
    
    result.fill_score = round(fill_score, 4)
    result.is_filled = fill_score >= thresholds.min_fill_ratio
    
    if fill_score >= thresholds.strong_fill_ratio:
        result.status = "detected"
    elif fill_score >= thresholds.min_fill_ratio:
        result.status = "uncertain"
    elif fill_score >= thresholds.blank_threshold:
        result.status = "possible"
    else:
        result.status = "blank"
    
    return result


def _calculate_local_background(gray: np.ndarray, x: int, y: int, size: int = 50) -> float:
    """Calculate local background level around a point."""
    h, w = gray.shape
    x1 = max(0, x - size)
    x2 = min(w, x + size)
    y1 = max(0, y - size)
    y2 = min(h, y + size)
    
    local_region = gray[y1:y2, x1:x2]
    if local_region.size > 0:
        # Use higher percentile as background estimate (paper is white)
        return float(np.percentile(local_region, 85))
    return 200.0  # Default assumption


# ---------------------------------------------------------------------------
# Main Processing Functions
# ---------------------------------------------------------------------------

def process_omr_image_v2(
    image_path: str,
    template_config: dict,
    thresholds: DetectionThresholds | None = None,
    generate_debug_image: bool = False
) -> dict:
    """
    Process OMR image with enhanced detection pipeline.
    
    Args:
        image_path: Path to the image file
        template_config: Template configuration with grid parameters
        thresholds: Optional custom detection thresholds
        generate_debug_image: Whether to generate debug overlay
    
    Returns:
        Dictionary with success status, answers, confidence, and optional debug image path
    """
    if not CV2_AVAILABLE:
        return _error_result("OpenCV not installed. Please install opencv-python-headless.")
    
    if not os.path.exists(image_path):
        return _error_result("Image file not found.")
    
    if thresholds is None:
        thresholds = DetectionThresholds(
            min_fill_ratio=template_config.get("min_fill_ratio", 0.12),
            strong_fill_ratio=template_config.get("strong_fill_ratio", 0.22),
            min_difference_from_second=template_config.get("min_difference_from_second", 0.06),
        )
    
    try:
        # Load image
        img = cv2.imread(image_path)
        if img is None:
            return _error_result("Could not read image. Check file format (JPG/PNG supported).")
        
        original = img.copy()
        
        # Resize for processing if too large
        h, w = img.shape[:2]
        scale = 1.0
        if max(h, w) > 2000:
            scale = 2000 / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Get target dimensions from template
        target_w = template_config.get("image_width", 1000)
        target_h = template_config.get("image_height", 1400)
        
        # Step 1: Document Detection and Perspective Correction
        contour, contour_debug = _detect_document_contour(gray)
        perspective_corrected = False
        correction_quality = {}
        
        if contour is not None:
            # Adjust contour for resize scale
            if scale != 1.0:
                contour = contour / scale
            
            # Apply perspective transform
            warped = _perspective_transform(original, contour, target_w, target_h)
            perspective_corrected = True
            
            # Validate perspective quality
            correction_quality = _validate_perspective_quality(warped, original)
            
            if not correction_quality["valid"]:
                # Fall back to simple resize if perspective looks bad
                warped = cv2.resize(original, (target_w, target_h))
                perspective_corrected = False
        else:
            # No document contour found - use simple resize
            warped = cv2.resize(original, (target_w, target_h))
        
        # Convert warped to grayscale for detection
        warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        
        # Step 2: Optional Registration Mark Detection for Alignment Verification
        registration_marks = _detect_registration_marks(warped_gray, template_config)
        alignment_confidence = 1.0 if registration_marks else 0.7
        
        # Step 3: Generate Answer Regions from Grid
        grid_config = build_grid_config_from_template(template_config)
        answer_regions = generate_answer_regions_from_grid(grid_config)
        
        # Step 4: Detect Bubbles
        answers = {}
        confidence = {}
        flagged_questions = []
        option_details = {}
        
        for region in answer_regions:
            q_num = str(region["question"])
            q_result = QuestionResult(question_num=region["question"])
            option_scores = {}
            
            for opt, box in region["boxes"].items():
                x = max(0, int(box["x"]))
                y = max(0, int(box["y"]))
                bw = int(box["w"])
                bh = int(box["h"])
                
                # Clamp to image bounds
                x = min(x, warped_gray.shape[1] - 1)
                y = min(y, warped_gray.shape[0] - 1)
                bw = min(bw, warped_gray.shape[1] - x)
                bh = min(bh, warped_gray.shape[0] - y)
                
                if bw <= 0 or bh <= 0:
                    option_scores[opt] = 0.0
                    continue
                
                # Get local background for relative darkness calculation
                local_bg = _calculate_local_background(warped_gray, x + bw//2, y + bh//2)
                
                # Detect bubble fill
                roi = warped_gray[y:y+bh, x:x+bw]
                result = _detect_bubble_fill(roi, thresholds, local_bg)
                option_scores[opt] = result.fill_score
            
            # Determine answer based on option scores
            sorted_opts = sorted(option_scores.items(), key=lambda x: x[1], reverse=True)
            
            if len(sorted_opts) >= 2:
                best_opt, best_score = sorted_opts[0]
                second_score = sorted_opts[1][1] if len(sorted_opts) > 1 else 0
                
                q_result.option_scores = option_scores
                
                # Decision logic
                if best_score < thresholds.blank_threshold:
                    # Definitely blank
                    q_result.detected_answer = "blank"
                    q_result.confidence = 0.0
                    q_result.status = "blank"
                    flagged_questions.append(region["question"])
                    
                elif best_score >= thresholds.strong_fill_ratio:
                    # Strong fill - confident answer
                    if best_score - second_score >= thresholds.min_difference_from_second:
                        q_result.detected_answer = best_opt
                        q_result.confidence = round(best_score * alignment_confidence, 4)
                        q_result.status = "detected"
                    else:
                        # Too close to second option
                        q_result.detected_answer = "uncertain"
                        q_result.confidence = round(best_score, 4)
                        q_result.status = "uncertain"
                        flagged_questions.append(region["question"])
                        
                elif best_score >= thresholds.min_fill_ratio:
                    # Weak fill - check margin from second
                    if best_score - second_score >= thresholds.min_difference_from_second:
                        q_result.detected_answer = best_opt
                        q_result.confidence = round(best_score * alignment_confidence * 0.8, 4)
                        q_result.status = "detected"
                        flagged_questions.append(region["question"])  # Flag for review
                    else:
                        q_result.detected_answer = "uncertain"
                        q_result.confidence = round(best_score, 4)
                        q_result.status = "uncertain"
                        flagged_questions.append(region["question"])
                        
                else:
                    # Between blank and min - uncertain
                    q_result.detected_answer = "uncertain"
                    q_result.confidence = round(best_score, 4)
                    q_result.status = "uncertain"
                    flagged_questions.append(region["question"])
            
            answers[q_num] = q_result.detected_answer
            confidence[q_num] = q_result.confidence
            option_details[q_num] = q_result.option_scores
        
        # Check detection coverage
        total_questions = len(answer_regions)
        confident_count = sum(1 for q, c in confidence.items() if c >= 0.5)
        coverage_ratio = confident_count / total_questions if total_questions > 0 else 0
        
        result = {
            "success": True,
            "perspective_corrected": perspective_corrected,
            "perspective_quality": correction_quality,
            "registration_marks_found": len(registration_marks) if registration_marks else 0,
            "template_id": template_config.get("template_id", "unknown"),
            "answers": answers,
            "confidence": confidence,
            "option_details": option_details,
            "flagged_questions": sorted(set(flagged_questions)),
            "coverage_ratio": round(coverage_ratio, 2),
            "coverage_warning": coverage_ratio < 0.70,
            "error": None,
        }
        
        # Generate debug image if requested
        if generate_debug_image:
            debug_path = _generate_debug_overlay(
                warped, answer_regions, answers, confidence, flagged_questions, option_details
            )
            result["debug_image_path"] = debug_path
        
        return result
        
    except Exception as exc:
        import traceback
        return _error_result(f"Processing error: {exc}\n{traceback.format_exc()}")


def _error_result(error_msg: str) -> dict:
    """Return a standard error result."""
    return {
        "success": False,
        "error": error_msg,
        "perspective_corrected": False,
        "answers": {},
        "confidence": {},
        "option_details": {},
        "flagged_questions": [],
        "coverage_ratio": 0,
        "coverage_warning": True,
    }


def _generate_debug_overlay(
    image: np.ndarray,
    answer_regions: list[dict],
    answers: dict[str, str],
    confidence: dict[str, float],
    flagged_questions: list[int],
    option_details: dict[str, dict[str, float]]
) -> str | None:
    """Generate a debug overlay image showing detected answers."""
    try:
        # Create a copy for overlay
        overlay = image.copy()
        
        for region in answer_regions:
            q_num = region["question"]
            q_str = str(q_num)
            answer = answers.get(q_str, "blank")
            conf = confidence.get(q_str, 0.0)
            is_flagged = q_num in flagged_questions
            
            # Determine color based on status
            if is_flagged:
                color = (0, 165, 255)  # Orange for flagged
            elif answer == "blank":
                color = (128, 128, 128)  # Gray for blank
            elif answer in ["uncertain", "multiple"]:
                color = (0, 0, 255)  # Red for uncertain/multiple
            else:
                color = (0, 255, 0)  # Green for detected
            
            # Draw boxes for each option
            for opt, box in region["boxes"].items():
                x, y = int(box["x"]), int(box["y"])
                w, h = int(box["w"]), int(box["h"])
                
                # Get fill score for this option
                opt_scores = option_details.get(q_str, {})
                fill_score = opt_scores.get(opt, 0)
                
                # If this is the detected answer, use brighter color
                if opt == answer:
                    box_color = color
                    thickness = 2
                else:
                    # Shade based on fill score
                    intensity = int(255 * min(fill_score * 2, 1.0))
                    box_color = (intensity, intensity, intensity)
                    thickness = 1
                
                cv2.rectangle(overlay, (x, y), (x + w, y + h), box_color, thickness)
                
                # Show fill score inside box (small text)
                if fill_score > 0.05:
                    score_text = f"{fill_score:.2f}"
                    cv2.putText(overlay, score_text, (x + 2, y + h//2), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 255), 1)
            
            # Draw question number and detected answer
            first_box = list(region["boxes"].values())[0]
            text_x = int(first_box["x"]) - 50
            text_y = int(first_box["y"]) + int(first_box["h"])//2
            
            text = f"Q{q_num}:{answer}"
            cv2.putText(overlay, text, (text_x, text_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        
        # Save debug image
        debug_filename = f"omr/debug/debug_{os.path.basename(image_path)}"
        _, buffer = cv2.imencode('.png', overlay)
        path = default_storage.save(debug_filename, ContentFile(buffer.tobytes()))
        return default_storage.path(path)
        
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Enhanced Quality Checks
# ---------------------------------------------------------------------------

def enhanced_quality_check(image_path: str, template_config: dict | None = None) -> dict:
    """
    Comprehensive image quality assessment.
    Returns warnings and quality metrics.
    """
    warnings = []
    metrics = {}
    
    if not CV2_AVAILABLE:
        return {"warnings": [], "metrics": {}, "pass": True}
    
    try:
        img = cv2.imread(image_path)
        if img is None:
            return {"warnings": ["Could not read image"], "metrics": {}, "pass": False}
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        
        # Brightness analysis
        mean_brightness = float(np.mean(gray))
        metrics["mean_brightness"] = mean_brightness
        
        if mean_brightness < 50:
            warnings.append("Image is too dark. Use better lighting or adjust camera exposure.")
        elif mean_brightness > 240:
            warnings.append("Image is overexposed. Reduce lighting or avoid glare.")
        
        # Contrast analysis
        std_brightness = float(np.std(gray))
        metrics["contrast"] = std_brightness
        
        if std_brightness < 30:
            warnings.append("Low contrast detected. Ensure clear difference between paper and marks.")
        
        # Blur detection using Laplacian variance
        laplacian_var = float(cv2.Laplacian(gray, cv2.cv2.CV_64F if hasattr(cv2, 'cv2') else cv2.CV_64F).var())
        metrics["sharpness"] = laplacian_var
        
        if laplacian_var < 100:
            warnings.append("Image appears blurry. Hold camera steady and ensure focus.")
        
        # Document size check (paper should fill most of frame)
        contour, _ = _detect_document_contour(gray)
        if contour is not None:
            contour_area = cv2.contourArea(contour)
            image_area = h * w
            fill_ratio = contour_area / image_area
            metrics["document_fill_ratio"] = fill_ratio
            
            if fill_ratio < 0.5:
                warnings.append("Sheet fills less than 50% of image. Move camera closer to paper.")
        else:
            warnings.append("Could not detect paper borders. Ensure full sheet is visible.")
            metrics["document_fill_ratio"] = 0
        
        # Tilt/rotation estimation
        if contour is not None:
            rect = cv2.minAreaRect(contour)
            angle = rect[2]
            metrics["rotation_angle"] = angle
            
            if abs(angle) > 15:
                warnings.append(f"Sheet appears tilted ({angle:.1f}°). Keep camera parallel to paper.")
        
        # Shadow detection (gradients)
        grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
        metrics["edge_strength"] = float(np.mean(gradient_magnitude))
        
        return {
            "warnings": warnings,
            "metrics": metrics,
            "pass": len(warnings) == 0 or all("Could not detect" not in w for w in warnings),
        }
        
    except Exception as exc:
        return {
            "warnings": [f"Quality check error: {exc}"],
            "metrics": {},
            "pass": False,
        }


# ---------------------------------------------------------------------------
# Template Calibration
# ---------------------------------------------------------------------------

def calibrate_template_from_reference(
    image_path: str,
    reference_points: dict
) -> dict | None:
    """
    Calibrate template from user-marked reference points.
    
    reference_points should contain:
    - top_left: (x, y) of top-left answer area
    - bottom_right: (x, y) of bottom-right answer area
    - first_row_y: y coordinate of first question row
    - last_row_y: y coordinate of last question row
    - option_positions: {opt: x} for each option position
    """
    if not CV2_AVAILABLE:
        return None
    
    try:
        img = cv2.imread(image_path)
        if img is None:
            return None
        
        h, w = img.shape[:2]
        
        # Calculate grid parameters from reference points
        tl = reference_points["top_left"]
        br = reference_points["bottom_right"]
        first_y = reference_points["first_row_y"]
        last_y = reference_points["last_row_y"]
        opt_positions = reference_points["option_positions"]
        
        # Determine number of columns
        columns = reference_points.get("columns", 3)
        questions_per_col = reference_points.get("questions_per_column", 20)
        
        # Calculate column widths
        total_width = br[0] - tl[0]
        col_width = total_width / columns
        
        # Calculate row height
        total_question_height = last_y - first_y
        row_height = total_question_height / (questions_per_col - 1)
        
        # Calculate option spacing
        opts = sorted(opt_positions.keys())
        if len(opts) >= 2:
            first_opt_x = opt_positions[opts[0]]
            last_opt_x = opt_positions[opts[-1]]
            option_span = last_opt_x - first_opt_x
            option_width = option_span / (len(opts) - 1)
            option_gap = option_width - reference_points.get("box_width", 36)
        else:
            option_width = 36
            option_gap = 8
        
        # Build column configs
        column_configs = []
        for col in range(columns):
            x_start = tl[0] + col * col_width + (opt_positions[opts[0]] - tl[0]) % col_width
            y_start = first_y
            column_configs.append({
                "x_start": x_start,
                "y_start": y_start,
                "row_height": row_height,
            })
        
        return {
            "image_width": w,
            "image_height": h,
            "column_configs": column_configs,
            "questions_per_column": questions_per_column,
            "option_width": option_width,
            "option_gap": option_gap,
            "box_width": reference_points.get("box_width", 36),
            "box_height": reference_points.get("box_height", 26),
            "calibrated": True,
        }
        
    except Exception:
        return None


# Backward compatibility wrapper
def process_omr_image(image_path: str, template_config: dict) -> dict:
    """Backward-compatible wrapper for V1 API."""
    return process_omr_image_v2(image_path, template_config)


def quality_check(image_path: str) -> dict:
    """Backward-compatible wrapper for V1 API."""
    result = enhanced_quality_check(image_path)
    return {"warnings": result["warnings"]}
