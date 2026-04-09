from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from .models import AuditLog


def _has_audit_access(user):
    if user.is_superuser or getattr(user, "role", None) == "super_admin":
        return True, True  # (has_access, is_superuser)
    if getattr(user, "role", None) == "school_admin" and getattr(user, "school", None):
        return True, False
    return False, False


@login_required
def audit_dashboard(request):
    """Audit log dashboard - superusers see all, school admins see their school's logs."""
    user = request.user
    has_access, is_super = _has_audit_access(user)
    if not has_access:
        return redirect("home")

    if is_super:
        logs = AuditLog.objects.all()
    else:
        logs = AuditLog.objects.filter(school=user.school)

    action_filter = request.GET.get("action", "")
    model_filter = request.GET.get("model", "")
    user_filter = request.GET.get("user", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    search_query = request.GET.get("q", "")

    if action_filter:
        logs = logs.filter(action=action_filter)
    if model_filter:
        logs = logs.filter(model_name__icontains=model_filter)
    if user_filter:
        logs = logs.filter(user__username__icontains=user_filter)
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)
    if search_query:
        logs = logs.filter(
            Q(object_repr__icontains=search_query)
            | Q(user__username__icontains=search_query)
            | Q(model_name__icontains=search_query)
        )

    logs = logs.select_related("user", "school").order_by("-timestamp")

    paginator = Paginator(logs, 50)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    context = {
        "page_obj": page_obj,
        "action_choices": [c[0] for c in AuditLog.ACTION_CHOICES],
        "can_view_all": is_super,
        "filters": {
            "action": action_filter,
            "model": model_filter,
            "user": user_filter,
            "date_from": date_from,
            "date_to": date_to,
            "q": search_query,
        },
    }
    return render(request, "audit/dashboard.html", context)


@login_required
def audit_log_detail(request, pk):
    """View details of a single audit log entry."""
    user = request.user
    has_access, is_super = _has_audit_access(user)
    if not has_access:
        return redirect("home")

    log_entry = get_object_or_404(
        AuditLog.objects.select_related("user", "school"), pk=pk
    )

    if not is_super and getattr(user, "school", None) != log_entry.school:
        return redirect("home")

    return render(request, "audit/log_detail.html", {"log": log_entry})
