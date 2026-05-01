"""
Core Celery tasks — ERP-grade background jobs.

Fix #27: Inventory low-stock alerts
Fix #28: Automated fee payment reminders
"""

import logging
from celery import shared_task
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fix #27 — Inventory low-stock alerts
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_inventory_low_stock_alerts(self):
    """Scan every school's inventory and notify admins of items below min_quantity.

    Scheduled: daily via django-celery-beat.
    """
    try:
        from operations.models.inventory import InventoryItem
        from schools.models import School
        from notifications.models import Notification

        low_items = (
            InventoryItem.objects.filter(quantity__lte=models.F("min_quantity"))
            .select_related("school", "category")
            .order_by("school", "name")
        )

        alerts_by_school: dict = {}
        for item in low_items:
            alerts_by_school.setdefault(item.school_id, {"school": item.school, "items": []})
            alerts_by_school[item.school_id]["items"].append(item)

        created = 0
        for school_id, data in alerts_by_school.items():
            school = data["school"]
            items = data["items"]
            message = (
                f"⚠ Low stock alert: {len(items)} item(s) below minimum threshold — "
                + ", ".join(f"{i.name} ({i.quantity}/{i.min_quantity})" for i in items[:5])
                + (f" (+{len(items)-5} more)" if len(items) > 5 else "")
            )
            from accounts.models import User
            admins = list(User.objects.filter(school=school, role__in=["school_admin", "bursar"]).values_list("id", flat=True))
            to_create = [
                Notification(
                    user_id=admin_id,
                    school=school,
                    notification_type="inventory_alert",
                    title=f"[{school.name}] Low Stock Alert",
                    message=message[:500],
                    is_read=False,
                )
                for admin_id in admins
            ]
            Notification.objects.bulk_create(to_create, ignore_conflicts=True)
            created += len(to_create)

        logger.info("inventory_low_stock_alerts: %d notifications created", created)
        return {"alerts_created": created}

    except Exception as exc:
        logger.exception("inventory_low_stock_alerts failed")
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Fix #28 — Automated fee payment reminders
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=600)
def send_fee_payment_reminders(self, days_before_due: int = 3):
    """Send SMS/in-app reminders to parents of students with outstanding fees.

    Scheduled: daily via django-celery-beat.
    Args:
        days_before_due: Notify this many days before fee.due_date.
    """
    try:
        from django.db.models import Q, F
        from datetime import timedelta
        from finance.models import Fee
        from services.sms_service import SMSService
        from notifications.models import Notification

        from students.models import StudentGuardian

        today = timezone.localdate()
        due_cutoff = today + timedelta(days=days_before_due)

        outstanding = (
            Fee.objects.filter(
                Q(paid=False) | Q(amount_paid__lt=F("amount")),
                is_active=True,
                due_date=due_cutoff,
            )
            .select_related("student", "student__user", "student__school")
        )

        sent_sms = 0
        sent_notif = 0
        for fee in outstanding:
            student = fee.student
            school = student.school
            balance = fee.amount - (fee.amount_paid or 0)
            student_name = student.user.get_full_name()

            msg = (
                f"[{school.name}] Fee reminder: GHS {balance:.2f} due on "
                f"{fee.due_date} for {student_name}. Please pay promptly."
            )

            # Notify all primary guardians (StudentGuardian) + fall back to legacy parent
            guardian_users = list(
                StudentGuardian.objects.filter(student=student, is_primary=True)
                .select_related("guardian")
                .values_list("guardian_id", "guardian__phone")
            )
            if not guardian_users and hasattr(student, "parent_id") and student.parent_id:
                legacy = student.parent
                if legacy:
                    guardian_users = [(legacy.pk, getattr(legacy, "phone", None))]

            for guardian_id, guardian_phone in guardian_users:
                if guardian_phone:
                    try:
                        svc = SMSService(school=school)
                        svc.send(numbers=[guardian_phone], message=msg)
                        sent_sms += 1
                    except Exception:
                        logger.warning("SMS reminder failed for fee %s guardian %s", fee.pk, guardian_id)

                Notification.objects.get_or_create(
                    user_id=guardian_id,
                    notification_type="fee_reminder",
                    message=msg[:500],
                    defaults={"school": school, "title": f"Fee Reminder – {student_name}", "is_read": False},
                )
                sent_notif += 1

        logger.info(
            "fee_reminders: %d SMS, %d in-app (days_before=%d)",
            sent_sms, sent_notif, days_before_due,
        )
        return {"sms": sent_sms, "in_app": sent_notif}

    except Exception as exc:
        logger.exception("fee_payment_reminders failed")
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Fix #35 — Paystack settlement reconciliation task
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def reconcile_paystack_settlements(self):
    """Reconcile all unreconciled PaystackSettlement rows against FeePayment records."""
    try:
        from finance.models import PaystackSettlement
        qs = PaystackSettlement.objects.filter(reconciled=False)
        count = 0
        for settlement in qs:
            try:
                settlement.reconcile()
                count += 1
            except Exception:
                logger.warning("Reconciliation failed for settlement %s", settlement.pk)
        logger.info("reconcile_paystack_settlements: %d reconciled", count)
        return {"reconciled": count}
    except Exception as exc:
        logger.exception("reconcile_paystack_settlements failed")
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Fix #26 — Rebuild transcripts when results are published
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def rebuild_student_transcript(self, student_id: int, academic_year_id: int, term_id: int = None):
    """Rebuild a single student transcript after result publication."""
    try:
        from students.models import Student
        from academics.models import AcademicYear, Term, StudentTranscript
        student = Student.objects.get(pk=student_id)
        academic_year = AcademicYear.objects.get(pk=academic_year_id)
        term = Term.objects.get(pk=term_id) if term_id else None
        StudentTranscript.rebuild_for(student, academic_year, term)
    except Exception as exc:
        logger.exception("rebuild_student_transcript failed student=%s", student_id)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Fix #24 — Leave balance rollover at year end
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2)
def rollover_leave_balances(self, from_year: str = None, to_year: str = None):
    """Carry over unused leave days (up to policy max) into the new academic year.

    from_year/to_year default to the current and next calendar year when not
    supplied (e.g. from the beat schedule which passes no kwargs).
    """
    try:
        from accounts.hr_models import LeaveBalance, LeavePolicy
        from decimal import Decimal
        from django.utils import timezone as _tz

        if not from_year or not to_year:
            now = _tz.now()
            from_year = from_year or str(now.year)
            to_year = to_year or str(now.year + 1)

        for balance in LeaveBalance.objects.filter(academic_year=from_year).select_related("user", "school"):
            try:
                policy = LeavePolicy.objects.filter(
                    school=balance.school, leave_type=balance.leave_type, is_active=True
                ).first()
                max_carry = Decimal(str(policy.carry_over_max_days)) if policy else Decimal("0")
                carry = min(balance.remaining, max_carry)
                LeaveBalance.objects.update_or_create(
                    school=balance.school,
                    user=balance.user,
                    leave_type=balance.leave_type,
                    academic_year=to_year,
                    defaults={
                        "allocated_days": Decimal(str(policy.days_per_year)) if policy else Decimal("0"),
                        "carried_over": carry,
                        "used_days": Decimal("0"),
                    },
                )
            except Exception:
                logger.warning("Leave rollover failed for balance %s", balance.pk)

        logger.info("leave_balance_rollover: %s → %s complete", from_year, to_year)
    except Exception as exc:
        logger.exception("rollover_leave_balances failed")
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Fix #34 — GDPR data export generation
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def generate_gdpr_export(self, export_request_id: int):
    """Collect all personal data for a user and store as a JSON file.

    Marks the GDPRExportRequest as ready when complete.
    """
    try:
        import json
        from audit.models import GDPRExportRequest
        from django.utils import timezone as _tz

        req = GDPRExportRequest.objects.select_related("subject_user", "school").get(pk=export_request_id)
        req.status = "processing"
        req.save(update_fields=["status"])

        user = req.subject_user
        payload = {
            "exported_at": _tz.now().isoformat(),
            "user": {
                "id": user.pk,
                "username": user.username,
                "email": user.email or "",
                "first_name": user.first_name,
                "last_name": user.last_name,
                "date_joined": user.date_joined.isoformat() if user.date_joined else None,
                "role": getattr(user, "role", ""),
            },
        }

        # Student record
        try:
            from students.models import Student
            s = Student.objects.filter(user=user).select_related("school", "school_class").first()
            if s:
                payload["student"] = {
                    "admission_number": s.admission_number,
                    "class_name": s.class_name,
                    "status": s.status,
                    "date_enrolled": s.date_enrolled.isoformat() if s.date_enrolled else None,
                }
        except Exception:
            pass

        # Fee payments
        try:
            from finance.models import FeePayment
            payments = list(
                FeePayment.objects.filter(fee__student__user=user)
                .values("id", "amount", "amount_paid", "status", "paid_at", "created_at")
            )
            for p in payments:
                if p.get("paid_at"):
                    p["paid_at"] = str(p["paid_at"])
                if p.get("created_at"):
                    p["created_at"] = str(p["created_at"])
            payload["fee_payments"] = payments
        except Exception:
            pass

        # Audit logs
        try:
            from audit.models import AuditLog
            logs = list(
                AuditLog.objects.filter(user=user)
                .values("action", "model_name", "timestamp", "ip_address")[:200]
            )
            for l in logs:
                if l.get("timestamp"):
                    l["timestamp"] = str(l["timestamp"])
            payload["audit_logs"] = logs
        except Exception:
            pass

        req.mark_ready(export_payload=payload)
        logger.info("generate_gdpr_export: completed for user %s", user.pk)

    except Exception as exc:
        logger.exception("generate_gdpr_export failed for request %s", export_request_id)
        try:
            from audit.models import GDPRExportRequest
            GDPRExportRequest.objects.filter(pk=export_request_id).update(
                status="failed", error_message=str(exc)
            )
        except Exception:
            pass
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# M-7 — Mark overdue FeeInstallmentPlans
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def mark_overdue_installments(self):
    """Transition pending FeeInstallmentPlan rows to overdue when due_date passes."""
    try:
        from django.utils import timezone as _tz
        from finance.models import FeeInstallmentPlan
        from notifications.models import Notification
        today = _tz.localdate()
        overdue_qs = FeeInstallmentPlan.objects.filter(
            due_date__lt=today,
            status="pending",
        ).select_related("school", "fee__student__user")
        count = overdue_qs.count()
        overdue_qs.update(status="overdue")

        notifs = []
        for plan in FeeInstallmentPlan.objects.filter(
            due_date__lt=today,
            status="overdue",
        ).select_related("school", "fee__student"):
            student = plan.fee.student
            school = plan.school
            try:
                primary = (
                    student.guardians.filter(is_primary=True)
                    .values_list("guardian_id", flat=True)
                    .first()
                )
                if primary:
                    notifs.append(Notification(
                        user_id=primary,
                        school=school,
                        title=f"Installment Overdue – {student}",
                        message=f"An installment of GHS {plan.amount_due} was due on {plan.due_date} and is now overdue.",
                        notification_type="installment_overdue",
                        is_read=False,
                    ))
            except Exception:
                pass
        if notifs:
            Notification.objects.bulk_create(notifs, ignore_conflicts=True)

        logger.info("mark_overdue_installments: %d marked overdue, %d notifs", count, len(notifs))
        return {"overdue": count, "notifs": len(notifs)}
    except Exception as exc:
        logger.exception("mark_overdue_installments failed")
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# M-8 — Auto-expire StaffContracts past end_date
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def auto_expire_staff_contracts(self):
    """Mark StaffContracts with end_date in the past as expired and notify admins."""
    try:
        from django.utils import timezone as _tz
        from accounts.hr_models import StaffContract
        from notifications.models import Notification
        today = _tz.localdate()
        expired = StaffContract.objects.filter(
            end_date__lt=today,
            status="active",
        ).select_related("school", "user")
        count = expired.count()
        for contract in expired:
            contract.status = "expired"
            contract.save(update_fields=["status"])
            from accounts.models import User
            admins = User.objects.filter(school=contract.school, role="school_admin").values_list("id", flat=True)
            Notification.objects.bulk_create([
                Notification(
                    user_id=admin_id,
                    school=contract.school,
                    title=f"Staff Contract Expired – {contract.user.get_full_name()}",
                    message=f"The contract for {contract.user.get_full_name()} expired on {contract.end_date}.",
                    notification_type="contract_expiry",
                    is_read=False,
                )
                for admin_id in admins
            ], ignore_conflicts=True)
        logger.info("auto_expire_staff_contracts: %d expired", count)
        return {"expired": count}
    except Exception as exc:
        logger.exception("auto_expire_staff_contracts failed")
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# E-3 — Auto-generate Fee rows from FeeStructure at term start
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def generate_fees_from_structures(self, term_id: int):
    """Stamp Fee records for all active students in a school based on FeeStructure rows for the given Term.

    Call this task when a new Term becomes is_current=True (via signal or admin action).
    """
    try:
        from academics.models import Term
        from finance.models import Fee, FeeStructure
        from students.models import Student
        term = Term.objects.select_related("school").get(pk=term_id)
        school = term.school
        structures = FeeStructure.objects.filter(school=school, is_active=True)
        students = Student.objects.filter(school=school, status="active").only("id")
        created = 0
        for structure in structures:
            for student in students:
                _, was_created = Fee.objects.get_or_create(
                    school=school,
                    student=student,
                    fee_structure=structure,
                    term=term,
                    defaults={
                        "amount": structure.amount,
                        "due_date": term.end_date,
                        "description": f"{structure.name} – {term.name}",
                    },
                )
                if was_created:
                    created += 1
        logger.info("generate_fees_from_structures: %d fees created for term %s", created, term_id)
        return {"created": created}
    except Exception as exc:
        logger.exception("generate_fees_from_structures failed for term %s", term_id)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# E-10 — Webhook delivery retry worker
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def retry_failed_webhook_deliveries(self):
    """Retry WebhookDeliveryAttempt rows that failed and have a next_retry_at <= now."""
    try:
        from django.utils import timezone as _tz
        from integrations.models import WebhookDeliveryAttempt
        import json, hmac, hashlib, requests as _req
        now = _tz.now()
        pending = WebhookDeliveryAttempt.objects.filter(
            status="failed",
            next_retry_at__lte=now,
            attempt_count__lte=5,
        ).select_related("endpoint")
        retried = 0
        for attempt in pending:
            endpoint = attempt.endpoint
            try:
                payload_str = json.dumps(attempt.payload or {})
                sig = hmac.new(
                    endpoint.signing_secret.encode(),
                    payload_str.encode(),
                    hashlib.sha256,
                ).hexdigest()
                resp = _req.post(
                    endpoint.url,
                    data=payload_str,
                    headers={
                        "Content-Type": "application/json",
                        "X-Mastex-Signature": f"sha256={sig}",
                    },
                    timeout=10,
                )
                if resp.ok:
                    attempt.mark_delivered(http_status=resp.status_code)
                    attempt.save(update_fields=["status", "last_http_status", "last_error", "next_retry_at", "delivered_at"])
                else:
                    attempt.attempt_count += 1
                    attempt.mark_failed(
                        message=f"HTTP {resp.status_code}",
                        http_status=resp.status_code,
                        next_retry_at=now + __import__("datetime").timedelta(
                            minutes=2 ** attempt.attempt_count
                        ),
                    )
                    attempt.save(update_fields=["attempt_count", "last_http_status", "last_error", "next_retry_at", "status"])
                retried += 1
            except Exception as e:
                logger.warning("webhook retry failed for attempt %s: %s", attempt.pk, e)
        logger.info("retry_failed_webhook_deliveries: %d processed", retried)
        return {"retried": retried}
    except Exception as exc:
        logger.exception("retry_failed_webhook_deliveries failed")
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# E15 — Subscription auto-expiry
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def auto_expire_subscriptions(self):
    """Mark schools as expired when subscription_end_date has passed the grace period.

    Scheduled: daily via CELERY_BEAT_SCHEDULE.
    """
    try:
        from schools.models import School
        import datetime as _dt
        from django.utils import timezone as _tz
        now = _tz.now()

        expired_qs = School.objects.filter(
            subscription_status__in=["active", "trial"],
            subscription_end_date__isnull=False,
        ).only("id", "subscription_end_date", "subscription_grace_days")

        to_expire = [
            school.pk
            for school in expired_qs
            if now > school.subscription_end_date + _dt.timedelta(days=school.subscription_grace_days)
        ]

        if to_expire:
            updated = School.objects.filter(pk__in=to_expire).update(subscription_status="expired")
            logger.info("auto_expire_subscriptions: %d schools expired", updated)
        return {"expired": len(to_expire)}
    except Exception as exc:
        logger.exception("auto_expire_subscriptions failed")
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# GAP-3 — Annual fixed asset depreciation
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# TASK-2 — Redis-based task deduplication lock
# ---------------------------------------------------------------------------

def _acquire_task_lock(lock_name: str, timeout: int = 3600) -> bool:
    """Try to acquire a distributed task lock via Django cache (Redis or DB).

    Returns True if the lock was acquired (task should run).
    Returns False if another worker already holds the lock (task should skip).
    Uses cache.add() which is atomic: returns True only when the key is NEW.
    """
    from django.core.cache import cache
    key = f"task_lock:{lock_name}"
    acquired = cache.add(key, "1", timeout)
    return bool(acquired)


def _release_task_lock(lock_name: str) -> None:
    from django.core.cache import cache
    cache.delete(f"task_lock:{lock_name}")


# ---------------------------------------------------------------------------
# DB-6 — Purge expired notifications
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def purge_expired_notifications(self):
    """Delete read notifications older than 90 days and any notification past expires_at.

    Runs weekly. Uses a dedup lock so overlapping runs are skipped safely.
    """
    lock = "purge_expired_notifications"
    if not _acquire_task_lock(lock, timeout=3600):
        logger.info("purge_expired_notifications: another worker holds the lock, skipping")
        return {"skipped": True}
    try:
        from notifications.models import Notification
        from django.utils import timezone as _tz
        now = _tz.now()
        cutoff = now - __import__("datetime").timedelta(days=90)
        # Delete read notifications older than 90 days
        deleted_old, _ = Notification.objects.filter(is_read=True, created_at__lt=cutoff).delete()
        # Delete any with explicit expires_at in the past
        deleted_exp, _ = Notification.objects.filter(
            expires_at__isnull=False, expires_at__lt=now
        ).delete()
        total = deleted_old + deleted_exp
        logger.info("purge_expired_notifications: removed %d notifications", total)
        return {"deleted": total}
    except Exception as exc:
        logger.exception("purge_expired_notifications failed")
        raise self.retry(exc=exc)
    finally:
        _release_task_lock(lock)


# ---------------------------------------------------------------------------
# ENH-4 — Attendance early-warning: 3+ consecutive absences
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def flag_attendance_early_warnings(self):
    """Find students with 3+ consecutive absent days and notify their parents and school admin.

    Checks the last 5 school days per school. Only fires one notification per
    student per day to avoid spam (dedup by cache key).
    Scheduled: daily via CELERY_BEAT_SCHEDULE.
    """
    lock = "flag_attendance_early_warnings"
    if not _acquire_task_lock(lock, timeout=82800):  # 23h — won't re-fire same day
        logger.info("flag_attendance_early_warnings: lock held, skipping")
        return {"skipped": True}
    try:
        from django.core.cache import cache
        from django.utils import timezone as _tz
        from operations.models.attendance import StudentAttendance
        from students.models import StudentGuardian
        from notifications.models import Notification
        from schools.models import School
        from accounts.models import User

        today = _tz.localdate()
        notified = 0

        for school in School.objects.filter(is_active=True).iterator(chunk_size=50):
            # Collect last 5 attendance dates for this school
            recent_dates = list(
                StudentAttendance.objects.filter(school=school, date__lte=today)
                .order_by("-date")
                .values_list("date", flat=True)
                .distinct()[:5]
            )
            if len(recent_dates) < 3:
                continue

            # Find students absent on ALL of the last 3 dates
            last_3 = recent_dates[:3]
            absent_student_ids = None
            for d in last_3:
                absent_on_day = set(
                    StudentAttendance.objects.filter(school=school, date=d, status="absent")
                    .values_list("student_id", flat=True)
                )
                if absent_student_ids is None:
                    absent_student_ids = absent_on_day
                else:
                    absent_student_ids &= absent_on_day

            if not absent_student_ids:
                continue

            for student_id in absent_student_ids:
                dedup_key = f"attn_warn:{school.pk}:{student_id}:{today}"
                if cache.get(dedup_key):
                    continue
                cache.set(dedup_key, "1", 86400)

                # Notify parents via StudentGuardian
                guardians = list(
                    StudentGuardian.objects.filter(student_id=student_id, is_primary_contact=True)
                    .select_related("guardian")[:3]
                )
                for sg in guardians:
                    Notification.create_notification(
                        user=sg.guardian,
                        title="Attendance Alert",
                        message=(
                            f"Your child has been absent for 3 or more consecutive school days. "
                            f"Please contact the school."
                        ),
                        notification_type="attendance",
                        school=school,
                        include_school=True,
                    )
                    notified += 1

                # Notify school admins
                admins = User.objects.filter(school=school, role__in=["school_admin", "deputy_head"])[:3]
                from students.models import Student
                try:
                    student = Student.objects.get(pk=student_id)
                    student_name = student.user.get_full_name() or str(student)
                except Exception:
                    student_name = f"Student #{student_id}"
                for admin in admins:
                    Notification.create_notification(
                        user=admin,
                        title="Attendance Early Warning",
                        message=f"{student_name} has been absent for 3+ consecutive days.",
                        notification_type="attendance",
                        school=school,
                        include_school=False,
                    )
                    notified += 1

        logger.info("flag_attendance_early_warnings: %d notifications sent", notified)
        return {"notified": notified}
    except Exception as exc:
        logger.exception("flag_attendance_early_warnings failed")
        raise self.retry(exc=exc)
    finally:
        _release_task_lock(lock)


# ---------------------------------------------------------------------------
# GAP-3 — Annual fixed asset depreciation
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def apply_fixed_asset_depreciation_annual(self):
    """Apply one year's straight-line depreciation to every active FixedAsset.

    Safe to run multiple times per year — skips assets that were already
    depreciated in the current calendar year (checks last updated_at year).
    Scheduled: once per year via CELERY_BEAT_SCHEDULE.
    """
    try:
        from finance.models import FixedAsset
        from django.utils import timezone as _tz
        current_year = _tz.now().year
        assets = FixedAsset.objects.filter(
            is_active=True,
            condition__in=["excellent", "good", "fair", "poor"],
        ).exclude(
            updated_at__year=current_year,
        )
        count = 0
        for asset in assets.iterator(chunk_size=200):
            asset.apply_annual_depreciation()
            count += 1
        logger.info("apply_fixed_asset_depreciation_annual: %d assets depreciated", count)
        return {"depreciated": count}
    except Exception as exc:
        logger.exception("apply_fixed_asset_depreciation_annual failed")
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# F9 — Early Warning Flag detection (predictive at-risk system)
# ---------------------------------------------------------------------------

_EW_ATTENDANCE_THRESHOLD = 75      # % below which attendance triggers a flag
_EW_SCORE_DROP_THRESHOLD = 15      # percentage-point drop in avg score vs. previous term
_EW_DISCIPLINE_THRESHOLD = 3       # incidents in current term that trigger a flag


@shared_task(bind=True, max_retries=2, default_retry_delay=600)
def detect_early_warning_flags(self):
    """Scan active students and raise EarlyWarningFlag rows for at-risk cases.

    Checks three independent signals:
    1. Attendance rate < threshold (default 75 %).
    2. Average score dropped by >= threshold vs. prior term.
    3. Three or more discipline incidents this term.

    Only creates a NEW flag if no open/acknowledged flag already exists for the
    student in the current academic year.

    Scheduled: weekly via CELERY_BEAT_SCHEDULE.
    Returns: {"flags_created": N, "students_scanned": M}
    """
    try:
        from django.db.models import Avg, Count, Q
        from django.utils import timezone as _tz
        from academics.models import EarlyWarningFlag, AcademicYear, Term
        from students.models import Student
        from operations.models import StudentAttendance, DisciplineIncident
        from academics.models import Result

        now = _tz.now().date()
        created_count = 0
        scanned = 0

        for school in __import__("schools.models", fromlist=["School"]).School.objects.filter(
            subscription_status__in=["active", "trial"]
        ).iterator(chunk_size=50):
            try:
                acad_year = AcademicYear.objects.filter(school=school, is_current=True).first()
                if not acad_year:
                    continue
                year_label = acad_year.name
                current_term = Term.objects.filter(
                    school=school, is_current=True
                ).first()
                term_label = current_term.name if current_term else ""

                # Determine attendance window
                term_start = current_term.start_date if current_term else acad_year.start_date
                term_end = min(current_term.end_date if current_term else acad_year.end_date, now)

                active_students = Student.objects.filter(
                    school=school, status="active", deleted_at__isnull=True
                )
                for student in active_students.iterator(chunk_size=100):
                    scanned += 1
                    risk_triggers = []
                    details = {}

                    # --- 1. Attendance rate --------------------------------
                    total_days = StudentAttendance.objects.filter(
                        school=school, student=student,
                        date__gte=term_start, date__lte=term_end,
                    ).count()
                    if total_days >= 10:
                        present_days = StudentAttendance.objects.filter(
                            school=school, student=student,
                            date__gte=term_start, date__lte=term_end,
                            status__in=["present", "late"],
                        ).count()
                        att_rate = round(present_days / total_days * 100, 1)
                        if att_rate < _EW_ATTENDANCE_THRESHOLD:
                            risk_triggers.append("attendance")
                            details["attendance_rate"] = att_rate

                    # --- 2. Score drop vs. prior term ----------------------
                    current_avg = Result.objects.filter(
                        school=school, student=student,
                        academic_year=acad_year,
                        term=current_term,
                    ).aggregate(avg=Avg("score"))["avg"]
                    if current_avg is not None:
                        prior_results = Result.objects.filter(
                            school=school, student=student,
                        ).exclude(
                            academic_year=acad_year,
                            term=current_term,
                        ).order_by("-id")[:20]
                        if prior_results.exists():
                            prior_avg = prior_results.aggregate(avg=Avg("score"))["avg"]
                            if prior_avg and (float(prior_avg) - float(current_avg)) >= _EW_SCORE_DROP_THRESHOLD:
                                risk_triggers.append("results")
                                details["score_drop"] = round(float(prior_avg) - float(current_avg), 1)
                                details["current_avg"] = round(float(current_avg), 1)

                    # --- 3. Discipline incidents ---------------------------
                    incident_count = DisciplineIncident.objects.filter(
                        school=school, student=student,
                        incident_date__gte=term_start, incident_date__lte=term_end,
                    ).count()
                    if incident_count >= _EW_DISCIPLINE_THRESHOLD:
                        risk_triggers.append("discipline")
                        details["discipline_count"] = incident_count

                    if not risk_triggers:
                        continue

                    # Determine overall risk level
                    n = len(risk_triggers)
                    if n >= 3:
                        risk_level = "critical"
                    elif n == 2:
                        risk_level = "high"
                    elif "attendance" in risk_triggers and details.get("attendance_rate", 100) < 50:
                        risk_level = "high"
                    else:
                        risk_level = "medium"

                    trigger_type = "composite" if n > 1 else risk_triggers[0]

                    # Skip if already an open/acknowledged flag this year
                    already_flagged = EarlyWarningFlag.objects.filter(
                        school=school, student=student,
                        academic_year=year_label,
                        status__in=["open", "acknowledged"],
                    ).exists()
                    if already_flagged:
                        continue

                    EarlyWarningFlag.objects.create(
                        school=school,
                        student=student,
                        risk_level=risk_level,
                        trigger_type=trigger_type,
                        status="open",
                        details=details,
                        academic_year=year_label,
                        term=term_label,
                    )
                    created_count += 1

            except Exception:
                logger.exception("detect_early_warning_flags: error processing school %s", school.pk)
                continue

        logger.info(
            "detect_early_warning_flags: scanned=%d flags_created=%d",
            scanned, created_count,
        )
        return {"flags_created": created_count, "students_scanned": scanned}

    except Exception as exc:
        logger.exception("detect_early_warning_flags failed")
        raise self.retry(exc=exc)
