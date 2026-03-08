from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Sum


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
            return redirect("home")
    return render(request, "accounts/login.html")

@login_required
def dashboard(request):
    if request.user.role == "parent":
        return redirect("students:parent_dashboard")

    from schools.models import School
    from students.models import Student
    from finance.models import Fee

    total_schools = School.objects.filter(is_active=True).count()
    total_students = Student.objects.count()
    paid_fees = Fee.objects.filter(paid=True).aggregate(total=Sum("amount"))["total"] or 0
    unpaid_count = Fee.objects.filter(paid=False).count()

    context = {
        "total_schools": total_schools,
        "total_students": total_students,
        "mrr": int(paid_fees),
        "unpaid_fees_count": unpaid_count,
    }
    return render(request, "dashboard.html", context)