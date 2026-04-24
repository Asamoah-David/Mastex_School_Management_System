"""
Daily scheduled task runner.

Run via cron (once per day):
    python manage.py run_scheduled_tasks

Or via a platform cron endpoint (CRON_SECRET_KEY) that calls this command.
"""
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run all daily maintenance tasks: contract expiry, hostel assignment deactivation, subscription expiry warnings."

    def handle(self, *args, **options):
        today = timezone.localdate()
        results = []

        # 1. Expire staff contracts
        try:
            from accounts.hr_utils import sync_expired_staff_contracts
            n = sync_expired_staff_contracts()
            results.append(f"Staff contracts expired: {n}")
        except Exception as e:
            logger.exception("run_scheduled_tasks: contract expiry failed")
            results.append(f"Staff contracts: ERROR ({e})")

        # 2. Deactivate hostel assignments past end_date
        try:
            from operations.models.hostel import HostelAssignment
            n = HostelAssignment.objects.filter(
                is_active=True,
                end_date__isnull=False,
                end_date__lt=today,
            ).update(is_active=False)
            results.append(f"Hostel assignments deactivated: {n}")
        except Exception as e:
            logger.exception("run_scheduled_tasks: hostel deactivation failed")
            results.append(f"Hostel assignments: ERROR ({e})")

        # 3. Notify schools nearing subscription expiry (7-day warning)
        try:
            from schools.models import School
            from datetime import timedelta
            warning_date = today + timedelta(days=7)
            expiring = School.objects.filter(
                is_active=True,
                subscription_status="active",
                subscription_end_date__date=warning_date,
            ).select_related()
            notified = 0
            for school in expiring:
                try:
                    from accounts.models import User
                    admins = User.objects.filter(school=school, role="school_admin", is_active=True)
                    for admin in admins:
                        from core.signals import _notify
                        _notify(
                            admin,
                            "Subscription expiring soon",
                            f"Your Mastex subscription for {school.name} expires in 7 days. Please renew to avoid interruption.",
                            notification_type="info",
                            link="/schools/subscription/",
                        )
                        notified += 1
                except Exception:
                    pass
            results.append(f"Subscription expiry notices sent: {notified}")
        except Exception as e:
            logger.exception("run_scheduled_tasks: subscription warning failed")
            results.append(f"Subscription warnings: ERROR ({e})")

        # 4. Auto-mark overdue library issues
        try:
            from operations.models.library import LibraryIssue
            n = LibraryIssue.objects.filter(
                status="issued",
                due_date__lt=today,
            ).update(status="overdue")
            results.append(f"Library issues marked overdue: {n}")
        except Exception as e:
            logger.exception("run_scheduled_tasks: library overdue failed")
            results.append(f"Library overdue: ERROR ({e})")

        for line in results:
            self.stdout.write(self.style.SUCCESS(line))
