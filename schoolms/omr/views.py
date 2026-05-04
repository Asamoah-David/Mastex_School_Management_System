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
from core.utils import get_effective_school

from .analysis import get_exam_analysis
from .models import OmrExam, OmrResult, OmrExamSectionB
from .omr_templates import get_template, list_templates
from .processor import process_omr_image, quality_check
from .scoring import apply_manual_corrections, calculate_score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEMP_DIR = "omr/temp"


def _save_temp_image(uploaded_file) -> str | None:
    """Save an uploaded image to a temporary location; return its path."""
    try:
        ext = os.path.splitext(uploaded_file.name)[1].lower() or ".jpg"
        temp_name = f"{TEMP_DIR}/{uuid.uuid4().hex}{ext}"
        path = default_storage.save(temp_name, ContentFile(uploaded_file.read()))
        return default_storage.path(path)
    except Exception:
        return None


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
    tmpl = get_template(exam.template_type)

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
            }
            return redirect("omr:answer_key_review", pk=exam.pk)

        image_file = request.FILES.get("image")
        if not image_file:
            messages.error(request, "Please select an image file to upload.")
            return render(request, "omr/answer_key_upload.html", {"exam": exam})

        tmp_path = _save_temp_image(image_file)
        if not tmp_path:
            messages.error(request, "Failed to save uploaded image. Please try again.")
            return render(request, "omr/answer_key_upload.html", {"exam": exam})

        quality_data = quality_check(tmp_path)
        result = process_omr_image(tmp_path, tmpl)
        _delete_temp_image(tmp_path)

        if not result["success"]:
            messages.error(request, result.get("error", "Image processing failed."))
            return render(request, "omr/answer_key_upload.html", {
                "exam": exam,
                "processing_error": result.get("error"),
            })

        session_key = f"omr_ak_{exam.pk}"
        request.session[session_key] = {
            "answers": result["answers"],
            "confidence": result["confidence"],
            "flagged_questions": result["flagged_questions"],
            "perspective_corrected": result["perspective_corrected"],
            "quality_warnings": quality_data.get("warnings", []),
            "manual_entry": False,
        }
        return redirect("omr:answer_key_review", pk=exam.pk)

    return render(request, "omr/answer_key_upload.html", {"exam": exam})


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
    tmpl = get_template(exam.template_type)
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
                "flagged": pending.get("flagged_questions", []),
                "quality_warnings": pending.get("quality_warnings", []),
                "perspective_corrected": pending.get("perspective_corrected", False),
                "manual_entry": pending.get("manual_entry", False),
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
        "flagged": pending["flagged_questions"],
        "quality_warnings": pending.get("quality_warnings", []),
        "perspective_corrected": pending.get("perspective_corrected", False),
        "manual_entry": pending.get("manual_entry", False),
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

    tmpl = get_template(exam.template_type)

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
            }
            return redirect("omr:student_review", pk=exam.pk)

        image_file = request.FILES.get("image")
        if not image_file:
            messages.error(request, "Please select an image file.")
            return render(request, "omr/student_upload.html", {"exam": exam, "post": request.POST})

        tmp_path = _save_temp_image(image_file)
        if not tmp_path:
            messages.error(request, "Failed to save uploaded image.")
            return render(request, "omr/student_upload.html", {"exam": exam, "post": request.POST})

        quality_data = quality_check(tmp_path)
        result = process_omr_image(tmp_path, tmpl)
        _delete_temp_image(tmp_path)

        if not result["success"]:
            messages.error(request, result.get("error", "Image processing failed."))
            return render(request, "omr/student_upload.html", {
                "exam": exam,
                "post": request.POST,
                "processing_error": result.get("error"),
            })

        # ── Fast-mode auto-save ──────────────────────────────────────────────
        # If the teacher enabled "fast mode" AND detection is clean (no flags,
        # no quality warnings), save the result immediately without review.
        auto_save = request.POST.get("auto_save") == "1"
        has_flags = bool(result["flagged_questions"])
        has_quality_issues = bool(quality_data.get("warnings"))

        if auto_save and not has_flags and not has_quality_issues:
            score_data = calculate_score(result["answers"], exam.answer_key, exam.total_questions)
            school = get_effective_school(request)
            OmrResult.objects.create(
                school=school,
                exam=exam,
                student_name=student_name,
                class_name=class_name,
                subject=exam.subject,
                template_type=exam.template_type,
                detected_answers=result["answers"],
                answer_key=exam.answer_key,
                per_question_result=score_data["per_question_result"],
                score=score_data["score"],
                total_questions=score_data["total_questions"],
                percentage=score_data["percentage"],
                correct_count=score_data["correct_count"],
                wrong_count=score_data["wrong_count"],
                blank_count=score_data["blank_count"],
                multiple_answer_count=score_data["multiple_answer_count"],
                flagged_questions=[],
                created_by=request.user,
            )
            messages.success(
                request,
                f"✓ {student_name}: {score_data['score']}/{score_data['total_questions']} "
                f"({score_data['percentage']:.1f}%) — saved."
            )
            return redirect("omr:student_upload", pk=exam.pk)

        # ── Standard path: go to review page ────────────────────────────────
        session_key = f"omr_st_{exam.pk}"
        request.session[session_key] = {
            "student_name": student_name,
            "class_name": class_name,
            "answers": result["answers"],
            "confidence": result["confidence"],
            "flagged_questions": result["flagged_questions"],
            "quality_warnings": quality_data.get("warnings", []),
            "manual_entry": False,
        }
        return redirect("omr:student_review", pk=exam.pk)

    return render(request, "omr/student_upload.html", {
        "exam": exam,
        "default_class": exam.class_name,
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
    tmpl = get_template(exam.template_type)
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
            elif val in tmpl["options"]:
                corrected_answers[str(q)] = val
            else:
                corrected_answers[str(q)] = "blank"

        score_data = calculate_score(corrected_answers, exam.answer_key, exam.total_questions)

        school = get_effective_school(request)
        OmrResult.objects.create(
            school=school,
            exam=exam,
            student_name=student_name,
            class_name=class_name,
            subject=exam.subject,
            template_type=exam.template_type,
            detected_answers=corrected_answers,
            answer_key=exam.answer_key,
            per_question_result=score_data["per_question_result"],
            score=score_data["score"],
            total_questions=score_data["total_questions"],
            percentage=score_data["percentage"],
            correct_count=score_data["correct_count"],
            wrong_count=score_data["wrong_count"],
            blank_count=score_data["blank_count"],
            multiple_answer_count=score_data["multiple_answer_count"],
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
        "flagged": pending["flagged_questions"],
        "quality_warnings": pending.get("quality_warnings", []),
        "perspective_corrected": pending.get("perspective_corrected", False),
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
        "Score", "Total", "Percentage", "Correct", "Wrong", "Blank", "Multiple Answers",
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

    tmpl = get_template(exam.template_type)

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

        school = get_effective_school(request)
        saved = 0
        errors = []

        for idx, img_file in enumerate(images):
            sname = student_names[idx] if student_names else f"Student {idx + 1}"
            tmp_path = _save_temp_image(img_file)
            if not tmp_path:
                errors.append(f"{sname}: could not save image.")
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
                answer_key=exam.answer_key,
                per_question_result=score_data["per_question_result"],
                score=score_data["score"],
                total_questions=score_data["total_questions"],
                percentage=score_data["percentage"],
                correct_count=score_data["correct_count"],
                wrong_count=score_data["wrong_count"],
                blank_count=score_data["blank_count"],
                multiple_answer_count=score_data["multiple_answer_count"],
                flagged_questions=result["flagged_questions"],
                created_by=request.user,
            )
            saved += 1

        if errors:
            for e in errors:
                messages.warning(request, e)
        if saved:
            messages.success(request, f"{saved} student sheet(s) processed and saved.")
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
    return render(request, "omr/printable_sheet.html", {"tmpl": tmpl})


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
