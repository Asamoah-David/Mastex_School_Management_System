from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.urls import reverse

from accounts.models import STAFF_ROLES, User
from accounts.hr_utils import sync_expired_staff_contracts
from accounts.hr_models import StaffContract, StaffPayrollPayment, StaffRoleChangeLog, StaffTeachingAssignment
from accounts.permissions import (
    user_can_manage_school,
    can_manage_finance,
    is_super_admin,
    can_review_staff_leave,
)
from academics.models import Subject, Timetable, Term
from schools.models import School
from students.models import Student, SchoolClass
from finance.models import Fee, FeePayment, FeeStructure
from finance.staff_payroll_paystack import school_staff_paystack_allowed
from operations.models import StudentAttendance, TeacherAttendance, AcademicCalendar
from operations.activity import recent_activities_for_dashboard
from core.pagination import paginate
from accounts.dashboard_insights import (
    build_academic_insights,
    build_attendance_trend,
    build_finance_insights,
    build_teacher_academic_insights,
    build_teacher_attendance_trend,
    build_teacher_students_by_class_chart,
)

# Supabase Storage for media files
try:
    from core.supabase_storage import supabase_storage
    SUPABASE_STORAGE_AVAILABLE = True
except ImportError:
    supabase_storage = None
    SUPABASE_STORAGE_AVAILABLE = False


def logout_view(request):
    """Log out and clear messages, then redirect to login page."""
    # Clear all messages before logging out so they don't appear on login page
    storage = messages.get_messages(request)
    for _ in storage:
        pass  # This marks messages as read/cleared
    logout(request)
    return redirect("/accounts/login/")


def home(request):
    """
    Smart entry point for the whole site.

    - If not logged in, send to the login page.
    - If logged in, send to the appropriate dashboard/portal based on role.
    This avoids redirect loops when a user already has a session.
    """
    # Make the root URL a stable landing page: render the login page directly
    # when unauthenticated instead of redirecting. This reduces redirect hops
    # and prevents proxy-level redirect loops from blocking the login screen.
    if request.user.is_authenticated:
        role = getattr(request.user, "role", None)
        if role in ["parent", "student"]:
            return redirect("portal")
        if role == "teacher":
            return redirect("accounts:teacher_dashboard")
        if role in ("school_admin", "deputy_head", "hod", "accountant",
                    "librarian", "admission_officer", "school_nurse", "admin_assistant", "staff"):
            return redirect("accounts:school_dashboard")
        if getattr(request.user, "is_superuser", False) or role == "super_admin":
            return redirect("accounts:dashboard")
    return login_view(request)

def _login_rate_limit_key(request):
    """Return a cache key based on client IP for login rate limiting."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "unknown")
    return f"login_ratelimit:{ip}"


def login_view(request):
    # If already logged in, send to the right place once (no loop)
    if request.user.is_authenticated:
        role = getattr(request.user, "role", None)
        if role in ["parent", "student"]:
            return redirect("portal")
        if role == "teacher":
            return redirect("accounts:teacher_dashboard")
        if role in ("school_admin", "deputy_head", "hod", "accountant",
                    "librarian", "admission_officer", "school_nurse", "admin_assistant", "staff"):
            return redirect("accounts:school_dashboard")
        if getattr(request.user, "is_superuser", False) or role == "super_admin":
            return redirect("accounts:dashboard")
        return redirect("accounts:dashboard")
    
    # Clear any old messages that might have been set from previous pages
    # This prevents showing stale messages on the login page
    list(messages.get_messages(request))
    
    # Process login form
    if request.method == "POST":
        from django.core.cache import cache
        rl_key = _login_rate_limit_key(request)
        ip_attempts = cache.get(rl_key, 0)
        if ip_attempts >= 20:
            messages.error(request, "Too many login attempts from this address. Please try again later.")
            return render(request, "accounts/login.html")
        cache.set(rl_key, ip_attempts + 1, 900)

        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        if not username or not password:
            messages.error(request, "Please enter both username and password.")
            return render(request, "accounts/login.html")

        import time, hashlib
        _generic_fail = "Invalid username or password."

        user_obj = User.objects.filter(username=username).first()

        if user_obj and user_obj.is_locked_out():
            remaining = user_obj.get_lockout_remaining_seconds()
            minutes = remaining // 60
            seconds = remaining % 60
            messages.error(
                request,
                f"Too many failed attempts. Please try again in {minutes}m {seconds}s.",
            )
            return render(request, "accounts/login.html")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            user_school = getattr(user, 'school', None)
            if user_school and not getattr(user, 'is_superuser', False) and getattr(user, 'role', None) != 'super_admin':
                if not user_school.is_active:
                    messages.error(request, _generic_fail)
                    return render(request, "accounts/login.html")

            if hasattr(user, 'reset_failed_logins'):
                user.reset_failed_logins()

            login(request, user)
            role = getattr(user, "role", None)
            if role in ["parent", "student"]:
                return redirect("portal")
            if role == "teacher":
                return redirect("accounts:teacher_dashboard")
            if role in ("school_admin", "deputy_head", "hod", "accountant",
                        "librarian", "admission_officer", "school_nurse", "admin_assistant", "staff"):
                return redirect("accounts:school_dashboard")
            if user.is_superuser or role == "super_admin":
                return redirect("accounts:dashboard")
            return redirect("accounts:dashboard")

        messages.error(request, _generic_fail)

        if user_obj and hasattr(user_obj, 'increment_failed_login'):
            user_obj.increment_failed_login()
        else:
            hashlib.pbkdf2_hmac("sha256", password.encode(), b"timing-pad", 260000)

        if user_obj and getattr(user_obj, "school_id", None):
            try:
                from operations.activity import client_ip_from_request, log_school_activity

                log_school_activity(
                    user=None,
                    school=getattr(user_obj, "school", None),
                    action="login_failed",
                    details="Incorrect password for existing account.",
                    ip=client_ip_from_request(request),
                )
            except Exception:
                pass
    
    return render(request, "accounts/login.html")


@login_required
def profile(request):
    """
    Logged-in user's own profile page.
    """
    student = None
    if getattr(request.user, "role", None) == "student":
        student = Student.objects.filter(user=request.user).select_related("school", "parent").first()
    return render(request, "accounts/profile.html", {"student": student})


@login_required
def force_password_change(request):
    """Force users with must_change_password=True to set a new password."""
    user = request.user
    if not getattr(user, "must_change_password", False):
        return redirect("home")
    if request.method == "POST":
        new_pw = request.POST.get("new_password", "")
        confirm = request.POST.get("confirm_password", "")
        if len(new_pw) < 8:
            messages.error(request, "Password must be at least 8 characters.")
        elif new_pw != confirm:
            messages.error(request, "Passwords do not match.")
        else:
            user.set_password(new_pw)
            user.must_change_password = False
            user.save(update_fields=["password", "must_change_password"])
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)
            try:
                from operations.activity import client_ip_from_request, log_school_activity

                log_school_activity(
                    user=user,
                    action="password_change",
                    details="Password updated (required change after login).",
                    ip=client_ip_from_request(request),
                )
            except Exception:
                pass
            messages.success(request, "Password changed successfully.")
            return redirect("home")
    return render(request, "accounts/force_password_change.html")


@login_required
def edit_profile(request):
    """
    Logged-in user can edit their own basic details.
    """
    user = request.user
    if request.method == "POST":
        first_name = (request.POST.get("first_name") or "").strip()
        last_name = (request.POST.get("last_name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        remove_photo = request.POST.get("remove_profile_photo") == "1"
        
        # Handle profile photo upload
        profile_photo = request.FILES.get("profile_photo")

        if email and User.objects.exclude(pk=user.pk).filter(email=email).exists():
            messages.error(request, "That email is already in use.")
        else:
            # Handle photo removal
            if remove_photo and user.profile_photo:
                old_url = str(user.profile_photo)
                user.profile_photo = None
                # Try to delete from Supabase if it's a Supabase URL
                if SUPABASE_STORAGE_AVAILABLE and old_url.startswith('http'):
                    supabase_storage.delete_file(old_url)
            
            # Handle new photo upload
            if profile_photo:
                # Delete old photo if exists
                if user.profile_photo and str(user.profile_photo).startswith('http'):
                    if SUPABASE_STORAGE_AVAILABLE:
                        supabase_storage.delete_file(str(user.profile_photo))
                
                # Upload to Supabase Storage
                if SUPABASE_STORAGE_AVAILABLE:
                    folder = f"profiles/{user.school_id}" if hasattr(user, 'school_id') and user.school_id else "profiles/default"
                    uploaded_url = supabase_storage.upload_file(profile_photo, folder=folder)
                    if uploaded_url:
                        user.profile_photo = uploaded_url
                        messages.info(request, "Photo uploaded to cloud storage.")
                    else:
                        messages.warning(request, "Cloud upload failed, saving locally.")
                        user.profile_photo = profile_photo
                else:
                    user.profile_photo = profile_photo
            
            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            user.phone = phone or None
            user.save(update_fields=["first_name", "last_name", "email", "phone", "profile_photo"])
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")

    return render(request, "accounts/edit_profile.html")


@login_required
def dashboard(request):
    if getattr(request.user, "role", None) in ["parent", "student"]:
        return redirect("portal")

    if getattr(request.user, "role", None) == "teacher" and getattr(request.user, "school", None):
        return redirect("accounts:teacher_dashboard")

    # Super admins and superusers get the main dashboard
    if (
        getattr(request.user, "is_superuser", False)
        or getattr(request.user, "role", None) == "super_admin"
        or getattr(request.user, "is_staff", False)
    ):
        school = getattr(request.user, "school", None)
        
        # Check if superuser (platform admin)
        is_superuser = request.user.is_superuser
        
        if school:
            total_schools = 1
            total_students = Student.objects.filter(school=school).count()
            total_staff = User.objects.filter(school=school, role__in=("school_admin", "teacher", "staff")).count()
            total_parents = User.objects.filter(school=school, role="parent").count()
            paid_fees = Fee.objects.filter(school=school, paid=True).aggregate(total=Sum("amount"))["total"] or 0
            unpaid_count = Fee.objects.filter(school=school, paid=False).count()
        else:
            total_schools = School.objects.filter(is_active=True).count()
            total_students = Student.objects.count()
            total_staff = User.objects.filter(role__in=("school_admin", "teacher", "staff")).count()
            total_parents = User.objects.filter(role="parent").count()
            paid_fees = Fee.objects.filter(paid=True).aggregate(total=Sum("amount"))["total"] or 0
            unpaid_count = Fee.objects.filter(paid=False).count()

        context = {
            "total_schools": total_schools,
            "total_students": total_students,
            "total_staff": total_staff,
            "total_parents": total_parents,
            "mrr": int(paid_fees),
            "unpaid_fees_count": unpaid_count,
            "school": school,
            "is_superuser": is_superuser,
            "recent_activities": recent_activities_for_dashboard(
                user=request.user, school=school, limit=12
            ),
        }
        return render(request, "dashboard.html", context)
    
    # Fallback: render a minimal dashboard instead of creating redirect loops.
    return render(
        request,
        "dashboard.html",
        {
            "school": None,
            "is_superuser": False,
            "recent_activities": recent_activities_for_dashboard(
                user=request.user, school=None, limit=12
            ),
        },
    )


@login_required
def school_dashboard(request):
    """Custom dashboard for school admins, teachers, and staff."""
    # Only school staff can access. Avoid redirect loops by checking roles first.
    allowed_roles = {
        "school_admin", "deputy_head", "hod", "teacher", "accountant",
        "librarian", "admission_officer", "school_nurse", "admin_assistant", "staff",
    }
    is_allowed_role = getattr(request.user, "role", None) in allowed_roles
    is_staff_flag = getattr(request.user, "is_staff_member", False)
    is_school_admin_flag = getattr(request.user, "is_school_admin", False)

    if not (is_allowed_role or is_staff_flag or is_school_admin_flag):
        # Non-staff users (e.g. parents, students) → main dashboard (one redirect only)
        return redirect("accounts:dashboard")
    
    school = getattr(request.user, "school", None)
    if not school:
        # Platform super admins / Django superusers should always see the super admin dashboard,
        # not a "no school" page.
        if getattr(request.user, "is_superuser", False) or getattr(request.user, "role", None) == "super_admin":
            return redirect("accounts:dashboard")
        # For normal staff without a linked school, show a clear message instead of looping.
        return render(request, "accounts/no_school.html")
    
    # Imports for models that are now at the top of the file
    # from students.models import Student
    # from finance.models import Fee
    # from operations.models import StudentAttendance, TeacherAttendance, AcademicCalendar
    
    from django.db.models import Count, Q

    today = timezone.now().date()

    student_stats = Student.objects.filter(school=school).aggregate(
        total=Count("id"),
        male=Count("id", filter=Q(user__gender="male")),
        female=Count("id", filter=Q(user__gender="female")),
    )
    total_students = student_stats["total"]
    male_students = student_stats["male"]
    female_students = student_stats["female"]

    user_stats = User.objects.filter(school=school).aggregate(
        total_staff=Count("id", filter=Q(role__in=("school_admin", "teacher", "staff"))),
        teachers_count=Count("id", filter=Q(role="teacher")),
    )
    total_staff = user_stats["total_staff"]
    teachers_count = user_stats["teachers_count"]
    inactive_staff_count = User.objects.filter(school=school, role__in=STAFF_ROLES, is_active=False).count()

    attendance_stats = StudentAttendance.objects.filter(school=school, date=today).aggregate(
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        late=Count("id", filter=Q(status="late")),
        excused=Count("id", filter=Q(status="excused")),
    )
    present_today = attendance_stats["present"]
    late_today = attendance_stats["late"]
    excused_today = attendance_stats["excused"]

    upcoming_events = AcademicCalendar.objects.filter(school=school, start_date__gte=today)[:5]

    fee_stats = Fee.objects.filter(school=school).aggregate(
        total=Sum("amount"),
        total_paid=Sum("amount_paid"),
    )
    total_fees = fee_stats["total"] or 0
    paid_fees = fee_stats["total_paid"] or 0
    unpaid_fees = max(0, float(total_fees) - float(paid_fees))
    
    # Get recent payments for the school (last 5 payments)
    recent_payments = (
        FeePayment.objects.filter(fee__school=school)
        .select_related("fee", "fee__student", "fee__student__user")
        .order_by("-created_at")[:5]
    )
    
    # Subscription expiry warning
    show_expiry_warning = False
    expiry_severity = "info"
    expiry_icon = "ℹ️"
    expiry_title = ""
    expiry_message = ""
    expiry_button_text = "Renew Now"
    
    if school.subscription_status == 'trial':
        show_expiry_warning = True
        expiry_severity = "warning"
        expiry_icon = "⚠️"
        expiry_title = "Trial Period Active"
        expiry_message = "Your trial period is active. Subscribe now to continue using the platform after the trial ends."
        expiry_button_text = "Subscribe Now"
    elif school.subscription_status == 'expired':
        show_expiry_warning = True
        expiry_severity = "critical"
        expiry_icon = "🚫"
        expiry_title = "Subscription Expired"
        expiry_message = "Your subscription has expired. Renew now to regain access to all features."
        expiry_button_text = "Renew Now"
    elif school.subscription_status == 'active' and school.days_until_expiry is not None:
        days_left = school.days_until_expiry
        if days_left <= 7:
            show_expiry_warning = True
            expiry_severity = "critical"
            expiry_icon = "⚠️"
            expiry_title = f"Subscription Expiring in {days_left} Day{'s' if days_left != 1 else ''}!"
            expiry_message = "Your subscription will expire soon. Renew now to avoid interruption."
            expiry_button_text = "Renew Now"
        elif days_left <= 14:
            show_expiry_warning = True
            expiry_severity = "warning"
            expiry_icon = "⏰"
            expiry_title = f"Subscription Expiring in {days_left} Days"
            expiry_message = "Your subscription is coming up for renewal. Consider renewing soon."
            expiry_button_text = "Renew Now"
    
    from operations.models import AdmissionApplication, LibraryIssue

    _open_admission_statuses = (
        "pending",
        "under_review",
        "interview",
        "documents_pending",
        "offered",
        "waitlisted",
    )
    pending_admissions = AdmissionApplication.objects.filter(
        school=school, status__in=_open_admission_statuses
    ).count()
    overdue_books = LibraryIssue.objects.filter(school=school, return_date__isnull=True, due_date__lt=today).count()
    absent_today = attendance_stats["absent"]

    from datetime import date, timedelta

    from operations.models import StaffLeave

    pending_staff_leave = 0
    if can_review_staff_leave(request.user):
        pending_staff_leave = StaffLeave.objects.filter(school=school, status="pending").count()

    hr_expiring_contracts = 0
    payroll_mtd_by_currency = []
    if can_manage_finance(request.user):
        horizon = today + timedelta(days=60)
        hr_expiring_contracts = StaffContract.objects.filter(
            school=school,
            status="active",
            end_date__isnull=False,
            end_date__lte=horizon,
            end_date__gte=today,
        ).count()
        month_start = date(today.year, today.month, 1)
        payroll_mtd_by_currency = list(
            StaffPayrollPayment.objects.filter(school=school, paid_on__gte=month_start, paid_on__lte=today)
            .values("currency")
            .annotate(total=Sum("amount"))
        )

    attendance_trend_chart = build_attendance_trend(school, days=14)
    academic_insights = build_academic_insights(school)
    finance_insights = build_finance_insights(school, float(total_fees), float(paid_fees))

    onboarding_checklist = []
    show_onboarding_card = False
    if user_can_manage_school(request.user) and school:
        onboarding_checklist = [
            {
                "label": "Active fee structures",
                "done": FeeStructure.objects.filter(school=school, is_active=True).exists(),
                "url": reverse("finance:fee_structure_list"),
            },
            {
                "label": "Enrolled students",
                "done": total_students > 0,
                "url": reverse("students:student_list"),
            },
            {
                "label": "Teaching staff accounts",
                "done": teachers_count > 0,
                "url": reverse("accounts:staff_list"),
            },
            {
                "label": "Current academic term",
                "done": Term.objects.filter(school=school, is_current=True).exists(),
                "url": None,
            },
            {
                "label": "Class timetable entries",
                "done": Timetable.objects.filter(school=school).exists(),
                "url": reverse("academics:timetable_list"),
            },
        ]
        done_n = sum(1 for x in onboarding_checklist if x["done"])
        show_onboarding_card = bool(onboarding_checklist) and done_n < len(onboarding_checklist)

    subject_perf_chart = {
        "labels": [r["name"] for r in academic_insights.get("subject_avgs", [])],
        "values": [r["avg_pct"] for r in academic_insights.get("subject_avgs", [])],
    }

    from notifications.models import Notification

    recent_notifications = list(
        Notification.objects.filter(user=request.user).order_by("-created_at")[:8]
    )
    unread_notification_count = Notification.get_unread_count(request.user)

    role = getattr(request.user, "role", None)
    if role == "teacher":
        quick_actions = [
            {"label": "Teacher home", "url": reverse("accounts:teacher_dashboard"), "icon": "🏠"},
            {"label": "Mark Attendance", "url": reverse("operations:attendance_mark"), "icon": "📋"},
            {"label": "Upload Results", "url": reverse("academics:result_upload"), "icon": "📊"},
            {"label": "Send Announcement", "url": reverse("messaging:send_message"), "icon": "📢"},
        ]
    else:
        quick_actions = [
            {"label": "Services hub", "url": reverse("operations:services_hub"), "icon": "🏫"},
            {"label": "Add Student", "url": reverse("students:student_register"), "icon": "👤"},
            {"label": "School fees", "url": reverse("finance:fee_list"), "icon": "📋"},
            {"label": "Record payment", "url": reverse("operations:record_payment"), "icon": "💳"},
            {"label": "Mark attendance", "url": reverse("operations:attendance_mark"), "icon": "✅"},
            {"label": "Send announcement", "url": reverse("messaging:send_message"), "icon": "📢"},
            {"label": "Public apply link", "url": reverse("operations:admission_apply"), "icon": "🌐"},
            {"label": "Track application", "url": reverse("operations:admission_track"), "icon": "🔎"},
        ]

    context = {
        "school": school,
        "total_students": total_students,
        "male_students": male_students,
        "female_students": female_students,
        "total_staff": total_staff,
        "teachers_count": teachers_count,
        "inactive_staff_count": inactive_staff_count,
        "present_today": present_today,
        "upcoming_events": upcoming_events,
        "total_fees": int(total_fees),
        "paid_fees": int(paid_fees),
        "unpaid_fees": unpaid_fees,
        "recent_payments": recent_payments,
        "show_expiry_warning": show_expiry_warning,
        "expiry_severity": expiry_severity,
        "expiry_icon": expiry_icon,
        "expiry_title": expiry_title,
        "expiry_message": expiry_message,
        "expiry_button_text": expiry_button_text,
        "pending_admissions": pending_admissions,
        "overdue_books": overdue_books,
        "absent_today": absent_today,
        "late_today": late_today,
        "excused_today": excused_today,
        "pending_staff_leave": pending_staff_leave,
        "hr_expiring_contracts": hr_expiring_contracts,
        "payroll_mtd_by_currency": payroll_mtd_by_currency,
        "attendance_trend_chart": attendance_trend_chart,
        "academic_insights": academic_insights,
        "finance_insights": finance_insights,
        "subject_perf_chart": subject_perf_chart,
        "recent_notifications": recent_notifications,
        "unread_notification_count": unread_notification_count,
        "quick_actions": quick_actions,
        "onboarding_checklist": onboarding_checklist,
        "show_onboarding_card": show_onboarding_card,
    }
    return render(request, "accounts/school_dashboard.html", context)


@login_required
def teacher_dashboard(request):
    """Dedicated dashboard for teachers showing their classes, attendance, and results."""
    from students.models import SchoolClass
    from academics.models import Subject, Term, Result, Homework
    from accounts.teaching_scope import teacher_attendance_classes_qs, teacher_result_subject_ids

    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")

    today = timezone.now().date()
    my_classes = SchoolClass.objects.filter(school=school, class_teacher=request.user).order_by("name")
    markable_classes = teacher_attendance_classes_qs(school, request.user)
    subject_id_set = teacher_result_subject_ids(school, request.user)
    my_subjects = Subject.objects.filter(school=school, id__in=subject_id_set).order_by("name")
    current_term = Term.objects.filter(school=school, is_current=True).first()

    from django.db.models import Count, Q, Subquery, OuterRef, IntegerField
    from django.db.models.functions import Coalesce

    class_names = list(markable_classes.values_list("name", flat=True))
    student_counts = dict(
        Student.objects.filter(school=school, class_name__in=class_names)
        .values("class_name")
        .annotate(cnt=Count("id"))
        .values_list("class_name", "cnt")
    )
    marked_counts = dict(
        StudentAttendance.objects.filter(
            school=school, date=today, student__class_name__in=class_names
        )
        .values("student__class_name")
        .annotate(cnt=Count("id"))
        .values_list("student__class_name", "cnt")
    )
    classes_attendance = []
    for cls in markable_classes:
        sc = student_counts.get(cls.name, 0)
        mc = marked_counts.get(cls.name, 0)
        classes_attendance.append({
            "class": cls,
            "student_count": sc,
            "marked": mc >= sc and sc > 0,
            "marked_count": mc,
        })

    pending_homework = Homework.objects.filter(
        school=school, created_by=request.user, due_date__gte=today
    ).order_by("due_date")[:5]

    recent_results_count = 0
    if current_term:
        recent_results_count = Result.objects.filter(
            student__school=school, term=current_term,
            subject__in=my_subjects,
        ).count()

    subject_ids = list(my_subjects.values_list("id", flat=True))
    teacher_academic = build_teacher_academic_insights(school, subject_ids, current_term)
    teacher_subject_chart = {
        "labels": [r["name"] for r in teacher_academic.get("subject_avgs", [])],
        "values": [r["avg_pct"] for r in teacher_academic.get("subject_avgs", [])],
    }
    teacher_attendance_trend = build_teacher_attendance_trend(school, request.user, days=14)
    teacher_class_strength = build_teacher_students_by_class_chart(school, request.user)
    teacher_class_chart = {
        "labels": teacher_class_strength["labels"],
        "values": teacher_class_strength["values"],
        "has_data": teacher_class_strength["has_data"],
    }

    from notifications.models import Notification

    teacher_notifications = list(
        Notification.objects.filter(user=request.user).order_by("-created_at")[:6]
    )
    teacher_unread_notifications = Notification.get_unread_count(request.user)

    context = {
        "school": school,
        "my_classes": my_classes,
        "my_subjects": my_subjects,
        "current_term": current_term,
        "classes_attendance": classes_attendance,
        "pending_homework": pending_homework,
        "recent_results_count": recent_results_count,
        "today": today,
        "teacher_academic": teacher_academic,
        "teacher_subject_chart": teacher_subject_chart,
        "teacher_attendance_trend": teacher_attendance_trend,
        "teacher_class_strength": teacher_class_strength,
        "teacher_class_chart": teacher_class_chart,
        "teacher_notifications": teacher_notifications,
        "teacher_unread_notifications": teacher_unread_notifications,
    }
    return render(request, "accounts/teacher_dashboard.html", context)


def _user_can_manage_school(request):
    """Backward-compatible wrapper around central permission helper."""
    return user_can_manage_school(request.user)


def _user_is_school_admin(request):
    """School leadership (head, deputy, HOD) or platform super-admins."""
    from accounts.permissions import is_school_leadership

    user = request.user
    if not user.is_authenticated:
        return False
    if user.is_superuser or getattr(user, "is_super_admin", False):
        return True
    return is_school_leadership(user)


@login_required
def staff_list(request):
    """
    Robust staff list:
    - School admins see staff for their school.
    - Super admins / superusers can see staff across all schools.
    - Users without permission get a friendly empty page (no 500 errors).
    """
    user = request.user
    has_manage_permission = _user_can_manage_school(request) or getattr(user, "is_super_admin", False)
    if not has_manage_permission:
        return render(
            request,
            "accounts/staff_list.html",
            {"staff_list": [], "staff_by_role": {}, "school": getattr(user, "school", None)},
        )

    school = getattr(user, "school", None)
    try:
        # Include all staff roles
        all_staff_roles = ("school_admin", "deputy_head", "hod", "teacher", 
                          "accountant", "librarian", "admission_officer", "school_nurse", 
                          "admin_assistant", "staff")
        if school and not getattr(user, "is_super_admin", False):
            staff = User.objects.filter(school=school, role__in=all_staff_roles).order_by("role", "username")
        else:
            # Platform view: list staff across all schools.
            staff = (
                User.objects.filter(role__in=all_staff_roles)
                .select_related("school")
                .order_by("school__name", "role", "username")
            )

        staff_by_role = {}
        for s in staff:
            role_label = s.get_role_display()
            staff_by_role.setdefault(role_label, []).append(s)
    except Exception:
        staff = []
        staff_by_role = {}

    page_obj = paginate(request, staff, per_page=30)

    return render(
        request,
        "accounts/staff_list.html",
        {"staff_list": page_obj, "staff_by_role": staff_by_role, "school": school, "page_obj": page_obj},
    )


@login_required
def staff_detail(request, pk):
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    # Include all staff roles
    all_staff_roles = (
        "school_admin", "deputy_head", "hod", "teacher",
        "accountant", "librarian", "admission_officer", "school_nurse",
        "admin_assistant", "staff",
    )
    qs = User.objects.filter(role__in=all_staff_roles)
    if school:
        qs = qs.filter(school=school)
    staff = get_object_or_404(
        qs.select_related("school").prefetch_related("assigned_subjects"),
        pk=pk,
    )
    if staff.school_id:
        sync_expired_staff_contracts(school=staff.school)
    assigned_subject_ids = set(staff.assigned_subjects.values_list("id", flat=True))
    ctx = {
        "staff": staff,
        "assigned_subject_ids": assigned_subject_ids,
        "contract_type_choices": StaffContract.CONTRACT_TYPES,
        "contract_status_choices": StaffContract.STATUS_CHOICES,
        "paystack_staff_enabled": school_staff_paystack_allowed(request),
    }
    school_obj = staff.school
    if school_obj:
        ctx["staff_contracts"] = list(
            StaffContract.objects.filter(user=staff, school=school_obj).order_by("-start_date", "-id")[:40]
        )
        ctx["staff_teaching"] = list(
            StaffTeachingAssignment.objects.filter(user=staff, school=school_obj)
            .select_related("subject")
            .order_by("-is_active", "class_name", "subject__name")[:60]
        )
        ctx["staff_role_logs"] = list(
            StaffRoleChangeLog.objects.filter(user=staff, school=school_obj).select_related("changed_by")[:40]
        )
        ctx["school_subjects"] = list(Subject.objects.filter(school=school_obj).order_by("name"))
        ctx["school_classes"] = list(SchoolClass.objects.filter(school=school_obj).order_by("name"))
        homeroom = SchoolClass.objects.filter(school=school_obj, class_teacher=staff).first()
        ctx["staff_homeroom_class"] = homeroom
        if can_manage_finance(request.user):
            ctx["staff_payroll"] = list(
                StaffPayrollPayment.objects.filter(user=staff, school=school_obj).order_by("-paid_on", "-id")[:60]
            )
        else:
            ctx["staff_payroll"] = []
    else:
        ctx["staff_contracts"] = []
        ctx["staff_teaching"] = []
        ctx["staff_role_logs"] = []
        ctx["school_subjects"] = []
        ctx["school_classes"] = []
        ctx["staff_homeroom_class"] = None
        ctx["staff_payroll"] = []
    return render(request, "accounts/staff_detail.html", ctx)


@login_required
def staff_register(request):
    # Only school admins (or platform admins) can create staff accounts
    if not _user_is_school_admin(request):
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        password = request.POST.get("password", "")
        role = request.POST.get("role", "teacher")
        phone = request.POST.get("phone", "").strip() or None
        valid_staff_roles = (
            "school_admin", "deputy_head", "hod", "teacher",
            "accountant", "librarian", "admission_officer",
            "school_nurse", "admin_assistant", "staff",
        )
        if username and email and password and role in valid_staff_roles:
            if User.objects.filter(username=username).exists():
                messages.error(request, "That username is already taken.")
            elif User.objects.filter(email=email).exists():
                messages.error(request, "That email is already in use.")
            else:
                User.objects.create(
                    username=username,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    password=make_password(password),
                    role=role,
                    school=school,
                    phone=phone,
                )
                messages.success(request, "Staff account created.")
                return redirect("accounts:staff_list")
        elif request.method == "POST":
            messages.error(request, "Please fill all required fields or select a valid role.")
    return render(request, "accounts/staff_register.html", {"school": school})


@login_required
def parent_list(request):
    """List all parents for the school."""
    # Only school admins (or platform admins) can manage parents
    if not _user_is_school_admin(request):
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    parents = User.objects.filter(school=school, role="parent").order_by("username")
    page_obj = paginate(request, parents, per_page=30)
    return render(request, "accounts/parent_list.html", {"parents": page_obj, "school": school, "page_obj": page_obj})


@login_required
def parent_register(request):
    """Register a new parent for the school."""
    if not _user_is_school_admin(request):
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        password = request.POST.get("password", "")
        phone = request.POST.get("phone", "").strip() or None
        parent_type = request.POST.get("parent_type", "").strip() or None
        
        if username and password:
            if User.objects.filter(username=username).exists():
                messages.error(request, "That username is already taken.")
            elif email and User.objects.filter(email=email).exists():
                messages.error(request, "That email is already in use.")
            else:
                User.objects.create(
                    username=username,
                    email=email or f"{username}@school.local",
                    first_name=first_name,
                    last_name=last_name,
                    password=make_password(password),
                    role="parent",
                    school=school,
                    phone=phone,
                    parent_type=parent_type,
                )
                messages.success(request, "Parent account created.")
                return redirect("accounts:parent_list")
        elif request.method == "POST":
            messages.error(request, "Please fill all required fields.")
    return render(request, "accounts/parent_register.html", {"school": school})


@login_required
def parent_detail(request, pk):
    """View parent details and their linked children."""
    if not _user_is_school_admin(request):
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    # from students.models import Student # Moved to top
    parent = get_object_or_404(User, pk=pk, school=school, role="parent")
    children = Student.objects.filter(parent=parent).select_related("user", "school")
    return render(request, "accounts/parent_detail.html", {"parent": parent, "children": children})


@login_required
def parent_edit(request, pk):
    """Edit an existing parent."""
    if not _user_is_school_admin(request):
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    parent = get_object_or_404(User, pk=pk, school=school, role="parent")
    
    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip() or None
        parent_type = request.POST.get("parent_type", "").strip() or None
        
        # Check for email conflicts (excluding self)
        if email and User.objects.exclude(pk=parent.pk).filter(email=email).exists():
            messages.error(request, "That email is already in use.")
        else:
            parent.first_name = first_name
            parent.last_name = last_name
            parent.email = email
            parent.phone = phone
            parent.parent_type = parent_type
            parent.save()
            messages.success(request, "Parent updated successfully.")
            return redirect("accounts:parent_detail", pk=parent.pk)
    
    return render(request, "accounts/parent_edit.html", {"parent": parent})


@login_required
def user_management(request):
    """User management dashboard for school admins."""
    if not _user_is_school_admin(request):
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    from django.db.models import Count, Q
    counts = User.objects.filter(school=school).aggregate(
        staff_count=Count("id", filter=Q(role__in=(
            "school_admin", "deputy_head", "hod", "teacher",
            "accountant", "librarian", "admission_officer", "school_nurse",
            "admin_assistant", "staff",
        ))),
        parent_count=Count("id", filter=Q(role="parent")),
    )
    student_count = Student.objects.filter(school=school).count()

    context = {
        "school": school,
        "staff_count": counts["staff_count"],
        "parent_count": counts["parent_count"],
        "student_count": student_count,
        "can_manage_finance": can_manage_finance(request.user),
    }
    return render(request, "accounts/user_management.html", context)


@login_required
def staff_delete(request, pk):
    """
    Deactivate a staff member instead of deleting them.

    This keeps their historical data (attendance, results, etc.) while blocking login.
    """
    if not _user_is_school_admin(request):
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    staff = get_object_or_404(User, pk=pk, school=school, role__in=STAFF_ROLES)

    if staff.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("accounts:staff_detail", pk=pk)

    if staff.role == "school_admin":
        other_active_admins = (
            User.objects.filter(school=school, role="school_admin", is_active=True).exclude(pk=staff.pk).count()
        )
        if other_active_admins == 0:
            messages.error(
                request,
                "Cannot deactivate the only active school administrator for this school.",
            )
            return redirect("accounts:staff_detail", pk=pk)

    if request.method == "POST":
        staff.is_active = False
        staff.save(update_fields=["is_active"])
        messages.success(
            request,
            f"Staff member '{staff.username}' has been deactivated and can no longer log into the system.",
        )
        return redirect("accounts:staff_list")
    
    return render(request, "accounts/confirm_delete.html", {
        "object": staff,
        "type": "staff member (deactivation)",
        "cancel_url": "accounts:staff_list"
    })


@login_required
def staff_reactivate(request, pk):
    """
    Reactivate a previously deactivated staff member.
    """
    if not _user_is_school_admin(request):
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")

    staff = get_object_or_404(User, pk=pk, school=school, role__in=STAFF_ROLES)

    if request.method == "POST":
        staff.is_active = True
        staff.save(update_fields=["is_active"])
        messages.success(
            request,
            f"Staff member '{staff.username}' has been reactivated and can log into the system again.",
        )
        return redirect("accounts:staff_detail", pk=staff.pk)

    return render(
        request,
        "accounts/confirm_delete.html",
        {
            "object": staff,
            "type": "staff reactivation",
            "cancel_url": "accounts:staff_detail",
        },
    )


@login_required
def staff_change_role(request, pk):
    """
    Allow school admins to change the role of any staff member.
    Supports all new roles: deputy_head, hod, teacher, accountant, librarian,
    admission_officer, school_nurse, admin_assistant, staff
    """
    if not _user_is_school_admin(request):
        messages.error(request, "Only school administrators can change user roles.")
        return redirect("accounts:school_dashboard")
    
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")

    # Get the staff member (include all non-parent/student roles)
    staff = get_object_or_404(
        User, 
        pk=pk, 
        school=school, 
        role__in=(
            "school_admin", "deputy_head", "hod", "teacher",
            "accountant", "librarian", "admission_officer", "school_nurse",
            "admin_assistant", "staff",
        )
    )

    # Prevent self-demotion
    if staff.pk == request.user.pk:
        messages.error(request, "You cannot change your own role.")
        return redirect("accounts:staff_detail", pk=pk)

    if request.method == "POST":
        new_role = request.POST.get("new_role", "")
        valid_roles = (
            "teacher",
            "deputy_head",
            "hod",
            "accountant",
            "librarian",
            "admission_officer",
            "school_nurse",
            "admin_assistant",
            "staff",
        )
        platform_assign_admin = request.user.is_superuser or is_super_admin(request.user)
        if new_role == "school_admin" and not platform_assign_admin:
            messages.error(request, "Only a platform administrator may assign the School Admin role.")
        elif new_role == "school_admin" and platform_assign_admin:
            old_key = staff.role
            old_label = staff.get_role_display()
            if old_key == new_role:
                messages.info(request, "Role is unchanged.")
            else:
                staff.role = new_role
                staff.save(update_fields=["role"])
                StaffRoleChangeLog.objects.create(
                    school=school,
                    user=staff,
                    change_kind=StaffRoleChangeLog.KIND_PRIMARY,
                    from_value=old_key,
                    to_value=new_role,
                    changed_by=request.user,
                )
                messages.success(
                    request,
                    f"Role changed from '{old_label}' to '{staff.get_role_display()}' for '{staff.username}'.",
                )
        elif new_role in valid_roles:
            old_key = staff.role
            old_label = staff.get_role_display()
            if old_key == new_role:
                messages.info(request, "Role is unchanged.")
            else:
                staff.role = new_role
                staff.save(update_fields=["role"])
                StaffRoleChangeLog.objects.create(
                    school=school,
                    user=staff,
                    change_kind=StaffRoleChangeLog.KIND_PRIMARY,
                    from_value=old_key,
                    to_value=new_role,
                    changed_by=request.user,
                )
                messages.success(
                    request,
                    f"Role changed from '{old_label}' to '{staff.get_role_display()}' for '{staff.username}'.",
                )
        else:
            messages.error(request, "Invalid role selected.")

    return redirect("accounts:staff_detail", pk=pk)


@login_required
def staff_manage_secondary_roles(request, pk):
    """
    Allow school admins to manage secondary roles for staff members.
    Users can have multiple secondary roles in addition to their primary role.
    """
    if not _user_is_school_admin(request):
        messages.error(request, "Only school administrators can manage secondary roles.")
        return redirect("accounts:school_dashboard")
    
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")

    # Get the staff member (include all non-parent/student roles)
    staff = get_object_or_404(
        User, 
        pk=pk, 
        school=school, 
        role__in=(
            "school_admin", "deputy_head", "hod", "teacher",
            "accountant", "librarian", "admission_officer", "school_nurse",
            "admin_assistant", "staff",
        )
    )

    if request.method == "POST":
        # Get selected secondary roles from form
        selected_roles = request.POST.getlist("secondary_roles")
        
        # Validate and store roles as comma-separated string
        valid_roles = (
            "teacher", "deputy_head", "hod", "accountant", "librarian",
            "admission_officer", "school_nurse", "admin_assistant", "staff"
        )
        
        # Filter to only valid roles and exclude primary role
        filtered_roles = [r for r in selected_roles if r in valid_roles and r != staff.role]
        
        from_secondary = staff.secondary_roles or ""
        # Store as comma-separated string
        staff.secondary_roles = ','.join(filtered_roles)
        staff.save(update_fields=['secondary_roles'])
        to_secondary = staff.secondary_roles or ""
        if from_secondary != to_secondary:
            StaffRoleChangeLog.objects.create(
                school=school,
                user=staff,
                change_kind=StaffRoleChangeLog.KIND_SECONDARY,
                from_value=from_secondary,
                to_value=to_secondary,
                changed_by=request.user,
            )
        
        count = len(filtered_roles)
        messages.success(
            request,
            f"Secondary roles updated for '{staff.username}'. "
            f"They now have access to features of: {staff.get_role_display()}" +
            (f" + {count} additional role(s)" if count > 0 else " (no additional roles)"),
        )

    return redirect("accounts:staff_detail", pk=pk)


@login_required
def parent_delete(request, pk):
    """
    Deactivate a parent instead of deleting them.

    This keeps their links to students and payments while blocking login.
    """
    if not _user_is_school_admin(request):
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    parent = get_object_or_404(User, pk=pk, school=school, role="parent")
    
    if request.method == "POST":
        parent.is_active = False
        parent.save(update_fields=["is_active"])
        messages.success(
            request,
            f"Parent '{parent.username}' has been deactivated and can no longer log into the system.",
        )
        return redirect("accounts:parent_list")
    
    return render(request, "accounts/confirm_delete.html", {
        "object": parent,
        "type": "parent (deactivation)",
        "cancel_url": "accounts:parent_list"
    })


@login_required
def parent_reactivate(request, pk):
    """
    Reactivate a previously deactivated parent account.
    """
    if not _user_is_school_admin(request):
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")

    parent = get_object_or_404(User, pk=pk, school=school, role="parent")

    if request.method == "POST":
        parent.is_active = True
        parent.save(update_fields=["is_active"])
        messages.success(
            request,
            f"Parent '{parent.username}' has been reactivated and can log into the system again.",
        )
        return redirect("accounts:parent_detail", pk=parent.pk)

    return render(
        request,
        "accounts/confirm_delete.html",
        {
            "object": parent,
            "type": "parent reactivation",
            "cancel_url": "accounts:parent_detail",
        },
    )


@login_required
def reset_user_password(request, pk):
    """
    Allow school leadership and platform admins to reset a user's password.

    This is the main way to help parents, students, staff, and administrators
    who have forgotten their login details.
    """
    user = request.user
    target_user = get_object_or_404(User, pk=pk)

    # Permission check:
    # - Platform superuser or super_admin can reset anyone.
    # - School leadership can only reset users in their own school.
    is_platform_admin = user.is_superuser or getattr(user, "is_super_admin", False)
    same_school = getattr(user, "school_id", None) and user.school_id == getattr(target_user, "school_id", None)
    from accounts.permissions import is_school_leadership

    is_school_level_admin = is_school_leadership(user) and same_school

    if not (is_platform_admin or is_school_level_admin):
        messages.error(request, "You do not have permission to reset this user's password.")
        return redirect("accounts:school_dashboard")

    if request.method == "POST":
        new_password = get_random_string(10)
        target_user.set_password(new_password)
        target_user.save()

        # Show the password once on the next page via a dedicated context variable
        # instead of Django messages (which may be logged or cached).
        request.session['_temp_reset_password'] = new_password
        request.session['_temp_reset_username'] = target_user.username

        messages.success(
            request,
            f"Password for user '{target_user.username}' has been reset. "
            "The new password is shown below. Please share it securely with the user.",
        )

        # Only allow internal redirects to prevent open redirect attacks
        next_url = request.GET.get("next", "")
        if next_url and next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)

        if target_user.role in ("school_admin", "teacher", "staff"):
            return redirect("accounts:staff_detail", pk=target_user.pk)
        if target_user.role == "parent":
            return redirect("accounts:parent_detail", pk=target_user.pk)

        return redirect("accounts:dashboard")

    return render(
        request,
        "accounts/confirm_delete.html",
        {
            "object": target_user,
            "type": "password reset",
            "cancel_url": "accounts:dashboard",
        },
    )


@login_required
def superuser_edit_credentials(request, pk):
    """
    Allow platform superusers / super_admins to change usernames, emails,
    and passwords for any user, including school admins.
    """
    if not (request.user.is_superuser or getattr(request.user, "is_super_admin", False)):
        messages.error(request, "Only platform administrators can edit login credentials at this level.")
        return redirect("accounts:dashboard")

    target_user = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")

        if username and username != target_user.username:
            # Avoid collisions
            if User.objects.exclude(pk=target_user.pk).filter(username=username).exists():
                messages.error(request, "Another user already has that username.")
                return redirect("accounts:superuser_edit_credentials", pk=target_user.pk)
            target_user.username = username

        if email:
            target_user.email = email
        if phone:
            target_user.phone = phone

        if password:
            target_user.set_password(password)

        target_user.save()
        messages.success(request, f"Login credentials for '{target_user.username}' have been updated.")

        next_url = request.GET.get("next", "")
        if next_url and next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)

        if target_user.role in ("school_admin", "teacher", "staff"):
            return redirect("accounts:staff_detail", pk=target_user.pk)
        if target_user.role == "parent":
            return redirect("accounts:parent_detail", pk=target_user.pk)

        return redirect("accounts:dashboard")

    return render(
        request,
        "accounts/staff_login_edit.html",
        {"target_user": target_user},
    )


@login_required
def global_search(request):
    """Search across students, staff, parents, and fees in one place."""
    q = request.GET.get("q", "").strip()
    school = getattr(request.user, "school", None)
    results = {
        "students": [],
        "staff": [],
        "parents": [],
        "fees": [],
    }
    total = 0

    if q and len(q) >= 2:
        if school:
            results["students"] = list(
                Student.objects.filter(school=school)
                .filter(
                    Q(user__first_name__icontains=q)
                    | Q(user__last_name__icontains=q)
                    | Q(admission_number__icontains=q)
                )
                .select_related("user")[:10]
            )
            staff_roles = (
                "school_admin", "deputy_head", "hod", "teacher",
                "accountant", "librarian", "admission_officer",
                "school_nurse", "admin_assistant", "staff",
            )
            results["staff"] = list(
                User.objects.filter(school=school, role__in=staff_roles)
                .filter(
                    Q(first_name__icontains=q)
                    | Q(last_name__icontains=q)
                    | Q(username__icontains=q)
                )[:10]
            )
            results["parents"] = list(
                User.objects.filter(school=school, role="parent")
                .filter(
                    Q(first_name__icontains=q)
                    | Q(last_name__icontains=q)
                    | Q(phone__icontains=q)
                )[:10]
            )
            results["fees"] = list(
                Fee.objects.filter(school=school)
                .filter(
                    Q(student__user__first_name__icontains=q)
                    | Q(student__user__last_name__icontains=q)
                    | Q(student__admission_number__icontains=q)
                )
                .select_related("student", "student__user")[:10]
            )
        elif request.user.is_superuser:
            results["students"] = list(
                Student.objects.filter(
                    Q(user__first_name__icontains=q)
                    | Q(user__last_name__icontains=q)
                    | Q(admission_number__icontains=q)
                )
                .select_related("user", "school")[:10]
            )
            results["staff"] = list(
                User.objects.filter(role__in=("school_admin", "teacher", "staff"))
                .filter(
                    Q(first_name__icontains=q)
                    | Q(last_name__icontains=q)
                    | Q(username__icontains=q)
                )
                .select_related("school")[:10]
            )

        total = sum(len(v) for v in results.values())

    return render(request, "accounts/global_search.html", {
        "q": q,
        "results": results,
        "total": total,
        "school": school,
    })
