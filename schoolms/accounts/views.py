from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.contrib.auth.hashers import make_password

from accounts.models import User
from schools.models import School


def logout_view(request):
    """Log out and redirect to login page (works with GET for link-based logout)."""
    logout(request)
    return redirect("accounts:login")


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            if user.role == "parent" or user.role == "student":
                return redirect("portal")
            return redirect("home")
    return render(request, "accounts/login.html")


@login_required
def dashboard(request):
    if request.user.role == "parent":
        return redirect("portal")
    if request.user.role == "student":
        return redirect("portal")

    from schools.models import School
    from students.models import Student
    from finance.models import Fee

    school = getattr(request.user, "school", None)
    
    # Check if superuser (platform admin)
    is_superuser = request.user.is_superuser
    
    if school:
        total_schools = 1
        total_students = Student.objects.filter(school=school).count()
        total_staff = User.objects.filter(school=school, role__in=("admin", "teacher")).count()
        total_parents = User.objects.filter(school=school, role="parent").count()
        paid_fees = Fee.objects.filter(school=school, paid=True).aggregate(total=Sum("amount"))["total"] or 0
        unpaid_count = Fee.objects.filter(school=school, paid=False).count()
    else:
        total_schools = School.objects.filter(is_active=True).count()
        total_students = Student.objects.count()
        total_staff = User.objects.filter(role__in=("admin", "teacher")).count()
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
    return render(request, "accounts/staff_list.html", {"staff_list": staff, "school": school})


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
