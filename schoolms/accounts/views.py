from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.urls import reverse

from accounts.models import User
from schools.models import School


def logout_view(request):
    """Log out and redirect to login page."""
    logout(request)
    return redirect(f"{reverse('accounts:login')}?logged_out=1")


def login_view(request):
    # Handle logout message
    if request.GET.get('logged_out') == '1':
        messages.success(request, "You have been logged out successfully.")
    
    # If already logged in, redirect to appropriate dashboard
    if request.user.is_authenticated:
        if request.user.role in ["parent", "student"]:
            return redirect("portal")
        elif request.user.role in ["school_admin", "teacher", "staff"]:
            return redirect("accounts:school_dashboard")
        elif request.user.is_superuser or request.user.role == "super_admin":
            return redirect("home")
    
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
            
            if user.role in ["parent", "student"]:
                return redirect("portal")
            elif user.role in ["school_admin", "teacher", "staff"]:
                return redirect("accounts:school_dashboard")
            elif user.is_superuser or user.role == "super_admin":
                return redirect("home")
            else:
                return redirect("home")
        else:
            messages.error(request, "Invalid username or password. Please try again.")
    
    return render(request, "accounts/login.html")


@login_required
def dashboard(request):
    # Redirect parents and students to their portal
    if request.user.role in ["parent", "student"]:
        return redirect("portal")
    
    # School admins, teachers, and staff get school admin dashboard
    if request.user.role in ["school_admin", "teacher", "staff"]:
        return redirect("accounts:school_dashboard")
    
    # Super admins and superusers get the main dashboard
    if request.user.is_superuser or request.user.role == "super_admin":
        from schools.models import School
        from students.models import Student
        from finance.models import Fee

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
    
    # Default redirect
    return redirect("accounts:login")


@login_required
def school_dashboard(request):
    """Custom dashboard for school admins, teachers, and staff."""
    # Only school staff can access
    if not request.user.is_staff_member and not request.user.is_school_admin:
        return redirect("home")
    
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    from students.models import Student
    from finance.models import Fee
    from operations.models import StudentAttendance, TeacherAttendance, AcademicCalendar
    
    # Get school statistics
    total_students = Student.objects.filter(school=school).count()
    male_students = Student.objects.filter(school=school, user__gender='male').count() if 'gender' in [f.name for f in Student._meta.get_fields()] else 0
    female_students = Student.objects.filter(school=school, user__gender='female').count() if 'gender' in [f.name for f in Student._meta.get_fields()] else 0
    
    # Get gender from user model if available
    try:
        male_students = Student.objects.filter(school=school, user__gender='male').count()
        female_students = Student.objects.filter(school=school, user__gender='female').count()
    except:
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
    """School admin or teacher can manage their school; superuser can manage any."""
    if request.user.is_superuser:
        return True
    return request.user.role in ("admin", "teacher") and getattr(request.user, "school_id", None)


@login_required
def staff_list(request):
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if school:
        staff = User.objects.filter(school=school, role__in=("admin", "teacher")).order_by("role", "username")
    else:
        staff = User.objects.filter(role__in=("admin", "teacher")).select_related("school").order_by("school", "username")
    
    # Group staff by role
    staff_by_role = {}
    for s in staff:
        role = s.get_role_display()  # This gets the display name like "Admin" or "Teacher"
        if role not in staff_by_role:
            staff_by_role[role] = []
        staff_by_role[role].append(s)
    
    return render(request, "accounts/staff_list.html", {"staff_list": staff, "staff_by_role": staff_by_role, "school": school})


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
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    parents = User.objects.filter(school=school, role="parent").order_by("username")
    return render(request, "accounts/parent_list.html", {"parents": parents, "school": school})


@login_required
def parent_register(request):
    """Register a new parent for the school."""
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
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    from students.models import Student
    parent = get_object_or_404(User, pk=pk, school=school, role="parent")
    children = Student.objects.filter(parent=parent).select_related("user", "school")
    return render(request, "accounts/parent_detail.html", {"parent": parent, "children": children})


@login_required
def user_management(request):
    """User management dashboard for school admins."""
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    # Get counts
    staff_count = User.objects.filter(school=school, role__in=("admin", "teacher")).count()
    parent_count = User.objects.filter(school=school, role="parent").count()
    from students.models import Student
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
    """Delete a staff member."""
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    staff = get_object_or_404(User, pk=pk, school=school, role__in=("admin", "teacher"))
    
    if request.method == "POST":
        staff.delete()
        messages.success(request, f"Staff member '{staff.username}' has been deleted.")
        return redirect("accounts:staff_list")
    
    return render(request, "accounts/confirm_delete.html", {
        "object": staff,
        "type": "staff member",
        "cancel_url": "accounts:staff_list"
    })


@login_required
def parent_delete(request, pk):
    """Delete a parent."""
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    parent = get_object_or_404(User, pk=pk, school=school, role="parent")
    
    if request.method == "POST":
        parent.delete()
        messages.success(request, f"Parent '{parent.username}' has been deleted.")
        return redirect("accounts:parent_list")
    
    return render(request, "accounts/confirm_delete.html", {
        "object": parent,
        "type": "parent",
        "cancel_url": "accounts:parent_list"
    })
