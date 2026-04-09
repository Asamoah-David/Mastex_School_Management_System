"""
Notification signal handlers.

Wire key model events (result saved, fee assigned, absence decided, admission
decided) to in-app notifications so parents/students/admins stay informed
without polling.
"""
import logging
from django.db.models.signals import post_save
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
    _notify(
        recipient,
        f"Absence Request {instance.get_status_display()}",
        f"The absence request for {student_name} on {instance.date} has been {instance.status}.",
        notification_type="attendance",
        link="/students/absence/children/",
    )


@receiver(post_save, sender="operations.AdmissionApplication")
def notify_admission_decision(sender, instance, created, **kwargs):
    """Notify school admins when a new application arrives; notify applicant on decision."""
    if not instance.school:
        return

    from accounts.models import User
    from notifications.models import Notification

    admin_ids = list(
        User.objects.filter(school=instance.school, role="school_admin")
        .values_list("id", flat=True)
    )
    if not admin_ids:
        return

    if created:
        title = f"[{instance.school.name}] New Admission Application"
        message = f"{instance.first_name} {instance.last_name} applied for {instance.class_applied_for}."
        link = "/operations/admission/"
    elif instance.status in ("approved", "rejected"):
        title = f"[{instance.school.name}] Application {instance.get_status_display()}"
        message = f"Application from {instance.first_name} {instance.last_name} has been {instance.status}."
        link = f"/operations/admission/{instance.pk}/"
    else:
        return

    Notification.objects.bulk_create([
        Notification(
            user_id=uid, title=title, message=message,
            notification_type="info", link=link,
        )
        for uid in admin_ids
    ])
    from django.core.cache import cache
    for uid in admin_ids:
        cache.delete(f"notif_count:{uid}")
