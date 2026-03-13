from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q

from students.models import Student
from schools.models import School
from accounts.permissions import user_can_manage_school
from .models import Subject, ExamType, Term, Result, GradeBoundary, Homework, ExamSchedule


def _get_school(request):
    """Get current user's school."""
    if not request.user.is_authenticated:
        return None
    return getattr(request.user, "school", None)


def _user_can_manage_school(request):
    """Delegate to central permission helper for consistency."""
    return user_can_manage_school(request.user)


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
    }
    
    return render(request, "academics/result_upload.html", context)


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
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
    class_filter = request.GET.get("class")
    qs = Homework.objects.filter(school=school).select_related("subject", "created_by").order_by("-due_date")
    if class_filter:
        qs = qs.filter(class_name=class_filter)
    classes = list(Student.objects.filter(school=school).values_list("class_name", flat=True).distinct())
    classes = [c for c in classes if c]
    return render(request, "academics/homework_list.html", {"homework": qs, "school": school, "classes": classes})


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
def exam_schedule_list(request):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    if not _user_can_manage_school(request):
        return redirect("accounts:school_dashboard")
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
    classes = (
        Student.objects.filter(school=school).values_list("class_name", flat=True).distinct()
    )
    classes = [c for c in classes if c]
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
def report_card_view(request, student_id):
    school = _get_school(request)
    if not school:
        return redirect("accounts:dashboard") if request.user.is_authenticated else redirect("home")
    student = get_object_or_404(Student, id=student_id, school=school)
    term_id = request.GET.get("term")
    results = Result.objects.filter(student=student).select_related("subject", "exam_type", "term").order_by("term", "subject")
    if term_id:
        results = results.filter(term_id=term_id)
    terms = Term.objects.filter(school=school).order_by("-is_current", "-id")
    total = sum(r.score for r in results) if results else 0
    avg = (total / len(results)) if results else 0
    from academics.models import get_grade_for_score
    grades = [get_grade_for_score(school, r.score) for r in results]
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
        },
    )
