"""
Academics signals: async notifications and result-summary maintenance.

``AssessmentScore`` / ``ExamScore`` / ``Result`` (with a term) saves and deletes enqueue a deduplicated
``StudentResultSummary`` reconcile on transaction commit (bulk uploads, admin,
and normal ORM paths). ``QuerySet.update`` and ``bulk_create`` do not fire these
signals; bulk **Result** creation in ``result_upload`` schedules reconcile via
``on_commit``.

SMS/email delivery is offloaded to a background thread so the request
completes immediately. If a proper task queue (Celery) is available later,
replace the thread pool with `.delay()` calls.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from academics.models import AssessmentScore, ExamScore, Homework, Result

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


def _queue_student_result_summary_refresh(student_id, subject_id, term_id):
    """Queue summary reconciles; flush runs after successful commit.

    Registers ``transaction.on_commit`` on each change. Django drops those
    callbacks on savepoint rollback (e.g. ``TestCase`` teardown), so we avoid
    a separate connection flag that would stick ``True`` if a commit never ran.
    """
    if not student_id or not subject_id or not term_id:
        return
    conn = transaction.get_connection()

    if not hasattr(conn, "_academics_summary_refresh_keys"):
        conn._academics_summary_refresh_keys = set()
    conn._academics_summary_refresh_keys.add((student_id, subject_id, term_id))

    def _flush_summaries():
        conn2 = transaction.get_connection()
        keys = getattr(conn2, "_academics_summary_refresh_keys", None)
        if keys is None:
            return
        conn2._academics_summary_refresh_keys = set()
        if not keys:
            return
        from students.models import Student

        from academics.models import Subject, Term
        from academics.services import GradingService

        for sid, subid, tid in keys:
            try:
                stu = Student.objects.get(pk=sid)
                if not Subject.objects.filter(pk=subid).exists():
                    continue
                subj = Subject.objects.get(pk=subid)
                trm = Term.objects.get(pk=tid)
                GradingService.reconcile_student_subject_term_summary(stu, subj, trm)
            except Exception:
                logger.exception(
                    "StudentResultSummary refresh failed student=%s subject=%s term=%s",
                    sid,
                    subid,
                    tid,
                )

    transaction.on_commit(_flush_summaries, using=conn.alias)


@receiver(post_save, sender=AssessmentScore)
def assessment_score_queue_summary_refresh(sender, instance, **kwargs):
    _queue_student_result_summary_refresh(
        instance.student_id,
        instance.subject_id,
        instance.term_id,
    )


@receiver(post_delete, sender=AssessmentScore)
def assessment_score_delete_queue_summary_refresh(sender, instance, **kwargs):
    _queue_student_result_summary_refresh(
        instance.student_id,
        instance.subject_id,
        instance.term_id,
    )


@receiver(post_save, sender=ExamScore)
def exam_score_queue_summary_refresh(sender, instance, **kwargs):
    _queue_student_result_summary_refresh(
        instance.student_id,
        instance.subject_id,
        instance.term_id,
    )


@receiver(post_delete, sender=ExamScore)
def exam_score_delete_queue_summary_refresh(sender, instance, **kwargs):
    _queue_student_result_summary_refresh(
        instance.student_id,
        instance.subject_id,
        instance.term_id,
    )


@receiver(post_save, sender=Result)
def result_saved_queue_summary_reconcile(sender, instance, **kwargs):
    """Keep ``StudentResultSummary`` aligned when legacy ``Result`` rows change."""
    if not instance.student_id or not instance.subject_id or not instance.term_id:
        return
    _queue_student_result_summary_refresh(
        instance.student_id,
        instance.subject_id,
        instance.term_id,
    )


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
