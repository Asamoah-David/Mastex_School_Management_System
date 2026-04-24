"""
Celery application for Mastex School Management System.

Usage:
    # Start worker (from repo root, alongside manage.py):
    celery -A schoolms worker -l info

    # Start beat scheduler for periodic tasks:
    celery -A schoolms beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler

Broker: configured via CELERY_BROKER_URL in settings (falls back to Redis from REDIS_URL).
"""
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolms.settings")

app = Celery("schoolms")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
