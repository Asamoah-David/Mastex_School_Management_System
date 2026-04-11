"""Write operations.ActivityLog rows for school-visible audit trail."""

from __future__ import annotations


def client_ip_from_request(request) -> str | None:
    if not request:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR")


def log_school_activity(
    *,
    action: str,
    details: str = "",
    user=None,
    school=None,
    ip: str | None = None,
) -> None:
    """
    Persist an activity row. Safe to call from signals/views; failures must not break UX.
    """
    try:
        from operations.models import ActivityLog

        if school is None and user is not None and getattr(user, "is_authenticated", False):
            school = getattr(user, "school", None)

        uid = None
        if user is not None and getattr(user, "is_authenticated", False):
            uid = user

        ActivityLog.objects.create(
            school=school,
            user=uid,
            action=(action or "action")[:100],
            details=(details or "")[:5000],
            ip_address=(ip or None) if ip else None,
        )
    except Exception:
        pass


def _dashboard_icon_for_action(action: str) -> tuple[str, str]:
    """Return (emoji, css_class) for activity list styling in dashboard_enhancements.css."""
    a = (action or "").lower()
    if any(k in a for k in ("fee", "payment", "invoice", "paystack", "receipt", "refund", "subscription")):
        return "💰", "finance"
    if any(k in a for k in ("student", "admission", "enroll", "promot", "library", "book")):
        return "🎓", "student"
    if any(k in a for k in ("login", "logout", "password", "session")):
        return "👤", "user"
    if any(k in a for k in ("message", "sms", "email", "notify", "broadcast")):
        return "📢", "school"
    return "📋", "school"


def activity_log_row_for_dashboard(log) -> dict:
    """Shape one ActivityLog for templates/dashboard.html recent activity widget."""
    icon, icon_class = _dashboard_icon_for_action(getattr(log, "action", "") or "")
    bits = []
    if getattr(log, "school", None):
        bits.append(log.school.name)
    if getattr(log, "user", None):
        u = log.user
        bits.append((u.get_full_name() or u.username or "").strip())
    headline = (log.details or "").strip()
    if not headline:
        headline = (log.action or "activity").replace("_", " ").strip().title()
    prefix = " · ".join(b for b in bits if b)
    description = f"{prefix + ' — ' if prefix else ''}{headline}".strip()
    if len(description) > 260:
        description = description[:257] + "…"
    return {
        "description": description,
        "timestamp": log.created_at,
        "icon": icon,
        "icon_class": icon_class,
    }


def recent_activities_for_dashboard(*, user, school=None, limit: int = 12) -> list:
    """
    Recent ActivityLog rows for the super-admin / staff dashboard.

    Platform admins (superuser or super_admin role) see activity across all schools.
    Other staff with a linked school see only that school's log.
    """
    if not getattr(user, "is_authenticated", False):
        return []
    try:
        from operations.models import ActivityLog
    except Exception:
        return []

    is_platform = user.is_superuser or getattr(user, "role", None) == "super_admin"
    qs = ActivityLog.objects.select_related("user", "school").order_by("-created_at")
    if not is_platform:
        if school:
            qs = qs.filter(school=school)
        else:
            return []

    return [activity_log_row_for_dashboard(log) for log in qs[:limit]]
