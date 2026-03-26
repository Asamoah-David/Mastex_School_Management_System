from .models import Notification

def notification_context(request):
    """Add unread notification count to all templates"""
    if request.user.is_authenticated:
        unread_count = Notification.get_unread_count(request.user)
        return {'unread_notification_count': unread_count}
    return {'unread_notification_count': 0}