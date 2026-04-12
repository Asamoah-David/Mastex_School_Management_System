"""
Delete old audit.AuditLog rows after archival. Guarded by settings and explicit flags.

Requires AUDIT_APPEND_ONLY bypass via allow_audit_deletion context.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from audit.models import AuditLog
from audit.protection import allow_audit_deletion


class Command(BaseCommand):
    help = (
        "Delete AuditLog rows older than N days (dry-run by default). "
        "Requires AUDIT_PRUNE_ENABLED=true or --force, and --execute to apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-days",
            type=int,
            default=0,
            help="Retention window in days (default: settings.AUDIT_RETENTION_DAYS).",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually delete rows. Without this flag, only prints counts.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow prune even when AUDIT_PRUNE_ENABLED is false (documented policy decision).",
        )

    def handle(self, *args, **opts):
        days = opts["older_than_days"] or getattr(settings, "AUDIT_RETENTION_DAYS", None)
        if not days or days < 1:
            raise CommandError(
                "Set --older-than-days N or AUDIT_RETENTION_DAYS in the environment (positive integer)."
            )

        cutoff = timezone.now() - timedelta(days=days)
        qs = AuditLog.objects.filter(timestamp__lt=cutoff)
        count = qs.count()

        self.stdout.write(
            f"Cutoff: {cutoff.isoformat()} - {count} AuditLog row(s) would be removed."
        )

        if not opts["execute"]:
            self.stdout.write(self.style.WARNING("Dry run only. Pass --execute to delete."))
            return

        if not getattr(settings, "AUDIT_PRUNE_ENABLED", False) and not opts["force"]:
            raise CommandError(
                "Refusing to delete: set AUDIT_PRUNE_ENABLED=true or pass --force (see docs / policy)."
            )

        with allow_audit_deletion():
            deleted, _by_model = qs.delete()

        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} object(s) (includes cascades if any)."))
