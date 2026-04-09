"""
Async notification signals for academics events.

SMS/email delivery is offloaded to a background thread so the request
completes immediately. If a proper task queue (Celery) is available later,
replace the thread pool with `.delay()` calls.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from django.db.models.signals import post_save
from django.dispatch import receiver
from academics.models import Homework, Result

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


def _send_homework_sms(school_id, class_name, title, due_date, subject_name):
    """Background: send SMS to all students in a class about new homework."""
    try:
        from messaging.utils import send_sms
        from students.models import Student

        phones = list(
            Student.objects.filter(school_id=school_id, class_name=class_name)
            .select_related("user")
            .values_list("user__phone", flat=True)
        )
        message = f"New Homework: {title} for {class_name}. Due: {due_date}. Subject: {subject_name}"
        for phone in phones:
            if phone:
                try:
                    send_sms(phone, message)
                except Exception:
                    logger.debug("SMS failed for %s", phone)
    except Exception:
        logger.warning("Homework SMS batch failed", exc_info=True)


def _send_result_sms(student_name, score, subject_name, exam_type_name, parent_phone):
    """Background: send a single SMS to a parent about a new result."""
    try:
        from messaging.utils import send_sms
        message = f"Result Update: {student_name} scored {score}% in {subject_name} ({exam_type_name})"
        send_sms(parent_phone, message)
    except Exception:
        logger.debug("Result SMS to %s failed", parent_phone)


@receiver(post_save, sender=Homework)
def homework_created_notification(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        _executor.submit(
            _send_homework_sms,
            instance.school_id,
            instance.class_name,
            instance.title,
            str(instance.due_date),
            instance.subject.name if instance.subject_id else "",
        )
    except Exception:
        logger.warning("Could not enqueue homework SMS", exc_info=True)


@receiver(post_save, sender=Result)
def result_uploaded_notification(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        student = instance.student
        parent = getattr(student, "parent", None)
        if not parent or not parent.phone:
            return
        _executor.submit(
            _send_result_sms,
            student.user.get_full_name() if hasattr(student, "user") else str(student),
            instance.score,
            str(instance.subject) if instance.subject_id else "",
            str(instance.exam_type) if instance.exam_type_id else "",
            parent.phone,
        )
    except Exception:
        logger.warning("Could not enqueue result SMS", exc_info=True)
