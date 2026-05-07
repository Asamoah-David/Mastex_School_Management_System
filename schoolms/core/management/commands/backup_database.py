"""
Write a timestamped database backup under BACKUP_DIR (default: project /backups).

- SQLite: copies db.sqlite3 (uses connection ``NAME``).
- PostgreSQL: runs ``pg_dump`` if available (uses DATABASE_URL or individual POSTGRES_* env vars).

Restore is environment-specific; keep copies off-server for production.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a timestamped database backup file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            dest="output_dir",
            default="",
            help="Directory for backup files (default: BACKUP_DIR setting or <BASE_DIR>/backups)",
        )

    def handle(self, *args, **options):
        base_dir = Path(getattr(settings, "BASE_DIR", Path.cwd()))
        out = options.get("output_dir") or getattr(settings, "BACKUP_DIR", "")
        backup_root = Path(out) if out else base_dir / "backups"
        backup_root.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_utc")
        engine = settings.DATABASES["default"]["ENGINE"]
        name = settings.DATABASES["default"].get("NAME", "")

        if "sqlite" in engine:
            db_path = Path(name)
            if not db_path.is_file():
                self.stderr.write(self.style.ERROR(f"SQLite database file not found: {db_path}"))
                return
            dest = backup_root / f"schoolms_{stamp}.sqlite3"
            shutil.copy2(db_path, dest)
            self.stdout.write(self.style.SUCCESS(f"Backed up SQLite to {dest}"))
            return

        if "postgresql" in engine:
            dest = backup_root / f"schoolms_{stamp}.sql"
            env = os.environ.copy()
            if settings.DATABASES["default"].get("PASSWORD"):
                env["PGPASSWORD"] = str(settings.DATABASES["default"]["PASSWORD"])
            cmd = [
                "pg_dump",
                "-h",
                str(settings.DATABASES["default"].get("HOST") or "localhost"),
                "-p",
                str(settings.DATABASES["default"].get("PORT") or "5432"),
                "-U",
                str(settings.DATABASES["default"].get("USER") or "postgres"),
                "-d",
                str(settings.DATABASES["default"].get("NAME") or ""),
                "-F",
                "p",
                "-f",
                str(dest),
            ]
            try:
                subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
            except FileNotFoundError:
                self.stderr.write(
                    self.style.ERROR(
                        "pg_dump not found. Install PostgreSQL client tools or backup manually."
                    )
                )
                return
            except subprocess.CalledProcessError as exc:
                self.stderr.write(self.style.ERROR(exc.stderr or str(exc)))
                return
            self.stdout.write(self.style.SUCCESS(f"Backed up PostgreSQL to {dest}"))
            return

        self.stderr.write(
            self.style.WARNING(
                f"Automatic backup not implemented for engine {engine}. Use vendor tools."
            )
        )
