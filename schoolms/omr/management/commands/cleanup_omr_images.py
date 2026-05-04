"""
Management command: cleanup_omr_images
=======================================
Removes temporary OMR scan images older than --hours (default 24) from
MEDIA_ROOT/omr/temp/.

Usage:
    python manage.py cleanup_omr_images
    python manage.py cleanup_omr_images --hours 2
    python manage.py cleanup_omr_images --dry-run
"""

import os
import time
from pathlib import Path

from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Delete temporary OMR scan images older than N hours."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=float,
            default=24,
            help="Delete files older than this many hours (default: 24).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without deleting.",
        )

    def handle(self, *args, **options):
        hours = options["hours"]
        dry_run = options["dry_run"]
        cutoff = time.time() - hours * 3600

        temp_dir = Path(settings.MEDIA_ROOT) / "omr" / "temp"
        if not temp_dir.exists():
            self.stdout.write("No omr/temp directory found — nothing to clean.")
            return

        deleted = 0
        skipped = 0

        for fpath in temp_dir.iterdir():
            if not fpath.is_file():
                continue
            mtime = fpath.stat().st_mtime
            if mtime < cutoff:
                if dry_run:
                    self.stdout.write(f"[dry-run] Would delete: {fpath.name}")
                else:
                    try:
                        fpath.unlink()
                        deleted += 1
                    except OSError as exc:
                        self.stderr.write(f"Error deleting {fpath.name}: {exc}")
            else:
                skipped += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry-run: {deleted} file(s) would be deleted, {skipped} kept."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} temporary OMR image(s). {skipped} kept."))
