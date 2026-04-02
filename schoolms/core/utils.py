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
