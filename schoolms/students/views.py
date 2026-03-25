from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.hashers import make_password
from django.contrib import messages
from django.utils import timezone

from .models import (
    Student,
    SchoolClass,
    StudentAchievement,
    StudentActivity,
    StudentDiscipline,
    AbsenceRequest,
)
from accounts.models import User
from accounts.permissions import user_can_manage_school, is_school_admin
from schools.models import School


def _user_can_manage_school(request):
    """Use central permission helper for consistency across apps."""
    return user_can_manage_school(request.user)


@login_required
def parent_dashboard(request):
    try:
        from finance.models import Fee
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
        
        # Calculate average and position for each child
        stats_by_child = {}
        for child in children:
            child_results = results_by_child.get(child.id, [])
            if child_results:
                total = sum(r.score for r in child_results)
                avg = total / len(child_results)
                # Calculate position
                all_students_in_class = Student.objects.filter(school=child.school, class_name=child.class_name).values_list('id', flat=True)
                scores = []
                for sid in all_students_in_class:
                    rlist = Result.objects.filter(student_id=sid)
                    if rlist:
                        avg_score = sum(r.score for r in rlist) / len(rlist)
                        scores.append((sid, avg_score))
                scores.sort(key=lambda x: x[1], reverse=True)
                position = next((i+1 for i, (sid, _) in enumerate(scores) if sid == child.id), None)
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

        # Attendance summary per child (recent 14 days)
        attendance_by_child = {}
        for child in children:
            recent = StudentAttendance.objects.filter(
                student=child, date__gte=timezone.now().date() - timezone.timedelta(days=14)
            ).order_by("-date")
            attendance_by_child[child.id] = list(recent[:14])

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
        })
    except Exception as e:
        # If any error, still show the page with empty data
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

            # Calculate average and position
            stats = {}
            if results:
                total = sum(r.score for r in results)
                avg = total / len(results)
                # Calculate position in class
                all_students = Student.objects.filter(school=student.school, class_name=student.class_name).values_list('id', flat=True)
                scores = []
                for sid in all_students:
                    rlist = Result.objects.filter(student_id=sid)
                    if rlist:
                        avg_score = sum(r.score for r in rlist) / len(rlist)
                        scores.append((sid, avg_score))
                scores.sort(key=lambda x: x[1], reverse=True)
                position = next((i+1 for i, (sid, _) in enumerate(scores) if sid == student.id), None)
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
            "fees": fees_qs[:200],
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
        class_name = student.class_name or "Unassigned"
        if class_name not in students_by_class:
            students_by_class[class_name] = []
        students_by_class[class_name].append(student)

    # For a global (super admin) view, pass school=None; template handles this.
    return render(
        request,
        "students/student_list.html",
        {"students": students, "students_by_class": students_by_class, "school": school},
    )


@login_required
def student_detail(request, pk):
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    student = get_object_or_404(Student, pk=pk, school=school)
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
        # Update student fields
        student.admission_number = request.POST.get("admission_number", "").strip()
        student.class_name = request.POST.get("class_name", "").strip()
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
                user = User.objects.create(
                    username=username,
                    email=email or f"{username}@school.local",
                    first_name=first_name,
                    last_name=last_name,
                    password=make_password(password),
                    role="student",
                    school=school,
                    phone=phone,
                )
                Student.objects.create(
                    school=school,
                    user=user,
                    admission_number=admission_number,
                    class_name=chosen_class,
                    parent_id=parent_id or None,
                    date_enrolled=date_enrolled,
                )
                messages.success(request, "Student registered.")
                return redirect("students:student_list")
        else:
            messages.error(request, "Please fill all required fields.")
    parents = User.objects.filter(school=school, role="parent").order_by("username")
    classes = SchoolClass.objects.filter(school=school).order_by("name")
    return render(request, "students/student_register.html", {"school": school, "parents": parents, "classes": classes})


@login_required
def student_delete(request, pk):
    """
    Deactivate a student instead of hard-deleting.

    - Marks the linked user as inactive so they cannot log in.
    - Updates the student's status and exit_date so history is preserved.
    """
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    student = get_object_or_404(Student, pk=pk, school=school)
    
    if request.method == "POST":
        user = student.user

        # Mark student as no longer active in the school
        if student.status == "active":
            student.status = "withdrawn"
        if not student.exit_date:
            student.exit_date = timezone.now().date()
        student.save()

        # Deactivate login without deleting history
        user.is_active = False
        user.save(update_fields=["is_active"])

        messages.success(
            request,
            f"Student '{user.get_full_name() or user.username}' has been deactivated and archived. "
            "They can no longer log into the system, but their records are kept.",
        )
        return redirect("students:student_detail", pk=student.pk)
    
    return render(request, "students/confirm_delete.html", {
        "object": student,
        "type": "student (deactivation)",
        "cancel_url": "students:student_list"
    })


@login_required
def student_reactivate(request, pk):
    """
    Reactivate a previously deactivated student and restore login access.
    """
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")

    student = get_object_or_404(Student, pk=pk, school=school)

    if request.method == "POST":
        user = student.user

        student.status = "active"
        # Keep exit_date as history; do not clear it automatically
        student.save()

        user.is_active = True
        user.save(update_fields=["is_active"])

        messages.success(
            request,
            f"Student '{user.get_full_name() or user.username}' has been reactivated and can log in again.",
        )
        return redirect("students:student_detail", pk=student.pk)

    return render(
        request,
        "students/confirm_delete.html",
        {
            "object": student,
            "type": "student reactivation",
            "cancel_url": "students:student_detail",
        },
    )


@login_required
def promote_students(request):
    """Promote all students to the next class."""
    if not _user_can_manage_school(request):
        return redirect("home")
    
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    if request.method == "POST":
        # Get current class names and map to next class
        current_class = request.POST.get("current_class", "").strip()
        new_class = request.POST.get("new_class", "").strip()
        
        if current_class and new_class:
            # Update all students in the current class to the new class
            updated_count = Student.objects.filter(
                school=school, 
                class_name=current_class
            ).update(class_name=new_class)
            
            messages.success(request, f"Successfully promoted {updated_count} students from {current_class} to {new_class}.")
            return redirect("students:student_list")
        else:
            messages.error(request, "Please select both current class and new class.")
    
    # Get all unique class names for this school
    classes = Student.objects.filter(school=school).values_list('class_name', flat=True).distinct()
    classes = [c for c in classes if c]  # Remove empty values
    
    return render(request, "students/promote.html", {"school": school, "classes": classes})


@login_required
def class_list(request):
    """List and manage classes (school admin only)."""
    if not is_school_admin(request.user) and not request.user.is_superuser:
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")
    classes = SchoolClass.objects.filter(school=school).select_related("class_teacher").order_by("name")
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
    teachers = User.objects.filter(school=school, role__in=["admin", "teacher"]).order_by("first_name", "last_name")
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
