import csv

from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count
from .models import AuditLog


def _has_audit_access(user):
    from accounts.permissions import is_super_admin, is_school_leadership

    if user.is_superuser or is_super_admin(user):
        return True, True  # (has_access, is_superuser)
    if is_school_leadership(user) and getattr(user, "school", None):
        return True, False
    return False, False


def _audit_filters_from_request(request):
    per_page = (request.GET.get("per_page") or "50").strip()
    if per_page not in ("25", "50", "100"):
        per_page = "50"
    return {
        "action": request.GET.get("action", ""),
        "model": request.GET.get("model", ""),
        "user": request.GET.get("user", ""),
        "date_from": request.GET.get("date_from", ""),
        "date_to": request.GET.get("date_to", ""),
        "q": request.GET.get("q", ""),
        "school_id": (request.GET.get("school_id") or "").strip(),
        "per_page": per_page,
    }


def _filtered_audit_queryset(user, is_super, filters):
    if is_super:
        logs = AuditLog.objects.all()
    else:
        logs = AuditLog.objects.filter(school=user.school)

    if is_super and filters["school_id"].isdigit():
        logs = logs.filter(school_id=int(filters["school_id"]))

    if filters["action"]:
        logs = logs.filter(action=filters["action"])
    if filters["model"]:
        logs = logs.filter(model_name__icontains=filters["model"])
    if filters["user"]:
        logs = logs.filter(user__username__icontains=filters["user"])
    if filters["date_from"]:
        logs = logs.filter(timestamp__date__gte=filters["date_from"])
    if filters["date_to"]:
        logs = logs.filter(timestamp__date__lte=filters["date_to"])
    if filters["q"]:
        logs = logs.filter(
            Q(object_repr__icontains=filters["q"])
            | Q(user__username__icontains=filters["q"])
            | Q(model_name__icontains=filters["q"])
        )

    return logs.select_related("user", "school").order_by("-timestamp")


@login_required
def audit_dashboard(request):
    """Audit log dashboard - superusers see all, school admins see their school's logs."""
    user = request.user
    has_access, is_super = _has_audit_access(user)
    if not has_access:
        return redirect("home")

    filters = _audit_filters_from_request(request)
    logs = _filtered_audit_queryset(user, is_super, filters)

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="audit_log_export.csv"'
        w = csv.writer(response)
        w.writerow(
            [
                "timestamp",
                "action",
                "model_name",
                "object_id",
                "object_repr",
                "username",
                "school",
                "ip_address",
            ]
        )
        for row in logs.iterator(chunk_size=500):
            w.writerow(
                [
                    row.timestamp.isoformat() if row.timestamp else "",
                    row.action,
                    row.model_name,
                    row.object_id or "",
                    (row.object_repr or "").replace("\n", " ")[:500],
                    row.user.username if row.user_id else "",
                    row.school.name if row.school_id else "",
                    row.ip_address or "",
                ]
            )
        return response

    paginator = Paginator(logs, int(filters["per_page"]))
    page_obj = paginator.get_page(request.GET.get("page", 1))

    audit_schools = []
    if is_super:
        from schools.models import School

        audit_schools = list(School.objects.order_by("name").values("id", "name")[:300])

    action_labels = dict(AuditLog.ACTION_CHOICES)
    action_summary = [
        {"action": row["action"], "label": action_labels.get(row["action"], row["action"]), "count": row["c"]}
        for row in logs.values("action").annotate(c=Count("id")).order_by("-c")[:10]
    ]
    max_action_count = max((row["count"] for row in action_summary), default=0)

    context = {
        "page_obj": page_obj,
        "action_choices": [c[0] for c in AuditLog.ACTION_CHOICES],
        "can_view_all": is_super,
        "filters": filters,
        "audit_schools": audit_schools,
        "action_summary": action_summary,
        "max_action_count": max_action_count,
        "total_filtered_count": paginator.count,
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
