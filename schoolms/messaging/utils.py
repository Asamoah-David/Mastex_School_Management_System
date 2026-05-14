from services.sms_service import SMSService


def send_sms(to, message, school_name=None):
    """
    Convenience wrapper used by other apps for sending SMS.
    Delegates to the central SMSService implementation.
    """
    return SMSService.send_sms(to, message, school_name=school_name)


def send_sms_notification(to, message):
    """
    Backwards-compatible alias; prefer send_sms going forward.
    """
    return SMSService.send_sms(to, message)


def resolve_messaging_school(request):
    """School for messaging views: user/subdomain school, else superuser session ``current_school_id``."""
    from core.utils import get_school
    from schools.models import School

    school = get_school(request)
    if not school and getattr(request.user, "is_superuser", False):
        sid = request.session.get("current_school_id")
        if sid:
            school = School.objects.filter(pk=sid).first()
    return school