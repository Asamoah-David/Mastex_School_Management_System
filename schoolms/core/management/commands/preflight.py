"""
Production preflight check — run before every deploy.

    python manage.py preflight

Validates environment variables, database connectivity, security settings,
third-party service keys, and Django system checks.
"""

import sys

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

        # ---- Security ----
        self._section("Security")
        checks = {
            "SECURE_SSL_REDIRECT": True,
            "SESSION_COOKIE_SECURE": True,
            "CSRF_COOKIE_SECURE": True,
            "SESSION_COOKIE_HTTPONLY": True,
            "SECURE_CONTENT_TYPE_NOSNIFF": True,
        }
        for key, expected in checks.items():
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
