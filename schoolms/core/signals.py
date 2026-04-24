"""
Notification signal handlers.

Wire key model events (result saved, fee assigned, absence decided, admission
decided) to in-app notifications so parents/students/admins stay informed
without polling.
"""
import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _notify(user, title, message, notification_type="info", link=None):
    """Safe wrapper around the notification helper."""
    try:
        from notifications.views import send_notification
        send_notification(user, title, message, notification_type=notification_type, link=link)
    except Exception:
        logger.warning("Failed to deliver notification to user %s", user, exc_info=True)


@receiver(post_save, sender="academics.Result")
def notify_result_saved(sender, instance, created, **kwargs):
    """Notify the student's parent when a result is created or updated."""
    if not instance.student:
        return
    parent = getattr(instance.student, "parent", None)
    if not parent:
        return
    student_name = instance.student.user.get_full_name() if instance.student.user else str(instance.student)
    subject_name = str(instance.subject) if instance.subject else "a subject"
    verb = "posted" if created else "updated"
    _notify(
        parent,
        f"Result {verb}: {subject_name}",
        f"{student_name}'s result for {subject_name} has been {verb}.",
        notification_type="result",
        link="/portal/",
    )


@receiver(post_save, sender="finance.Fee")
def notify_fee_assigned(sender, instance, created, **kwargs):
    """Notify parent when a new fee is assigned to their child."""
    if not created or not instance.student:
        return
    parent = getattr(instance.student, "parent", None)
    if not parent:
        return
    student_name = instance.student.user.get_full_name() if instance.student.user else str(instance.student)
    _notify(
        parent,
        "New Fee Assigned",
        f"A fee of GHS {instance.amount} has been assigned for {student_name}.",
        notification_type="payment",
        link="/finance/parent-fees/",
    )


@receiver(post_save, sender="students.AbsenceRequest")
def notify_absence_decision(sender, instance, created, **kwargs):
    """Notify submitter when an absence request is approved or rejected."""
    if created:
        return
    if instance.status not in ("approved", "rejected"):
        return
    student_name = instance.student.user.get_full_name() if instance.student and instance.student.user else "Student"
    recipient = instance.submitted_by or (instance.student.parent if instance.student else None)
    if not recipient:
        return
    end = instance.end_date or instance.date
    span = f"{instance.date}" if end == instance.date else f"{instance.date}–{end}"
    _notify(
        recipient,
        f"Absence Request {instance.get_status_display()}",
        f"The absence request for {student_name} for {span} has been {instance.status}.",
        notification_type="attendance",
        link="/students/absence/children/",
    )


@receiver(pre_save, sender="operations.AdmissionApplication")
def admission_cache_previous_status(sender, instance, **kwargs):
    if instance.pk:
        from operations.models import AdmissionApplication

        try:
            prev = AdmissionApplication.objects.only("status").get(pk=instance.pk)
            instance._prev_admission_status = prev.status
        except AdmissionApplication.DoesNotExist:
            instance._prev_admission_status = None
    else:
        instance._prev_admission_status = None


@receiver(post_save, sender="operations.AdmissionApplication")
def notify_admission_pipeline(sender, instance, created, **kwargs):
    """Admins + resolvable guardians: new application and every status transition."""
    from operations.admission_notifications import dispatch_admission_notifications

    old = getattr(instance, "_prev_admission_status", None)
    dispatch_admission_notifications(instance, created=created, old_status=old)


def _bulk_notify_user_ids(user_ids, title, message, *, notification_type="info", link=""):
    """Cap bulk in-app notifications to protect DB and task time."""
    from django.conf import settings
    from django.core.cache import cache
    from notifications.models import Notification

    cap = getattr(settings, "BULK_IN_APP_NOTIFICATION_CAP", 1500)
    raw = []
    for x in user_ids:
        try:
            raw.append(int(x))
        except (TypeError, ValueError):
            continue
    ids = list(dict.fromkeys(raw))[:cap]
    if not ids:
        return
    Notification.objects.bulk_create(
        [
            Notification(
                user_id=uid,
                title=str(title)[:255],
                message=str(message)[:2000],
                notification_type=notification_type,
                link=str(link or "")[:500],
            )
            for uid in ids
        ]
    )
    for uid in ids:
        cache.delete(f"notif_count:{uid}")


def _bulk_notify_by_link_groups(user_id_to_link, title, message, *, notification_type="info"):
    """Send the same title/body to many users; group by link to keep bulk_create efficient."""
    from collections import defaultdict

    buckets = defaultdict(list)
    for uid, lk in user_id_to_link.items():
        try:
            buckets[str(lk or "")].append(int(uid))
        except (TypeError, ValueError):
            continue
    for lk, uids in buckets.items():
        _bulk_notify_user_ids(uids, title, message, notification_type=notification_type, link=lk)


def _active_parent_ids_for_school(school_id):
    from students.models import Student

    return list(
        Student.objects.filter(school_id=school_id, status="active")
        .exclude(parent_id__isnull=True)
        .values_list("parent_id", flat=True)
        .distinct()
    )


def _active_student_user_ids_for_school(school_id):
    from students.models import Student

    return list(
        Student.objects.filter(school_id=school_id, status="active")
        .values_list("user_id", flat=True)
        .distinct()
    )


def _notify_parent_fee_balance_after_credit(fee_or_pk, credited_amount):
    """Tell the parent the credited amount and remaining balance (single in-app message)."""
    from finance.models import Fee

    pk = fee_or_pk.pk if getattr(fee_or_pk, "pk", None) else fee_or_pk
    fee = (
        Fee.objects.select_related("student", "student__user", "student__parent")
        .filter(pk=pk)
        .first()
    )
    if not fee or not fee.student_id:
        return
    parent = getattr(fee.student, "parent", None)
    if not parent:
        return
    fee.refresh_from_db()
    remaining = float(fee.amount) - float(fee.amount_paid or 0)
    student_name = fee.student.user.get_full_name() if fee.student.user else str(fee.student)
    try:
        paid = float(credited_amount)
    except (TypeError, ValueError):
        paid = 0.0
    if remaining <= 0.009:
        _notify(
            parent,
            "Fee fully paid",
            f"Payment of GHS {paid:.2f} recorded for {student_name}. This fee is now fully paid.",
            notification_type="payment",
            link="/finance/parent-fees/",
        )
    else:
        _notify(
            parent,
            "Fee payment received",
            f"GHS {paid:.2f} credited for {student_name}. Remaining balance: GHS {remaining:.2f}.",
            notification_type="payment",
            link="/finance/parent-fees/",
        )


@receiver(pre_save, sender="finance.Fee")
def fee_cache_amount_paid_for_parent_notify(sender, instance, **kwargs):
    if not instance.pk:
        instance._fee_prev_amount_paid_notify = None
        return
    from finance.models import Fee

    prev = Fee.objects.filter(pk=instance.pk).values_list("amount_paid", flat=True).first()
    instance._fee_prev_amount_paid_notify = prev


@receiver(post_save, sender="finance.Fee")
def notify_parent_on_fee_balance_credited_without_payment_row(sender, instance, created, **kwargs):
    """Staff actions that change amount_paid without a FeePayment row (mark paid / partial)."""
    if created:
        return
    prev = getattr(instance, "_fee_prev_amount_paid_notify", None)
    if prev is None:
        return
    try:
        new_paid = float(instance.amount_paid or 0)
        old_paid = float(prev)
    except (TypeError, ValueError):
        return
    if new_paid <= old_paid + 0.0001:
        return
    _notify_parent_fee_balance_after_credit(instance, new_paid - old_paid)


@receiver(post_save, sender="finance.FeePayment")
def notify_parent_fee_balance_after_payment(sender, instance, **kwargs):
    """After a completed payment row, tell the parent the remaining balance (if any)."""
    if instance.status != "completed":
        return
    _notify_parent_fee_balance_after_credit(instance.fee, instance.amount)


@receiver(post_save, sender="operations.SchoolEvent")
def notify_guardians_new_school_event(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.target_audience not in ("all", "parents"):
        return
    from django.urls import reverse

    ids = _active_parent_ids_for_school(instance.school_id)
    if not ids:
        return
    link = reverse("operations:school_event_detail", args=[instance.pk])
    sn = instance.school.name if instance.school else ""
    _bulk_notify_user_ids(
        ids,
        f"[{sn}] Event: {instance.title[:120]}",
        (instance.description or "")[:900],
        notification_type="info",
        link=link,
    )


@receiver(post_save, sender="operations.AcademicCalendar")
def notify_guardians_calendar_entry(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.event_type not in ("holiday", "term_start", "term_end", "exam_start", "exam_end"):
        return
    from django.urls import reverse

    ids = _active_parent_ids_for_school(instance.school_id)
    if not ids:
        return
    link = reverse("operations:services_hub")
    sn = instance.school.name if instance.school else ""
    when = f"{instance.start_date}"
    if instance.end_date:
        when += f" – {instance.end_date}"
    _bulk_notify_user_ids(
        ids,
        f"[{sn}] Calendar: {instance.title[:100]}",
        f"{instance.get_event_type_display()} · {when}. {(instance.description or '')[:500]}",
        notification_type="info",
        link=link,
    )


@receiver(post_save, sender="operations.Announcement")
def notify_audience_new_announcement(sender, instance, created, **kwargs):
    if not created:
        return
    from django.urls import reverse
    from accounts.models import User, STAFF_ROLES

    sn = instance.school.name if instance.school else ""
    title = f"[{sn}] {instance.title[:160]}"
    body = (instance.content or "")[:1900]
    portal_link = reverse("students:announcements_list")
    staff_link = reverse("operations:announcement_list")

    if instance.target_audience == "all":
        links = {}
        for uid in _active_parent_ids_for_school(instance.school_id):
            links[uid] = portal_link
        for uid in _active_student_user_ids_for_school(instance.school_id):
            links.setdefault(uid, portal_link)
        staff_ids = User.objects.filter(
            school_id=instance.school_id, role__in=STAFF_ROLES, is_active=True
        ).values_list("id", flat=True)
        for uid in staff_ids:
            links[uid] = staff_link
        _bulk_notify_by_link_groups(links, title, body, notification_type="info")
        return

    if instance.target_audience == "parents":
        _bulk_notify_user_ids(
            _active_parent_ids_for_school(instance.school_id),
            title,
            body,
            notification_type="info",
            link=portal_link,
        )
    elif instance.target_audience == "students":
        _bulk_notify_user_ids(
            _active_student_user_ids_for_school(instance.school_id),
            title,
            body,
            notification_type="info",
            link=portal_link,
        )
    elif instance.target_audience == "staff":
        staff_ids = User.objects.filter(
            school_id=instance.school_id, role__in=STAFF_ROLES, is_active=True
        ).values_list("id", flat=True)
        _bulk_notify_user_ids(
            list(staff_ids),
            title,
            body,
            notification_type="info",
            link=staff_link,
        )


@receiver(post_save, sender="operations.PTMeetingBooking")
def notify_pt_meeting_booking(sender, instance, created, **kwargs):
    """Notify parent and the meeting organiser when a PT meeting slot is booked."""
    if not created:
        return
    try:
        from django.urls import reverse
        meeting = instance.meeting
        parent = instance.parent
        student_name = instance.student.user.get_full_name() if instance.student and instance.student.user else "student"
        meeting_date = meeting.meeting_date.strftime("%d %b %Y %H:%M") if meeting.meeting_date else "TBD"
        link = reverse("operations:pt_meeting_detail", args=[meeting.pk])

        _notify(
            parent,
            "PT Meeting Booked",
            f"Your slot for {student_name} has been confirmed for {meeting_date}.",
            notification_type="info",
            link=link,
        )

        organiser = getattr(meeting, "created_by", None)
        if organiser and organiser != parent:
            _notify(
                organiser,
                "New PT Meeting Booking",
                f"{parent.get_full_name() or parent.username} booked a slot for {student_name} ({meeting_date}).",
                notification_type="info",
                link=link,
            )
    except Exception:
        pass
