from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.messages.storage import default_storage
from django.db.models import Sum
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.urls import reverse

from accounts.models import User
from accounts.permissions import user_can_manage_school, is_school_admin
from schools.models import School
from students.models import Student
from finance.models import Fee
from operations.models import StudentAttendance, TeacherAttendance, AcademicCalendar


def logout_view(request):
    """Log out and redirect to login page."""
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
        if role in ["admin", "school_admin", "teacher", "staff"]:
            return redirect("accounts:school_dashboard")
        if getattr(request.user, "is_superuser", False) or role == "super_admin":
            return redirect("accounts:dashboard")
    return login_view(request)

def login_view(request):
    # If already logged in, send to the right place once (no loop)
    if request.user.is_authenticated:
        role = getattr(request.user, "role", None)
        if role in ["parent", "student"]:
            return redirect("portal")
        if role in ["admin", "school_admin", "teacher", "staff"]:
            return redirect("accounts:school_dashboard")
        if getattr(request.user, "is_superuser", False) or role == "super_admin":
            return redirect("accounts:dashboard")
        return redirect("accounts:dashboard")
    
    # Clear any old messages that might have been set from previous pages
    # This prevents showing stale messages on the login page
    list(messages.get_messages(request))
    
    # Process login form
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        
        if not username or not password:
            messages.error(request, "Please enter both username and password.")
            return render(request, "accounts/login.html")
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            role = getattr(user, "role", None)
            if role in ["parent", "student"]:
                return redirect("portal")
            if role in ["admin", "school_admin", "teacher", "staff"]:
                return redirect("accounts:school_dashboard")
            if user.is_superuser or role == "super_admin":
                return redirect("accounts:dashboard")
            return redirect("accounts:dashboard")
        messages.error(request, "Invalid username or password.")
    
    return render(request, "accounts/login.html")


@login_required
def dashboard(request):
    # Redirect parents and students to their unified portal
    if getattr(request.user, "role", None) in ["parent", "student"]:
        return redirect("portal")

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
        }
        return render(request, "dashboard.html", context)
    
    # Fallback: render a minimal dashboard instead of creating redirect loops.
    return render(request, "dashboard.html", {"school": None, "is_superuser": False})


@login_required
def school_dashboard(request):
    """Custom dashboard for school admins, teachers, and staff."""
    # Only school staff can access. Avoid redirect loops by checking roles first.
    allowed_roles = {"admin", "school_admin", "teacher", "staff"}
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
    
    # Get school statistics
    total_students = Student.objects.filter(school=school).count()

    # Get gender distribution defensively; fall back to zeros if the field does not exist.
    try:
        field_names = [f.name for f in Student._meta.get_fields()]
        if "user" in field_names:
            male_students = Student.objects.filter(
                school=school, user__gender="male"
            ).count()
            female_students = Student.objects.filter(
                school=school, user__gender="female"
            ).count()
        else:
            male_students = 0
            female_students = 0
    except Exception:
        male_students = 0
        female_students = 0
    
    total_staff = User.objects.filter(school=school, role__in=("school_admin", "teacher", "staff")).count()
    teachers_count = User.objects.filter(school=school, role="teacher").count()
    
    # Get recent attendance
    today = timezone.now().date()
    present_today = StudentAttendance.objects.filter(school=school, date=today, status="present").count()
    
    # Get upcoming calendar events
    upcoming_events = AcademicCalendar.objects.filter(school=school, start_date__gte=today)[:5]
    
    # Fee statistics
    total_fees = Fee.objects.filter(school=school).aggregate(total=Sum("amount"))["total"] or 0
    paid_fees = Fee.objects.filter(school=school, paid=True).aggregate(total=Sum("amount"))["total"] or 0
    unpaid_fees = Fee.objects.filter(school=school, paid=False).count()
    
    context = {
        "school": school,
        "total_students": total_students,
        "male_students": male_students,
        "female_students": female_students,
        "total_staff": total_staff,
        "teachers_count": teachers_count,
        "present_today": present_today,
        "upcoming_events": upcoming_events,
        "total_fees": int(total_fees),
        "paid_fees": int(paid_fees),
        "unpaid_fees": unpaid_fees,
    }
    return render(request, "accounts/school_dashboard.html", context)


def _user_can_manage_school(request):
    """Backward-compatible wrapper around central permission helper."""
    return user_can_manage_school(request.user)


def _user_is_school_admin(request):
    """Helper for actions that only school admins (or above) should perform."""
    user = request.user
    if not user.is_authenticated:
        return False
    if user.is_superuser or getattr(user, "is_super_admin", False):
        return True
    return is_school_admin(user)


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
        if school and not getattr(user, "is_super_admin", False):
            staff = User.objects.filter(school=school, role__in=("admin", "teacher")).order_by("role", "username")
        else:
            # Platform view: list staff across all schools.
            staff = (
                User.objects.filter(role__in=("admin", "teacher"))
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

    return render(
        request,
        "accounts/staff_list.html",
        {"staff_list": staff, "staff_by_role": staff_by_role, "school": school},
    )


@login_required
def staff_detail(request, pk):
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    qs = User.objects.filter(role__in=("admin", "teacher"))
    if school:
        qs = qs.filter(school=school)
    staff = get_object_or_404(qs, pk=pk)
    return render(request, "accounts/staff_detail.html", {"staff": staff})


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
        if username and email and password and role in ("admin", "teacher"):
            if not User.objects.filter(username=username).exists():
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
                return redirect("accounts:staff_list")
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
    return render(request, "accounts/parent_list.html", {"parents": parents, "school": school})


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
            if not User.objects.filter(username=username).exists():
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
                return redirect("accounts:parent_list")
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
def user_management(request):
    """User management dashboard for school admins."""
    if not _user_is_school_admin(request):
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    # Get counts
    staff_count = User.objects.filter(school=school, role__in=("admin", "teacher")).count()
    parent_count = User.objects.filter(school=school, role="parent").count()
    # from students.models import Student # Moved to top
    student_count = Student.objects.filter(school=school).count()
    
    context = {
        "school": school,
        "staff_count": staff_count,
        "parent_count": parent_count,
        "student_count": student_count,
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
    
    staff = get_object_or_404(User, pk=pk, school=school, role__in=("admin", "teacher"))
    
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

    staff = get_object_or_404(User, pk=pk, school=school, role__in=("admin", "teacher"))

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
    Allow school admins and platform admins to reset a user's password.

    This is the main way to help parents, students, staff, and school admins
    who have forgotten their login details.
    """
    user = request.user
    target_user = get_object_or_404(User, pk=pk)

    # Permission check:
    # - Platform superuser or super_admin can reset anyone.
    # - School admins can only reset users in their own school.
    is_platform_admin = user.is_superuser or getattr(user, "is_super_admin", False)
    same_school = getattr(user, "school_id", None) and user.school_id == getattr(target_user, "school_id", None)
    is_school_level_admin = is_school_admin(user) and same_school

    if not (is_platform_admin or is_school_level_admin):
        messages.error(request, "You do not have permission to reset this user's password.")
        return redirect("accounts:school_dashboard")

    if request.method == "POST":
        new_password = get_random_string(10)
        target_user.set_password(new_password)
        target_user.save()

        messages.success(
            request,
            f"Password for user '{target_user.username}' has been reset. "
            f"New password: {new_password}",
        )

        # Redirect back to an appropriate detail page if possible
        next_url = request.GET.get("next")
        if next_url:
            return redirect(next_url)

        if target_user.role in ("admin", "teacher"):
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

        next_url = request.GET.get("next")
        if next_url:
            return redirect(next_url)

        if target_user.role in ("admin", "teacher"):
            return redirect("accounts:staff_detail", pk=target_user.pk)
        if target_user.role == "parent":
            return redirect("accounts:parent_detail", pk=target_user.pk)

        return redirect("accounts:dashboard")

    return render(
        request,
        "accounts/staff_login_edit.html",
        {"target_user": target_user},
    )
