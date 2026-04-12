"""
Export audit.AuditLog rows to newline-delimited JSON for cold storage / compliance.

Example:
  python manage.py archive_audit_logs --after 2024-01-01 --before 2025-01-01
"""

from __future__ import annotations

import json
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from audit.models import AuditLog


def _serialize(obj: AuditLog) -> dict:
    return {
        "id": obj.pk,
        "timestamp": obj.timestamp.isoformat() if obj.timestamp else None,
        "user_id": obj.user_id,
        "username": obj.user.get_username() if obj.user_id else None,
        "action": obj.action,
        "model_name": obj.model_name,
        "object_id": obj.object_id,
        "object_repr": obj.object_repr,
        "changes": obj.changes,
        "ip_address": str(obj.ip_address) if obj.ip_address else None,
        "user_agent": obj.user_agent,
        "school_id": obj.school_id,
    }


class Command(BaseCommand):
    help = "Write AuditLog rows to a JSONL file under AUDIT_ARCHIVE_DIR (ERP / compliance archive)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--after",
            type=str,
            default="",
            help="Inclusive lower bound (ISO 8601 datetime), UTC recommended.",
        )
        parser.add_argument(
            "--before",
            type=str,
            default="",
            help="Exclusive upper bound (ISO 8601 datetime).",
        )
        parser.add_argument(
            "--out-dir",
            type=str,
            default="",
            help="Directory for output (default: settings.AUDIT_ARCHIVE_DIR).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum rows to export (0 = no limit).",
        )

    def handle(self, *args, **opts):
        out_dir = Path(opts["out_dir"] or str(settings.AUDIT_ARCHIVE_DIR))
        out_dir.mkdir(parents=True, exist_ok=True)

        qs = AuditLog.objects.all().order_by("timestamp", "pk")
        if opts["after"]:
            dt = parse_datetime(opts["after"])
            if not dt:
                self.stderr.write(self.style.ERROR(f"Could not parse --after={opts['after']!r}"))
                return
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, dt_timezone.utc)
            qs = qs.filter(timestamp__gte=dt)
        if opts["before"]:
            dt = parse_datetime(opts["before"])
            if not dt:
                self.stderr.write(self.style.ERROR(f"Could not parse --before={opts['before']!r}"))
                return
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, dt_timezone.utc)
            qs = qs.filter(timestamp__lt=dt)

        limit = opts["limit"] or None
        if limit:
            qs = qs[:limit]

        stamp = datetime.now(dt_timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"audit_log_archive_{stamp}.jsonl"
        n = 0
        with path.open("w", encoding="utf-8") as f:
            for obj in qs.iterator(chunk_size=500):
                f.write(json.dumps(_serialize(obj), ensure_ascii=False, default=str))
                f.write("\n")
                n += 1

        self.stdout.write(self.style.SUCCESS(f"Wrote {n} rows to {path}"))
