"""
Management command: cleanup_omr_images
=======================================
Removes OMR files from **disk** (not the database):

- ``MEDIA_ROOT/omr/temp/`` — upload scratch files (default retention: settings or 24h)
- ``MEDIA_ROOT/omr/debug/`` — debug PNGs from scans (default: 72h; can grow fast)

Schedule daily via Celery (``core.tasks.cleanup_omr_media_files``) or cron.

Usage:
    python manage.py cleanup_omr_images
    python manage.py cleanup_omr_images --hours 12 --debug-hours 48
    python manage.py cleanup_omr_images --dry-run
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from omr.storage_cleanup import prune_omr_directory


class Command(BaseCommand):
    help = "Delete old OMR temp uploads and debug PNGs under MEDIA_ROOT/omr/."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=float,
            default=None,
            help="Temp folder: delete files older than this many hours (default: OMR_TEMP_RETENTION_HOURS or 24).",
        )
        parser.add_argument(
            "--debug-hours",
            type=float,
            default=None,
            help="Debug folder: delete files older than this many hours (default: OMR_DEBUG_RETENTION_HOURS or 72).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show counts only; do not delete.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if not getattr(settings, "AUTO_CLEANUP_ENABLED", True) and not dry_run:
            self.stdout.write(
                self.style.WARNING("AUTO_CLEANUP_ENABLED=False — skipping cleanup.")
            )
            return
        hours = options["hours"]
        if hours is None:
            hours = float(getattr(settings, "OMR_TEMP_RETENTION_HOURS", 24))
        debug_hours = options["debug_hours"]
        if debug_hours is None:
            debug_hours = float(getattr(settings, "OMR_DEBUG_RETENTION_HOURS", 72))

        temp_del, temp_kept, temp_err = prune_omr_directory(
            "temp", older_than_hours=hours, dry_run=dry_run
        )
        dbg_del, dbg_kept, dbg_err = prune_omr_directory(
            "debug", older_than_hours=debug_hours, dry_run=dry_run
        )

        for msg in temp_err + dbg_err:
            self.stderr.write(msg)

        label = "Would delete" if dry_run else "Deleted"
        self.stdout.write(
            f"omr/temp/:  {label} {temp_del} file(s), kept {temp_kept} (cutoff {hours}h)."
        )
        self.stdout.write(
            f"omr/debug/: {label} {dbg_del} file(s), kept {dbg_kept} (cutoff {debug_hours}h)."
        )
        if not dry_run:
            self.stdout.write(self.style.SUCCESS("OMR media cleanup finished."))
        else:
            self.stdout.write(self.style.WARNING("Dry-run only — no files removed."))
