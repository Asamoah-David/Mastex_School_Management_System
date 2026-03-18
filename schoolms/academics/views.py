from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse

from students.models import Student
from schools.models import School
from accounts.permissions import user_can_manage_school
from .models import Subject, ExamType, Term, Result, GradeBoundary, Homework, ExamSchedule, Timetable


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
    return render(request, "accounts/confirm_delete.html", {"object": result, "type": "result"})


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
        # Filter by term date range (approximate)
        term = terms.filter(id=term_id).first()
        if term:
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
