"""Library fine management views."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import user_can_manage_school
from core.utils import get_school
from schools.features import is_feature_enabled


def _require_library_manager(request):
    return user_can_manage_school(request.user) or getattr(request.user, "has_role", lambda r: False)("librarian")


@login_required
def library_fine_list(request):
    """List all library fines for the school, filterable by status."""
    from operations.models import LibraryFine

    school = get_school(request)
    if not school:
        return redirect("home")
    if not is_feature_enabled(request, "library"):
        messages.error(request, "Library feature is not enabled for your school.")
        return redirect("home")
    if not _require_library_manager(request):
        messages.error(request, "Access denied.")
        return redirect("home")

    status_filter = request.GET.get("status", "")
    student_q = request.GET.get("q", "").strip()

    qs = LibraryFine.objects.filter(school=school).select_related(
        "issue", "issue__student", "issue__student__user", "issue__book", "waived_by"
    ).order_by("-created_at")

    if status_filter:
        qs = qs.filter(status=status_filter)
    if student_q:
        qs = qs.filter(
            Q(issue__student__user__first_name__icontains=student_q)
            | Q(issue__student__user__last_name__icontains=student_q)
            | Q(issue__student__user__username__icontains=student_q)
            | Q(issue__student__admission_number__icontains=student_q)
        )

    counts = {
        "total": LibraryFine.objects.filter(school=school).count(),
        "pending": LibraryFine.objects.filter(school=school, status="pending").count(),
        "partial": LibraryFine.objects.filter(school=school, status="partial").count(),
        "paid": LibraryFine.objects.filter(school=school, status="paid").count(),
        "waived": LibraryFine.objects.filter(school=school, status="waived").count(),
    }

    return render(request, "operations/library_fine_list.html", {
        "fines": qs[:200],
        "status_filter": status_filter,
        "student_q": student_q,
        "counts": counts,
    })


@login_required
@require_POST
def library_fine_mark_paid(request, pk):
    """Record a full or partial payment against a library fine."""
    from operations.models import LibraryFine

    school = get_school(request)
    if not school:
        return redirect("home")
    if not is_feature_enabled(request, "library"):
        messages.error(request, "Library feature is not enabled for your school.")
        return redirect("home")
    if not _require_library_manager(request):
        messages.error(request, "Access denied.")
        return redirect("operations:library_fine_list")

    fine = get_object_or_404(LibraryFine, pk=pk, school=school)
    if fine.status in ("paid", "waived"):
        messages.warning(request, "Fine is already settled.")
        return redirect("operations:library_fine_list")

    amount_str = request.POST.get("amount", "").strip()
    try:
        amount = Decimal(str(amount_str))
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError, InvalidOperation):
        messages.error(request, "Enter a valid positive amount.")
        return redirect("operations:library_fine_list")

    fine.mark_paid(amount, recorded_by=request.user)
    messages.success(request, f"Payment of GHS {amount:.2f} recorded for fine #{fine.pk}.")
    return redirect("operations:library_fine_list")


@login_required
@require_POST
def library_fine_waive(request, pk):
    """Waive a library fine with a reason."""
    from operations.models import LibraryFine

    school = get_school(request)
    if not school:
        return redirect("home")
    if not is_feature_enabled(request, "library"):
        messages.error(request, "Library feature is not enabled for your school.")
        return redirect("home")
    if not _require_library_manager(request):
        messages.error(request, "Access denied.")
        return redirect("operations:library_fine_list")

    fine = get_object_or_404(LibraryFine, pk=pk, school=school)
    if fine.status in ("paid", "waived"):
        messages.warning(request, "Fine is already settled.")
        return redirect("operations:library_fine_list")

    reason = request.POST.get("reason", "").strip()
    fine.waive(request.user, reason=reason)
    messages.success(request, f"Fine #{fine.pk} has been waived.")
    return redirect("operations:library_fine_list")
