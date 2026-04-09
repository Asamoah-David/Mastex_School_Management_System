from django.core.cache import cache


def notification_context(request):
    """Add unread notification count to all templates (cached 60s per user)."""
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0}

    cache_key = f"notif_count:{request.user.pk}"
    count = cache.get(cache_key)
    if count is None:
        from .models import Notification
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        cache.set(cache_key, count, 60)
    return {"unread_notification_count": count}
