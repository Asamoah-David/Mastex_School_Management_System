"""
Run automated production checks and remind operators of manual verification steps.

Usage:
    python manage.py audit_security_gaps
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.core.management.base import BaseCommand


def _find_manage_py() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "manage.py"
        if candidate.is_file():
            return candidate
    return None


class Command(BaseCommand):
    help = "Run production_check and print a concise security / tenancy QA checklist."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Automated checks"))
        manage_py = _find_manage_py()
        if manage_py:
            proc = subprocess.run(
                [sys.executable, str(manage_py), "production_check"],
                cwd=str(manage_py.parent),
                capture_output=True,
                text=True,
            )
            if proc.stdout:
                self.stdout.write(proc.stdout)
            if proc.stderr:
                self.stderr.write(proc.stderr)
            if proc.returncode != 0:
                self.stderr.write(
                    self.style.ERROR("production_check reported issues (see above).")
                )
        else:
            self.stderr.write(
                self.style.WARNING("Could not locate manage.py; skip production_check subprocess.")
            )

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Manual verification (each release)"))
        checklist = [
            "Run full test suite: python manage.py test",
            "Smoke-test parent portal: fees, results, child-scoped data only",
            "Smoke-test JWT: obtain token, call /api/v1/results/ as parent vs teacher",
            "Review Paystack webhooks and finance reconciliation in staging",
            "Confirm NUM_PROXIES and CSRF_TRUSTED_ORIGINS match your reverse proxy",
            "Backup: python manage.py backup_database",
        ]
        for line in checklist:
            self.stdout.write(f"  • {line}")
        self.stdout.write(self.style.SUCCESS("\nChecklist printed."))
