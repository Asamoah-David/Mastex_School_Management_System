from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required

def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect("dashboard")
    return render(request, "accounts/login.html")

@login_required
def dashboard(request):
    if request.user.role == "parent":
        return redirect("students:parent_dashboard")
    return render(request, "dashboard.html")