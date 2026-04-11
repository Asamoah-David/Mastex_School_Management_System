"""In-app notifications for admission pipeline changes (admins + guardians)."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


def admission_track_path(public_reference: str) -> str:
    base = reverse("operations:admission_track")
    return f"{base}?{urlencode({'ref': public_reference.strip()})}"


def _admin_recipient_ids(school):
    from accounts.models import User

    if not school:
        return []
    return list(
        User.objects.filter(
            school=school,
            role__in=("school_admin", "deputy_head", "admission_officer"),
            is_active=True,
        ).values_list("id", flat=True)
    )


def _resolve_guardian_user(application):
    """Parent user linked to enrolled student, or parent account matching application email."""
    from accounts.models import User

    if application.created_student_id:
        st = application.created_student
        if st and st.parent_id:
            return st.parent
    email = (application.parent_email or "").strip()
    if email and application.school_id:
        return User.objects.filter(
            role="parent",
            school_id=application.school_id,
            email__iexact=email,
            is_active=True,
        ).first()
    return None


def dispatch_admission_notifications(application, *, created: bool, old_status: str | None) -> None:
    """
    Notify school staff of new applications and any status change.
    Notify guardian (in-app) when status changes if we can resolve a parent User.
    """
    if not application.school_id:
        return

    from django.core.cache import cache
    from notifications.models import Notification

    admin_ids = _admin_recipient_ids(application.school)
    school_name = application.school.name if application.school else ""

    if created:
        if not admin_ids:
            return
        title = f"[{school_name}] New admission application"
        message = f"{application.first_name} {application.last_name} applied for {application.class_applied_for}."
        link = reverse("operations:admission_detail", args=[application.pk])
        Notification.objects.bulk_create(
            [
                Notification(
                    user_id=uid,
                    title=title,
                    message=message,
                    notification_type="info",
                    link=link,
                )
                for uid in admin_ids
            ]
        )
        for uid in admin_ids:
            cache.delete(f"notif_count:{uid}")
        return

    if old_status == application.status:
        return

    if admin_ids:
        title = f"[{school_name}] Admission status updated"
        message = (
            f"{application.first_name} {application.last_name} ({application.public_reference}): "
            f"{application.get_status_display()}."
        )
        link = reverse("operations:admission_detail", args=[application.pk])
        Notification.objects.bulk_create(
            [
                Notification(
                    user_id=uid,
                    title=title,
                    message=message,
                    notification_type="info",
                    link=link,
                )
                for uid in admin_ids
            ]
        )
        for uid in admin_ids:
            cache.delete(f"notif_count:{uid}")

    guardian = _resolve_guardian_user(application)
    if guardian:
        track = admission_track_path(application.public_reference)
        Notification.create_notification(
            guardian,
            f"Application {application.public_reference}",
            f"Status is now: {application.get_status_display()}.",
            notification_type="info",
            link=track,
            include_school=True,
        )

    phone = (application.parent_phone or "").strip()
    if (
        phone
        and getattr(settings, "ADMISSION_STATUS_SMS_ENABLED", True)
        and getattr(settings, "MNOTIFY_API_KEY", "")
    ):
        try:
            from messaging.utils import send_sms
            from operations.admission_sms import admission_status_change_message

            body = admission_status_change_message(
                school_name,
                application.public_reference,
                application.get_status_display(),
            )
            send_sms(phone, body)
        except Exception:
            logger.warning("Admission status SMS failed", exc_info=True)
