from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.urls import reverse

from core.pagination import paginate

from .models import Notification

_NOTIF_URL_PLACEHOLDER = 987654321


def _notification_api_url_templates():
    """Stable URL patterns for list-page JS (avoids hard-coded /notifications/… paths)."""
    read = reverse("notifications:mark_read", kwargs={"notification_id": _NOTIF_URL_PLACEHOLDER})
    delete = reverse("notifications:delete", kwargs={"notification_id": _NOTIF_URL_PLACEHOLDER})
    ph = str(_NOTIF_URL_PLACEHOLDER)
    return {
        "mark_read": read.replace(ph, "__ID__"),
        "delete": delete.replace(ph, "__ID__"),
        "mark_all_read": reverse("notifications:mark_all_read"),
    }


@login_required
def notification_list(request):
    """List all notifications for the user (paginated)."""
    qs = Notification.objects.filter(user=request.user).order_by("-created_at")
    page_obj = paginate(request, qs, per_page=25)
    unread_count = Notification.get_unread_count(request.user)
    return render(
        request,
        "notifications/list.html",
        {
            "page_obj": page_obj,
            "notifications": page_obj,
            "unread_count": unread_count,
            "notification_api": _notification_api_url_templates(),
        },
    )

@login_required
def get_notifications(request):
    """Get notifications as JSON for AJAX calls"""
    notifications = Notification.objects.filter(user=request.user)[:10]
    unread_count = Notification.get_unread_count(request.user)
    
    data = {
        'notifications': [
            {
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'type': n.notification_type,
                'link': n.link,
                'is_read': n.is_read,
                'created_at': n.created_at.strftime('%b %d, %Y %H:%M')
            }
            for n in notifications
        ],
        'unread_count': unread_count
    }
    return JsonResponse(data)

@login_required
@require_http_methods(["POST"])
def mark_as_read(request, notification_id):
    """Mark a single notification as read"""
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
        notification.mark_as_read()
        return JsonResponse({'success': True})
    except Notification.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Notification not found'})

@login_required
@require_http_methods(["POST"])
def mark_all_as_read(request):
    """Mark all notifications as read"""
    Notification.mark_all_as_read(request.user)
    return JsonResponse({'success': True})

@login_required
@require_http_methods(["POST"])
def delete_notification(request, notification_id):
    """Delete a notification"""
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
        notification.delete()
        return JsonResponse({'success': True})
    except Notification.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Notification not found'})

def send_notification(user, title, message, notification_type='info', link=None):
    """Helper function to send notifications"""
    return Notification.create_notification(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        link=link
    )
