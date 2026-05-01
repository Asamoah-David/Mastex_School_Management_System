"""
Scholarship management views — F13

Provides list/create/detail/award surfaces for Scholarship and ScholarshipAward.
Guarded to school_admin / admin / finance roles.
"""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from schools.features import is_feature_enabled

logger = logging.getLogger(__name__)


def _school(request):
    return getattr(request.user, "school", None)


def _is_finance_admin(request):
    user = request.user
    if user.is_superuser or getattr(user, "is_super_admin", False):
        return True
    return getattr(user, "role", None) in ("school_admin", "admin", "bursar", "finance", "deputy_head")


# ---------------------------------------------------------------------------
# Scholarship List
# ---------------------------------------------------------------------------

@login_required
def scholarship_list(request):
    from finance.models import Scholarship

    school = _school(request)
    if not school:
        return redirect("home")
    if not is_feature_enabled(request, "scholarships"):
        messages.error(request, "Scholarship management is not enabled for your school.")
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")

    scholarships = Scholarship.objects.filter(school=school).order_by("-created_at")
    return render(request, "finance/scholarship_list.html", {
        "scholarships": scholarships,
    })


# ---------------------------------------------------------------------------
# Scholarship Create
# ---------------------------------------------------------------------------

@login_required
def scholarship_create(request):
    from finance.models import Scholarship

    school = _school(request)
    if not school:
        return redirect("home")
    if not is_feature_enabled(request, "scholarships"):
        messages.error(request, "Scholarship management is not enabled for your school.")
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        scholarship_type = request.POST.get("scholarship_type", "full")
        cycle = request.POST.get("cycle", "annual")
        total_budget = request.POST.get("total_budget") or None
        amount_per_award = request.POST.get("amount_per_award") or None
        percentage_discount = request.POST.get("percentage_discount") or None
        max_beneficiaries = request.POST.get("max_beneficiaries") or None
        eligibility_criteria = request.POST.get("eligibility_criteria", "")
        description = request.POST.get("description", "")

        if not name:
            messages.error(request, "Scholarship name is required.")
            return render(request, "finance/scholarship_form.html", {"action": "Create", "post": request.POST})

        Scholarship.objects.create(
            school=school,
            name=name,
            scholarship_type=scholarship_type,
            cycle=cycle,
            total_budget=total_budget,
            amount_per_award=amount_per_award,
            percentage_discount=percentage_discount,
            max_beneficiaries=max_beneficiaries,
            eligibility_criteria=eligibility_criteria,
            description=description,
            is_active=True,
        )
        messages.success(request, f"Scholarship '{name}' created.")
        return redirect("finance:scholarship_list")

    return render(request, "finance/scholarship_form.html", {"action": "Create"})


# ---------------------------------------------------------------------------
# Scholarship Detail (includes award list)
# ---------------------------------------------------------------------------

@login_required
def scholarship_detail(request, pk):
    from finance.models import Scholarship, ScholarshipAward

    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")

    scholarship = get_object_or_404(Scholarship, pk=pk, school=school)
    awards = ScholarshipAward.objects.filter(
        scholarship=scholarship
    ).select_related("student", "student__user").order_by("-created_at")

    return render(request, "finance/scholarship_detail.html", {
        "scholarship": scholarship,
        "awards": awards,
    })


# ---------------------------------------------------------------------------
# Award a scholarship to a student
# ---------------------------------------------------------------------------

@login_required
def scholarship_award_create(request, scholarship_pk):
    from finance.models import Scholarship, ScholarshipAward

    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")

    scholarship = get_object_or_404(Scholarship, pk=scholarship_pk, school=school)

    if request.method == "POST":
        from students.models import Student
        student_id = request.POST.get("student")
        student = get_object_or_404(Student, pk=student_id, school=school)
        academic_year = request.POST.get("academic_year", "").strip()
        term = request.POST.get("term", "").strip()
        awarded_amount = request.POST.get("awarded_amount") or scholarship.amount_per_award or 0

        if ScholarshipAward.objects.filter(scholarship=scholarship, student=student, academic_year=academic_year).exists():
            messages.error(request, "This student already has an award for this scholarship in the selected year.")
        else:
            ScholarshipAward.objects.create(
                school=school,
                scholarship=scholarship,
                student=student,
                academic_year=academic_year,
                term=term,
                awarded_amount=awarded_amount,
                status="pending",
            )
            messages.success(request, f"Award created for {student.user.get_full_name()}.")

        return redirect("finance:scholarship_detail", pk=scholarship_pk)

    from students.models import Student
    students = Student.objects.filter(school=school, status="active").select_related("user").order_by("user__last_name")
    return render(request, "finance/scholarship_award_form.html", {
        "scholarship": scholarship,
        "students": students,
    })


# ---------------------------------------------------------------------------
# Activate / revoke an award
# ---------------------------------------------------------------------------

@login_required
@require_POST
def scholarship_award_action(request, pk):
    from finance.models import ScholarshipAward

    school = _school(request)
    if not school:
        return redirect("home")
    if not _is_finance_admin(request):
        return HttpResponseForbidden("Access denied.")

    award = get_object_or_404(ScholarshipAward, pk=pk, school=school)
    action = request.POST.get("action")

    if action == "activate" and award.status == "pending":
        award.activate(approver=request.user)
        messages.success(request, f"Award for {award.student.user.get_full_name()} activated.")
    elif action == "revoke" and award.status == "active":
        award.status = "revoked"
        award.save(update_fields=["status", "updated_at"])
        messages.success(request, f"Award for {award.student.user.get_full_name()} revoked.")
    else:
        messages.error(request, f"Cannot apply '{action}' to award with status '{award.status}'.")

    return redirect("finance:scholarship_detail", pk=award.scholarship_id)
