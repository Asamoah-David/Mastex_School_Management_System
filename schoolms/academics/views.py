from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse

from students.models import Student
from schools.models import School
from accounts.permissions import user_can_manage_school
from .models import Subject, ExamType, Term, Result, GradeBoundary, Homework, ExamSchedule, Timetable, Quiz, QuizQuestion, QuizAttempt, QuizAnswer


def _get_school(request):
    """Get current user's school."""
    if not request.user.is_authenticated:
        return None
    return getattr(request.user, "school", None)


def _user_can_manage_school(request):
    """Delegate to central permission helper for consistency."""
    return user_can_manage_school(request.user)

def _can_view_student_record(user, student):
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_super_admin", False):
        return True
    if user_can_manage_school(user):
        # Staff can view within their school only
        return bool(getattr(user, "school_id", None)) and user.school_id == student.school_id
    role = getattr(user, "role", None)
    if role == "student":
        return student.user_id == user.id
    if role == "parent":
        return student.parent_id == user.id
    return False


def _build_report_card_pdf_bytes(*, school, student, results, average, term_label):
    """
    Produce a professional PDF for a student's report card using ReportLab.
    Returns bytes.
    """
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.units import mm
    from academics.models import get_grade_for_score
    from datetime import datetime
    from reportlab.pdfgen import canvas as pdf_canvas
    from django.utils import timezone as dj_timezone

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Report Card - {student.user.get_full_name() or student.user.username}",
    )

    styles = getSampleStyleSheet()
    story = []

    generated_at = dj_timezone.now()

    def _draw_footer_and_watermark(c: pdf_canvas.Canvas, d):
        c.saveState()
        # Watermark
        c.setFillColor(colors.HexColor("#E5E7EB"))
        c.setFont("Helvetica-Bold", 46)
        c.translate(210, 260)
        c.rotate(35)
        c.drawCentredString(0, 0, school.name.upper()[:28])
        c.restoreState()

        c.saveState()
        # Footer
        c.setFillColor(colors.HexColor("#6B7280"))
        c.setFont("Helvetica", 8)
        page_num = c.getPageNumber()
        footer_left = f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M')} · Mastex SchoolOS"
        footer_right = f"Page {page_num}"
        c.drawString(18 * mm, 12 * mm, footer_left)
        c.drawRightString(A4[0] - 18 * mm, 12 * mm, footer_right)
        c.restoreState()

    # Branding header (optional logo + contact info)
    logo = None
    try:
        logo_url = (getattr(school, "logo_url", "") or "").strip()
        if logo_url:
            import requests
            from io import BytesIO
            r = requests.get(logo_url, timeout=5)
            if r.ok and r.content:
                logo = Image(BytesIO(r.content))
                logo.drawHeight = 18 * mm
                logo.drawWidth = 18 * mm
    except Exception:
        logo = None

    contact_bits = []
    if getattr(school, "address", None):
        contact_bits.append(str(school.address).replace("\n", ", "))
    if getattr(school, "phone", None):
        contact_bits.append(f"Tel: {school.phone}")
    if getattr(school, "email", None):
        contact_bits.append(f"Email: {school.email}")
    if getattr(school, "academic_year", None):
        contact_bits.append(f"Academic Year: {school.academic_year}")
    contact_line = " · ".join([b for b in contact_bits if b])

    title_para = Paragraph(f"<b>{school.name}</b><br/><font size=11>Report Card</font>", styles["Title"])
    if logo:
        header_table = Table([[logo, title_para]], colWidths=[22 * mm, 160 * mm])
        header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(header_table)
    else:
        story.append(title_para)
    if contact_line:
        story.append(Paragraph(f"<font size=9 color='#374151'>{contact_line}</font>", styles["Normal"]))
    story.append(Spacer(1, 10))

    meta = [
        ["Student", student.user.get_full_name() or student.user.username, "Admission No", student.admission_number],
        ["Class", student.class_name or "—", "Term", term_label or "All terms"],
        ["Average", f"{average}%", "Generated", datetime.now().strftime("%Y-%m-%d %H:%M")],
    ]
    meta_table = Table(meta, colWidths=[26 * mm, 70 * mm, 26 * mm, 55 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("BACKGROUND", (2, 0), (2, -1), colors.whitesmoke),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 10))

    rows = [["Subject", "Exam", "Term", "Score", "Grade"]]
    for r in results:
        grade = get_grade_for_score(school, r.score)
        rows.append([r.subject.name, getattr(r.exam_type, "name", "") or "—", getattr(r.term, "name", "") or "—", str(r.score), grade])

    table = Table(rows, colWidths=[60 * mm, 40 * mm, 28 * mm, 18 * mm, 18 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ]
        )
    )
    story.append(table)

    # Grading legend (uses GradeBoundary config if present)
    try:
        from academics.models import GradeBoundary
        boundaries = list(GradeBoundary.objects.filter(school=school).order_by("-min_score"))
    except Exception:
        boundaries = []
    if boundaries:
        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>Grading Legend</b>", styles["Heading3"]))
        legend_rows = [["Grade", "Range"]]
        for b in boundaries[:10]:
            legend_rows.append([b.grade, f"{b.min_score:g} - {b.max_score:g}"])
        legend = Table(legend_rows, colWidths=[25 * mm, 60 * mm])
        legend.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                ]
            )
        )
        story.append(legend)

    # Remarks section (blank lines for official completion)
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Remarks</b>", styles["Heading3"]))
    remarks = Table(
        [
            ["Class Teacher's Remark:", "______________________________________________"],
            ["Headteacher's Remark:", "______________________________________________"],
        ],
        colWidths=[45 * mm, 130 * mm],
    )
    remarks.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(remarks)

    story.append(Spacer(1, 14))
    sig = Table(
        [
            ["Class Teacher", "", "Headteacher", ""],
            ["__________________________", "", "__________________________", ""],
        ],
        colWidths=[35 * mm, 55 * mm, 35 * mm, 55 * mm],
    )
    sig.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ]
        )
    )
    story.append(sig)

    doc.build(story, onFirstPage=_draw_footer_and_watermark, onLaterPages=_draw_footer_and_watermark)
    return buf.getvalue()


# Core academic configuration that should always be available per school.
CORE_TERMS = [
    "Term 1",
    "Term 2",
    "Term 3",
    "Semester 1",
    "Semester 2",
    "Mid Term",
    "Mid Semester",
]

CORE_EXAM_TYPES = [
    "End of Term",
    "Midterm",
    "Midsem",
    "Pre sem",
    "Pre term",
    "End of semester",
    "Trials",
    "Others",
]

CORE_SUBJECTS = [
    "English Language",
    "Ghanaian Language",
    "Social Studies",
    "Core Mathematics",
    "Integrated Science",
    "Physical Education (PE)",
    "Our World Our People (OWOP)",
    "RME (Religious and Moral Education)",
    "Creative Art",
    "Career Technology",
    "STEM",
    "Biology",
    "Physics",
    "Chemistry",
    "Information and Communication Technology (ICT)",
    "Christian Religious Studies (CRS)",
    "Elective Mathematics",
    "Economics",
    "Geography",
    "History",
    "Literature",
    "French",
    "Accounting",
    "Food and Nutrition",
    "Management in Living",
    "Clothing and Textiles",
    "General Knowledge in Art (GKA)",
    "Picture Making",
    "Sculpture",
    "Ceramics",
    "Graphic Design",
]


def _ensure_core_academics_for_school(school):
    """
    Ensure that each school has a minimal set of terms, exam types, and subjects
    so dropdowns are never empty (no manual setup required for non-technical users).
    """
    if not school:
        return

    for name in CORE_TERMS:
        Term.objects.get_or_create(school=school, name=name)
    for name in CORE_EXAM_TYPES:
        ExamType.objects.get_or_create(school=school, name=name)
    for name in CORE_SUBJECTS:
        Subject.objects.get_or_create(school=school, name=name)


@login_required
def results_management(request):
    """Results Management Hub - consolidated results entry page."""
    school = _get_school(request)
    
    # Get recent results for activity display
    from academics.models import Result
    from django.contrib.auth import get_user_model
    
    recent_results = []
    if school:
        recent_results = Result.objects.filter(
            student__school=school
        ).select_related('student', 'student__user', 'subject').order_by('-id')[:10]
    
    context = {
        'school': school,
        'recent_results': recent_results,
    }
    return render(request, 'academics/results_management.html', context)

@login_required
def result_upload(request):
    """Upload student results - for teachers and school admins.

    This view is hardened so that:
    - Users without a school see a clear message instead of a 500 or confusing redirect.
    - Only school-linked staff (teacher / admin roles) and platform super admins can save results.
    """
    school = _get_school(request)
    user = request.user

    # No school attached
    if not school and not getattr(user, "is_super_admin", False):
        return render(
            request,
            "academics/result_upload.html",
            {
                "school": None,
                "classes": [],
                "subjects": [],
                "exam_types": [],
                "terms": [],
                "students": [],
                "selected_class": None,
                "selected_subject": None,
                "selected_exam_type": None,
                "selected_term": None,
                "existing_results": {},
                "error": "Your account is not linked to any school yet. Please contact an administrator.",
            },
        )

    # Only admins, teachers, and super admins can upload results
    if not _user_can_manage_school(request) and not getattr(user, "is_super_admin", False):
        return render(
            request,
            "academics/result_upload.html",
            {
                "school": school,
                "classes": [],
                "subjects": [],
                "exam_types": [],
                "terms": [],
                "students": [],
                "selected_class": None,
                "selected_subject": None,
                "selected_exam_type": None,
                "selected_term": None,
                "existing_results": {},
                "error": "You do not have permission to upload results.",
            },
        )
    
    # Get query parameters
    class_name = request.GET.get("class")
    subject_id = request.GET.get("subject")
    exam_type_id = request.GET.get("exam_type")
    term_id = request.GET.get("term")
    
    # Ensure the school has the standard terms, exam types, and subjects available.
    _ensure_core_academics_for_school(school)

    # Get filter options
    classes = Student.objects.filter(school=school).values_list("class_name", flat=True).distinct()
    classes = [c for c in classes if c]
    subjects = Subject.objects.filter(school=school).order_by("name")
    exam_types = ExamType.objects.filter(school=school).order_by("name")
    terms = Term.objects.filter(school=school).order_by("-is_current", "-id")
    
    # Get students filtered by class
    students = []
    if class_name:
        students = Student.objects.filter(school=school, class_name=class_name).select_related("user").order_by("admission_number")
    
    # Process form submission - handle multiple students at once
    if request.method == "POST":
        subject_id = request.POST.get("subject")
        exam_type_id = request.POST.get("exam_type")
        term_id = request.POST.get("term")
        
        if subject_id and exam_type_id and term_id:
            try:
                subject = Subject.objects.get(id=subject_id, school=school)
                exam_type = ExamType.objects.get(id=exam_type_id, school=school)
                term = Term.objects.get(id=term_id, school=school)
                
                saved_count = 0
                # Loop through all POST data to find score inputs
                for key, value in request.POST.items():
                    if key.startswith("score_student_") and value.strip():
                        student_id = key.replace("score_student_", "")
                        try:
                            score = float(value)
                            if 0 <= score <= 100:
                                student = Student.objects.get(id=student_id, school=school)
                                
                                # Check if result already exists
                                existing = Result.objects.filter(
                                    student=student,
                                    subject=subject,
                                    exam_type=exam_type,
                                    term=term
                                ).first()
                                
                                if existing:
                                    existing.score = score
                                    existing.save()
                                else:
                                    Result.objects.create(
                                        student=student,
                                        subject=subject,
                                        exam_type=exam_type,
                                        term=term,
                                        score=score
                                    )
                                saved_count += 1
                        except (Student.DoesNotExist, ValueError):
                            continue
                
                if saved_count > 0:
                    messages.success(request, f"Successfully saved {saved_count} score(s)")
                
                return redirect(request.get_full_path())
                
            except (Subject.DoesNotExist, ExamType.DoesNotExist, Term.DoesNotExist) as e:
                messages.error(request, "Invalid selection. Please try again.")
    
    # Get existing results for display
    existing_results = {}
    if class_name and subject_id and exam_type_id and term_id:
        results = Result.objects.filter(
            student__school=school,
            student__class_name=class_name,
            subject_id=subject_id,
            exam_type_id=exam_type_id,
            term_id=term_id
        )
        existing_results = {r.student_id: r.score for r in results}
    
    context = {
        "school": school,
        "classes": classes,
        "subjects": subjects,
        "exam_types": exam_types,
        "terms": terms,
        "students": students,
        "selected_class": class_name,
        "selected_subject": subject_id,
        "selected_exam_type": exam_type_id,
        "selected_term": term_id,
        "existing_results": existing_results,
        "selected_subject_name": subjects.filter(id=subject_id).first().name if subject_id else "",
        "all_results": _get_all_results_summary(school, class_name, term_id) if school and class_name and term_id else [],
    }
    
    return render(request, "academics/result_upload.html", context)


def _get_all_results_summary(school, class_name, term_id):
    """Get summary of all saved results for a class and term."""
    from django.db.models import Count, Avg
    results = Result.objects.filter(
        student__school=school,
        student__class_name=class_name,
        term_id=term_id
    ).values('subject__name', 'exam_type__name').annotate(
        count=Count('id'),
        avg_score=Avg('score')
    )
    return [
        {
            'subject': r['subject__name'] or 'Unknown',
            'exam_type': r['exam_type__name'] or 'Unknown',
            'count': r['count'],
            'avg_score': r['avg_score'] or 0
        }
        for r in results
    ]


@login_required
def result_list(request):
    """View all results with filtering."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    
    if not _user_can_manage_school(request):
        return redirect("home")
    
    # Get filter parameters
    class_name = request.GET.get("class")
    subject_id = request.GET.get("subject")
    term_id = request.GET.get("term")
    
    # Base query
    results = Result.objects.filter(student__school=school).select_related(
        "student", "student__user", "subject", "exam_type", "term"
    )
    
    # Apply filters
    if class_name:
        results = results.filter(student__class_name=class_name)
    if subject_id:
        results = results.filter(subject_id=subject_id)
    if term_id:
        results = results.filter(term_id=term_id)
    
    # Order by student and term
    results = results.order_by("student__admission_number", "term__name", "subject__name")
    
    # Get filter options
    classes = Student.objects.filter(school=school).values_list("class_name", flat=True).distinct()
    classes = [c for c in classes if c]
    subjects = Subject.objects.filter(school=school).order_by("name")
    terms = Term.objects.filter(school=school).order_by("-is_current", "-id")
    
    context = {
        "school": school,
        "results": results,
        "classes": classes,
        "subjects": subjects,
        "terms": terms,
        "selected_class": class_name,
        "selected_subject": subject_id,
        "selected_term": term_id,
    }
    
    return render(request, "academics/result_list.html", context)


@login_required
def result_edit(request, pk):
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("home")
    result = get_object_or_404(Result, pk=pk, student__school=school)
    if request.method == "POST":
        score = request.POST.get("score")
        if score:
            try:
                result.score = float(score)
                result.save()
                messages.success(request, "Result updated successfully!")
            except ValueError:
                messages.error(request, "Invalid score value.")
        return redirect("academics:result_list")
    return render(request, "academics/result_edit.html", {"result": result, "school": school})


@login_required
def result_delete(request, pk):
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("home")
    result = get_object_or_404(Result, pk=pk, student__school=school)
    if request.method == "POST":
        result.delete()
        messages.success(request, "Result deleted successfully!")
        return redirect("academics:result_list")
    # Pass a custom name for the template to display
    student_name = result.student.user.get_full_name() or getattr(result.student.user, 'username', 'Unknown')
    return render(request, "accounts/confirm_delete.html", {
        "object": result, 
        "type": "result",
        "custom_name": f"{student_name} - {result.subject.name} ({result.score})",
        "cancel_url": "academics:result_list"
    })


@login_required
def report_card_generator(request):
    """
    Staff workflow: select class/student/term, then jump to the report card view.
    """
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")

    _ensure_core_academics_for_school(school)

    selected_class = (request.GET.get("class") or "").strip()
    selected_student = (request.GET.get("student") or "").strip()
    selected_term = (request.GET.get("term") or "").strip()

    classes = [c for c in Student.objects.filter(school=school).values_list("class_name", flat=True).distinct() if c]
    students = (
        Student.objects.filter(school=school, class_name=selected_class).select_related("user").order_by("admission_number")
        if selected_class
        else []
    )
    terms = Term.objects.filter(school=school).order_by("-is_current", "-id")

    report_url = None
    if selected_student:
        try:
            student = Student.objects.get(id=selected_student, school=school)
            report_url = f"/academics/report-card/{student.id}/"
            if selected_term:
                report_url += f"?term={selected_term}"
        except Student.DoesNotExist:
            report_url = None

    return render(
        request,
        "academics/report_card_generator.html",
        {
            "school": school,
            "classes": classes,
            "students": students,
            "terms": terms,
            "selected_class": selected_class,
            "selected_student": selected_student,
            "selected_term": selected_term,
            "report_url": report_url,
        },
    )


@login_required
def grade_boundary_list(request):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    boundaries = GradeBoundary.objects.filter(school=school).order_by("-min_score")
    return render(request, "academics/grade_boundary_list.html", {"boundaries": boundaries, "school": school})


@login_required
def grade_boundary_create(request):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    if request.method == "POST":
        grade = request.POST.get("grade", "").strip()
        try:
            min_s = float(request.POST.get("min_score", 0))
            max_s = float(request.POST.get("max_score", 100))
            if grade and 0 <= min_s <= max_s <= 100:
                GradeBoundary.objects.update_or_create(
                    school=school, grade=grade,
                    defaults={"min_score": min_s, "max_score": max_s}
                )
                messages.success(request, f"Grade {grade} boundary saved.")
                return redirect("academics:grade_boundary_list")
        except (ValueError, TypeError):
            pass
    return redirect("academics:grade_boundary_list")


@login_required
def homework_list(request):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    role = getattr(request.user, "role", None)
    can_manage = _user_can_manage_school(request)
    class_filter = (request.GET.get("class") or "").strip()

    qs = Homework.objects.filter(school=school).select_related("subject", "created_by").order_by("-due_date")

    # Students and parents get a read-only view scoped to relevant classes.
    if not can_manage:
        if role == "student":
            student = Student.objects.filter(user=request.user).only("class_name", "school_id").first()
            if not student:
                return redirect("home")
            if student.class_name:
                qs = qs.filter(class_name=student.class_name)
            else:
                qs = qs.none()
            classes = [student.class_name] if student.class_name else []
            return render(
                request,
                "academics/homework_list.html",
                {"homework": qs, "school": school, "classes": classes, "read_only": True},
            )
        if role == "parent":
            children = list(Student.objects.filter(parent=request.user, school=school).only("class_name"))
            class_names = sorted({c.class_name for c in children if c.class_name})
            qs = qs.filter(class_name__in=class_names) if class_names else qs.none()
            if class_filter and class_filter in class_names:
                qs = qs.filter(class_name=class_filter)
            return render(
                request,
                "academics/homework_list.html",
                {"homework": qs, "school": school, "classes": class_names, "read_only": True},
            )
        return redirect("home")

    # Staff view: optionally filter by class.
    if class_filter:
        qs = qs.filter(class_name=class_filter)
    classes = list(Student.objects.filter(school=school).values_list("class_name", flat=True).distinct())
    classes = [c for c in classes if c]
    return render(request, "academics/homework_list.html", {"homework": qs, "school": school, "classes": classes, "read_only": False})


@login_required
def homework_create(request):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        desc = request.POST.get("description", "").strip()
        class_name = request.POST.get("class_name", "").strip()
        subject_id = request.POST.get("subject")
        due = request.POST.get("due_date")
        if title and class_name and subject_id and due:
            try:
                subject = Subject.objects.get(id=subject_id, school=school)
                from datetime import datetime
                due_d = datetime.strptime(due, "%Y-%m-%d").date()
                Homework.objects.create(
                    school=school, subject=subject, class_name=class_name,
                    title=title, description=desc, due_date=due_d, created_by=request.user
                )
                messages.success(request, "Homework added.")
                return redirect("academics:homework_list")
            except (Subject.DoesNotExist, ValueError):
                pass
    subjects = Subject.objects.filter(school=school).order_by("name")
    classes = list(Student.objects.filter(school=school).values_list("class_name", flat=True).distinct())
    classes = [c for c in classes if c]
    return render(request, "academics/homework_form.html", {"school": school, "subjects": subjects, "classes": classes})


@login_required
def homework_edit(request, pk):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    homework = get_object_or_404(Homework, pk=pk, school=school)
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        desc = request.POST.get("description", "").strip()
        class_name = request.POST.get("class_name", "").strip()
        subject_id = request.POST.get("subject")
        due = request.POST.get("due_date")
        if title and class_name and subject_id and due:
            try:
                subject = Subject.objects.get(id=subject_id, school=school)
                from datetime import datetime
                due_d = datetime.strptime(due, "%Y-%m-%d").date()
                homework.title = title
                homework.description = desc
                homework.class_name = class_name
                homework.subject = subject
                homework.due_date = due_d
                homework.save()
                messages.success(request, "Homework updated.")
                return redirect("academics:homework_list")
            except (Subject.DoesNotExist, ValueError):
                pass
    subjects = Subject.objects.filter(school=school).order_by("name")
    classes = list(Student.objects.filter(school=school).values_list("class_name", flat=True).distinct())
    classes = [c for c in classes if c]
    return render(request, "academics/homework_form.html", {"school": school, "subjects": subjects, "classes": classes, "homework": homework})


@login_required
def homework_delete(request, pk):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    homework = get_object_or_404(Homework, pk=pk, school=school)
    if request.method == "POST":
        homework.delete()
        messages.success(request, "Homework deleted.")
        return redirect("academics:homework_list")
    return render(request, "accounts/confirm_delete.html", {"object": homework, "type": "homework"})


@login_required
def exam_schedule_list(request):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    role = getattr(request.user, "role", None)
    can_manage = _user_can_manage_school(request)
    # Ensure common terms and subjects exist so filters are useful.
    _ensure_core_academics_for_school(school)

    term_id = request.GET.get("term")
    class_name = request.GET.get("class")
    qs = ExamSchedule.objects.filter(school=school).select_related("term", "subject").order_by("exam_date", "start_time")
    if term_id:
        qs = qs.filter(term_id=term_id)
    if class_name:
        qs = qs.filter(class_name=class_name)
    terms = Term.objects.filter(school=school).order_by("-is_current", "-id")
    classes = [c for c in Student.objects.filter(school=school).values_list("class_name", flat=True).distinct() if c]

    if not can_manage:
        if role == "student":
            student = Student.objects.filter(user=request.user).only("class_name").first()
            allowed = [student.class_name] if student and student.class_name else []
            qs = qs.filter(Q(class_name__in=allowed) | Q(class_name="") | Q(class_name__isnull=True))
            classes = allowed
        elif role == "parent":
            children = list(Student.objects.filter(parent=request.user, school=school).only("class_name"))
            allowed = sorted({c.class_name for c in children if c.class_name})
            qs = qs.filter(Q(class_name__in=allowed) | Q(class_name="") | Q(class_name__isnull=True))
            classes = allowed
        else:
            return redirect("home")
    return render(
        request,
        "academics/exam_schedule_list.html",
        {
            "exams": qs,
            "school": school,
            "terms": terms,
            "classes": classes,
            "selected_term": term_id,
            "selected_class": class_name,
            "read_only": not can_manage,
        },
    )


@login_required
def exam_schedule_create(request):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    if request.method == "POST":
        term_id = request.POST.get("term")
        subject_id = request.POST.get("subject")
        class_name = (request.POST.get("class_name") or "").strip()
        exam_date = request.POST.get("exam_date")
        start = request.POST.get("start_time") or None
        end = request.POST.get("end_time") or None
        room = request.POST.get("room", "").strip()
        notes = request.POST.get("notes", "").strip()
        if term_id and subject_id and exam_date:
            try:
                from datetime import datetime
                term = Term.objects.get(id=term_id, school=school)
                subject = Subject.objects.get(id=subject_id, school=school)
                exam_d = datetime.strptime(exam_date, "%Y-%m-%d").date()
                st = None
                en = None
                if start and start.strip():
                    st = datetime.strptime(start.strip(), "%H:%M").time()
                if end and end.strip():
                    en = datetime.strptime(end.strip(), "%H:%M").time()
                ExamSchedule.objects.create(
                    school=school,
                    term=term,
                    subject=subject,
                    class_name=class_name,
                    exam_date=exam_d,
                    start_time=st,
                    end_time=en,
                    room=room,
                    notes=notes,
                )
                messages.success(request, "Exam scheduled.")
                return redirect("academics:exam_schedule_list")
            except (Term.DoesNotExist, Subject.DoesNotExist, ValueError, TypeError):
                pass
    # Ensure standard options exist for dropdowns.
    _ensure_core_academics_for_school(school)
    terms = Term.objects.filter(school=school).order_by("-is_current", "-id")
    subjects = Subject.objects.filter(school=school).order_by("name")
    classes = (
        Student.objects.filter(school=school).values_list("class_name", flat=True).distinct()
    )
    classes = [c for c in classes if c]
    return render(
        request,
        "academics/exam_schedule_form.html",
        {"school": school, "terms": terms, "subjects": subjects, "classes": classes},
    )


@login_required
def exam_schedule_edit(request, pk):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    exam = get_object_or_404(ExamSchedule, pk=pk, school=school)
    if request.method == "POST":
        term_id = request.POST.get("term")
        subject_id = request.POST.get("subject")
        class_name = (request.POST.get("class_name") or "").strip()
        exam_date = request.POST.get("exam_date")
        start = request.POST.get("start_time") or None
        end = request.POST.get("end_time") or None
        room = request.POST.get("room", "").strip()
        notes = request.POST.get("notes", "").strip()
        if term_id and subject_id and exam_date:
            try:
                from datetime import datetime
                term = Term.objects.get(id=term_id, school=school)
                subject = Subject.objects.get(id=subject_id, school=school)
                exam_d = datetime.strptime(exam_date, "%Y-%m-%d").date()
                st = None
                en = None
                if start and start.strip():
                    st = datetime.strptime(start.strip(), "%H:%M").time()
                if end and end.strip():
                    en = datetime.strptime(end.strip(), "%H:%M").time()
                exam.term = term
                exam.subject = subject
                exam.class_name = class_name
                exam.exam_date = exam_d
                exam.start_time = st
                exam.end_time = en
                exam.room = room
                exam.notes = notes
                exam.save()
                messages.success(request, "Exam schedule updated.")
                return redirect("academics:exam_schedule_list")
            except (Term.DoesNotExist, Subject.DoesNotExist, ValueError, TypeError):
                pass
    _ensure_core_academics_for_school(school)
    terms = Term.objects.filter(school=school).order_by("-is_current", "-id")
    subjects = Subject.objects.filter(school=school).order_by("name")
    classes = Student.objects.filter(school=school).values_list("class_name", flat=True).distinct()
    classes = [c for c in classes if c]
    return render(
        request,
        "academics/exam_schedule_form.html",
        {"school": school, "terms": terms, "subjects": subjects, "classes": classes, "exam": exam},
    )


@login_required
def exam_schedule_delete(request, pk):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    exam = get_object_or_404(ExamSchedule, pk=pk, school=school)
    if request.method == "POST":
        exam.delete()
        messages.success(request, "Exam schedule deleted.")
        return redirect("academics:exam_schedule_list")
    return render(request, "accounts/confirm_delete.html", {"object": exam, "type": "exam schedule"})


@login_required
def report_card_view(request, student_id):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    student = get_object_or_404(Student, id=student_id, school=school)
    if not _can_view_student_record(request.user, student):
        return redirect("home")
    term_id = request.GET.get("term")
    results = Result.objects.filter(student=student).select_related("subject", "exam_type", "term").order_by("term", "subject")
    if term_id:
        results = results.filter(term_id=term_id)
    terms = Term.objects.filter(school=school).order_by("-is_current", "-id")
    total = sum(r.score for r in results) if results else 0
    avg = (total / len(results)) if results else 0
    from academics.models import get_grade_for_score
    grades = [get_grade_for_score(school, r.score) for r in results]
    
    # Get attendance summary
    from operations.models import StudentAttendance
    attendance_qs = StudentAttendance.objects.filter(student=student)
    if term_id:
        # Filter by term date range (approximate) - only if term has valid dates
        term = terms.filter(id=term_id).first()
        if term and term.start_date and term.end_date:
            attendance_qs = attendance_qs.filter(date__gte=term.start_date, date__lte=term.end_date)
    total_days = attendance_qs.count()
    present_days = attendance_qs.filter(status="present").count()
    absent_days = attendance_qs.filter(status="absent").count()
    late_days = attendance_qs.filter(status="late").count()
    attendance_rate = round((present_days / total_days * 100), 1) if total_days > 0 else 0
    
    return render(
        request,
        "academics/report_card.html",
        {
            "student": student,
            "results": results,
            "terms": terms,
            "average": round(avg, 1),
            "school": school,
            "selected_term": term_id,
            "attendance_total": total_days,
            "attendance_present": present_days,
            "attendance_absent": absent_days,
            "attendance_late": late_days,
            "attendance_rate": attendance_rate,
        },
    )


@login_required
def report_card_pdf(request, student_id):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    student = get_object_or_404(Student, id=student_id, school=school)
    if not _can_view_student_record(request.user, student):
        return redirect("home")

    term_id = request.GET.get("term")
    results = Result.objects.filter(student=student).select_related("subject", "exam_type", "term").order_by("term", "subject")
    term_label = ""
    if term_id:
        results = results.filter(term_id=term_id)
        term = Term.objects.filter(id=term_id, school=school).first()
        term_label = term.name if term else ""

    total = sum(r.score for r in results) if results else 0
    avg = (total / len(results)) if results else 0
    pdf_bytes = _build_report_card_pdf_bytes(
        school=school,
        student=student,
        results=list(results),
        average=round(avg, 1),
        term_label=term_label,
    )

    filename = f"report_card_{student.admission_number}_{term_label or 'all'}.pdf".replace(" ", "_")
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@login_required
def report_cards_export_zip(request):
    """
    Staff batch export: download a ZIP of PDFs for a class (optionally a term).
    """
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")

    class_name = (request.GET.get("class") or "").strip()
    term_id = (request.GET.get("term") or "").strip()
    if not class_name:
        messages.error(request, "Please select a class to export.")
        return redirect("academics:report_card_generator")

    term_label = ""
    if term_id:
        term = Term.objects.filter(id=term_id, school=school).first()
        term_label = term.name if term else ""

    students = (
        Student.objects.filter(school=school, class_name=class_name)
        .select_related("user")
        .order_by("admission_number")
    )

    from io import BytesIO
    import zipfile

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for s in students:
            results = Result.objects.filter(student=s).select_related("subject", "exam_type", "term").order_by("term", "subject")
            if term_id:
                results = results.filter(term_id=term_id)
            total = sum(r.score for r in results) if results else 0
            avg = (total / len(results)) if results else 0
            pdf_bytes = _build_report_card_pdf_bytes(
                school=school,
                student=s,
                results=list(results),
                average=round(avg, 1),
                term_label=term_label,
            )
            safe_name = (s.user.get_full_name() or s.user.username or s.admission_number).strip().replace(" ", "_")
            entry = f"{class_name.replace(' ', '_')}/{safe_name}_{s.admission_number}.pdf"
            zf.writestr(entry, pdf_bytes)

    zip_filename = f"report_cards_{class_name}_{term_label or 'all'}.zip".replace(" ", "_")
    resp = HttpResponse(zip_buf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
    return resp


# Timetable
@login_required
def timetable_list(request):
    """
    Staff management view for class timetable entries.
    """
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or _user_can_manage_school(request)):
        return redirect("home")

    class_name = (request.GET.get("class_name") or "").strip()
    day = (request.GET.get("day") or "").strip()

    qs = Timetable.objects.filter(school=school).select_related("subject").order_by("class_name", "day", "start_time")
    if class_name:
        qs = qs.filter(class_name=class_name)
    if day:
        qs = qs.filter(day__iexact=day)

    classes = (
        Timetable.objects.filter(school=school)
        .order_by("class_name")
        .values_list("class_name", flat=True)
        .distinct()
    )
    return render(
        request,
        "academics/timetable_list.html",
        {"school": school, "items": qs[:800], "classes": classes, "selected_class": class_name, "selected_day": day},
    )


@login_required
def timetable_create(request):
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or _user_can_manage_school(request)):
        return redirect("home")

    subjects = Subject.objects.filter(school=school).order_by("name")
    suggested_classes = (
        Student.objects.filter(school=school)
        .exclude(class_name__isnull=True)
        .exclude(class_name__exact="")
        .order_by("class_name")
        .values_list("class_name", flat=True)
        .distinct()
    )

    if request.method == "POST":
        from datetime import time

        class_name = (request.POST.get("class_name") or "").strip()
        subject_id = request.POST.get("subject")
        day = (request.POST.get("day") or "").strip()
        start_time = (request.POST.get("start_time") or "").strip()
        end_time = (request.POST.get("end_time") or "").strip()

        subject = Subject.objects.filter(id=subject_id, school=school).first()
        if not (class_name and subject and day and start_time and end_time):
            messages.error(request, "Please fill all required fields.")
        else:
            try:
                st = time.fromisoformat(start_time)
                et = time.fromisoformat(end_time)
            except ValueError:
                st, et = None, None

            if not st or not et or st >= et:
                messages.error(request, "Invalid time range.")
            else:
                Timetable.objects.create(
                    school=school,
                    class_name=class_name,
                    subject=subject,
                    day=day,
                    start_time=st,
                    end_time=et,
                )
                messages.success(request, "Timetable entry created.")
                return redirect("academics:timetable_list")

    return render(
        request,
        "academics/timetable_form.html",
        {"school": school, "subjects": subjects, "suggested_classes": suggested_classes},
    )


@login_required
def timetable_delete(request, pk):
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or _user_can_manage_school(request)):
        return redirect("home")
    item = get_object_or_404(Timetable, pk=pk, school=school)
    if request.method == "POST":
        item.delete()
        messages.success(request, "Deleted.")
        return redirect("academics:timetable_list")
    return render(request, "accounts/confirm_delete.html", {"object": item})


@login_required
def timetable_my(request):
    """
    Student/parent read-only timetable view based on student's class.
    """
    school = _get_school(request)
    if not school:
        return redirect("home")

    role = getattr(request.user, "role", None)
    if role == "student":
        student = Student.objects.filter(user=request.user, school=school).first()
        class_name = getattr(student, "class_name", "") if student else ""
        items = (
            Timetable.objects.filter(school=school, class_name=class_name)
            .select_related("subject")
            .order_by("day", "start_time")
        ) if class_name else Timetable.objects.none()
        return render(
            request,
            "academics/timetable_my.html",
            {"school": school, "mode": "student", "student": student, "class_name": class_name, "items": items},
        )

    if role == "parent":
        children = list(
            Student.objects.filter(parent=request.user, school=school)
            .select_related("user")
            .order_by("class_name", "admission_number")
        )
        selected_id = request.GET.get("student")
        selected = None
        for c in children:
            if str(c.id) == str(selected_id):
                selected = c
                break
        if not selected and children:
            selected = children[0]
        class_name = getattr(selected, "class_name", "") if selected else ""
        items = (
            Timetable.objects.filter(school=school, class_name=class_name)
            .select_related("subject")
            .order_by("day", "start_time")
        ) if class_name else Timetable.objects.none()
        return render(
            request,
            "academics/timetable_my.html",
            {"school": school, "mode": "parent", "children": children, "selected": selected, "class_name": class_name, "items": items},
        )

    if request.user.is_superuser or _user_can_manage_school(request):
        return redirect("academics:timetable_list")
    return redirect("home")


# Analytics Views
@login_required
def performance_analytics(request):
    """Student performance analytics dashboard"""
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("home")
    
    class_name = request.GET.get("class")
    term_id = request.GET.get("term")
    
    # Get filter options
    classes = [c for c in Student.objects.filter(school=school).values_list("class_name", flat=True).distinct() if c]
    terms = Term.objects.filter(school=school).order_by("-is_current", "-id")
    
    # Base query for results
    results_qs = Result.objects.filter(student__school=school)
    
    if class_name:
        results_qs = results_qs.filter(student__class_name=class_name)
    if term_id:
        results_qs = results_qs.filter(term_id=term_id)
    
    # Class performance summary
    class_stats = []
    for cls in classes:
        cls_results = results_qs.filter(student__class_name=cls)
        if cls_results.exists():
            avg = cls_results.aggregate(Avg('score'))['score__avg'] or 0
            count = cls_results.count()
            class_stats.append({
                'class': cls,
                'avg_score': round(avg, 1),
                'total_results': count,
                'student_count': cls_results.values('student').distinct().count()
            })
    
    # Subject performance
    subject_stats = []
    subjects = Subject.objects.filter(school=school)
    for subj in subjects:
        subj_results = results_qs.filter(subject=subj)
        if subj_results.exists():
            avg = subj_results.aggregate(Avg('score'))['score__avg'] or 0
            subject_stats.append({
                'subject': subj.name,
                'avg_score': round(avg, 1),
                'total_results': subj_results.count()
            })
    subject_stats.sort(key=lambda x: x['avg_score'], reverse=True)
    
    # Top performing students
    from django.db.models import Avg
    top_students = (
        results_qs.values('student__user__first_name', 'student__user__last_name', 
                         'student__admission_number', 'student__class_name')
        .annotate(avg_score=Avg('score'))
        .order_by('-avg_score')[:10]
    )
    
    context = {
        'school': school,
        'classes': classes,
        'terms': terms,
        'selected_class': class_name,
        'selected_term': term_id,
        'class_stats': class_stats,
        'subject_stats': subject_stats[:10],  # Top 10 subjects
        'top_students': top_students,
    }
    return render(request, "academics/performance_analytics.html", context)


# Quiz Views
@login_required
def quiz_list(request):
    """List all quizzes"""
    school = _get_school(request)
    if not school:
        return redirect("home")
    
    role = getattr(request.user, "role", None)
    can_manage = _user_can_manage_school(request)
    
    if can_manage:
        # Staff: see all quizzes
        quizzes = Quiz.objects.filter(school=school).select_related('subject', 'created_by').order_by('-id')
    elif role == "student":
        # Students: see quizzes for their class
        student = Student.objects.filter(user=request.user, school=school).first()
        if student and student.class_name:
            quizzes = Quiz.objects.filter(school=school, class_name=student.class_name, is_active=True).order_by('-id')
        else:
            quizzes = Quiz.objects.none()
    else:
        quizzes = Quiz.objects.none()
    
    return render(request, "academics/quiz_list.html", {"quizzes": quizzes, "school": school, "can_manage": can_manage})


@login_required
def quiz_create(request):
    """Create a new quiz"""
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("home")
    
    subjects = Subject.objects.filter(school=school).order_by('name')
    terms = Term.objects.filter(school=school).order_by('-is_current', '-id')
    classes = [c for c in Student.objects.filter(school=school).values_list('class_name', flat=True).distinct() if c]
    
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        subject_id = request.POST.get("subject")
        term_id = request.POST.get("term")
        class_name = request.POST.get("class_name", "").strip()
        duration = request.POST.get("duration_minutes", "30")
        passing = request.POST.get("passing_score", "50")
        
        if title and subject_id and class_name:
            try:
                from datetime import datetime
                quiz = Quiz.objects.create(
                    school=school,
                    title=title,
                    description=description,
                    subject_id=subject_id,
                    term_id=term_id or None,
                    class_name=class_name,
                    duration_minutes=int(duration),
                    passing_score=int(passing),
                    created_by=request.user
                )
                messages.success(request, "Quiz created! Add questions now.")
                return redirect("academics:quiz_detail", pk=quiz.pk)
            except Exception as e:
                messages.error(request, f"Error creating quiz: {str(e)}")
    
    return render(request, "academics/quiz_form.html", {
        "school": school, 
        "subjects": subjects, 
        "terms": terms, 
        "classes": classes,
        "quiz": None
    })


@login_required
def quiz_detail(request, pk):
    """Quiz detail with questions"""
    school = _get_school(request)
    if not school:
        return redirect("home")
    
    quiz = get_object_or_404(Quiz, pk=pk, school=school)
    questions = quiz.questions.all().order_by('order')
    can_edit = _user_can_manage_school(request)
    
    return render(request, "academics/quiz_detail.html", {
        "quiz": quiz, 
        "questions": questions, 
        "school": school,
        "can_edit": can_edit
    })


@login_required
def quiz_add_question(request, pk):
    """Add a question to quiz"""
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("home")
    
    quiz = get_object_or_404(Quiz, pk=pk, school=school)
    
    if request.method == "POST":
        question_text = request.POST.get("question_text", "").strip()
        question_type = request.POST.get("question_type", "multiple_choice")
        option_a = request.POST.get("option_a", "").strip()
        option_b = request.POST.get("option_b", "").strip()
        option_c = request.POST.get("option_c", "").strip()
        option_d = request.POST.get("option_d", "").strip()
        correct = request.POST.get("correct_answer", "").strip()
        marks = request.POST.get("marks", "1")
        order = quiz.questions.count()
        
        if question_text and correct:
            QuizQuestion.objects.create(
                quiz=quiz,
                question_text=question_text,
                question_type=question_type,
                option_a=option_a,
                option_b=option_b,
                option_c=option_c,
                option_d=option_d,
                correct_answer=correct,
                marks=int(marks),
                order=order
            )
            messages.success(request, "Question added!")
        
        return redirect("academics:quiz_detail", pk=pk)
    
    return redirect("academics:quiz_detail", pk=pk)


@login_required
def quiz_take(request, pk):
    """Student takes a quiz"""
    school = _get_school(request)
    if not school:
        return redirect("home")
    
    role = getattr(request.user, "role", None)
    if role != "student":
        return redirect("home")
    
    student = Student.objects.filter(user=request.user, school=school).first()
    if not student:
        return redirect("home")
    
    quiz = get_object_or_404(Quiz, pk=pk, school=school, is_active=True)
    
    # Check if already attempted
    existing = QuizAttempt.objects.filter(quiz=quiz, student=student, is_completed=True).first()
    if existing:
        messages.info(request, "You have already completed this quiz.")
        return redirect("academics:quiz_result", pk=existing.pk)
    
    # Get or create attempt
    attempt, created = QuizAttempt.objects.get_or_create(
        quiz=quiz, 
        student=student, 
        is_completed=False,
        defaults={}
    )
    
    questions = quiz.questions.all().order_by('order')
    
    if request.method == "POST":
        total_marks = 0
        for question in questions:
            answer = request.POST.get(f"q_{question.pk}", "")
            is_correct = answer.upper() == question.correct_answer.upper() if answer else False
            marks = question.marks if is_correct else 0
            total_marks += marks
            
            QuizAnswer.objects.update_or_create(
                attempt=attempt,
                question=question,
                defaults={'answer': answer, 'is_correct': is_correct, 'marks_obtained': marks}
            )
        
        # Calculate percentage
        max_marks = sum(q.marks for q in questions)
        score = (total_marks / max_marks * 100) if max_marks > 0 else 0
        
        attempt.score = score
        attempt.is_passed = score >= quiz.passing_score
        attempt.is_completed = True
        from django.utils import timezone
        attempt.submitted_at = timezone.now()
        attempt.save()
        
        messages.success(request, f"Quiz completed! Score: {round(score, 1)}%")
        return redirect("academics:quiz_result", pk=attempt.pk)
    
    return render(request, "academics/quiz_take.html", {
        "quiz": quiz, 
        "questions": questions, 
        "attempt": attempt,
        "school": school
    })


@login_required
def quiz_result(request, pk):
    """View quiz result"""
    school = _get_school(request)
    if not school:
        return redirect("home")

    attempt = get_object_or_404(QuizAttempt, pk=pk, student__school=school)

    # Check permission
    role = getattr(request.user, "role", None)
    if role == "student" and attempt.student.user != request.user:
        return redirect("home")

    answers = attempt.answers.all().select_related('question')

    return render(request, "academics/quiz_result.html", {
        "attempt": attempt,
        "answers": answers,
        "school": school
    })


@login_required
def quiz_edit(request, pk):
    """Edit a quiz"""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect("home")

    quiz = get_object_or_404(Quiz, pk=pk, school=school)

    if request.method == "POST":
        quiz.title = request.POST.get("title", "").strip()
        quiz.description = request.POST.get("description", "").strip()
        quiz.time_limit = request.POST.get("time_limit") or None
        quiz.passing_score = request.POST.get("passing_score") or 0
        quiz.is_published = request.POST.get("is_published") == "on"
        quiz.save()
        from django.contrib import messages
        messages.success(request, "Quiz updated!")
        return redirect("academics:quiz_detail", pk=quiz.pk)

    return render(request, "academics/quiz_form.html", {"quiz": quiz, "school": school})


@login_required
def quiz_delete(request, pk):
    """Delete a quiz"""
    from accounts.permissions import user_can_manage_school
    school = _get_school(request)
    if not school or not user_can_manage_school(request.user):
        return redirect("home")

    quiz = get_object_or_404(Quiz, pk=pk, school=school)

    if request.method == "POST":
        quiz.delete()
        from django.contrib import messages
        messages.success(request, "Quiz deleted!")
        return redirect("academics:quiz_list")

    return render(request, "accounts/confirm_delete.html", {"object": quiz, "type": "quiz"})


# ==========================================
# NEW VIEWS FOR COMPREHENSIVE GRADING SYSTEM
# ==========================================

@login_required
def grading_policy_view(request):
    """View and manage the school's grading policy."""
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    
    from .models import GradingPolicy, GradePoint, AssessmentType
    from .services import ensure_default_grading_setup
    
    # Ensure default setup exists
    ensure_default_grading_setup(school)
    
    # Get current policy
    policy = GradingPolicy.objects.filter(school=school, is_default=True).first()
    if not policy:
        policy = GradingPolicy.objects.create(
            school=school,
            name="Default Policy",
            ca_weight=50.0,
            exam_weight=50.0,
            is_default=True
        )
    
    # Get grade points
    grade_points = GradePoint.objects.filter(school=school, scale='5.0').order_by('-min_score')
    
    # Get assessment types
    assessment_types = AssessmentType.objects.filter(school=school, is_active=True).order_by('name')
    
    context = {
        'school': school,
        'policy': policy,
        'grade_points': grade_points,
        'assessment_types': assessment_types,
    }
    
    return render(request, "academics/grading_policy.html", context)


@login_required
def grading_policy_update(request):
    """Update the school's grading policy."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    
    from .models import GradingPolicy
    
    if request.method == "POST":
        ca_weight = request.POST.get("ca_weight", "50")
        exam_weight = request.POST.get("exam_weight", "50")
        
        try:
            ca = float(ca_weight)
            exam = float(exam_weight)
            
            if ca + exam != 100:
                messages.error(request, "CA weight and Exam weight must add up to 100%")
                return redirect("academics:grading_policy")
            
            policy = GradingPolicy.objects.filter(school=school, is_default=True).first()
            if policy:
                policy.ca_weight = ca
                policy.exam_weight = exam
                policy.save()
                messages.success(request, f"Grading policy updated: {ca}% CA + {exam}% Exam")
            else:
                GradingPolicy.objects.create(
                    school=school,
                    name="Default Policy",
                    ca_weight=ca,
                    exam_weight=exam,
                    is_default=True
                )
                messages.success(request, f"Grading policy created: {ca}% CA + {exam}% Exam")
                
        except ValueError:
            messages.error(request, "Invalid weight values")
    
    return redirect("academics:grading_policy")


@login_required
def assessment_type_list(request):
    """List assessment types."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    
    from .models import AssessmentType
    
    assessment_types = AssessmentType.objects.filter(school=school).order_by('name')
    
    return render(request, "academics/assessment_type_list.html", {
        'school': school,
        'assessment_types': assessment_types,
    })


@login_required
def assessment_type_create(request):
    """Create a new assessment type."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    
    from .models import AssessmentType
    
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        
        if name:
            AssessmentType.objects.create(
                school=school,
                name=name,
                description=description
            )
            messages.success(request, f"Assessment type '{name}' created")
    
    return redirect("academics:assessment_type_list")


@login_required
def assessment_score_list(request):
    """List assessment scores."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("home")
    
    from .models import AssessmentScore
    
    class_name = request.GET.get("class")
    subject_id = request.GET.get("subject")
    term_id = request.GET.get("term")
    
    scores = AssessmentScore.objects.filter(student__school=school).select_related(
        'student', 'student__user', 'subject', 'assessment_type', 'term'
    ).order_by('-date')
    
    if class_name:
        scores = scores.filter(student__class_name=class_name)
    if subject_id:
        scores = scores.filter(subject_id=subject_id)
    if term_id:
        scores = scores.filter(term_id=term_id)
    
    classes = [c for c in Student.objects.filter(school=school).values_list('class_name', flat=True).distinct() if c]
    subjects = Subject.objects.filter(school=school).order_by('name')
    terms = Term.objects.filter(school=school).order_by('-is_current', '-id')
    
    return render(request, "academics/assessment_score_list.html", {
        'school': school,
        'scores': scores[:100],
        'classes': classes,
        'subjects': subjects,
        'terms': terms,
        'selected_class': class_name,
        'selected_subject': subject_id,
        'selected_term': term_id,
    })


@login_required
def assessment_score_upload(request):
    """Upload assessment scores in bulk."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    
    from .models import AssessmentScore, AssessmentType
    from datetime import datetime
    
    class_name = request.GET.get("class")
    subject_id = request.GET.get("subject")
    term_id = request.GET.get("term")
    assessment_type_id = request.GET.get("assessment_type")
    
    classes = [c for c in Student.objects.filter(school=school).values_list('class_name', flat=True).distinct() if c]
    subjects = Subject.objects.filter(school=school).order_by('name')
    terms = Term.objects.filter(school=school).order_by('-is_current', '-id')
    assessment_types = AssessmentType.objects.filter(school=school, is_active=True).order_by('name')
    
    students = []
    existing_scores = {}
    
    if class_name and subject_id and term_id and assessment_type_id:
        students = Student.objects.filter(school=school, class_name=class_name).select_related("user").order_by("admission_number")
        scores = AssessmentScore.objects.filter(
            student__school=school,
            student__class_name=class_name,
            subject_id=subject_id,
            term_id=term_id,
            assessment_type_id=assessment_type_id
        )
        existing_scores = {s.student_id: s.score for s in scores}
    
    if request.method == "POST":
        subject_id = request.POST.get("subject")
        term_id = request.POST.get("term")
        assessment_type_id = request.POST.get("assessment_type")
        assessment_date = request.POST.get("date", datetime.now().strftime("%Y-%m-%d"))
        
        if subject_id and term_id and assessment_type_id:
            try:
                subject = Subject.objects.get(id=subject_id, school=school)
                term = Term.objects.get(id=term_id, school=school)
                ass_type = AssessmentType.objects.get(id=assessment_type_id, school=school)
                date = datetime.strptime(assessment_date, "%Y-%m-%d").date()
                
                saved_count = 0
                for key, value in request.POST.items():
                    if key.startswith("score_student_") and value.strip():
                        student_id = key.replace("score_student_", "")
                        try:
                            score = float(value)
                            if 0 <= score <= 100:
                                student = Student.objects.get(id=student_id, school=school)
                                AssessmentScore.objects.update_or_create(
                                    student=student,
                                    subject=subject,
                                    term=term,
                                    assessment_type=ass_type,
                                    defaults={'score': score, 'date': date}
                                )
                                saved_count += 1
                        except (Student.DoesNotExist, ValueError):
                            continue
                
                if saved_count > 0:
                    messages.success(request, f"Successfully saved {saved_count} assessment score(s)")
                
                return redirect(request.get_full_path())
                
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
    
    return render(request, "academics/assessment_score_upload.html", {
        'school': school,
        'classes': classes,
        'subjects': subjects,
        'terms': terms,
        'assessment_types': assessment_types,
        'students': students,
        'existing_scores': existing_scores,
        'selected_class': class_name,
        'selected_subject': subject_id,
        'selected_term': term_id,
        'selected_assessment_type': assessment_type_id,
    })


@login_required
def exam_score_list(request):
    """List exam scores."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("home")
    
    from .models import ExamScore
    
    class_name = request.GET.get("class")
    subject_id = request.GET.get("subject")
    term_id = request.GET.get("term")
    
    scores = ExamScore.objects.filter(student__school=school).select_related(
        'student', 'student__user', 'subject', 'exam_type', 'term'
    ).order_by('-date')
    
    if class_name:
        scores = scores.filter(student__class_name=class_name)
    if subject_id:
        scores = scores.filter(subject_id=subject_id)
    if term_id:
        scores = scores.filter(term_id=term_id)
    
    classes = [c for c in Student.objects.filter(school=school).values_list('class_name', flat=True).distinct() if c]
    subjects = Subject.objects.filter(school=school).order_by('name')
    terms = Term.objects.filter(school=school).order_by('-is_current', '-id')
    
    return render(request, "academics/exam_score_list.html", {
        'school': school,
        'scores': scores[:100],
        'classes': classes,
        'subjects': subjects,
        'terms': terms,
        'selected_class': class_name,
        'selected_subject': subject_id,
        'selected_term': term_id,
    })


@login_required
def exam_score_upload(request):
    """Upload exam scores in bulk."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    
    from .models import ExamScore, ExamType
    from datetime import datetime
    
    class_name = request.GET.get("class")
    subject_id = request.GET.get("subject")
    term_id = request.GET.get("term")
    exam_type_id = request.GET.get("exam_type")
    
    classes = [c for c in Student.objects.filter(school=school).values_list('class_name', flat=True).distinct() if c]
    subjects = Subject.objects.filter(school=school).order_by('name')
    terms = Term.objects.filter(school=school).order_by('-is_current', '-id')
    exam_types = ExamType.objects.filter(school=school).order_by('name')
    
    students = []
    existing_scores = {}
    
    if class_name and subject_id and term_id:
        students = Student.objects.filter(school=school, class_name=class_name).select_related("user").order_by("admission_number")
        scores = ExamScore.objects.filter(
            student__school=school,
            student__class_name=class_name,
            subject_id=subject_id,
            term_id=term_id
        )
        existing_scores = {s.student_id: s.score for s in scores}
    
    if request.method == "POST":
        subject_id = request.POST.get("subject")
        term_id = request.POST.get("term")
        exam_type_id = request.POST.get("exam_type")
        exam_date = request.POST.get("date", datetime.now().strftime("%Y-%m-%d"))
        
        if subject_id and term_id:
            try:
                subject = Subject.objects.get(id=subject_id, school=school)
                term = Term.objects.get(id=term_id, school=school)
                exam_type = ExamType.objects.get(id=exam_type_id, school=school) if exam_type_id else None
                date = datetime.strptime(exam_date, "%Y-%m-%d").date()
                
                saved_count = 0
                for key, value in request.POST.items():
                    if key.startswith("score_student_") and value.strip():
                        student_id = key.replace("score_student_", "")
                        try:
                            score = float(value)
                            if 0 <= score <= 100:
                                student = Student.objects.get(id=student_id, school=school)
                                ExamScore.objects.update_or_create(
                                    student=student,
                                    subject=subject,
                                    term=term,
                                    defaults={
                                        'score': score,
                                        'exam_type': exam_type,
                                        'date': date
                                    }
                                )
                                saved_count += 1
                        except (Student.DoesNotExist, ValueError):
                            continue
                
                if saved_count > 0:
                    messages.success(request, f"Successfully saved {saved_count} exam score(s)")
                
                return redirect(request.get_full_path())
                
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
    
    return render(request, "academics/exam_score_upload.html", {
        'school': school,
        'classes': classes,
        'subjects': subjects,
        'terms': terms,
        'exam_types': exam_types,
        'students': students,
        'existing_scores': existing_scores,
        'selected_class': class_name,
        'selected_subject': subject_id,
        'selected_term': term_id,
        'selected_exam_type': exam_type_id,
    })


@login_required
def class_rankings(request):
    """View class rankings."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("home")
    
    from .models import StudentResultSummary
    from .services import GradingService
    
    class_name = request.GET.get("class")
    term_id = request.GET.get("term")
    
    classes = [c for c in Student.objects.filter(school=school).values_list('class_name', flat=True).distinct() if c]
    terms = Term.objects.filter(school=school).order_by('-is_current', '-id')
    
    rankings = []
    
    if class_name and term_id:
        term = Term.objects.filter(id=term_id, school=school).first()
        if term:
            # Get all students in class with results
            students = Student.objects.filter(school=school, class_name=class_name)
            
            for student in students:
                summaries = StudentResultSummary.objects.filter(student=student, term=term)
                if summaries.exists():
                    total_score = sum(s.final_score for s in summaries)
                    subject_count = summaries.count()
                    avg_score = total_score / subject_count if subject_count > 0 else 0
                    gpa = GradingService.calculate_term_gpa(student, term)
                    
                    rankings.append({
                        'student': student,
                        'total_score': round(total_score, 2),
                        'avg_score': round(avg_score, 2),
                        'gpa': gpa,
                        'subjects_count': subject_count,
                    })
            
            # Sort by average score
            rankings.sort(key=lambda x: x['avg_score'], reverse=True)
            
            # Assign positions
            for i, r in enumerate(rankings, 1):
                r['position'] = i
    
    return render(request, "academics/class_rankings.html", {
        'school': school,
        'classes': classes,
        'terms': terms,
        'rankings': rankings,
        'selected_class': class_name,
        'selected_term': term_id,
    })


@login_required
def generate_result_summary(request):
    """Generate result summaries for students."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    
    from .models import StudentResultSummary
    from .services import GradingService
    
    if request.method == "POST":
        class_name = request.POST.get("class")
        term_id = request.POST.get("term")
        
        if class_name and term_id:
            term = Term.objects.filter(id=term_id, school=school).first()
            if term:
                students = Student.objects.filter(school=school, class_name=class_name)
                subjects = Subject.objects.filter(school=school)
                
                generated_count = 0
                for student in students:
                    for subject in subjects:
                        # Check if there are any scores for this student/subject/term
                        has_assessments = AssessmentScore.objects.filter(
                            student=student, subject=subject, term=term
                        ).exists()
                        has_exam = ExamScore.objects.filter(
                            student=student, subject=subject, term=term
                        ).exists()
                        
                        if has_assessments or has_exam:
                            GradingService.update_student_result_summary(student, subject, term)
                            generated_count += 1
                
                messages.success(request, f"Generated {generated_count} result summaries")
            else:
                messages.error(request, "Invalid term selected")
        else:
            messages.error(request, "Please select class and term")
    
    classes = [c for c in Student.objects.filter(school=school).values_list('class_name', flat=True).distinct() if c]
    terms = Term.objects.filter(school=school).order_by('-is_current', '-id')
    
    return render(request, "academics/generate_result_summary.html", {
        'school': school,
        'classes': classes,
        'terms': terms,
    })


@login_required
def enhanced_report_card(request, student_id):
    """Enhanced report card with CA, Exam, Final scores, GPA, and Position."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    
    student = get_object_or_404(Student, id=student_id, school=school)
    if not _can_view_student_record(request.user, student):
        return redirect("home")
    
    from .models import StudentResultSummary, GradingPolicy, AssessmentScore, ExamScore
    from .services import GradingService
    
    term_id = request.GET.get("term")
    terms = Term.objects.filter(school=school).order_by('-is_current', '-id')
    
    # Get grading policy
    policy = GradingPolicy.get_active_policy(school)
    
    # Get results
    results = []
    if term_id:
        summaries = StudentResultSummary.objects.filter(
            student=student, term_id=term_id
        ).select_related('subject', 'term').order_by('subject__name')
        
        term_obj = terms.filter(id=term_id).first()
        
        # Get detailed assessment info
        for summary in summaries:
            assessments = AssessmentScore.objects.filter(
                student=student, subject=summary.subject, term_id=term_id
            ).select_related('assessment_type')
            
            exam = ExamScore.objects.filter(
                student=student, subject=summary.subject, term_id=term_id
            ).first()
            
            results.append({
                'summary': summary,
                'assessments': list(assessments),
                'exam': exam,
            })
        
        # Calculate overall stats
        term_gpa = GradingService.calculate_term_gpa(student, term_obj) if term_obj else 0
        cumulative_gpa = GradingService.calculate_cumulative_gpa(student)
        
        # Get positions
        term_position = None
        cumulative_position = None
        
        if student.class_name and term_obj:
            term_rankings = GradingService.calculate_class_rankings(
                student.class_name, term_obj, school
            )
            term_position = term_rankings.get(student.id)
            
            cumulative_rankings = GradingService.calculate_cumulative_rankings(
                student.class_name, school
            )
            cumulative_position = cumulative_rankings.get(student.id)
    else:
        # All terms
        summaries = StudentResultSummary.objects.filter(
            student=student
        ).select_related('subject', 'term').order_by('term', 'subject__name')
        
        term_gpa = 0
        cumulative_gpa = GradingService.calculate_cumulative_gpa(student)
        term_position = None
        cumulative_position = None
        
        # Group by term
        terms_data = {}
        for summary in summaries:
            term_name = summary.term.name if summary.term else "Unknown"
            if term_name not in terms_data:
                terms_data[term_name] = {
                    'term': summary.term,
                    'results': [],
                    'gpa': 0,
                }
            terms_data[term_name]['results'].append({
                'summary': summary,
                'assessments': list(AssessmentScore.objects.filter(
                    student=student, subject=summary.subject, term=summary.term
                )),
                'exam': ExamScore.objects.filter(
                    student=student, subject=summary.subject, term=summary.term
                ).first(),
            })
        
        results = terms_data
    
    # Get attendance summary
    from operations.models import StudentAttendance
    attendance_qs = StudentAttendance.objects.filter(student=student)
    if term_id:
        term_obj = terms.filter(id=term_id).first()
        if term_obj and term_obj.start_date and term_obj.end_date:
            attendance_qs = attendance_qs.filter(date__gte=term_obj.start_date, date__lte=term_obj.end_date)
    
    total_days = attendance_qs.count()
    present_days = attendance_qs.filter(status="present").count()
    absent_days = attendance_qs.filter(status="absent").count()
    late_days = attendance_qs.filter(status="late").count()
    attendance_rate = round((present_days / total_days * 100), 1) if total_days > 0 else 0
    
    return render(request, "academics/enhanced_report_card.html", {
        'student': student,
        'results': results,
        'terms': terms,
        'selected_term': term_id,
        'term_gpa': term_gpa,
        'cumulative_gpa': cumulative_gpa,
        'term_position': term_position,
        'cumulative_position': cumulative_position,
        'policy': policy,
        'school': school,
        'attendance_total': total_days,
        'attendance_present': present_days,
        'attendance_absent': absent_days,
        'attendance_late': late_days,
        'attendance_rate': attendance_rate,
    })


@login_required
def enhanced_report_card_pdf(request, student_id):
    """Generate PDF for enhanced report card."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    
    student = get_object_or_404(Student, id=student_id, school=school)
    if not _can_view_student_record(request.user, student):
        return redirect("home")
    
    from .models import StudentResultSummary, GradingPolicy
    from .services import GradingService
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm
    from django.utils import timezone as dj_timezone
    from datetime import datetime
    
    term_id = request.GET.get("term")
    term_label = "All Terms"
    
    summaries = StudentResultSummary.objects.filter(student=student)
    if term_id:
        summaries = summaries.filter(term_id=term_id)
        term = Term.objects.filter(id=term_id, school=school).first()
        term_label = term.name if term else "Unknown"
    
    summaries = list(summaries.select_related('subject', 'term').order_by('term', 'subject__name'))
    
    if not summaries:
        messages.error(request, "No results found for this student")
        return redirect("academics:enhanced_report_card", student_id=student_id)
    
    # Calculate stats
    total_scores = [s.final_score for s in summaries]
    avg_score = sum(total_scores) / len(total_scores) if total_scores else 0
    gpa = GradingService.calculate_term_gpa(student, term_id) if term_id else GradingService.calculate_cumulative_gpa(student)
    
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm)
    
    styles = getSampleStyleSheet()
    story = []
    
    # Header
    story.append(Paragraph(f"<b>{school.name}</b><br/>Enhanced Report Card", styles["Title"]))
    story.append(Paragraph(f"<font size=9>{getattr(school, 'address', '') or ''}</font>", styles["Normal"]))
    story.append(Spacer(1, 10))
    
    # Student info
    meta = [
        ["Student:", student.user.get_full_name() or student.user.username, "Class:", student.class_name or "—"],
        ["Adm No:", student.admission_number, "Term:", term_label],
        ["Average Score:", f"{avg_score:.1f}%", "GPA:", f"{gpa:.2f}"],
    ]
    meta_table = Table(meta, colWidths=[30*mm, 60*mm, 25*mm, 60*mm])
    meta_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor("#F3F4F6")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 15))
    
    # Results table
    rows = [["Subject", "CA (50%)", "Exam (50%)", "Final", "Grade", "Point"]]
    for s in summaries:
        rows.append([
            s.subject.name,
            f"{s.ca_score:.1f}",
            f"{s.exam_score:.1f}",
            f"{s.final_score:.1f}",
            s.grade,
            f"{s.grade_point:.1f}"
        ])
    
    results_table = Table(rows, colWidths=[50*mm, 25*mm, 25*mm, 25*mm, 20*mm, 20*mm])
    results_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
    ]))
    story.append(results_table)
    story.append(Spacer(1, 15))
    
    # Remarks section
    story.append(Paragraph("<b>Remarks</b>", styles["Heading3"]))
    remarks = Table([
        ["Class Teacher:", "________________________________________"],
        ["Headteacher:", "________________________________________"],
    ], colWidths=[35*mm, 140*mm])
    remarks.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(remarks)
    
    # Footer
    story.append(Spacer(1, 20))
    footer_text = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Mastex SchoolOS"
    story.append(Paragraph(f"<font size=8 color='gray'>{footer_text}</font>", styles["Normal"]))
    
    doc.build(story)
    
    filename = f"enhanced_report_card_{student.admission_number}_{term_label.replace(' ', '_')}.pdf"
    response = HttpResponse(buf.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
