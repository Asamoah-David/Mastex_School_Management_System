"""
PDF Report Card Generator
=========================
Generates professional PDF report cards showing:
  - Student information header
  - CA Score (%) | Exam Score (%) | Final Score | Grade per subject
  - Term GPA & position
  - AI-generated teacher comments
  - School branding

Depends on ReportLab (already in requirements.txt).
"""
import io
import logging
from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from schools.features import is_feature_enabled

logger = logging.getLogger(__name__)


# ── Helper: get school from request ──────────────────────────────────────────

def _get_school(request):
    school = getattr(request.user, "school", None)
    if school:
        return school
    if request.user.is_superuser or getattr(request.user, "is_super_admin", False):
        from schools.models import School
        sid = request.session.get("current_school_id")
        if sid:
            return School.objects.filter(pk=sid).first()
    return None


# ── Core PDF builder ──────────────────────────────────────────────────────────

def _build_report_card_pdf_bytes(student, term, school):
    """Build and return raw PDF bytes for a single student's report card.

    Shows CA / Exam / Final breakdown per subject and any saved AI comment.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph,
            Spacer, HRFlowable,
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    except ImportError:
        raise RuntimeError("ReportLab is not installed. Run: pip install reportlab")

    from academics.models import (
        AssessmentScore, ExamScore, StudentResultSummary,
        GradingPolicy, get_grade_for_score, AIStudentComment,
    )
    from operations.models import StudentAttendance

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "SchoolTitle",
        parent=styles["Title"],
        fontSize=18,
        textColor=colors.HexColor("#1e3a5f"),
        spaceAfter=2,
        alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        "SubTitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#444444"),
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    heading2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=11,
        textColor=colors.HexColor("#1e3a5f"),
        spaceBefore=8,
        spaceAfter=4,
    )
    normal = ParagraphStyle(
        "NormalText",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
    )
    comment_style = ParagraphStyle(
        "Comment",
        parent=styles["Normal"],
        fontSize=9,
        leading=14,
        textColor=colors.HexColor("#333333"),
        leftIndent=6,
        rightIndent=6,
        borderPad=4,
    )

    # ── Get grading policy ────────────────────────────────────────────────────
    policy = GradingPolicy.get_active_policy(school)
    ca_weight = policy.ca_weight
    exam_weight = policy.exam_weight

    # ── Gather subject data ───────────────────────────────────────────────────
    subjects_data = []  # list of dicts

    if term:
        # Try StudentResultSummary first (pre-computed)
        summaries = list(
            StudentResultSummary.objects.filter(student=student, term=term)
            .select_related("subject")
            .order_by("subject__name")
        )
        if summaries:
            for s in summaries:
                subjects_data.append({
                    "subject": s.subject.name,
                    "ca": round(s.ca_score, 1),
                    "exam": round(s.exam_score, 1),
                    "final": round(s.final_score, 1),
                    "grade": s.grade or get_grade_for_score(school, s.final_score),
                })
        else:
            # Fall back: compute from AssessmentScore + ExamScore
            from academics.models import Subject
            subjects = Subject.objects.filter(school=school)
            for subj in subjects.order_by("name"):
                assessments = AssessmentScore.objects.filter(
                    student=student, subject=subj, term=term
                )
                exam_obj = ExamScore.objects.filter(
                    student=student, subject=subj, term=term
                ).first()

                if not assessments.exists() and not exam_obj:
                    continue

                ca_scores = [a.normalized_score for a in assessments]
                ca_avg = round(sum(ca_scores) / len(ca_scores), 1) if ca_scores else 0.0
                exam_score = round(exam_obj.normalized_score, 1) if exam_obj else 0.0
                final = round(
                    (ca_avg * ca_weight / 100) + (exam_score * exam_weight / 100), 1
                )
                grade = get_grade_for_score(school, final)
                subjects_data.append({
                    "subject": subj.name,
                    "ca": ca_avg,
                    "exam": exam_score,
                    "final": final,
                    "grade": grade,
                })

    # If no advanced scores, fall back to legacy Result model
    if not subjects_data:
        from academics.models import Result
        results_qs = Result.objects.filter(student=student).select_related("subject")
        if term:
            results_qs = results_qs.filter(term=term)
        for r in results_qs.order_by("subject__name"):
            subjects_data.append({
                "subject": r.subject.name,
                "ca": "—",
                "exam": "—",
                "final": r.percentage,
                "grade": r.grade,
            })

    # ── Attendance ────────────────────────────────────────────────────────────
    att_qs = StudentAttendance.objects.filter(student=student)
    if term:
        if hasattr(term, "start_date") and term.start_date:
            att_qs = att_qs.filter(date__gte=term.start_date)
        if hasattr(term, "end_date") and term.end_date:
            att_qs = att_qs.filter(date__lte=term.end_date)
    total_days = att_qs.count()
    present_days = att_qs.filter(status="present").count()
    att_rate = f"{round(present_days / total_days * 100)}%" if total_days else "N/A"
    att_text = f"{present_days}/{total_days} days ({att_rate})"

    # ── Position & GPA ────────────────────────────────────────────────────────
    position_text = "—"
    gpa_text = "—"
    if subjects_data:
        try:
            from academics.services import GradingService
            term_rankings = GradingService.calculate_class_rankings(
                student.class_name, term, school
            ) if (term and student.class_name) else {}
            pos = term_rankings.get(student.id)
            position_text = f"{pos}" if pos else "—"
            gpa = GradingService.calculate_term_gpa(student, term) if term else 0
            gpa_text = f"{gpa:.2f}" if gpa else "—"
        except Exception:
            pass

    # ── AI Comment ────────────────────────────────────────────────────────────
    ai_comment_text = ""
    try:
        term_name = term.name if term else ""
        ai_comment = AIStudentComment.objects.filter(
            student=student, school=school
        )
        if term_name:
            ai_comment = ai_comment.filter(term=term_name)
        ai_comment = ai_comment.order_by("-created_at").first()
        if ai_comment:
            ai_comment_text = ai_comment.content
    except Exception:
        pass

    # ── Build PDF flowable elements ───────────────────────────────────────────
    elements = []

    # Header
    elements.append(Paragraph(school.name.upper(), title_style))
    if school.address:
        elements.append(Paragraph(school.address, subtitle_style))
    if school.phone:
        elements.append(Paragraph(f"Tel: {school.phone}", subtitle_style))
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1e3a5f")))
    elements.append(Spacer(1, 4))

    report_title = f"STUDENT REPORT CARD"
    if term:
        report_title += f" — {term.name}"
    elements.append(Paragraph(report_title, title_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    elements.append(Spacer(1, 8))

    # Student info grid
    student_name = student.user.get_full_name() or student.user.username
    info_data = [
        ["Student Name:", student_name, "Admission No.:", student.admission_number or "—"],
        ["Class:", student.class_name or "—", "Academic Year:", school.academic_year or date.today().strftime("%Y/%Y")],
        ["Term:", term.name if term else "—", "Date Issued:", date.today().strftime("%d %b %Y")],
        ["Attendance:", att_text, "Term Position:", position_text],
    ]
    info_table = Table(info_data, colWidths=[3.5 * cm, 6 * cm, 3.5 * cm, 5 * cm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#1e3a5f")),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f7f9fc"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))

    # ── Results table ────────────────────────────────────────────────────────
    elements.append(Paragraph("Academic Performance", heading2))

    # Table header
    header_row = [
        Paragraph("<b>Subject</b>", normal),
        Paragraph(f"<b>CA Score\n({int(ca_weight)}%)</b>", normal),
        Paragraph(f"<b>Exam Score\n({int(exam_weight)}%)</b>", normal),
        Paragraph("<b>Final Score\n(/100)</b>", normal),
        Paragraph("<b>Grade</b>", normal),
        Paragraph("<b>Remarks</b>", normal),
    ]
    table_data = [header_row]

    def _grade_color(grade):
        g = (grade or "").upper()
        if g.startswith("A"):
            return colors.HexColor("#16a34a")
        if g.startswith("B"):
            return colors.HexColor("#2563eb")
        if g.startswith("C"):
            return colors.HexColor("#d97706")
        if g.startswith("D"):
            return colors.HexColor("#dc2626")
        if g == "F":
            return colors.HexColor("#991b1b")
        return colors.black

    def _remarks(score):
        try:
            s = float(score)
        except (ValueError, TypeError):
            return "—"
        if s >= 80: return "Excellent"
        if s >= 70: return "Very Good"
        if s >= 60: return "Good"
        if s >= 50: return "Pass"
        return "Needs Improvement"

    for row in subjects_data:
        grade = row["grade"]
        final = row["final"]
        table_data.append([
            Paragraph(row["subject"], normal),
            Paragraph(str(row["ca"]), normal),
            Paragraph(str(row["exam"]), normal),
            Paragraph(str(final), normal),
            Paragraph(f"<b>{grade}</b>", ParagraphStyle(
                "GradeCell", parent=normal,
                textColor=_grade_color(grade), fontSize=9,
            )),
            Paragraph(_remarks(final), normal),
        ])

    col_widths = [5.5 * cm, 2.8 * cm, 2.8 * cm, 2.8 * cm, 1.8 * cm, 3.5 * cm]
    results_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    results_table.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        # Body
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f0f4f8"), colors.white]),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c0c0c0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (0, -1), 6),
    ]))
    elements.append(results_table)

    # ── Grading key ──────────────────────────────────────────────────────────
    elements.append(Spacer(1, 6))
    key_text = (
        f"Grading: CA ({int(ca_weight)}%) + Exam ({int(exam_weight)}%) = Final Score (100%)  |  "
        "A=80–100 (Excellent)  B=70–79 (Very Good)  C=60–69 (Good)  D=50–59 (Pass)  F=0–49 (Fail)"
    )
    elements.append(Paragraph(key_text, ParagraphStyle(
        "GradingKey", parent=normal,
        fontSize=7.5, textColor=colors.HexColor("#666666"), spaceAfter=8,
    )))

    # ── Summary stats ─────────────────────────────────────────────────────────
    if subjects_data:
        numeric_finals = [r["final"] for r in subjects_data if isinstance(r["final"], (int, float))]
        if numeric_finals:
            avg_final = round(sum(numeric_finals) / len(numeric_finals), 1)
            summary_data = [
                ["Overall Average:", f"{avg_final}%", "GPA:", gpa_text,
                 "Term Position:", position_text],
            ]
            summary_table = Table(summary_data, colWidths=[3.5 * cm, 2 * cm, 1.5 * cm, 2 * cm, 3 * cm, 2 * cm])
            summary_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e8f0fe")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1e3a5f")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#9ab0d4")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            elements.append(summary_table)

    elements.append(Spacer(1, 14))

    # ── AI / Teacher Comment ──────────────────────────────────────────────────
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph("Class Teacher's Comment", heading2))
    if ai_comment_text:
        elements.append(Paragraph(ai_comment_text, comment_style))
    else:
        elements.append(Paragraph(
            "_____________________________________________________________"
            "_____________________________________________________________",
            comment_style,
        ))
    elements.append(Spacer(1, 10))

    # ── Signature row ─────────────────────────────────────────────────────────
    sig_data = [["Class Teacher:", "__________________________",
                 "Head Teacher:", "__________________________",
                 "Parent/Guardian:", "__________________________"]]
    sig_table = Table(sig_data, colWidths=[2.5 * cm, 4 * cm, 2.5 * cm, 4 * cm, 3 * cm, 4 * cm])
    sig_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, 0), "Helvetica-Bold"),
        ("FONTNAME", (4, 0), (4, 0), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (2, 0), (2, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (4, 0), (4, 0), colors.HexColor("#1e3a5f")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
    ]))
    elements.append(sig_table)
    elements.append(Spacer(1, 10))

    # ── Footer ────────────────────────────────────────────────────────────────
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    footer_text = (
        f"This is an official report card from {school.name}. "
        f"Generated on {date.today().strftime('%d %B %Y')} by Mastex SchoolOS."
    )
    elements.append(Paragraph(footer_text, ParagraphStyle(
        "Footer", parent=normal,
        fontSize=7.5, textColor=colors.HexColor("#888888"),
        alignment=TA_CENTER, spaceAfter=0,
    )))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


# ── Views ──────────────────────────────────────────────────────────────────────

@login_required
def generate_report_card_pdf(request, student_id):
    """Generate and download PDF report card for a single student."""
    from students.models import Student
    from academics.models import Term

    school = _get_school(request)
    if not school:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("No school found.")

    student = get_object_or_404(Student, pk=student_id, school=school)

    # Permission check
    user = request.user
    role = getattr(user, "role", None)
    is_manager = user.is_superuser or role in ("school_admin", "admin", "teacher", "hod", "deputy_head", "accountant")
    is_own_student = role == "student" and student.user_id == user.id
    is_parent = role == "parent" and student.parent_id == user.id
    if not (is_manager or is_own_student or is_parent):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")

    # Get term
    term_id = request.GET.get("term")
    term = None
    if term_id:
        term = Term.objects.filter(pk=term_id, school=school).first()
    if not term:
        term = Term.objects.filter(school=school, is_current=True).first()

    try:
        pdf_bytes = _build_report_card_pdf_bytes(student, term, school)
    except Exception as exc:
        logger.exception("PDF generation failed for student %s: %s", student_id, exc)
        return HttpResponse(f"PDF generation failed: {exc}", status=500, content_type="text/plain")

    fname = f"report_card_{student.admission_number or student_id}_{term.name if term else 'all'}.pdf"
    fname = fname.replace(" ", "_").replace("/", "-")

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{fname}"'
    return response


@login_required
def generate_bulk_report_cards(request):
    """Generate a ZIP of report card PDFs for an entire class."""
    import zipfile
    from students.models import Student
    from academics.models import Term

    school = _get_school(request)
    if not school:
        from django.shortcuts import redirect
        return redirect("home")

    user = request.user
    role = getattr(user, "role", None)
    if not (user.is_superuser or role in ("school_admin", "admin", "teacher", "hod", "deputy_head")):
        from django.shortcuts import redirect
        return redirect("home")

    class_name = request.GET.get("class", "")
    term_id = request.GET.get("term")
    term = None
    if term_id:
        term = Term.objects.filter(pk=term_id, school=school).first()
    if not term:
        term = Term.objects.filter(school=school, is_current=True).first()

    students_qs = Student.objects.filter(school=school, status="active").select_related("user")
    if class_name:
        students_qs = students_qs.filter(class_name=class_name)

    if not students_qs.exists():
        return HttpResponse("No students found for selected filters.", status=404)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for student in students_qs:
            try:
                pdf_bytes = _build_report_card_pdf_bytes(student, term, school)
                fname = (
                    f"{student.class_name or 'class'}/"
                    f"{student.admission_number or student.pk}_"
                    f"{student.user.get_full_name() or 'student'}.pdf"
                ).replace(" ", "_")
                zf.writestr(fname, pdf_bytes)
            except Exception as exc:
                logger.warning("Skipping PDF for student %s: %s", student.pk, exc)

    zip_buffer.seek(0)
    term_label = term.name.replace(" ", "_") if term else "all_terms"
    class_label = class_name.replace(" ", "_") if class_name else "all_classes"
    zip_name = f"report_cards_{class_label}_{term_label}.zip"

    response = HttpResponse(zip_buffer.read(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_name}"'
    return response


# ---------------------------------------------------------------------------
# F22 — Generate, persist, and verify report cards via ReportCard model
# ---------------------------------------------------------------------------

@login_required
def generate_and_save_report_card(request, student_id):
    """Generate a PDF report card, persist it as a ReportCard record, and stream it.

    Creates (or replaces) the ReportCard row for the student/term combination.
    The generated file is saved to MEDIA so it can be downloaded later.

    Query params:
        term=<pk>   — Term to generate for (defaults to current term).
        publish=1   — Immediately mark as published so parents can access it.
    """
    from students.models import Student
    from academics.models import Term, AcademicYear, ReportCard
    from django.core.files.base import ContentFile

    school = _get_school(request)
    if not school:
        return redirect("home")

    if not is_feature_enabled(request, "report_cards"):
        from django.contrib import messages
        messages.error(request, "Digital Report Cards are not enabled for your school.")
        return redirect("home")

    user = request.user
    role = getattr(user, "role", None)
    if not (user.is_superuser or role in ("school_admin", "admin", "teacher", "hod", "deputy_head")):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")

    student = get_object_or_404(Student, pk=student_id, school=school)

    term_id = request.GET.get("term")
    term = None
    if term_id:
        term = Term.objects.filter(pk=term_id, school=school).first()
    if not term:
        term = Term.objects.filter(school=school, is_current=True).first()

    academic_year = AcademicYear.objects.filter(school=school, is_current=True).first()

    try:
        pdf_bytes = _build_report_card_pdf_bytes(student, term, school)
    except Exception as exc:
        logger.exception("PDF generation failed for student %s", student_id)
        return HttpResponse(f"PDF generation failed: {exc}", status=500, content_type="text/plain")

    publish = request.GET.get("publish") == "1"

    # Mark previous as not latest, then create new record
    ReportCard.objects.filter(
        school=school, student=student, term=term, is_latest=True,
    ).update(is_latest=False)

    rc = ReportCard(
        school=school,
        student=student,
        academic_year=academic_year,
        term=term,
        is_latest=True,
        generated_by=user,
        published=publish,
    )
    if publish:
        rc.published_at = timezone.now()

    fname = (
        f"report_cards/{school.pk}/"
        f"{student.admission_number or student_id}_{term.name if term else 'all'}.pdf"
    ).replace(" ", "_").replace("/", "-", 1)  # keep first slash for directory

    rc.pdf_file.save(fname, ContentFile(pdf_bytes), save=False)
    rc.save()

    # Stream the PDF immediately
    resp_fname = f"report_card_{student.admission_number or student_id}_{term.name if term else 'all'}.pdf"
    resp_fname = resp_fname.replace(" ", "_").replace("/", "-")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{resp_fname}"'
    return response


def verify_report_card_qr(request, qr_token):
    """Public QR-code verification endpoint — no login required.

    Displays a simple confirmation page (or JSON) that the report card is
    authentic and has not been tampered with.
    """
    from academics.models import ReportCard
    from django.shortcuts import render as _render

    try:
        rc = ReportCard.objects.select_related(
            "student", "student__user", "school", "term", "academic_year", "generated_by"
        ).get(qr_token=qr_token)
    except ReportCard.DoesNotExist:
        if request.headers.get("accept", "").startswith("application/json"):
            from django.http import JsonResponse
            return JsonResponse({"valid": False, "error": "Report card not found."}, status=404)
        return HttpResponse(
            "<h2>Invalid or expired QR code.</h2><p>This report card could not be verified.</p>",
            status=404,
        )

    ctx = {
        "report_card": rc,
        "student": rc.student,
        "school": rc.school,
        "term": rc.term,
        "academic_year": rc.academic_year,
        "generated_at": rc.generated_at,
        "generated_by": rc.generated_by,
        "published": rc.published,
    }

    if request.headers.get("accept", "").startswith("application/json"):
        from django.http import JsonResponse
        return JsonResponse({
            "valid": True,
            "student": rc.student.user.get_full_name(),
            "admission_number": rc.student.admission_number,
            "school": rc.school.name,
            "term": str(rc.term) if rc.term else None,
            "academic_year": str(rc.academic_year) if rc.academic_year else None,
            "generated_at": rc.generated_at.isoformat(),
            "published": rc.published,
        })

    try:
        return _render(request, "academics/report_card_verify.html", ctx)
    except Exception:
        # Fallback if template doesn't exist yet
        body = (
            f"<h2>Report Card Verified</h2>"
            f"<p><strong>Student:</strong> {rc.student.user.get_full_name()}</p>"
            f"<p><strong>School:</strong> {rc.school.name}</p>"
            f"<p><strong>Term:</strong> {rc.term or 'N/A'}</p>"
            f"<p><strong>Generated:</strong> {rc.generated_at.strftime('%d %b %Y %H:%M')}</p>"
            f"<p style='color:green'><strong>✓ Authentic document</strong></p>"
        )
        return HttpResponse(body)
