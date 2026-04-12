"""
Production preflight check — run before every deploy.

    python manage.py preflight

Validates environment variables, database connectivity, security settings,
third-party service keys, and Django system checks.
"""

import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Run production readiness checks before deployment"

    def handle(self, *args, **options):
        errors = []
        warnings = []

        self.stdout.write(self.style.MIGRATE_HEADING("\n  Mastex SchoolOS — Preflight Checks\n"))

        # ---- Core ----
        self._section("Core settings")
        if settings.DEBUG:
            errors.append("DEBUG is True — must be False in production")
        else:
            self._ok("DEBUG is False")

        if settings.SECRET_KEY == "unsafe-local-secret":
            errors.append("SECRET_KEY is still the default value")
        else:
            self._ok("SECRET_KEY is set")

        if not settings.ALLOWED_HOSTS or settings.ALLOWED_HOSTS == ["*"]:
            errors.append("ALLOWED_HOSTS is not properly configured")
        else:
            self._ok(f"ALLOWED_HOSTS has {len(settings.ALLOWED_HOSTS)} entries")

        # ---- Database ----
        self._section("Database")
        try:
            connection.ensure_connection()
            self._ok(f"Connected to {connection.vendor}")
        except Exception as exc:
            errors.append(f"Database connection failed: {exc}")

        self._section("Migrations")
        try:
            from django.db.migrations.executor import MigrationExecutor

            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if plan:
                for migration, _backwards in plan:
                    errors.append(f"Unapplied migration: {migration}")
            else:
                self._ok("No pending migrations")
        except Exception as exc:
            errors.append(f"Could not verify migrations: {exc}")

        # ---- Security ----
        self._section("Security")
        behind_edge = getattr(settings, "BEHIND_TLS_TERMINATING_PROXY", False)
        if behind_edge and not getattr(settings, "SECURE_SSL_REDIRECT", False):
            self._ok("SECURE_SSL_REDIRECT off (TLS at edge; normal for Railway/Render/Fly)")
        elif not getattr(settings, "SECURE_SSL_REDIRECT", False):
            errors.append(
                "SECURE_SSL_REDIRECT is False — set True or set BEHIND_TLS_TERMINATING_PROXY=1 when HTTPS is at the proxy"
            )
        else:
            self._ok("SECURE_SSL_REDIRECT is True")

        cookie_checks = {
            "SESSION_COOKIE_SECURE": True,
            "CSRF_COOKIE_SECURE": True,
            "SESSION_COOKIE_HTTPONLY": True,
            "SECURE_CONTENT_TYPE_NOSNIFF": True,
        }
        for key, expected in cookie_checks.items():
            actual = getattr(settings, key, None)
            if actual != expected:
                errors.append(f"{key} is {actual!r}, expected {expected!r}")
            else:
                self._ok(key)

        hsts = getattr(settings, "SECURE_HSTS_SECONDS", 0)
        if hsts < 3600:
            warnings.append(f"SECURE_HSTS_SECONDS is {hsts} — recommend >= 31536000")
        else:
            self._ok(f"HSTS enabled ({hsts}s)")

        if not settings.CSRF_TRUSTED_ORIGINS:
            warnings.append("CSRF_TRUSTED_ORIGINS is empty")
        else:
            self._ok(f"CSRF_TRUSTED_ORIGINS has {len(settings.CSRF_TRUSTED_ORIGINS)} origins")

        # ---- Third-party keys ----
        self._section("Service keys")
        key_checks = {
            "PAYSTACK_SECRET_KEY": settings.PAYSTACK_SECRET_KEY,
            "MNOTIFY_API_KEY": settings.MNOTIFY_API_KEY,
            "SENTRY_DSN": settings.SENTRY_DSN,
            "CRON_SECRET_KEY": settings.CRON_SECRET_KEY,
        }
        for name, val in key_checks.items():
            if val:
                self._ok(f"{name} is set")
            else:
                warnings.append(f"{name} is not set")

        optional_keys = {
            "GROQ_API_KEY": settings.GROQ_API_KEY,
            "SENDGRID_API_KEY": settings.SENDGRID_API_KEY,
            "SUPABASE_URL": settings.SUPABASE_URL,
        }
        for name, val in optional_keys.items():
            if val:
                self._ok(f"{name} is set")
            else:
                self._stdout_warn(f"{name} not configured (optional)")

        # ---- Compliance / audit (ERP) ----
        self._section("Compliance / audit")
        if getattr(settings, "AUDIT_APPEND_ONLY", False):
            self._ok("AUDIT_APPEND_ONLY is on (model audit log is append-only)")
            archive_dir = getattr(settings, "AUDIT_ARCHIVE_DIR", None)
            if archive_dir:
                try:
                    ad = Path(archive_dir)
                    ad.mkdir(parents=True, exist_ok=True)
                    probe = ad / ".preflight_write_test"
                    probe.write_text("", encoding="utf-8")
                    probe.unlink(missing_ok=True)
                    self._ok(f"AUDIT_ARCHIVE_DIR is writable ({ad})")
                except OSError as exc:
                    warnings.append(f"AUDIT_ARCHIVE_DIR not writable ({archive_dir}): {exc}")
            if not getattr(settings, "AUDIT_PRUNE_ENABLED", False):
                self._stdout_warn("AUDIT_PRUNE_ENABLED is off (recommended; use archive_audit_logs + policy before any prune)")
        else:
            self._stdout_warn("AUDIT_APPEND_ONLY is off — audit rows can be deleted from Django admin")

        # ---- Logging / Monitoring ----
        self._section("Monitoring")
        if settings.SENTRY_DSN and not settings.DEBUG:
            self._ok("Sentry is configured")
        elif settings.DEBUG:
            self._stdout_warn("Sentry disabled (DEBUG mode)")
        else:
            warnings.append("Sentry DSN not set — no error tracking in production")

        # ---- Django system checks ----
        self._section("Django system checks")
        from django.core import checks as django_checks

        all_issues = django_checks.run_checks(include_deployment_checks=True)
        critical = [i for i in all_issues if i.level >= django_checks.ERROR]
        deploy_warnings = [i for i in all_issues if i.level == django_checks.WARNING]

        if critical:
            for issue in critical:
                errors.append(f"[{issue.id}] {issue.msg}")
        else:
            self._ok(f"No critical issues ({len(deploy_warnings)} warnings)")

        # ---- Summary ----
        self.stdout.write("")
        self._section("Summary")
        if errors:
            for e in errors:
                self.stdout.write(self.style.ERROR(f"  FAIL  {e}"))
        if warnings:
            for w in warnings:
                self.stdout.write(self.style.WARNING(f"  WARN  {w}"))
        if not errors and not warnings:
            self.stdout.write(self.style.SUCCESS("  All checks passed!"))

        total_issues = len(errors) + len(warnings)
        self.stdout.write(
            f"\n  {len(errors)} errors, {len(warnings)} warnings\n"
        )

        if errors:
            self.stdout.write(self.style.ERROR("  PREFLIGHT FAILED — fix errors before deploying.\n"))
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("  PREFLIGHT PASSED\n"))

    def _section(self, title):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n  [{title}]"))

    def _ok(self, msg):
        self.stdout.write(self.style.SUCCESS(f"    OK  {msg}"))

    def _stdout_warn(self, msg):
        self.stdout.write(self.style.WARNING(f"    --  {msg}"))
