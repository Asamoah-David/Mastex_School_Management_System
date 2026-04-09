"""Shared utilities including activity logging and common view helpers."""
import logging

logger = logging.getLogger(__name__)


def get_school(request):
    """Return the school for the current request.

    Priority: ``request.user.school`` → ``request.school`` (set by
    SchoolMiddleware from the subdomain).  Returns *None* for
    unauthenticated users or platform admins without a school.
    """
    if hasattr(request, "user") and request.user.is_authenticated:
        school = getattr(request.user, "school", None)
        if school:
            return school
    return getattr(request, "school", None)


def can_manage(request):
    """Check if the requesting user can manage school data."""
    from accounts.permissions import user_can_manage_school
    return request.user.is_superuser or user_can_manage_school(request.user)


def get_effective_school(request):
    """Alias for ``get_school`` — kept for backward compatibility."""
    return get_school(request)


def log_activity(user, action, details="", school=None, request=None):
    """
    Record an activity for audit trail. 
    Fails silently to avoid breaking views.
    Logs to audit.AuditLog model.
    """
    try:
        from audit.models import AuditLog
        
        ip = None
        user_agent = ""
        if request and hasattr(request, "META"):
            ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
        
        # Determine school
        if not school:
            school = getattr(user, "school", None)
        
        AuditLog.objects.create(
            user=user,
            action=action,
            model_name="activity",
            object_repr=details[:255] if details else "",
            object_id=str(user.id) if user else None,
            ip_address=ip,
            user_agent=user_agent,
            school=school,
        )
    except Exception as e:
        logger.warning("Activity log failed: %s", e)


def log_view(user, model_name, object_id, object_repr, school=None, request=None):
    """
    Log a view/access action.
    """
    try:
        from audit.models import AuditLog
        
        ip = None
        user_agent = ""
        if request and hasattr(request, "META"):
            ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
        
        if not school:
            school = getattr(user, "school", None)
        
        AuditLog.objects.create(
            user=user,
            action="view",
            model_name=model_name,
            object_id=str(object_id) if object_id else None,
            object_repr=str(object_repr)[:255] if object_repr else "",
            ip_address=ip,
            user_agent=user_agent,
            school=school,
        )
    except Exception as e:
        logger.warning("View log failed: %s", e)
