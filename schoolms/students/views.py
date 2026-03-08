from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.hashers import make_password

from .models import Student
from accounts.models import User
from schools.models import School


def _user_can_manage_school(request):
    if request.user.is_superuser:
        return True
    return request.user.role in ("admin", "teacher") and getattr(request.user, "school_id", None)


@login_required
def parent_dashboard(request):
    from finance.models import Fee
    children = Student.objects.filter(parent=request.user).select_related("school", "user")
    
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
    
    return render(request, "students/parent_dashboard.html", {
        "children": children,
        "fees_by_child": fees_by_child
    })


@login_required
def portal(request):
    """Single portal URL: parents see children; students see own dashboard."""
    if request.user.role == "parent":
        return parent_dashboard(request)
    if request.user.role == "student":
        try:
            student = Student.objects.get(user=request.user)
            return render(request, "students/student_portal.html", {"student": student})
        except Student.DoesNotExist:
            return render(request, "students/student_portal.html", {"student": None})
    return redirect("home")


@login_required
def student_list(request):
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    students = Student.objects.filter(school=school).select_related("user", "parent").order_by("class_name", "admission_number")
    return render(request, "students/student_list.html", {"students": students, "school": school})


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
        parent_id = request.POST.get("parent") or None
        if username and admission_number and password:
            if not User.objects.filter(username=username).exists():
                user = User.objects.create(
                    username=username,
                    email=email or f"{username}@school.local",
                    first_name=first_name,
                    last_name=last_name,
                    password=make_password(password),
                    role="student",
                    school=school,
                )
                Student.objects.create(
                    school=school,
                    user=user,
                    admission_number=admission_number,
                    class_name=class_name,
                    parent_id=parent_id or None,
                )
                return redirect("students:student_list")
    parents = User.objects.filter(school=school, role="parent").order_by("username")
    return render(request, "students/student_register.html", {"school": school, "parents": parents})