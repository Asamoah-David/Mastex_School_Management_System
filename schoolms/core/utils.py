"""Shared utilities including activity logging."""
import logging

logger = logging.getLogger(__name__)


def log_activity(user, action, details="", school=None, request=None):
    """Record an activity for audit trail. Fails silently to avoid breaking views."""
    try:
        from operations.models import ActivityLog
        ip = None
        if request and hasattr(request, "META"):
            ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
        ActivityLog.objects.create(
            user=user,
            action=action,
            details=details[:500] if details else "",
            school=school or getattr(user, "school", None),
            ip_address=ip,
        )
    except Exception as e:
        logger.warning("Activity log failed: %s", e)
