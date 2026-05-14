"""
OMR Marking Views
=================
Workflow:
  1. Dashboard       — list exams                  GET  /omr/
  2. Create Exam     — create new exam              GET/POST  /omr/create/
  3. Exam Detail     — overview + status           GET  /omr/<pk>/
  4. Answer Key Upload → process → Review → Save
  5. Student Sheet Upload → process → Review → Save
  6. Results list    — table + CSV export
  7. Analysis        — class statistics
"""

from __future__ import annotations

import csv
import io
import json
import os
import uuid
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import user_can_manage_school
from core.feature_access import feature_required
from core.upload_validation import InvalidUploadError, validate_image_upload
from core.utils import get_effective_school

from .analysis import get_exam_analysis
from .models import OmrExam, OmrResult, OmrExamSectionB, OmrTemplateCalibration
from .omr_templates_v2 import get_template, list_templates, get_capture_guidance
from .template_manager import get_processing_template
from .pipeline import CAPTURE_GUIDANCE_LINES, process_omr_scan
from .omr_processor_v2 import enhanced_quality_check
from .processor import process_omr_image
from .scoring import apply_manual_corrections, calculate_score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEMP_DIR = "omr/temp"


def _save_temp_image(uploaded_file) -> tuple[str | None, str | None]:
    """Validate, save upload to a temp path. Returns (path, error_message)."""
    try:
        validate_image_upload(uploaded_file)
    except InvalidUploadError as exc:
        return None, exc.message
    try:
        ext = os.path.splitext(uploaded_file.name)[1].lower() or ".jpg"
        temp_name = f"{TEMP_DIR}/{uuid.uuid4().hex}{ext}"
        path = default_storage.save(temp_name, ContentFile(uploaded_file.read()))
        return default_storage.path(path), None
    except Exception:
        return None, "Failed to save uploaded image. Please try again."


def _delete_temp_image(path: str):
    """Delete a temporary image file silently."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _require_staff(request):
    """Return None if OK, else redirect with message."""
    if not user_can_manage_school(request.user):
        messages.error(request, "You do not have permission to access this feature.")
        return redirect("home")
    return None


def _get_school_exam(request, pk):
    school = get_effective_school(request)
    return get_object_or_404(OmrExam, pk=pk, school=school)


# ---------------------------------------------------------------------------
# 1. Dashboard
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_dashboard(request):
    guard = _require_staff(request)
    if guard:
        return guard

    school = get_effective_school(request)
    exams = OmrExam.objects.for_school(school).prefetch_related("results")
    return render(request, "omr/dashboard.html", {"exams": exams})


# ---------------------------------------------------------------------------
# 2. Create Exam
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_exam_create(request):
    guard = _require_staff(request)
    if guard:
        return guard

    school = get_effective_school(request)
    templates = list_templates()

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        subject = request.POST.get("subject", "").strip()
        class_name = request.POST.get("class_name", "").strip()
        date_str = request.POST.get("date", "")
        template_type = request.POST.get("template_type", "")
        total_str = request.POST.get("total_questions", "")

        errors = []
        if not title:
            errors.append("Exam title is required.")
        if not subject:
            errors.append("Subject is required.")
        if not class_name:
            errors.append("Class name is required.")
        if not date_str:
            errors.append("Date is required.")
        if not get_template(template_type):
            errors.append("Please select a valid template type.")

        tmpl = get_template(template_type)
        max_q = tmpl["total_questions"] if tmpl else 60
        try:
            total_questions = int(total_str)
            if total_questions < 1 or total_questions > max_q:
                errors.append(f"Total questions must be between 1 and {max_q} for this template.")
        except (ValueError, TypeError):
            errors.append("Total questions must be a number.")
            total_questions = 0

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "omr/exam_create.html", {
                "templates": templates,
                "post": request.POST,
            })

        exam = OmrExam.objects.create(
            school=school,
            title=title,
            subject=subject,
            class_name=class_name,
            date=date_str,
            template_type=template_type,
            total_questions=total_questions,
            created_by=request.user,
        )
        messages.success(request, f'Exam "{title}" created. Now upload the answer key.')
        return redirect("omr:exam_detail", pk=exam.pk)

    return render(request, "omr/exam_create.html", {"templates": templates, "today": date.today().isoformat()})


# ---------------------------------------------------------------------------
# 3. Exam Detail
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_exam_detail(request, pk):
    guard = _require_staff(request)
    if guard:
        return guard

    exam = _get_school_exam(request, pk)
    recent_results = exam.results.order_by("-created_at")[:10]
    return render(request, "omr/exam_detail.html", {
        "exam": exam,
        "recent_results": recent_results,
        "tmpl": get_template(exam.template_type),
    })


@login_required
@feature_required("omr_marking")
@require_POST
def omr_exam_delete(request, pk):
    guard = _require_staff(request)
    if guard:
        return guard

    exam = _get_school_exam(request, pk)
    title = exam.title
    exam.delete()
    messages.success(request, f'Exam "{title}" and all its results have been deleted.')
    return redirect("omr:dashboard")


# ---------------------------------------------------------------------------
# 4a. Answer Key — Upload & Process
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_answer_key_upload(request, pk):
    guard = _require_staff(request)
    if guard:
        return guard

    exam = _get_school_exam(request, pk)
    school = get_effective_school(request)
    tmpl = get_processing_template(school, exam.template_type) or get_template(exam.template_type)

    if request.method == "POST":
        upload_mode = request.POST.get("upload_mode", "file")

        if upload_mode == "manual":
            # Teacher skips image processing and enters answers directly
            # Store empty detected_answers in session to trigger manual review
            session_key = f"omr_ak_{exam.pk}"
            request.session[session_key] = {
                "answers": {str(q): "" for q in range(1, exam.total_questions + 1)},
                "confidence": {},
                "flagged_questions": list(range(1, exam.total_questions + 1)),
                "perspective_corrected": False,
                "quality_warnings": [],
                "manual_entry": True,
                "per_question": {},
                "debug_urls": {},
                "answer_key_needs_review": True,
            }
            return redirect("omr:answer_key_review", pk=exam.pk)

        image_file = request.FILES.get("image")
        if not image_file:
            messages.error(request, "Please select an image file to upload.")
            return render(request, "omr/answer_key_upload.html", {"exam": exam})

        tmp_path, upload_err = _save_temp_image(image_file)
        if upload_err:
            messages.error(request, upload_err)
            return render(request, "omr/answer_key_upload.html", {"exam": exam})

        quality_data = enhanced_quality_check(tmp_path, tmpl)
        result = process_omr_scan(tmp_path, tmpl, save_debug=True)
        _delete_temp_image(tmp_path)

        if not result["success"]:
            for tip in result.get("capture_guidance") or CAPTURE_GUIDANCE_LINES:
                messages.info(request, tip)
            messages.error(request, result.get("error", "Image processing failed."))
            return render(request, "omr/answer_key_upload.html", {
                "exam": exam,
                "processing_error": result.get("error"),
                "quality_warnings": quality_data.get("warnings", []),
            })

        if result.get("coverage_warning"):
            messages.warning(
                request,
                "Many questions were not high-confidence detections. "
                "Use the debug review screen and correct the grid before confirming the key.",
            )
        if result.get("answer_key_needs_review"):
            messages.warning(
                request,
                "More than 10% of questions are blank, multiple, or uncertain — "
                "review carefully before saving the official answer key.",
            )
        if result.get("quality_marginal"):
            messages.warning(
                request,
                "Photo quality is marginal (blur, shadows, or framing). "
                "Automatic reading ran with extra safeguards — review flagged questions carefully.",
            )
        if not result.get("used_blank_subtraction"):
            messages.warning(
                request,
                "No blank template is configured for subtraction; accuracy is lower. "
                "Upload a clean blank in OMR calibration and attach it to this template.",
            )

        session_key = f"omr_ak_{exam.pk}"
        request.session[session_key] = {
            "answers": result["answers"],
            "confidence": result["confidence"],
            "option_details": result.get("option_details", {}),
            "per_question": result.get("per_question", {}),
            "flagged_questions": result["flagged_questions"],
            "perspective_corrected": result["perspective_corrected"],
            "perspective_quality": result.get("perspective_quality", {}),
            "registration_marks_found": result.get("registration_marks_found", 0),
            "quality_warnings": quality_data.get("warnings", []),
            "coverage_ratio": result.get("coverage_ratio", 0),
            "coverage_warning": result.get("coverage_warning", False),
            "debug_image_path": result.get("debug_image_path"),
            "debug_urls": result.get("debug_urls", {}),
            "answer_key_needs_review": result.get("answer_key_needs_review", False),
            "used_blank_subtraction": result.get("used_blank_subtraction", False),
            "quality_marginal": result.get("quality_marginal", False),
            "manual_entry": False,
        }
        return redirect("omr:answer_key_review", pk=exam.pk)

    capture_guidance = list(get_capture_guidance(exam.template_type)) + list(CAPTURE_GUIDANCE_LINES)
    return render(request, "omr/answer_key_upload.html", {
        "exam": exam,
        "capture_guidance": capture_guidance,
    })


# ---------------------------------------------------------------------------
# 4b. Answer Key — Review & Confirm
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_answer_key_review(request, pk):
    guard = _require_staff(request)
    if guard:
        return guard

    exam = _get_school_exam(request, pk)
    school = get_effective_school(request)
    tmpl = get_processing_template(school, exam.template_type) or get_template(exam.template_type)
    session_key = f"omr_ak_{exam.pk}"

    if request.method == "POST":
        # Build corrected answer key from POST data
        corrected_key = {}
        for q in range(1, exam.total_questions + 1):
            val = request.POST.get(f"q_{q}", "").strip().upper()
            if val in tmpl["options"]:
                corrected_key[str(q)] = val
            else:
                corrected_key[str(q)] = val if val else ""

        # Validate all answers are filled
        missing = [q for q in range(1, exam.total_questions + 1)
                   if not corrected_key.get(str(q))]
        if missing:
            messages.warning(
                request,
                f"Questions {', '.join(map(str, missing[:10]))} have no answer set. "
                "Please fill in all answers before confirming."
            )
            pending = request.session.get(session_key, {})
            return render(request, "omr/answer_key_review.html", {
                "exam": exam,
                "tmpl": tmpl,
                "detected": corrected_key,
                "confidence": pending.get("confidence", {}),
                "per_question": pending.get("per_question", {}),
                "flagged": pending.get("flagged_questions", []),
                "quality_warnings": pending.get("quality_warnings", []),
                "perspective_corrected": pending.get("perspective_corrected", False),
                "manual_entry": pending.get("manual_entry", False),
                "answer_key_needs_review": pending.get("answer_key_needs_review", False),
                "quality_marginal": pending.get("quality_marginal", False),
                "debug_urls": pending.get("debug_urls", {}),
                "debug_image_path": pending.get("debug_image_path"),
                "questions_range": range(1, exam.total_questions + 1),
            })

        exam.answer_key = corrected_key
        exam.answer_key_confirmed = True
        exam.save(update_fields=["answer_key", "answer_key_confirmed", "updated_at"])

        if session_key in request.session:
            del request.session[session_key]

        messages.success(request, "Answer key confirmed. You can now upload student sheets.")
        return redirect("omr:exam_detail", pk=exam.pk)

    pending = request.session.get(session_key)
    if not pending:
        messages.info(request, "No pending answer key data. Please upload an image first.")
        return redirect("omr:answer_key_upload", pk=exam.pk)

    return render(request, "omr/answer_key_review.html", {
        "exam": exam,
        "tmpl": tmpl,
        "detected": pending["answers"],
        "confidence": pending["confidence"],
        "per_question": pending.get("per_question", {}),
        "flagged": pending["flagged_questions"],
        "quality_warnings": pending.get("quality_warnings", []),
        "perspective_corrected": pending.get("perspective_corrected", False),
        "manual_entry": pending.get("manual_entry", False),
        "answer_key_needs_review": pending.get("answer_key_needs_review", False),
        "quality_marginal": pending.get("quality_marginal", False),
        "debug_urls": pending.get("debug_urls", {}),
        "debug_image_path": pending.get("debug_image_path"),
        "questions_range": range(1, exam.total_questions + 1),
    })


# ---------------------------------------------------------------------------
# 5a. Student Sheet — Upload & Process
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_student_upload(request, pk):
    guard = _require_staff(request)
    if guard:
        return guard

    exam = _get_school_exam(request, pk)

    if not exam.has_answer_key:
        messages.error(request, "Please confirm the answer key before uploading student sheets.")
        return redirect("omr:answer_key_upload", pk=exam.pk)

    school = get_effective_school(request)
    tmpl = get_processing_template(school, exam.template_type) or get_template(exam.template_type)

    if request.method == "POST":
        student_name = request.POST.get("student_name", "").strip()
        class_name = request.POST.get("class_name", exam.class_name).strip()
        upload_mode = request.POST.get("upload_mode", "file")

        if not student_name:
            messages.error(request, "Student name is required.")
            return render(request, "omr/student_upload.html", {"exam": exam, "post": request.POST})

        if upload_mode == "manual":
            session_key = f"omr_st_{exam.pk}"
            request.session[session_key] = {
                "student_name": student_name,
                "class_name": class_name,
                "answers": {str(q): "" for q in range(1, exam.total_questions + 1)},
                "confidence": {},
                "flagged_questions": list(range(1, exam.total_questions + 1)),
                "quality_warnings": [],
                "manual_entry": True,
                "per_question": {},
                "debug_urls": {},
            }
            return redirect("omr:student_review", pk=exam.pk)

        image_file = request.FILES.get("image")
        if not image_file:
            messages.error(request, "Please select an image file.")
            return render(request, "omr/student_upload.html", {"exam": exam, "post": request.POST})

        tmp_path, upload_err = _save_temp_image(image_file)
        if upload_err:
            messages.error(request, upload_err)
            return render(request, "omr/student_upload.html", {"exam": exam, "post": request.POST})

        quality_data = enhanced_quality_check(tmp_path, tmpl)
        result = process_omr_scan(tmp_path, tmpl, save_debug=True)
        _delete_temp_image(tmp_path)

        if not result["success"]:
            for tip in result.get("capture_guidance") or CAPTURE_GUIDANCE_LINES:
                messages.info(request, tip)
            messages.error(request, result.get("error", "Image processing failed."))
            return render(request, "omr/student_upload.html", {
                "exam": exam,
                "post": request.POST,
                "processing_error": result.get("error"),
                "quality_warnings": quality_data.get("warnings", []),
            })

        session_key = f"omr_st_{exam.pk}"
        request.session[session_key] = {
            "student_name": student_name,
            "class_name": class_name,
            "answers": result["answers"],
            "raw_cv_answers": dict(result["answers"]),
            "confidence": result["confidence"],
            "option_details": result.get("option_details", {}),
            "per_question": result.get("per_question", {}),
            "flagged_questions": result["flagged_questions"],
            "perspective_corrected": result["perspective_corrected"],
            "perspective_quality": result.get("perspective_quality", {}),
            "registration_marks_found": result.get("registration_marks_found", 0),
            "quality_warnings": quality_data.get("warnings", []),
            "coverage_ratio": result.get("coverage_ratio", 0),
            "coverage_warning": result.get("coverage_warning", False),
            "debug_image_path": result.get("debug_image_path"),
            "debug_urls": result.get("debug_urls", {}),
            "used_blank_subtraction": result.get("used_blank_subtraction", False),
            "manual_entry": False,
            "quality_marginal": result.get("quality_marginal", False),
        }
        n_flag = len(result.get("flagged_questions") or [])
        if n_flag > 8:
            messages.info(
                request,
                f"{n_flag} questions were flagged for review (unclear or low confidence). "
                "Please check the highlighted items on the next screen before saving — this avoids unfair marks.",
            )
        elif not result.get("used_blank_subtraction"):
            messages.info(
                request,
                "Tip: upload a calibrated blank sheet for this template to improve accuracy (OMR → Calibrate).",
            )
        if result.get("quality_marginal"):
            messages.warning(
                request,
                "Photo quality is marginal — answers were read with extra safeguards. "
                "Please verify highlighted questions before saving.",
            )
        return redirect("omr:student_review", pk=exam.pk)

    capture_guidance = list(get_capture_guidance(exam.template_type)) + list(CAPTURE_GUIDANCE_LINES)
    return render(request, "omr/student_upload.html", {
        "exam": exam,
        "default_class": exam.class_name,
        "capture_guidance": capture_guidance,
    })


# ---------------------------------------------------------------------------
# 5b. Student Sheet — Review & Save
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_student_review(request, pk):
    guard = _require_staff(request)
    if guard:
        return guard

    exam = _get_school_exam(request, pk)
    school = get_effective_school(request)
    tmpl = get_processing_template(school, exam.template_type) or get_template(exam.template_type)
    session_key = f"omr_st_{exam.pk}"

    if request.method == "POST":
        pending = request.session.get(session_key, {})
        student_name = pending.get("student_name", request.POST.get("student_name", ""))
        class_name = pending.get("class_name", exam.class_name)

        # Build corrected answers from POST
        corrected_answers: dict[str, str] = {}
        for q in range(1, exam.total_questions + 1):
            val = request.POST.get(f"q_{q}", "").strip().upper()
            if val in ("BLANK", ""):
                corrected_answers[str(q)] = "blank"
            elif val == "MULTIPLE":
                corrected_answers[str(q)] = "multiple"
            elif val == "UNCERTAIN":
                corrected_answers[str(q)] = "uncertain"
            elif val in tmpl["options"]:
                corrected_answers[str(q)] = val
            else:
                corrected_answers[str(q)] = "blank"

        score_data = calculate_score(corrected_answers, exam.answer_key, exam.total_questions)
        raw_cv = pending.get("raw_cv_answers") or pending.get("answers", {})

        school = get_effective_school(request)
        OmrResult.objects.create(
            school=school,
            exam=exam,
            student_name=student_name,
            class_name=class_name,
            subject=exam.subject,
            template_type=exam.template_type,
            detected_answers=corrected_answers,
            raw_cv_answers=raw_cv,
            cv_per_question=pending.get("per_question", {}),
            answer_key=exam.answer_key,
            per_question_result=score_data["per_question_result"],
            score=score_data["score"],
            total_questions=score_data["total_questions"],
            percentage=score_data["percentage"],
            correct_count=score_data["correct_count"],
            wrong_count=score_data["wrong_count"],
            blank_count=score_data["blank_count"],
            multiple_answer_count=score_data["multiple_answer_count"],
            uncertain_count=score_data.get("uncertain_count", 0),
            flagged_questions=[],
            created_by=request.user,
        )

        if session_key in request.session:
            del request.session[session_key]

        messages.success(
            request,
            f"{student_name}: {score_data['score']}/{score_data['total_questions']} "
            f"({score_data['percentage']}%) — saved."
        )

        # Allow chaining: "save and upload next"
        if request.POST.get("action") == "save_next":
            return redirect("omr:student_upload", pk=exam.pk)
        return redirect("omr:results", pk=exam.pk)

    pending = request.session.get(session_key)
    if not pending:
        messages.info(request, "No pending student sheet data. Please upload an image first.")
        return redirect("omr:student_upload", pk=exam.pk)

    preview_score = calculate_score(
        pending["answers"], exam.answer_key, exam.total_questions
    )

    return render(request, "omr/student_review.html", {
        "exam": exam,
        "tmpl": tmpl,
        "student_name": pending["student_name"],
        "class_name": pending["class_name"],
        "detected": pending["answers"],
        "confidence": pending["confidence"],
        "option_details": pending.get("option_details", {}),
        "per_question": pending.get("per_question", {}),
        "flagged": pending["flagged_questions"],
        "quality_warnings": pending.get("quality_warnings", []),
        "perspective_corrected": pending.get("perspective_corrected", False),
        "perspective_quality": pending.get("perspective_quality", {}),
        "registration_marks_found": pending.get("registration_marks_found", 0),
        "coverage_ratio": pending.get("coverage_ratio", 0),
        "coverage_warning": pending.get("coverage_warning", False),
        "quality_marginal": pending.get("quality_marginal", False),
        "debug_image_path": pending.get("debug_image_path"),
        "debug_urls": pending.get("debug_urls", {}),
        "manual_entry": pending.get("manual_entry", False),
        "preview": preview_score,
        "questions_range": range(1, exam.total_questions + 1),
        "answer_key": exam.answer_key,
    })


# ---------------------------------------------------------------------------
# 6. Results
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_results(request, pk):
    guard = _require_staff(request)
    if guard:
        return guard

    exam = _get_school_exam(request, pk)
    results = exam.results.order_by("-percentage", "student_name")
    return render(request, "omr/results.html", {"exam": exam, "results": results})


@login_required
@feature_required("omr_marking")
def omr_result_detail(request, result_pk):
    guard = _require_staff(request)
    if guard:
        return guard

    school = get_effective_school(request)
    result = get_object_or_404(OmrResult, pk=result_pk, school=school)
    tmpl = get_template(result.template_type)

    # Build question breakdown with correct answer enrichment
    pqr = result.per_question_result or {}
    questions = []
    for q in range(1, result.total_questions + 1):
        q_str = str(q)
        qdata = pqr.get(q_str, {})
        questions.append({
            "number": q,
            "student_answer": qdata.get("student_answer", "blank"),
            "correct_answer": qdata.get("correct_answer", ""),
            "status": qdata.get("status", "wrong"),
        })

    return render(request, "omr/result_detail.html", {
        "result": result,
        "exam": result.exam,
        "questions": questions,
        "tmpl": tmpl,
    })


@login_required
@feature_required("omr_marking")
@require_POST
def omr_result_delete(request, result_pk):
    guard = _require_staff(request)
    if guard:
        return guard

    school = get_effective_school(request)
    result = get_object_or_404(OmrResult, pk=result_pk, school=school)
    exam_pk = result.exam_id
    name = result.get_student_display_name()
    result.delete()
    messages.success(request, f"Result for {name} deleted.")
    return redirect("omr:results", pk=exam_pk)


# ---------------------------------------------------------------------------
# 7. Analysis
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_analysis(request, pk):
    guard = _require_staff(request)
    if guard:
        return guard

    exam = _get_school_exam(request, pk)
    analysis = get_exam_analysis(exam.results.all())
    return render(request, "omr/analysis.html", {
        "exam": exam,
        "analysis": analysis,
        "dist_labels": list(analysis["score_distribution"].keys()),
        "dist_values": list(analysis["score_distribution"].values()),
    })


# ---------------------------------------------------------------------------
# 8. CSV Export
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_export_csv(request, pk):
    guard = _require_staff(request)
    if guard:
        return guard

    exam = _get_school_exam(request, pk)
    results = exam.results.order_by("student_name")

    response = HttpResponse(content_type="text/csv")
    fname = f"omr_{exam.title.replace(' ', '_')}_{exam.date}.csv"
    response["Content-Disposition"] = f'attachment; filename="{fname}"'

    writer = csv.writer(response)

    # Header row — dynamic Q columns up to total_questions
    base_headers = [
        "Student Name", "Class", "Subject", "Exam Title",
        "Score", "Total", "Percentage", "Correct", "Wrong", "Blank", "Multiple Answers", "Uncertain",
    ]
    q_headers = [f"Q{q}" for q in range(1, exam.total_questions + 1)]
    writer.writerow(base_headers + q_headers)

    for r in results:
        pqr = r.per_question_result or {}
        q_answers = [
            pqr.get(str(q), {}).get("student_answer", "blank")
            for q in range(1, exam.total_questions + 1)
        ]
        row = [
            r.get_student_display_name(),
            r.class_name,
            r.subject,
            exam.title,
            r.score,
            r.total_questions,
            f"{r.percentage:.1f}%",
            r.correct_count,
            r.wrong_count,
            r.blank_count,
            r.multiple_answer_count,
            getattr(r, "uncertain_count", 0),
        ] + q_answers
        writer.writerow(row)

    return response


# ---------------------------------------------------------------------------
# 9. Bulk Upload
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_bulk_upload(request, pk):
    guard = _require_staff(request)
    if guard:
        return guard

    exam = _get_school_exam(request, pk)

    if not exam.has_answer_key:
        messages.error(request, "Please confirm the answer key before uploading student sheets.")
        return redirect("omr:answer_key_upload", pk=exam.pk)

    school = get_effective_school(request)
    tmpl = get_processing_template(school, exam.template_type) or get_template(exam.template_type)

    if request.method == "POST":
        images = request.FILES.getlist("images")
        names_raw = request.POST.get("student_names", "")
        student_names = [n.strip() for n in names_raw.splitlines() if n.strip()]
        class_name = request.POST.get("class_name", exam.class_name).strip()

        if not images:
            messages.error(request, "Please select at least one image.")
            return render(request, "omr/bulk_upload.html", {"exam": exam})

        if student_names and len(student_names) != len(images):
            messages.error(
                request,
                f"You provided {len(student_names)} names but {len(images)} images. "
                "Either match them 1-to-1 or leave names blank."
            )
            return render(request, "omr/bulk_upload.html", {"exam": exam, "post": request.POST})

        saved = 0
        errors = []

        for idx, img_file in enumerate(images):
            sname = student_names[idx] if student_names else f"Student {idx + 1}"
            tmp_path, upload_err = _save_temp_image(img_file)
            if upload_err:
                errors.append(f"{sname}: {upload_err}")
                continue

            result = process_omr_image(tmp_path, tmpl)
            _delete_temp_image(tmp_path)

            if not result["success"]:
                errors.append(f"{sname}: {result.get('error', 'Processing failed.')}")
                continue

            score_data = calculate_score(result["answers"], exam.answer_key, exam.total_questions)
            OmrResult.objects.create(
                school=school,
                exam=exam,
                student_name=sname,
                class_name=class_name,
                subject=exam.subject,
                template_type=exam.template_type,
                detected_answers=result["answers"],
                raw_cv_answers=dict(result["answers"]),
                cv_per_question=result.get("per_question", {}),
                answer_key=exam.answer_key,
                per_question_result=score_data["per_question_result"],
                score=score_data["score"],
                total_questions=score_data["total_questions"],
                percentage=score_data["percentage"],
                correct_count=score_data["correct_count"],
                wrong_count=score_data["wrong_count"],
                blank_count=score_data["blank_count"],
                multiple_answer_count=score_data["multiple_answer_count"],
                uncertain_count=score_data.get("uncertain_count", 0),
                flagged_questions=result["flagged_questions"],
                created_by=request.user,
            )
            saved += 1

        if errors:
            for e in errors:
                messages.warning(request, e)
        if saved:
            messages.success(request, f"{saved} student sheet(s) processed and saved.")
            messages.info(
                request,
                "Bulk mode does not show the per-question review screen. Open results below and use "
                "“Edit” / detail if any score looks wrong — faint marks or tilt often need a quick fix.",
            )
        return redirect("omr:results", pk=exam.pk)

    return render(request, "omr/bulk_upload.html", {
        "exam": exam,
        "default_class": exam.class_name,
    })


# ---------------------------------------------------------------------------
# 10. Printable Answer Sheet
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_printable_sheet(request, template_id):
    tmpl = get_template(template_id)
    if not tmpl:
        messages.error(request, "Unknown template.")
        return redirect("omr:dashboard")
    exam_id = request.GET.get("exam_id", "")
    student_id = request.GET.get("student_id", "")
    qr_b64 = None
    if exam_id or student_id:
        from core.qr_utils import generate_qr_code_base64

        payload = f"omr|exam_id={exam_id}|student_id={student_id}|template_id={template_id}"
        qr_b64 = generate_qr_code_base64(payload)
    return render(request, "omr/printable_sheet.html", {
        "tmpl": tmpl,
        "qr_b64": qr_b64,
    })


# ---------------------------------------------------------------------------
# Section B — manual mark entry for OMR exams
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_section_b_entry(request, pk):
    """Bulk-enter Section B scores for every student in an OMR exam."""
    school = get_effective_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        messages.error(request, "You do not have permission to enter Section B scores.")
        return redirect("omr:dashboard")
    exam = get_object_or_404(OmrExam, pk=pk, school=school)

    from students.models import Student
    students = Student.objects.filter(school=school, class_name=exam.class_name).order_by("admission_number")
    omr_results = {r.student_id: r for r in OmrResult.objects.filter(exam=exam)}
    existing_b = {b.student_id: b for b in OmrExamSectionB.objects.filter(exam=exam)}

    if request.method == "POST":
        section_b_max = float(request.POST.get("section_b_max", "40") or 40)
        # Apply the new max to ALL existing records for consistency
        OmrExamSectionB.objects.filter(exam=exam).update(section_b_max_score=section_b_max)
        saved = 0
        errors = []
        for student in students:
            raw = request.POST.get(f"score_{student.pk}", "").strip()
            if raw == "":
                continue
            try:
                score_val = float(raw)
                if score_val < 0 or score_val > section_b_max:
                    errors.append(f"{student}: score {score_val} out of range (0–{section_b_max}).")
                    continue
                override_raw = request.POST.get(f"override_{student.pk}", "").strip()
                override_val = float(override_raw) if override_raw else None

                omr_res = omr_results.get(student.pk)
                sec_a_score = float(omr_res.score) if omr_res else None
                sec_a_max = float(exam.total_questions) if exam.total_questions else None

                OmrExamSectionB.objects.update_or_create(
                    exam=exam,
                    student=student,
                    defaults={
                        "school": school,
                        "student_name": student.user.get_full_name(),
                        "section_b_max_score": section_b_max,
                        "section_b_score": score_val,
                        "section_a_omr_score": sec_a_score,
                        "section_a_max_score": sec_a_max,
                        "section_a_override": override_val,
                        "notes": request.POST.get(f"notes_{student.pk}", "").strip(),
                        "created_by": request.user,
                    },
                )
                saved += 1
            except ValueError:
                errors.append(f"{student}: invalid score '{raw}'.")
        for err in errors:
            messages.warning(request, err)
        if saved:
            messages.success(request, f"{saved} Section B score(s) saved.")
        return redirect("omr:section_b_entry", pk=exam.pk)

    rows = []
    for student in students:
        omr_res = omr_results.get(student.pk)
        sec_b = existing_b.get(student.pk)
        rows.append({
            "student": student,
            "sec_a_score": omr_res.score if omr_res else "—",
            "sec_a_pct": omr_res.percentage if omr_res else "—",
            "sec_b_score": sec_b.section_b_score if sec_b else "",
            "override": sec_b.section_a_override if sec_b and sec_b.section_a_override is not None else "",
            "notes": sec_b.notes if sec_b else "",
            "total": sec_b.total_raw_score if sec_b else "—",
        })

    section_b_max = exam.section_b_scores.first().section_b_max_score if exam.section_b_scores.exists() else 40

    return render(request, "omr/section_b_entry.html", {
        "school": school,
        "exam": exam,
        "rows": rows,
        "section_b_max": section_b_max,
    })


# ---------------------------------------------------------------------------
# OMR Testing & Debug Page
# ---------------------------------------------------------------------------

@login_required
@feature_required("omr_marking")
def omr_testing_page(request):
    """
    OMR Testing/Debug Page
    Upload an image and see detailed detection results including:
    - Perspective-corrected sheet
    - Detected answer boxes overlay
    - Fill scores for every option
    - Final detected answers
    - Confidence scores
    - Flagged questions
    """
    guard = _require_staff(request)
    if guard:
        return guard

    templates = list_templates()
    result_data = None
    quality_data = None

    if request.method == "POST":
        template_type = request.POST.get("template_type", "bece_60_ae")
        school = get_effective_school(request)
        tmpl = get_processing_template(school, template_type) or get_template(template_type)

        image_file = request.FILES.get("image")
        if not image_file:
            messages.error(request, "Please select an image file to test.")
            return render(request, "omr/testing_page.html", {"templates": templates})

        tmp_path, upload_err = _save_temp_image(image_file)
        if upload_err:
            messages.error(request, upload_err)
            return render(request, "omr/testing_page.html", {"templates": templates})

        quality_data = enhanced_quality_check(tmp_path, tmpl)
        result = process_omr_scan(tmp_path, tmpl, save_debug=True)
        _delete_temp_image(tmp_path)

        if not result["success"]:
            for tip in result.get("capture_guidance") or CAPTURE_GUIDANCE_LINES:
                messages.info(request, tip)
            messages.error(request, result.get("error", "Processing failed."))
        else:
            questions_detail = []
            for q_num in range(1, tmpl["total_questions"] + 1):
                q_str = str(q_num)
                option_scores = result.get("option_details", {}).get(q_str, {})
                pq = result.get("per_question", {}).get(q_str, {})
                questions_detail.append({
                    "number": q_num,
                    "answer": result["answers"].get(q_str, "blank"),
                    "status": pq.get("status", ""),
                    "confidence": result["confidence"].get(q_str, 0),
                    "confidence_level": pq.get("confidence_level", ""),
                    "option_scores": option_scores,
                    "is_flagged": q_num in result["flagged_questions"],
                })

            result_data = {
                "success": result["success"],
                "perspective_corrected": result["perspective_corrected"],
                "perspective_quality": result.get("perspective_quality", {}),
                "registration_marks_found": result.get("registration_marks_found", 0),
                "coverage_ratio": result.get("coverage_ratio", 0),
                "coverage_warning": result.get("coverage_warning", False),
                "quality_marginal": result.get("quality_marginal", False),
                "used_blank_subtraction": result.get("used_blank_subtraction", False),
                "template_id": result["template_id"],
                "questions": questions_detail,
                "flagged_count": len(result["flagged_questions"]),
                "debug_image_path": result.get("debug_image_path"),
                "debug_urls": result.get("debug_urls", {}),
            }

    return render(request, "omr/testing_page.html", {
        "templates": templates,
        "result": result_data,
        "quality": quality_data,
    })


def _calibration_build_from_geometry(tmpl: dict, geo: dict) -> dict:
    """Build calibrated_config dict from JSON posted by the drag/drop calibration UI."""
    from .omr_templates_v2 import _generate_regions_from_grid

    tw = int(tmpl["image_width"])
    th = int(tmpl["image_height"])
    qpc = int(tmpl["questions_per_column"])
    box_y_off = int(geo.get("box_y_offset", tmpl.get("box_y_offset", 2)))
    options = tmpl["options"]

    img_w = float(geo.get("image_natural_width") or tw)
    img_h = float(geo.get("image_natural_height") or th)
    sx = tw / img_w if img_w else 1.0
    sy = th / img_h if img_h else 1.0

    def _scale_rect(b: dict) -> dict:
        return {
            "x": int(round(float(b["x"]) * sx)),
            "y": int(round(float(b["y"]) * sy)),
            "w": int(round(float(b["w"]) * sx)),
            "h": int(round(float(b["h"]) * sy)),
        }

    row_h = max(8, int(round(float(geo["row_height"]) * sy)))
    col_payloads = geo["columns"]
    columns = []
    box_ws: list[int] = []
    box_hs: list[int] = []

    for col in col_payloads:
        scaled = {k: _scale_rect(v) for k, v in col["boxes"].items()}
        options_x = {opt: scaled[opt]["x"] for opt in options}
        y0 = min(scaled[o]["y"] for o in options)
        for o in options:
            box_ws.append(scaled[o]["w"])
            box_hs.append(scaled[o]["h"])
        y_start = max(0, y0 - box_y_off)
        columns.append({
            "x_start": options_x[options[0]],
            "y_start": y_start,
            "row_height": row_h,
            "options_x": options_x,
        })

    box_w = int(round(sum(box_ws) / max(1, len(box_ws))))
    box_h = int(round(sum(box_hs) / max(1, len(box_hs))))

    opt0 = options[0]
    opt1 = options[1] if len(options) > 1 else options[0]
    ow = columns[0]["options_x"][opt1] - columns[0]["options_x"][opt0]
    option_gap = max(0, ow - box_w)

    column_configs = [
        {"x_start": c["x_start"], "y_start": c["y_start"], "row_height": c["row_height"]}
        for c in columns
    ]

    regions = _generate_regions_from_grid(
        col_configs=columns,
        rows_per_col=qpc,
        box_w=box_w,
        box_h=box_h,
        box_y_offset=box_y_off,
        options=options,
    )

    return {
        "column_configs": column_configs,
        "questions_per_column": qpc,
        "option_width": ow,
        "option_gap": option_gap,
        "box_width": box_w,
        "box_height": box_h,
        "box_y_offset": box_y_off,
        "answer_regions": regions,
        "image_width": tw,
        "image_height": th,
    }


@login_required
@feature_required("omr_marking")
def omr_calibration_page(request, template_id):
    """
    Visual drag/resize calibration + blank sheet upload for template subtraction.
    """
    guard = _require_staff(request)
    if guard:
        return guard

    school = get_effective_school(request)
    tmpl = get_template(template_id)
    if not tmpl:
        messages.error(request, "Unknown template.")
        return redirect("omr:dashboard")

    calibration_result = None
    cal = OmrTemplateCalibration.objects.filter(school=school, template_id=template_id).first()
    initial_regions_source = None
    if cal and cal.calibrated_config and cal.calibrated_config.get("answer_regions"):
        initial_regions_source = cal.calibrated_config["answer_regions"]
    else:
        initial_regions_source = tmpl["answer_regions"]

    if request.method == "POST":
        blank_file = request.FILES.get("blank_sheet")
        geometry_raw = (request.POST.get("geometry_json") or "").strip()

        if geometry_raw:
            import json

            try:
                geo = json.loads(geometry_raw)
                calibrated = _calibration_build_from_geometry(tmpl, geo)
                tmpl_updates = {
                    k: tmpl[k]
                    for k in (
                        "min_fill_ratio",
                        "strong_fill_ratio",
                        "min_difference_from_second",
                        "min_mark_area_ratio",
                        "strong_mark_area_ratio",
                        "min_gap_from_second",
                        "uncertainty_gap",
                        "inner_zone_ratio",
                        "sheet_design",
                        "legacy_mode",
                    )
                    if k in tmpl
                }
                calibrated.update(tmpl_updates)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                messages.error(request, f"Invalid calibration data: {exc}")
                err_blank_url = ""
                if cal and cal.blank_sheet:
                    try:
                        err_blank_url = cal.blank_sheet.url
                    except Exception:
                        pass
                return render(request, "omr/calibration_page.html", {
                    "tmpl": tmpl,
                    "calibration_points": tmpl.get("calibration_points", {}),
                    "result": None,
                    "initial_regions_json": initial_regions_source,
                    "template_meta_json": {
                        "template_id": tmpl["template_id"],
                        "image_width": tmpl["image_width"],
                        "image_height": tmpl["image_height"],
                        "options": tmpl["options"],
                        "questions_per_column": tmpl["questions_per_column"],
                        "columns": tmpl.get("columns", len(tmpl["column_configs"])),
                        "box_y_offset": tmpl.get("box_y_offset", 2),
                    },
                    "has_saved_blank": bool(cal and cal.blank_sheet),
                    "blank_preview_url": err_blank_url,
                })
        else:
            # Legacy numeric fallback
            first_y = int(request.POST.get("first_row_y", tmpl["calibration_points"]["first_row_y"]))
            last_y = int(request.POST.get("last_row_y", tmpl["calibration_points"]["last_row_y"]))
            qpc = tmpl["questions_per_column"]
            row_h = max(8, int(round((last_y - first_y) / max(1, qpc - 1))))
            base_reg = tmpl["answer_regions"][0]
            delta_a = int(request.POST.get("opt_A", base_reg["boxes"]["A"]["x"])) - base_reg["boxes"]["A"]["x"]
            columns = []
            ncols = tmpl.get("columns", len(tmpl["column_configs"]))
            for ci in range(ncols):
                idx = ci * qpc
                reg = tmpl["answer_regions"][idx]
                options_x = {o: int(reg["boxes"][o]["x"]) + delta_a for o in tmpl["options"]}
                columns.append({
                    "x_start": options_x[tmpl["options"][0]],
                    "y_start": first_y,
                    "row_height": row_h,
                    "options_x": options_x,
                })
            from .omr_templates_v2 import _generate_regions_from_grid

            regions = _generate_regions_from_grid(
                col_configs=columns,
                rows_per_col=qpc,
                box_w=tmpl["box_width"],
                box_h=tmpl["box_height"],
                box_y_offset=tmpl.get("box_y_offset", 2),
                options=tmpl["options"],
            )
            column_configs = [{"x_start": c["x_start"], "y_start": c["y_start"], "row_height": c["row_height"]} for c in columns]
            calibrated = {
                "column_configs": column_configs,
                "questions_per_column": qpc,
                "option_width": tmpl.get("option_width", 43),
                "option_gap": tmpl.get("option_gap", 7),
                "box_width": tmpl["box_width"],
                "box_height": tmpl["box_height"],
                "box_y_offset": tmpl.get("box_y_offset", 2),
                "answer_regions": regions,
                "image_width": tmpl["image_width"],
                "image_height": tmpl["image_height"],
            }

        obj, _ = OmrTemplateCalibration.objects.update_or_create(
            school=school,
            template_id=template_id,
            defaults={
                "template_name": tmpl.get("name", template_id),
                "calibrated_config": calibrated,
            },
        )
        if blank_file:
            try:
                validate_image_upload(blank_file)
            except InvalidUploadError as exc:
                messages.warning(
                    request,
                    f"Calibration saved, but blank sheet was not stored: {exc.message}",
                )
                blank_file = None
            else:
                obj.blank_sheet = blank_file
                obj.save(update_fields=["blank_sheet", "updated_at"])

        calibration_result = {"saved": True, "questions": len(calibrated["answer_regions"])}
        if blank_file:
            messages.success(
                request,
                "Calibration saved. Blank template image stored for subtraction.",
            )
        else:
            messages.success(request, "Calibration coordinates saved for your school.")

        cal = obj
        initial_regions_source = calibrated["answer_regions"]

    blank_preview_url = ""
    if cal and cal.blank_sheet:
        try:
            blank_preview_url = cal.blank_sheet.url
        except Exception:
            blank_preview_url = ""

    return render(request, "omr/calibration_page.html", {
        "tmpl": tmpl,
        "calibration_points": tmpl.get("calibration_points", {}),
        "result": calibration_result,
        "initial_regions_json": initial_regions_source,
        "template_meta_json": {
            "template_id": tmpl["template_id"],
            "image_width": tmpl["image_width"],
            "image_height": tmpl["image_height"],
            "options": tmpl["options"],
            "questions_per_column": tmpl["questions_per_column"],
            "columns": tmpl.get("columns", len(tmpl["column_configs"])),
            "box_y_offset": tmpl.get("box_y_offset", 2),
        },
        "has_saved_blank": bool(cal and cal.blank_sheet),
        "blank_preview_url": blank_preview_url,
    })
