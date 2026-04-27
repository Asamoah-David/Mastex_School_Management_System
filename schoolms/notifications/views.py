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
    """Get notifications as JSON for AJAX calls.

    Query params:
      ?type=<notification_type>  — filter by notification_type
      ?after=<iso-datetime>      — return only notifications created after this timestamp
      ?limit=<int>               — max results (default 10, max 50)
      ?unread_only=1             — return only unread notifications
    """
    qs = Notification.objects.filter(user=request.user).select_related("school")

    notif_type = request.GET.get("type")
    if notif_type:
        qs = qs.filter(notification_type=notif_type)

    after = request.GET.get("after")
    if after:
        try:
            from django.utils.dateparse import parse_datetime
            after_dt = parse_datetime(after)
            if after_dt:
                qs = qs.filter(created_at__gt=after_dt)
        except (ValueError, TypeError):
            pass

    if request.GET.get("unread_only") == "1":
        qs = qs.filter(is_read=False)

    try:
        limit = min(int(request.GET.get("limit", 10)), 50)
    except (ValueError, TypeError):
        limit = 10

    notifications = qs[:limit]
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
                'created_at': n.created_at.strftime('%b %d, %Y %H:%M'),
                'created_at_iso': n.created_at.isoformat(),
            }
            for n in notifications
        ],
        'unread_count': unread_count,
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

@login_required
@require_http_methods(["GET"])
def dashboard_summary(request):
    """UX-2: JSON summary consumed by the dashboard widget.

    Returns unread count, pending fee totals, AI token quota, and current term.
    Cached per-user for 60 seconds to avoid per-request DB hit on every page load.
    """
    from django.core.cache import cache
    uid = request.user.pk
    key = f"dash_summary:{uid}"
    data = cache.get(key)
    if data is None:
        school = getattr(request.user, "school", None)
        data = {
            "unread_notifications": Notification.get_unread_count(request.user),
            "school_name": school.name if school else "",
            "current_term": None,
            "unpaid_fees": None,
            "overdue_installments": None,
            "pending_po": None,
            "ai_token_used": None,
            "ai_token_cap": None,
        }
        try:
            from academics.models import Term
            term = Term.objects.filter(school=school, is_current=True).values("name", "end_date").first()
            if term:
                data["current_term"] = {"name": term["name"], "end_date": str(term["end_date"])}
        except Exception:
            pass
        try:
            from finance.models import Fee
            from django.db.models import Sum
            role = getattr(request.user, "role", "")
            if role in ("student", "parent"):
                from students.models import Student
                if role == "parent":
                    stu_qs = Student.objects.filter(school=school, parent=request.user)
                else:
                    stu_qs = Student.objects.filter(school=school, user=request.user)
                unpaid = Fee.objects.filter(
                    student__in=stu_qs, paid=False, deleted_at__isnull=True
                ).aggregate(t=Sum("amount"))["t"]
                data["unpaid_fees"] = float(unpaid or 0)
                from finance.models import FeeInstallmentPlan
                data["overdue_installments"] = FeeInstallmentPlan.objects.filter(
                    fee__student__in=stu_qs, status="overdue"
                ).count()
            if role in ("school_admin", "bursar") and school:
                from finance.models import PurchaseOrder
                data["pending_po"] = PurchaseOrder.objects.filter(
                    school=school, status__in=["submitted", "approved"]
                ).count()
        except Exception:
            pass
        try:
            if school:
                data["ai_token_used"] = getattr(school, "ai_total_tokens_used", None)
                data["ai_token_cap"] = getattr(school, "ai_monthly_token_cap", None)
        except Exception:
            pass
        cache.set(key, data, 60)
    return JsonResponse(data)


@login_required
@require_http_methods(["POST"])
def bulk_dismiss_notifications(request):
    """UX-3: Bulk-delete a list of notification IDs sent as JSON body."""
    import json
    try:
        body = json.loads(request.body)
        ids = [int(i) for i in body.get("ids", [])]
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"success": False, "error": "Invalid request body"}, status=400)
    if not ids:
        return JsonResponse({"success": False, "error": "No IDs provided"}, status=400)
    deleted, _ = Notification.objects.filter(user=request.user, pk__in=ids).delete()
    Notification._invalidate_count_cache(request.user.pk)
    return JsonResponse({"success": True, "deleted": deleted})


@login_required
@require_http_methods(["POST"])
def snooze_notifications(request):
    """UX-4: Mute all notifications for X minutes (updates NotificationPreference.muted_until)."""
    import json
    from django.utils import timezone
    from datetime import timedelta
    from .models import NotificationPreference
    try:
        body = json.loads(request.body)
        minutes = int(body.get("minutes", 60))
        if minutes < 1 or minutes > 10080:  # max 1 week
            raise ValueError
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"success": False, "error": "minutes must be 1–10080"}, status=400)
    pref, _ = NotificationPreference.objects.get_or_create(user=request.user)
    pref.muted_until = timezone.now() + timedelta(minutes=minutes)
    pref.save(update_fields=["muted_until"])
    return JsonResponse({"success": True, "muted_until": pref.muted_until.isoformat()})


@login_required
@require_http_methods(["POST"])
def update_notification_preferences(request):
    """UX-4: Update NotificationPreference fields from JSON body.

    Accepts any subset of boolean fields; unknown keys are ignored.
    """
    import json
    from .models import NotificationPreference
    ALLOWED_BOOL_FIELDS = {
        "email_enabled", "sms_enabled", "push_enabled",
        "payment_alerts", "attendance_alerts", "result_alerts",
        "message_alerts", "announcement_alerts", "fee_reminder_alerts",
        "academic_event_alerts", "contract_expiry_alerts",
        "installment_overdue_alerts", "inventory_alerts",
        "leave_alerts", "purchase_order_alerts", "subscription_alerts",
    }
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    pref, _ = NotificationPreference.objects.get_or_create(user=request.user)
    updated = []
    for field in ALLOWED_BOOL_FIELDS:
        if field in body:
            setattr(pref, field, bool(body[field]))
            updated.append(field)
    if updated:
        pref.save(update_fields=updated)
    return JsonResponse({"success": True, "updated_fields": updated})


def send_notification(user, title, message, notification_type='info', link=None, school=None):
    """Helper function to send notifications.

    ``school`` is forwarded to ``Notification.create_notification()`` so
    every notification is tenant-scoped.  Falls back to ``user.school``
    when omitted (handled inside ``create_notification``).
    """
    return Notification.create_notification(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        link=link,
        include_school=school is None,
    )
