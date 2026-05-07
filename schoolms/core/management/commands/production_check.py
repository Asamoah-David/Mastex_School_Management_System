"""
Fail fast in production if critical security-related settings are unsafe.

Usage:
    python manage.py production_check

Exits with code 1 if any check fails. Use in deploy pipeline after collectstatic/migrate.
"""

import os
import sys

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Validate Django settings for production (DEBUG, secret key, ALLOWED_HOSTS, broker)."

    def handle(self, *args, **options):
        errors = []
        if settings.DEBUG:
            errors.append("DEBUG is True — must be False in production.")
        secret = getattr(settings, "SECRET_KEY", "") or ""
        if not secret or secret.startswith("django-insecure-") or len(secret) < 40:
            errors.append("SECRET_KEY is missing, too short, or django-insecure.")
        hosts = getattr(settings, "ALLOWED_HOSTS", []) or []
        if not hosts or hosts == ["*"]:
            errors.append("ALLOWED_HOSTS must be set to explicit hostnames in production.")
        if os.environ.get("DJANGO_DEBUG", "").lower() in ("1", "true", "yes"):
            errors.append("DJANGO_DEBUG env is enabled.")

        broker = getattr(settings, "CELERY_BROKER_URL", "") or ""
        if not settings.DEBUG and broker.startswith("memory://"):
            errors.append(
                "CELERY_BROKER_URL is memory:// — use Redis in production for real task queues."
            )

        csrf_trusted = getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or []
        if not settings.DEBUG and not csrf_trusted:
            errors.append(
                "CSRF_TRUSTED_ORIGINS is empty — set HTTPS origins behind a reverse proxy."
            )

        if errors:
            for msg in errors:
                self.stderr.write(self.style.ERROR(msg))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS("Production settings checks passed."))
