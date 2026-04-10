import hashlib
import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, F, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.hashers import make_password
from django.contrib import messages
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.safestring import mark_safe

from .models import (
    Student,
    SchoolClass,
    StudentAchievement,
    StudentActivity,
    StudentDiscipline,
    AbsenceRequest,
)
from .student_lifecycle import (
    bulk_exit_reason_for_status,
    deactivate_parent_if_no_active_children,
    reactivate_parent_if_has_active_children,
)
from accounts.models import User
from accounts.permissions import (
    user_can_manage_school,
    is_school_admin,
    can_bulk_promote_students,
)
from core.utils import log_activity
from schools.models import School
from core.pagination import paginate


def _user_can_manage_school(request):
    """Use central permission helper for consistency across apps."""
    return user_can_manage_school(request.user)


@login_required
def parent_dashboard(request):
    try:
        from finance.models import Fee, FeePayment
        from academics.models import Result, ExamType, Term, ExamSchedule
        
        children = Student.objects.filter(parent=request.user).select_related("school", "user")
        
        # Handle case with no children
        if not children:
            from operations.models import Announcement
            fallback_school = getattr(request.user, "school", None)
            announcements = (
                Announcement.objects.filter(
                    school=fallback_school,
                    target_audience__in=["all", "parents"],
                )
                .select_related("school", "created_by")
                .order_by("-is_pinned", "-created_at")[:10]
                if fallback_school
                else []
            )
            return render(request, "students/parent_dashboard.html", {
                "children": [],
                "fees_by_child": {},
                "results_by_child": {},
                "stats_by_child": {},
                "achievements_by_child": {},
                "activities_by_child": {},
                "discipline_by_child": {},
                "announcements": announcements,
                "attendance_by_child": {},
                "terms": [],
                "exam_types": [],
            })
        
        # Get fees for all children
        children_ids = [c.id for c in children]
        fees = Fee.objects.filter(student_id__in=children_ids).select_related("student", "student__user").order_by("-created_at")
        
        # Group fees by child
        fees_by_child = {}
        for fee in fees:
            child_id = fee.student_id
            if child_id not in fees_by_child:
                fees_by_child[child_id] = []
            fees_by_child[child_id].append(fee)
        
        # Get results for all children
        results_by_child = {}
        results = Result.objects.filter(student_id__in=children_ids).select_related("student", "subject", "exam_type", "term")
        
        for result in results:
            child_id = result.student_id
            if child_id not in results_by_child:
                results_by_child[child_id] = []
            results_by_child[child_id].append(result)
        
        stats_by_child = {}
        for child in children:
            child_results = results_by_child.get(child.id, [])
            if child_results:
                total = sum(r.score for r in child_results)
                avg = total / len(child_results)
                # Single aggregation query instead of per-student loop
                from django.db.models import Avg
                class_averages = (
                    Result.objects.filter(
                        student__school=child.school,
                        student__class_name=child.class_name,
                    )
                    .values("student_id")
                    .annotate(avg_score=Avg("score"))
                    .order_by("-avg_score")
                )
                position = None
                for i, row in enumerate(class_averages, 1):
                    if row["student_id"] == child.id:
                        position = i
                        break
                stats_by_child[child.id] = {"average": round(avg, 1), "position": position, "total_subjects": len(child_results)}
            else:
                stats_by_child[child.id] = {"average": None, "position": None, "total_subjects": 0}
        
        # Enrich portal with achievements, activities, and discipline records
        achievements_by_child = {}
        activities_by_child = {}
        discipline_by_child = {}

        achievements = (
            StudentAchievement.objects.filter(student_id__in=children_ids)
            .select_related("student", "student__user")
            .order_by("-date_achieved")
        )
        for ach in achievements:
            achievements_by_child.setdefault(ach.student_id, []).append(ach)

        activities = (
            StudentActivity.objects.filter(student_id__in=children_ids)
            .select_related("student", "student__user")
            .order_by("-start_date")
        )
        for act in activities:
            activities_by_child.setdefault(act.student_id, []).append(act)

        discipline_records = (
            StudentDiscipline.objects.filter(student_id__in=children_ids)
            .select_related("student", "student__user", "reported_by")
            .order_by("-incident_date")
        )
        for rec in discipline_records:
            discipline_by_child.setdefault(rec.student_id, []).append(rec)

        # Announcements for parents (from children's schools)
        from operations.models import Announcement
        from operations.models import StudentAttendance
        from django.utils import timezone
        schools = list({c.school for c in children})
        announcements = Announcement.objects.filter(
            school__in=schools,
            target_audience__in=["all", "parents"]
        ).select_related("school", "created_by").order_by("-is_pinned", "-created_at")[:10] if schools else []

        # Attendance summary per child (recent 14 days) — single query
        attendance_by_child = {}
        cutoff_date = timezone.now().date() - timezone.timedelta(days=14)
        all_attendance = (
            StudentAttendance.objects.filter(
                student_id__in=children_ids,
                date__gte=cutoff_date,
            )
            .order_by("-date")
        )
        for att in all_attendance:
            attendance_by_child.setdefault(att.student_id, [])
            if len(attendance_by_child[att.student_id]) < 14:
                attendance_by_child[att.student_id].append(att)

        # Get available terms, exam types, and exam schedule (per school)
        terms = Term.objects.filter(school__in=schools).order_by("-is_current", "-id") if schools else []
        exam_types = ExamType.objects.filter(school__in=schools) if schools else []
        exam_schedule = (
            ExamSchedule.objects.filter(school__in=schools, term__in=terms)
            .select_related("subject", "term")
            .order_by("exam_date", "start_time")
            if schools and terms
            else []
        )

        # Get recent payments for all children (last 5 payments)
        recent_payments = (
            FeePayment.objects.filter(fee__student_id__in=children_ids)
            .select_related("fee", "fee__student", "fee__school")
            .order_by("-created_at")[:5]
        )

        return render(request, "students/parent_dashboard.html", {
            "children": children,
            "announcements": announcements,
            "attendance_by_child": attendance_by_child,
            "fees_by_child": fees_by_child,
            "results_by_child": results_by_child,
            "stats_by_child": stats_by_child,
            "achievements_by_child": achievements_by_child,
            "activities_by_child": activities_by_child,
            "discipline_by_child": discipline_by_child,
            "terms": terms,
            "exam_types": exam_types,
            "exam_schedule": exam_schedule,
            "recent_payments": recent_payments,
        })
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading parent dashboard")
        return render(request, "students/parent_dashboard.html", {
            "children": [],
            "fees_by_child": {},
            "results_by_child": {},
            "stats_by_child": {},
            "achievements_by_child": {},
            "activities_by_child": {},
            "discipline_by_child": {},
            "announcements": [],
            "attendance_by_child": {},
            "terms": [],
            "exam_types": [],
            "exam_schedule": [],
        })


@login_required
def portal(request):
    """Single portal URL: parents see children; students see own dashboard."""
    if request.user.role == "parent":
        return parent_dashboard(request)
    if request.user.role == "student":
        try:
            student = Student.objects.get(user=request.user)
            # Get results for this student
            from academics.models import Result, ExamType, Term

            results = Result.objects.filter(student=student).select_related("subject", "exam_type", "term").order_by("-id")

            stats = {}
            if results:
                total = sum(r.score for r in results)
                avg = total / len(results)
                from django.db.models import Avg
                from django.core.cache import cache as _cache

                class_slug = hashlib.sha256(
                    (student.class_name or "").encode("utf-8")
                ).hexdigest()[:16]
                cache_key = f"class_pos_{student.school_id}_{class_slug}_{student.id}"
                position = _cache.get(cache_key)
                if position is None:
                    class_averages = list(
                        Result.objects.filter(
                            student__school=student.school,
                            student__class_name=student.class_name,
                        )
                        .values("student_id")
                        .annotate(avg_score=Avg("score"))
                        .order_by("-avg_score")
                    )
                    for i, row in enumerate(class_averages, 1):
                        if row["student_id"] == student.id:
                            position = i
                            break
                    if position is not None:
                        _cache.set(cache_key, position, 600)
                stats = {"average": round(avg, 1), "position": position, "total_subjects": len(results)}
            else:
                stats = {"average": None, "position": None, "total_subjects": 0}
            
            # Get available terms and exam types
            terms = Term.objects.filter(school=student.school).order_by("-is_current", "-id")
            exam_types = ExamType.objects.filter(school=student.school)

            # Announcements for students
            from operations.models import Announcement
            from operations.models import StudentAttendance
            from django.utils import timezone
            announcements = Announcement.objects.filter(
                school=student.school,
                target_audience__in=["all", "students"]
            ).select_related("created_by").order_by("-is_pinned", "-created_at")[:10]

            # Recent attendance
            recent_attendance = list(
                StudentAttendance.objects.filter(
                    student=student,
                    date__gte=timezone.now().date() - timezone.timedelta(days=14)
                ).order_by("-date")[:14]
            )

            # Term-over-term averages for progress chart
            from django.db.models import Avg
            term_averages = list(
                Result.objects.filter(student=student)
                .values("term__name", "term_id")
                .annotate(avg=Avg("score"))
                .order_by("term_id")
            )
            chart_labels = [t["term__name"] or f"Term {t['term_id']}" for t in term_averages]
            chart_data = [round(t["avg"], 1) for t in term_averages]

            # Class average per term for comparison
            class_term_averages = list(
                Result.objects.filter(
                    student__school=student.school,
                    student__class_name=student.class_name,
                )
                .values("term__name", "term_id")
                .annotate(avg=Avg("score"))
                .order_by("term_id")
            )
            class_chart_data = [round(t["avg"], 1) for t in class_term_averages]

            # Quiz attempts for unified results view
            from academics.models import QuizAttempt
            quiz_attempts = (
                QuizAttempt.objects.filter(student=student, is_completed=True)
                .select_related("quiz", "quiz__subject", "quiz__term")
                .order_by("-submitted_at")
            )

            # Enrich portal with achievements, activities, and discipline records
            achievements = (
                StudentAchievement.objects.filter(student=student)
                .order_by("-date_achieved")
            )
            activities = (
                StudentActivity.objects.filter(student=student)
                .order_by("-start_date")
            )
            discipline_records = (
                StudentDiscipline.objects.filter(student=student)
                .select_related("reported_by")
                .order_by("-incident_date")
            )

            from academics.models import bulk_annotate_grades
            bulk_annotate_grades(results, student.school)

            return render(request, "students/student_portal.html", {
                "student": student,
                "results": results,
                "stats": stats,
                "terms": terms,
                "exam_types": exam_types,
                "achievements": achievements,
                "activities": activities,
                "discipline_records": discipline_records,
                "announcements": announcements,
                "recent_attendance": recent_attendance,
                "chart_labels": chart_labels,
                "chart_data": chart_data,
                "class_chart_data": class_chart_data,
                "quiz_attempts": quiz_attempts,
            })
        except Student.DoesNotExist:
            return render(request, "students/student_portal.html", {"student": None})
    return redirect("home")


@login_required
def announcements_list(request):
    """
    Parent/student view: browse announcements relevant to them.
    """
    from operations.models import Announcement

    role = getattr(request.user, "role", None)
    if role == "student":
        try:
            student = Student.objects.select_related("school").get(user=request.user)
        except Student.DoesNotExist:
            messages.error(request, "No student record is linked to this account.")
            return redirect("home")
        qs = Announcement.objects.filter(
            school=student.school,
            target_audience__in=["all", "students"],
        )
        return render(
            request,
            "students/announcements_list.html",
            {"announcements": qs.select_related("created_by").order_by("-is_pinned", "-created_at")[:100]},
        )

    if role == "parent":
        children = list(Student.objects.filter(parent=request.user).select_related("school"))
        schools = list({c.school for c in children if c.school_id})
        fallback_school = getattr(request.user, "school", None)
        if fallback_school and fallback_school not in schools:
            schools.append(fallback_school)
        if not schools:
            return render(request, "students/announcements_list.html", {"announcements": []})
        qs = Announcement.objects.filter(
            school__in=schools,
            target_audience__in=["all", "parents"],
        )
        return render(
            request,
            "students/announcements_list.html",
            {"announcements": qs.select_related("school", "created_by").order_by("-is_pinned", "-created_at")[:100]},
        )

    return redirect("home")


@login_required
def fees_list(request):
    """
    Parent/student view: view fees (and payment status).
    """
    from finance.models import Fee

    role = getattr(request.user, "role", None)
    if role == "student":
        student = Student.objects.filter(user=request.user).select_related("user").first()
        if not student:
            messages.error(request, "No student record is linked to this account.")
            return redirect("home")
        fees = Fee.objects.filter(student=student).order_by("-created_at")
        return render(request, "students/fees_list.html", {"fees": fees, "mode": "student", "student": student})

    if role == "parent":
        children = list(Student.objects.filter(parent=request.user).select_related("user").order_by("class_name", "admission_number"))
        fees = Fee.objects.filter(student__in=children).select_related("student", "student__user").order_by("-created_at") if children else []
        return render(request, "students/fees_list.html", {"fees": fees, "mode": "parent", "children": children})

    return redirect("home")


@login_required
def results_list(request):
    """
    Parent/student view: view results with filters and report card link.
    """
    from academics.models import Result, Term, ExamType

    role = getattr(request.user, "role", None)
    term_id = (request.GET.get("term") or "").strip()
    exam_type_id = (request.GET.get("exam_type") or "").strip()
    student_id = (request.GET.get("student") or "").strip()

    if role == "student":
        student = Student.objects.filter(user=request.user).select_related("school", "user").first()
        if not student:
            messages.error(request, "No student record is linked to this account.")
            return redirect("home")
        qs = Result.objects.filter(student=student).select_related("subject", "exam_type", "term").order_by("-id")
        terms = Term.objects.filter(school=student.school).order_by("-is_current", "-id")
        exam_types = ExamType.objects.filter(school=student.school).order_by("name")
        if term_id:
            qs = qs.filter(term_id=term_id)
        if exam_type_id:
            qs = qs.filter(exam_type_id=exam_type_id)
        return render(
            request,
            "students/results_list.html",
            {
                "mode": "student",
                "student": student,
                "results": qs[:400],
                "terms": terms,
                "exam_types": exam_types,
                "selected_term": term_id,
                "selected_exam_type": exam_type_id,
            },
        )

    if role == "parent":
        children = list(Student.objects.filter(parent=request.user).select_related("school", "user").order_by("class_name", "admission_number"))
        if not children:
            return render(request, "students/results_list.html", {"mode": "parent", "children": [], "results": [], "terms": [], "exam_types": []})

        # Parent can filter by a specific child; default to first.
        active_child = None
        if student_id:
            active_child = next((c for c in children if str(c.id) == str(student_id)), None)
        if not active_child:
            active_child = children[0]

        qs = Result.objects.filter(student=active_child).select_related("subject", "exam_type", "term").order_by("-id")
        terms = Term.objects.filter(school=active_child.school).order_by("-is_current", "-id")
        exam_types = ExamType.objects.filter(school=active_child.school).order_by("name")
        if term_id:
            qs = qs.filter(term_id=term_id)
        if exam_type_id:
            qs = qs.filter(exam_type_id=exam_type_id)

        return render(
            request,
            "students/results_list.html",
            {
                "mode": "parent",
                "children": children,
                "active_child": active_child,
                "results": qs[:400],
                "terms": terms,
                "exam_types": exam_types,
                "selected_term": term_id,
                "selected_exam_type": exam_type_id,
            },
        )

    return redirect("home")


@login_required
def parent_child_detail(request, pk):
    """
    Parent view: child detail + quick actions.
    """
    if getattr(request.user, "role", None) != "parent":
        return redirect("home")

    child = get_object_or_404(Student.objects.select_related("user", "school", "parent"), pk=pk, parent=request.user)

    from academics.models import Result, Term, ExamType
    from finance.models import Fee
    from operations.models import StudentAttendance

    term_id = (request.GET.get("term") or "").strip()
    exam_type_id = (request.GET.get("exam_type") or "").strip()

    results_qs = Result.objects.filter(student=child).select_related("subject", "exam_type", "term").order_by("-id")
    if term_id:
        results_qs = results_qs.filter(term_id=term_id)
    if exam_type_id:
        results_qs = results_qs.filter(exam_type_id=exam_type_id)

    fees_qs = Fee.objects.filter(student=child).order_by("-created_at")
    fees_list = list(fees_qs[:200])
    first_unpaid_fee = next((f for f in fees_list if not f.is_fully_paid), None)
    attendance_qs = StudentAttendance.objects.filter(student=child).order_by("-date")[:30]
    absence_qs = AbsenceRequest.objects.filter(student=child).select_related("decided_by").order_by("-created_at")[:50]

    terms = Term.objects.filter(school=child.school).order_by("-is_current", "-id")
    exam_types = ExamType.objects.filter(school=child.school).order_by("name")

    return render(
        request,
        "students/parent_child_detail.html",
        {
            "child": child,
            "results": results_qs[:200],
            "fees": fees_list,
            "first_unpaid_fee": first_unpaid_fee,
            "attendance": attendance_qs,
            "absence_requests": absence_qs,
            "terms": terms,
            "exam_types": exam_types,
            "selected_term": term_id,
            "selected_exam_type": exam_type_id,
        },
    )


@login_required
def student_list(request):
    """
    List students for the current school.

    - School admins / staff see their own school's students.
    - Platform super admins (no attached school) see students across all schools.
    - If a user is not allowed or not attached to any school, show a friendly
      empty state instead of redirecting in circles.
    """
    if not _user_can_manage_school(request) and not getattr(request.user, "is_super_admin", False):
        return render(
            request,
            "students/student_list.html",
            {
                "students": [],
                "students_by_class": {},
                "school": None,
                "no_access": True,
            },
        )

    school = getattr(request.user, "school", None)

    # Super admin without a school: show a cross-school view
    if not school and getattr(request.user, "is_super_admin", False):
        students = (
            Student.objects.select_related("user", "parent", "school")
            .order_by("school__name", "class_name", "admission_number")
        )
    elif school:
        students = (
            Student.objects.filter(school=school)
            .select_related("user", "parent")
            .order_by("class_name", "admission_number")
        )
    else:
        # School-scoped user but no school attached: show explanatory state
        return render(
            request,
            "students/student_list.html",
            {
                "students": [],
                "students_by_class": {},
                "school": None,
                "no_school": True,
            },
        )

    # Group students by class for display
    students_by_class = {}
    for student in students:
        cls = student.class_name or "Unassigned"
        if cls not in students_by_class:
            students_by_class[cls] = []
        students_by_class[cls].append(student)

    page_obj = paginate(request, students, per_page=30)

    return render(
        request,
        "students/student_list.html",
        {"students": page_obj, "students_by_class": students_by_class, "school": school, "page_obj": page_obj},
    )


@login_required
def student_detail(request, pk):
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    student = get_object_or_404(
        Student.objects.select_related("user", "parent", "school"), pk=pk, school=school
    )
    return render(request, "students/student_detail.html", {"student": student})


@login_required
def student_edit(request, pk):
    """Edit an existing student - including linking to a parent."""
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    student = get_object_or_404(Student, pk=pk, school=school)
    
    if request.method == "POST":
        student.admission_number = request.POST.get("admission_number", "").strip()
        student.class_name = request.POST.get("class_name", "").strip()
        
        phone = request.POST.get("phone", "").strip()
        gender = request.POST.get("gender", "").strip()
        
        user = student.user
        user.phone = phone if phone else ""
        if gender in ["male", "female"]:
            user.gender = gender
        user.save()
        
        student.status = request.POST.get("status", "active")
        
        # Update parent link
        parent_id = request.POST.get("parent")
        if parent_id:
            try:
                parent = User.objects.get(pk=parent_id, school=school, role="parent")
                student.parent = parent
            except User.DoesNotExist:
                messages.error(request, "Selected parent not found.")
        else:
            student.parent = None
        
        student.save()
        messages.success(request, "Student updated successfully.")
        return redirect("students:student_detail", pk=student.pk)
    
    # Get all parents in this school for the dropdown
    parents = User.objects.filter(school=school, role="parent").order_by("first_name", "last_name")
    classes = SchoolClass.objects.filter(school=school).order_by("name")
    
    return render(request, "students/student_edit.html", {
        "student": student,
        "parents": parents,
        "classes": classes,
    })


@login_required
def student_register(request):
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        password = request.POST.get("password", "")
        admission_number = request.POST.get("admission_number", "").strip()
        class_name = request.POST.get("class_name", "").strip()
        class_selected = request.POST.get("class_selected", "").strip()
        parent_id = request.POST.get("parent") or None
        phone = request.POST.get("phone", "").strip() or None
        date_enrolled_str = request.POST.get("date_enrolled", "").strip()

        create_parent = request.POST.get("create_parent") == "on"
        if create_parent:
            p_first = request.POST.get("parent_first_name", "").strip()
            p_last = request.POST.get("parent_last_name", "").strip()
            p_phone = request.POST.get("parent_phone", "").strip()
            p_email = request.POST.get("parent_email", "").strip()
            if p_first and p_last and p_phone:
                import uuid as _uuid
                p_username = f"parent_{p_phone.replace(' ', '').replace('+', '')[-8:]}"
                if User.objects.filter(username=p_username).exists():
                    p_username = f"parent_{_uuid.uuid4().hex[:8]}"
                _parent_pw = get_random_string(12)
                parent_user = User.objects.create(
                    username=p_username,
                    first_name=p_first,
                    last_name=p_last,
                    email=p_email or f"{p_username}@school.local",
                    phone=p_phone,
                    role="parent",
                    school=school,
                    password=make_password(_parent_pw),
                    must_change_password=True,
                )
                parent_id = parent_user.id
            else:
                messages.error(request, "Parent first name, last name, and phone are required when creating a new parent.")
                parents = User.objects.filter(school=school, role="parent").order_by("username")
                classes = SchoolClass.objects.filter(school=school).order_by("name")
                return render(request, "students/student_register.html", {"school": school, "parents": parents, "classes": classes})

        if username and admission_number and password:
            if User.objects.filter(username=username).exists():
                messages.error(request, "That username is already taken.")
            elif email and User.objects.filter(email=email).exists():
                messages.error(request, "That email is already in use.")
            else:
                chosen_class = class_name or class_selected
                date_enrolled = None
                if date_enrolled_str:
                    try:
                        date_enrolled = timezone.datetime.strptime(date_enrolled_str, "%Y-%m-%d").date()
                    except ValueError:
                        messages.error(request, "Invalid enrolled date format.")
                        date_enrolled = None
                gender = request.POST.get("gender", "").strip()
                user = User.objects.create(
                    username=username,
                    email=email or f"{username}@school.local",
                    first_name=first_name,
                    last_name=last_name,
                    password=make_password(password),
                    role="student",
                    school=school,
                    phone=phone,
                    gender=gender if gender in ["male", "female"] else "",
                )
                Student.objects.create(
                    school=school,
                    user=user,
                    admission_number=admission_number,
                    class_name=chosen_class,
                    parent_id=parent_id or None,
                    date_enrolled=date_enrolled,
                )
                messages.success(request, "Student registered successfully.")
                return redirect("students:student_list")
        else:
            messages.error(request, "Please fill all required fields.")
    parents = User.objects.filter(school=school, role="parent").order_by("username")
    classes = SchoolClass.objects.filter(school=school).order_by("name")
    return render(request, "students/student_register.html", {"school": school, "parents": parents, "classes": classes})


@login_required
def student_delete(request, pk):
    """Legacy URL — use the canonical exit flow (records exit reason and parent options)."""
    return redirect("students:student_exit", pk=pk)


@login_required
def student_exit(request, pk):
    """
    Process student exit with specific reason - allows graduating, withdrawing,
    suspending, or dismissing an individual student.
    """
    if not _user_can_manage_school(request):
        return redirect("home")
    
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    student = get_object_or_404(Student, pk=pk, school=school)

    if request.method == "GET":
        if student.status not in ("active", "suspended"):
            messages.info(
                request,
                "This student is not on roll as active or suspended. Open their profile to reactivate or review history.",
            )
            return redirect("students:student_detail", pk=pk)

    if request.method == "POST":
        exit_reason = request.POST.get("exit_reason", "").strip()
        exit_notes = request.POST.get("exit_notes", "").strip()
        deactivate_parent = request.POST.get("deactivate_parent") == "on"
        
        # Map exit reason to status
        status_map = {
            "graduated": "graduated",
            "left": "withdrawn",
            "transferred": "withdrawn",
            "suspended": "suspended",
            "expelled": "dismissed",
            "deceased": "deceased",
        }
        
        new_status = status_map.get(exit_reason, "withdrawn")
        
        if exit_reason not in status_map:
            messages.error(request, "Please select a valid exit reason.")
            return redirect("students:student_exit", pk=pk)

        with transaction.atomic():
            student.status = new_status
            student.exit_date = timezone.now().date()
            student.exit_reason = exit_reason
            student.exit_notes = exit_notes.strip()
            student.save()

            if new_status != "suspended" and student.user:
                User.objects.filter(pk=student.user_id).update(is_active=False)

            parent_deactivated = False
            if deactivate_parent and student.parent_id:
                parent_deactivated = deactivate_parent_if_no_active_children(
                    student.parent, school, exclude_student_pk=student.pk
                )

        status_display = dict(Student.STATUS_CHOICES).get(new_status, new_status)
        msg = (
            f"Student '{student.user.get_full_name() or student.user.username}' has been marked as {status_display}. "
            f"Exit reason: {exit_reason}. Records preserved."
        )
        if parent_deactivated:
            msg += " Linked parent account was deactivated (no other active children at this school)."
        messages.success(request, msg)

        log_activity(
            request.user,
            "STUDENT_EXIT",
            f"Student {student.id} exited: {exit_reason}",
            school=school,
            request=request,
        )
        return redirect("students:student_detail", pk=student.pk)
    
    return render(request, "students/student_exit.html", {
        "student": student,
        "cancel_url": "students:student_detail"
    })


@login_required
def student_reactivate(request, pk):
    """
    Reactivate a previously exited student, restore login, and optionally the
    linked parent when they again have an active child at this school.
    """
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")

    student = get_object_or_404(
        Student.objects.select_related("user", "parent"), pk=pk, school=school
    )

    if student.status == "active" and getattr(student.user, "is_active", True):
        messages.info(request, "This student is already active.")
        return redirect("students:student_detail", pk=pk)

    if request.method == "POST":
        reactivate_parent = request.POST.get("reactivate_parent") == "on"

        with transaction.atomic():
            student.status = "active"
            student.exit_reason = ""
            student.exit_notes = ""
            student.save()

            User.objects.filter(pk=student.user_id).update(is_active=True)

            parent_reactivated = False
            if reactivate_parent and student.parent_id:
                parent_reactivated = reactivate_parent_if_has_active_children(
                    student.parent, school
                )

        user = student.user
        msg = (
            f"Student '{user.get_full_name() or user.username}' is active again and can log in."
        )
        if parent_reactivated:
            msg += " Linked parent account was reactivated (they have an active child at this school)."
        messages.success(request, msg)
        log_activity(
            request.user,
            "STUDENT_REACTIVATE",
            f"Student {student.id} reactivated",
            school=school,
            request=request,
        )
        return redirect("students:student_detail", pk=student.pk)

    suggest_parent = bool(
        student.parent_id and not student.parent.is_active
    )
    return render(
        request,
        "students/student_reactivate.html",
        {
            "student": student,
            "suggest_reactivate_parent": suggest_parent,
        },
    )


_STANDARD_PROMOTION_TARGETS = (
    "Nursery 1",
    "Nursery 2",
    "Kindergarten 1",
    "Kindergarten 2",
    "Primary 1",
    "Primary 2",
    "Primary 3",
    "Primary 4",
    "Primary 5",
    "Primary 6",
    "JHS 1",
    "JHS 2",
    "JHS 3",
    "Form 1",
    "Form 2",
    "Form 3",
    "Form 4",
    "SHS 1",
    "SHS 2",
    "SHS 3",
)


def _promotion_source_class_names(school):
    """Classes that appear in roster or class setup (promote *from*)."""
    from_schoolclass = set(
        SchoolClass.objects.filter(school=school).values_list("name", flat=True)
    )
    from_students = set(
        Student.objects.filter(school=school, status="active")
        .exclude(class_name="")
        .values_list("class_name", flat=True)
    )
    names = from_schoolclass | from_students
    return sorted(names, key=lambda x: (x.lower(), x))


def _promotion_target_class_names(school):
    """Allowed promote-to labels: roster, class setup, and common templates."""
    return sorted(
        set(_promotion_source_class_names(school)) | set(_STANDARD_PROMOTION_TARGETS),
        key=lambda x: (x.lower(), x),
    )


def _active_student_counts_by_class(school):
    rows = (
        Student.objects.filter(school=school, status="active")
        .exclude(class_name="")
        .values("class_name")
        .annotate(c=Count("id"))
    )
    return {row["class_name"]: row["c"] for row in rows}


@login_required
def promote_students(request):
    """
    Move all *active* students from one class_name to another and refresh school_class FK
    when a matching SchoolClass row exists.
    """
    if not can_bulk_promote_students(request.user):
        messages.error(request, "You do not have permission to run class promotions.")
        return redirect("home")

    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")

    source_names = set(_promotion_source_class_names(school))
    target_names = set(_promotion_target_class_names(school))

    if request.method == "POST":
        current_class = request.POST.get("current_class", "").strip()
        new_class = request.POST.get("new_class", "").strip()
        confirm = request.POST.get("confirm_promote") == "on"

        if current_class not in source_names:
            messages.error(request, "Invalid source class.")
        elif new_class not in target_names:
            messages.error(request, "Invalid destination class.")
        elif not confirm:
            messages.error(request, "Please tick the box to confirm this promotion.")
        elif current_class == new_class:
            messages.error(request, "Source and destination class must be different.")
        else:
            with transaction.atomic():
                qs = Student.objects.filter(
                    school=school,
                    class_name=current_class,
                    status="active",
                )
                ids = list(qs.values_list("pk", flat=True))
                if not ids:
                    messages.warning(
                        request,
                        f"No active students in “{current_class}” to promote.",
                    )
                else:
                    qs.update(class_name=new_class)
                    sc = SchoolClass.objects.filter(school=school, name=new_class).first()
                    follow = Student.objects.filter(pk__in=ids)
                    if sc:
                        follow.update(school_class=sc)
                    else:
                        follow.update(school_class=None)

                    updated_count = len(ids)
                    messages.success(
                        request,
                        f"Promoted {updated_count} student(s) from “{current_class}” to “{new_class}”.",
                    )
                    log_activity(
                        request.user,
                        "PROMOTE_STUDENTS",
                        f"Promoted {updated_count} from {current_class!r} to {new_class!r}",
                        school=school,
                        request=request,
                    )
                    return redirect("students:student_list")

    class_counts = _active_student_counts_by_class(school)

    return render(
        request,
        "students/promote.html",
        {
            "school": school,
            "classes": _promotion_source_class_names(school),
            "target_classes": _promotion_target_class_names(school),
            "class_counts": class_counts,
        },
    )


@login_required
def class_list(request):
    """List and manage classes (school admin only)."""
    if not is_school_admin(request.user) and not request.user.is_superuser:
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")
    classes = (
        SchoolClass.objects.filter(school=school)
        .select_related("class_teacher")
        .annotate(
            student_count=Count(
                "school__student_set",
                filter=Q(school__student_set__class_name=F("name")),
            )
        )
        .order_by("name")
    )
    return render(request, "students/class_list.html", {"classes": classes, "school": school})


@login_required
def class_create(request):
    if not is_school_admin(request.user) and not request.user.is_superuser:
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        capacity = request.POST.get("capacity") or None
        teacher_id = request.POST.get("class_teacher") or None
        if name:
            try:
                cap = int(capacity) if capacity else 40
                teacher = User.objects.get(pk=teacher_id, school=school) if teacher_id else None
                SchoolClass.objects.get_or_create(school=school, name=name, defaults={"capacity": cap, "class_teacher": teacher})
                messages.success(request, f"Class {name} created.")
                return redirect("students:class_list")
            except (User.DoesNotExist, ValueError):
                pass
    teachers = User.objects.filter(school=school, role__in=["school_admin", "teacher"]).order_by("first_name", "last_name")
    return render(request, "students/class_form.html", {"school": school, "teachers": teachers})


@login_required
def absence_request_create(request):
    """
    Allow a logged-in student to request permission to be absent.
    """
    if getattr(request.user, "role", None) != "student":
        return redirect("home")

    try:
        student = Student.objects.select_related("school", "user").get(user=request.user)
    except Student.DoesNotExist:
        messages.error(request, "No student record is linked to this account.")
        return redirect("home")

    if not student.is_active_student:
        messages.error(request, "Inactive or exited students cannot request absence.")
        return redirect("home")

    if request.method == "POST":
        date_str = request.POST.get("date", "").strip()
        reason = request.POST.get("reason", "").strip()

        if not date_str or not reason:
            messages.error(request, "Please provide both a date and a reason.")
        else:
            try:
                # Parse date from the HTML date input (YYYY-MM-DD)
                absence_date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                messages.error(request, "Invalid date format.")
            else:
                AbsenceRequest.objects.create(
                    school=student.school,
                    student=student,
                    submitted_by=request.user,
                    date=absence_date,
                    reason=reason,
                )
                messages.success(request, "Your absence request has been submitted for approval.")
                return redirect("students:my_absence_requests")

    return render(
        request,
        "students/absence_request_form.html",
        {
            "student": student,
        },
    )


@login_required
def my_absence_requests(request):
    """
    Student view: list their own absence requests.
    """
    if getattr(request.user, "role", None) != "student":
        return redirect("home")

    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return render(
            request,
            "students/absence_request_list_student.html",
            {"student": None, "requests": []},
        )

    requests = student.absence_requests.select_related("decided_by").all()
    return render(
        request,
        "students/absence_request_list_student.html",
        {"student": student, "requests": requests},
    )


@login_required
def parent_absence_request_create(request):
    """
    Parent view: submit an absence request for one of their linked children.
    """
    if getattr(request.user, "role", None) != "parent":
        return redirect("home")

    children = list(
        Student.objects.filter(parent=request.user)
        .select_related("school", "user")
        .order_by("class_name", "admission_number")
    )
    if not children:
        messages.error(request, "No children are linked to this parent account yet.")
        return redirect("portal")

    if request.method == "POST":
        student_id = (request.POST.get("student_id") or "").strip()
        date_str = (request.POST.get("date") or "").strip()
        reason = (request.POST.get("reason") or "").strip()

        if not student_id or not date_str or not reason:
            messages.error(request, "Please select a child and provide both a date and a reason.")
        else:
            try:
                child = Student.objects.select_related("school", "user").get(id=int(student_id), parent=request.user)
            except (Student.DoesNotExist, ValueError):
                messages.error(request, "Invalid child selected.")
            else:
                if not child.is_active_student:
                    messages.error(request, "Inactive or exited students cannot request absence.")
                else:
                    try:
                        absence_date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
                    except ValueError:
                        messages.error(request, "Invalid date format.")
                    else:
                        AbsenceRequest.objects.create(
                            school=child.school,
                            student=child,
                            submitted_by=request.user,
                            date=absence_date,
                            reason=reason,
                        )
                        messages.success(request, "Absence request submitted for approval.")
                        return redirect("students:parent_absence_requests")

    return render(request, "students/absence_request_form_parent.html", {"children": children})


@login_required
def parent_absence_requests(request):
    """
    Parent view: list absence requests across all of their children.
    """
    if getattr(request.user, "role", None) != "parent":
        return redirect("home")

    qs = (
        AbsenceRequest.objects.filter(student__parent=request.user)
        .select_related("student", "student__user", "decided_by")
        .order_by("-created_at")
    )
    return render(request, "students/absence_request_list_parent.html", {"requests": qs})


@login_required
def absence_requests_review(request):
    """
    Staff / school admin view: see absence requests for their school.
    """
    if not _user_can_manage_school(request) and not getattr(request.user, "is_super_admin", False):
        return redirect("home")

    school = getattr(request.user, "school", None)

    if school:
        qs = AbsenceRequest.objects.filter(school=school)
    else:
        # Super admins can see all schools
        qs = AbsenceRequest.objects.select_related("school")

    status_filter = request.GET.get("status") or ""
    if status_filter in {"pending", "approved", "rejected"}:
        qs = qs.filter(status=status_filter)

    requests_qs = qs.select_related("student", "student__user", "decided_by").order_by("-created_at")
    return render(
        request,
        "students/absence_request_list_staff.html",
        {"requests": requests_qs, "school": school, "status_filter": status_filter},
    )


@login_required
def absence_request_decide(request, pk, decision):
    """
    Approve or reject an absence request.
    """
    if not _user_can_manage_school(request) and not getattr(request.user, "is_super_admin", False):
        return redirect("home")

    school = getattr(request.user, "school", None)

    if school:
        absence_request = get_object_or_404(AbsenceRequest, pk=pk, school=school)
    else:
        absence_request = get_object_or_404(AbsenceRequest, pk=pk)

    if absence_request.status != "pending":
        messages.info(request, "This request has already been reviewed.")
        return redirect("students:absence_requests_review")

    if decision not in {"approve", "reject"}:
        messages.error(request, "Invalid decision.")
        return redirect("students:absence_requests_review")

    absence_request.status = "approved" if decision == "approve" else "rejected"
    absence_request.decided_by = request.user
    absence_request.decided_at = timezone.now()
    absence_request.save()

    messages.success(request, f"Absence request has been {absence_request.status}.")
    return redirect("students:absence_requests_review")


@login_required
def bulk_student_status(request):
    """
    Bulk update student status by class - allows graduating, withdrawing, 
    or dismissing an entire class at once.
    
    Supports ?status= query parameter to pre-select a status (e.g., ?status=graduated).
    """
    if not _user_can_manage_school(request):
        return redirect("home")
    
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    # Check for pre-selected status via query param
    preselected_status = request.GET.get("status", "")
    if preselected_status and preselected_status not in ["graduated", "withdrawn", "dismissed", "active"]:
        preselected_status = ""
    
    if request.method == "POST":
        class_name = request.POST.get("class_name", "").strip()
        new_status = request.POST.get("status", "").strip()
        deactivate_parent = request.POST.get("deactivate_parent") == "on"
        reactivate_parent = request.POST.get("reactivate_parent") == "on"

        if not class_name or new_status not in ["graduated", "withdrawn", "dismissed", "active"]:
            messages.error(request, "Please select a valid class and status.")
            return redirect("students:bulk_student_status")

        is_reactivation = new_status == "active"

        if is_reactivation:
            students = Student.objects.filter(school=school, class_name=class_name).exclude(
                status="active"
            )
        else:
            students = Student.objects.filter(
                school=school, class_name=class_name, status="active"
            )

        if not students.exists():
            label = "non-active" if is_reactivation else "active"
            messages.warning(request, f"No {label} students found in class {class_name}.")
            return redirect("students:student_list")

        today = timezone.now().date()
        parents_deactivated_ids = set()
        parents_reactivated_ids = set()
        updated_count = 0

        with transaction.atomic():
            student_list = list(students.select_related("user", "parent"))
            for student in student_list:
                student.status = new_status
                if is_reactivation:
                    student.exit_reason = ""
                    student.exit_notes = ""
                    student.save()
                    if student.user_id:
                        User.objects.filter(pk=student.user_id).update(is_active=True)
                    if reactivate_parent and student.parent_id:
                        parents_reactivated_ids.add(student.parent_id)
                else:
                    student.exit_date = today
                    student.exit_reason = bulk_exit_reason_for_status(new_status)
                    student.save()
                    if student.user_id:
                        User.objects.filter(pk=student.user_id).update(is_active=False)
                    if deactivate_parent and student.parent_id:
                        if deactivate_parent_if_no_active_children(
                            student.parent, school, exclude_student_pk=student.pk
                        ):
                            parents_deactivated_ids.add(student.parent_id)
                updated_count += 1

            parents_reactivated = 0
            if is_reactivation and reactivate_parent and parents_reactivated_ids:
                for pid in parents_reactivated_ids:
                    parent = User.objects.filter(pk=pid).first()
                    if parent and reactivate_parent_if_has_active_children(parent, school):
                        parents_reactivated += 1

        status_display = dict(Student.STATUS_CHOICES).get(new_status, new_status)
        msg = f"Updated {updated_count} student(s) in {class_name} to “{status_display}”."
        if not is_reactivation and deactivate_parent and parents_deactivated_ids:
            msg += f" Deactivated {len(parents_deactivated_ids)} parent account(s) with no remaining active children."
        if is_reactivation and reactivate_parent and parents_reactivated:
            msg += f" Reactivated {parents_reactivated} parent account(s) that now have an active child."

        messages.success(request, msg)
        log_activity(
            request.user,
            "BULK_STUDENT_STATUS",
            f"Updated {updated_count} students in {class_name!r} to {new_status}",
            school=school,
            request=request,
        )
        return redirect("students:student_list")
    
    # Get all classes for this school (only those with students)
    classes = Student.objects.filter(school=school).values_list('class_name', flat=True).distinct()
    classes = [c for c in classes if c]
    
    return render(request, "students/bulk_status.html", {
        "school": school,
        "classes": classes,
        "preselected_status": preselected_status,
    })


@login_required
def graduate_class(request):
    """
    One-click graduation for an entire class - sets status to 'graduated',
    sets exit date, and optionally deactivates parents.
    """
    if not can_bulk_promote_students(request):
        messages.error(request, "You do not have permission to graduate a whole class.")
        return redirect("home")
    
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    if request.method == "POST":
        class_name = request.POST.get("class_name", "").strip()
        deactivate_parents = request.POST.get("deactivate_parents") == "on"

        if not class_name:
            messages.error(request, "Please select a class.")
            return redirect("students:graduate_class")

        active_qs = Student.objects.filter(
            school=school, class_name=class_name, status="active"
        )
        if not active_qs.exists():
            messages.warning(request, f"No active students found in class {class_name}.")
            return redirect("students:student_list")

        today = timezone.now().date()
        parents_deactivated_ids = set()

        with transaction.atomic():
            student_ids = list(active_qs.values_list("pk", flat=True))
            Student.objects.filter(pk__in=student_ids).update(
                status="graduated",
                exit_date=today,
                exit_reason="graduated",
            )
            graduated = list(
                Student.objects.filter(pk__in=student_ids).select_related("user", "parent")
            )

            if deactivate_parents:
                for student in graduated:
                    if student.parent_id and deactivate_parent_if_no_active_children(
                        student.parent, school, exclude_student_pk=student.pk
                    ):
                        parents_deactivated_ids.add(student.parent_id)

            for student in graduated:
                if student.user_id:
                    User.objects.filter(pk=student.user_id).update(is_active=False)

        count = len(student_ids)
        msg = f"Graduated {count} student(s) from class {class_name}."
        if deactivate_parents and parents_deactivated_ids:
            msg += f" Deactivated {len(parents_deactivated_ids)} parent account(s) with no remaining active children."

        messages.success(request, msg)
        log_activity(
            request.user,
            "GRADUATE_CLASS",
            f"Graduated {count} students from {class_name!r}",
            school=school,
            request=request,
        )
        return redirect("students:student_list")
    
    # Get classes for the form
    classes = Student.objects.filter(school=school, status="active").values_list('class_name', flat=True).distinct()
    classes = [c for c in classes if c]
    
    return render(request, "students/graduate_class.html", {
        "school": school,
        "classes": classes,
    })
