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
from finance.models import Fee, FeePayment
from operations.models import StudentAttendance, TeacherAttendance, AcademicCalendar

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
        
        # First check if user exists (to check for lockout before authenticating)
        try:
            user_obj = User.objects.get(username=username)
            # Check if user is locked out
            if user_obj.is_locked_out():
                remaining = user_obj.get_lockout_remaining_seconds()
                minutes = remaining // 60
                seconds = remaining % 60
                messages.error(request, f"Account temporarily locked. Please try again in {minutes} minute(s) {seconds} second(s).")
                return render(request, "accounts/login.html")
        except User.DoesNotExist:
            pass  # User doesn't exist, will handle below
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if user's school is active (skip for superusers/super_admins)
            user_school = getattr(user, 'school', None)
            if user_school and not getattr(user, 'is_superuser', False) and getattr(user, 'role', None) != 'super_admin':
                if not user_school.is_active:
                    messages.error(request, "Your school's account is currently inactive. Please contact the administrator.")
                    return render(request, "accounts/login.html")
            
            # Reset failed login counter on successful login
            if hasattr(user, 'reset_failed_logins'):
                user.reset_failed_logins()
            
            login(request, user)
            role = getattr(user, "role", None)
            if role in ["parent", "student"]:
                return redirect("portal")
            if role in ["admin", "school_admin", "teacher", "staff"]:
                return redirect("accounts:school_dashboard")
            if user.is_superuser or role == "super_admin":
                return redirect("accounts:dashboard")
            return redirect("accounts:dashboard")
        
        # Login failed - track attempts
        messages.error(request, "Invalid username or password.")
        
        # Try to find user and increment failed attempts
        try:
            user_obj = User.objects.get(username=username)
            if hasattr(user_obj, 'increment_failed_login'):
                user_obj.increment_failed_login()
                remaining_attempts = 5 - user_obj.failed_login_attempts
                if remaining_attempts > 0 and remaining_attempts <= 3:
                    messages.warning(request, f"Invalid login. {remaining_attempts} attempt(s) remaining before account lockout.")
        except User.DoesNotExist:
            pass  # No user found, nothing to track
    
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
                    from django.conf import settings
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
    
    # Fee statistics - Calculate actual amounts paid and outstanding
    total_fees = Fee.objects.filter(school=school).aggregate(total=Sum("amount"))["total"] or 0
    # Sum amount_paid for fees that have been partially or fully paid
    paid_fees = Fee.objects.filter(school=school).aggregate(total=Sum("amount_paid"))["total"] or 0
    # Calculate actual outstanding (total amount - amount paid)
    all_fees = Fee.objects.filter(school=school)
    unpaid_fees = sum(max(0, float(f.amount) - float(f.amount_paid)) for f in all_fees)
    
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
        "recent_payments": recent_payments,
        "show_expiry_warning": show_expiry_warning,
        "expiry_severity": expiry_severity,
        "expiry_icon": expiry_icon,
        "expiry_title": expiry_title,
        "expiry_message": expiry_message,
        "expiry_button_text": expiry_button_text,
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
    # Include all staff roles
    all_staff_roles = ("admin", "school_admin", "deputy_head", "hod", "teacher", 
                      "accountant", "librarian", "admission_officer", "school_nurse", 
                      "admin_assistant", "staff")
    qs = User.objects.filter(role__in=all_staff_roles)
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
            messages.error(request, "Please fill all required fields.")
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
    
    staff = get_object_or_404(User, pk=pk, school=school, role__in=("school_admin", "teacher"))
    
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

    staff = get_object_or_404(User, pk=pk, school=school, role__in=("school_admin", "teacher"))

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
        role__in=("admin", "school_admin", "deputy_head", "hod", "teacher", 
                  "accountant", "librarian", "admission_officer", "school_nurse", 
                  "admin_assistant", "staff")
    )

    # Prevent self-demotion
    if staff.pk == request.user.pk:
        messages.error(request, "You cannot change your own role.")
        return redirect("accounts:staff_detail", pk=pk)

    if request.method == "POST":
        new_role = request.POST.get("new_role", "")
        valid_roles = (
            "teacher", "deputy_head", "hod", "accountant", "librarian",
            "admission_officer", "school_nurse", "admin_assistant", "staff"
        )
        
        if new_role in valid_roles:
            old_role = staff.get_role_display()
            staff.role = new_role
            staff.save(update_fields=["role"])
            messages.success(
                request,
                f"Role changed from '{old_role}' to '{staff.get_role_display()}' for '{staff.username}'.",
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
        role__in=("admin", "school_admin", "deputy_head", "hod", "teacher", 
                  "accountant", "librarian", "admission_officer", "school_nurse", 
                  "admin_assistant", "staff")
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
        
        # Store as comma-separated string
        staff.secondary_roles = ','.join(filtered_roles)
        staff.save(update_fields=['secondary_roles'])
        
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
