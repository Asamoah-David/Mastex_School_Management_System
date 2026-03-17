"""Shared utilities including activity logging."""
import logging

logger = logging.getLogger(__name__)


def get_effective_school(request):
    """
    Get the effective school for the current request.
    Returns the school from request.user.school if available,
    otherwise tries to get from subdomain via middleware.
    """
    if not request:
        return None
    
    # First try to get from authenticated user
    if hasattr(request, "user") and request.user.is_authenticated:
        school = getattr(request.user, "school", None)
        if school:
            return school
    
    # Try to get from request attribute set by middleware
    return getattr(request, "_school", None)


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
