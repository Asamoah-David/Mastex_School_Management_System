"""
Management command: cleanup_job_applications

Deletes abandoned JobApplication records that were never paid.
Safe to schedule via cron (e.g. nightly).

Usage:
    python manage.py cleanup_job_applications
    python manage.py cleanup_job_applications --hours 48   # keep last 48 h
    python manage.py cleanup_job_applications --dry-run
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = "Delete unpaid/abandoned JobApplication records older than --hours (default 24)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Delete unpaid applications older than this many hours (default: 24).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the count of records that would be deleted without actually deleting.",
        )

    def handle(self, *args, **options):
        from recruitment.models import JobApplication

        cutoff = timezone.now() - timedelta(hours=options["hours"])
        qs = JobApplication.objects.filter(
            payment_status="unpaid",
            applied_at__lt=cutoff,
        )
        count = qs.count()
        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] Would delete {count} abandoned unpaid application(s) "
                    f"older than {options['hours']} hours."
                )
            )
            return

        deleted, _ = qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted} abandoned unpaid application(s) "
                f"older than {options['hours']} hours."
            )
        )
