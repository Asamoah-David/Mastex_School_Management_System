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
