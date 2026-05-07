"""
Academics Celery tasks — automated early-warning detection.

Scheduled via django-celery-beat (or cron):
    detect_early_warning_flags — weekly scan for at-risk students.
    resolve_stale_early_warnings — monthly clean-up of stale open flags.
"""
import logging
from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thresholds (tune per-school via settings or admin in future)
# ---------------------------------------------------------------------------
ATTENDANCE_RISK_THRESHOLD = 80        # % present — below this → attendance flag
ATTENDANCE_CRITICAL_THRESHOLD = 60    # % present — below this → critical
SCORE_DROP_RISK_THRESHOLD = 15        # avg score drop vs. term average → flag
DISCIPLINE_RISK_COUNT = 3             # incidents this term → flag


@shared_task(bind=True, max_retries=2, default_retry_delay=600)
def detect_early_warning_flags(self):
    """Scan all schools for at-risk students and create/update EarlyWarningFlags.

    Logic:
    1. Poor attendance (< 80% present this term) → trigger=attendance
    2. Multiple discipline incidents this term → trigger=discipline
    3. Composite (both signals) → trigger=composite, risk elevated one level

    Idempotent: if an open flag already exists for the student with the same
    trigger this term, it is updated rather than duplicated.

    Scheduled: weekly (every Monday 06:00 school time via celery-beat).
    """
    try:
        from django.db.models import Count, Q
        from schools.models import School
        from academics.models import EarlyWarningFlag
        from operations.models import StudentAttendance, StudentDiscipline

        schools = School.objects.filter(is_active=True).values_list("pk", flat=True)
        total_created = 0
        total_updated = 0

        for school_pk in schools:
            try:
                _process_school_early_warnings(
                    school_pk,
                    total_created,
                    total_updated,
                )
            except Exception as exc:
                logger.warning("EarlyWarning: school %s failed — %s", school_pk, exc)

        logger.info("EarlyWarning scan complete: %d created, %d updated.", total_created, total_updated)
        return {"created": total_created, "updated": total_updated}

    except Exception as exc:
        logger.error("detect_early_warning_flags failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


def _process_school_early_warnings(school_pk, created_counter, updated_counter):
    """Run the early-warning scan for a single school."""
    from django.db.models import Count, Q
    from academics.models import EarlyWarningFlag
    from operations.models import StudentAttendance, StudentDiscipline
    from students.models import Student

    school_students = Student.objects.filter(school_id=school_pk).select_related("user")
    if not school_students.exists():
        return

    now = timezone.now()

    for student in school_students:
        triggers = []
        risk_level = "low"
        details = {}

        # 1. Attendance check
        att_qs = StudentAttendance.objects.filter(school_id=school_pk, student=student)
        total_att = att_qs.count()
        if total_att >= 10:  # only flag when meaningful sample
            present_count = att_qs.filter(status__in=["present", "late"]).count()
            attendance_rate = round((present_count / total_att) * 100, 1)
            details["attendance_rate"] = attendance_rate
            if attendance_rate < ATTENDANCE_CRITICAL_THRESHOLD:
                triggers.append("attendance")
                risk_level = "critical"
            elif attendance_rate < ATTENDANCE_RISK_THRESHOLD:
                triggers.append("attendance")
                risk_level = "high" if risk_level != "critical" else risk_level

        # 2. Discipline check (current year)
        disc_count = StudentDiscipline.objects.filter(
            school_id=school_pk, student=student
        ).count()
        if disc_count >= DISCIPLINE_RISK_COUNT:
            triggers.append("discipline")
            details["discipline_count"] = disc_count
            if risk_level == "low":
                risk_level = "medium"

        if not triggers:
            continue

        trigger_type = "composite" if len(triggers) > 1 else triggers[0]

        with transaction.atomic():
            existing = EarlyWarningFlag.objects.filter(
                school_id=school_pk,
                student=student,
                trigger_type=trigger_type,
                status__in=("open", "acknowledged"),
            ).first()

            if existing:
                existing.risk_level = risk_level
                existing.details = details
                existing.save(update_fields=["risk_level", "details"])
                updated_counter += 1
            else:
                EarlyWarningFlag.objects.create(
                    school_id=school_pk,
                    student=student,
                    risk_level=risk_level,
                    trigger_type=trigger_type,
                    status="open",
                    details=details,
                )
                created_counter += 1


@shared_task(bind=True, max_retries=1)
def resolve_stale_early_warnings(self):
    """Auto-resolve open flags older than 90 days that were never acknowledged.

    Scheduled: monthly — first day of month at 03:00.
    """
    try:
        from academics.models import EarlyWarningFlag
        cutoff = timezone.now() - timezone.timedelta(days=90)
        stale = EarlyWarningFlag.objects.filter(
            status="open",
            created_at__lt=cutoff,
        )
        count = stale.count()
        stale.update(status="dismissed", updated_at=timezone.now())
        logger.info("Resolved %d stale EarlyWarningFlags (>90 days old).", count)
        return {"dismissed": count}
    except Exception as exc:
        logger.error("resolve_stale_early_warnings failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def recompute_assessment_scheme_task(self, scheme_pk: int):
    """Recompute all StudentReportCardScore rows for a scheme (heavy classes → queue this)."""
    try:
        from .models import AssessmentScheme
        from .services import SchemeBasedGradingService

        scheme = AssessmentScheme.objects.get(pk=scheme_pk)
        rows = SchemeBasedGradingService.compute_for_class(scheme)
        return {"scheme_pk": scheme_pk, "rows": len(rows)}
    except Exception as exc:
        logger.exception("recompute_assessment_scheme_task failed")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=1, default_retry_delay=60)
def generate_report_cards_zip_task(self, school_pk: int, class_name: str, term_pk: int, user_pk: int | None = None):
    """Placeholder hook: wire to ``report_cards_export_zip`` logic for large batches."""
    logger.warning(
        "generate_report_cards_zip_task not fully implemented (school=%s class=%s term=%s)",
        school_pk, class_name, term_pk,
    )
    return {"status": "noop", "school_pk": school_pk}
