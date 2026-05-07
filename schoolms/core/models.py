"""Core database models (operational metadata)."""

from django.conf import settings
from django.db import models


class AsyncJob(models.Model):
    """Application-level record for long-running / queued work (complements Celery task IDs)."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="async_jobs",
    )
    job_type = models.CharField(
        max_length=64,
        db_index=True,
        help_text="e.g. omr_process, report_card_pdf, csv_export, backup",
    )
    celery_task_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending", db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    result_summary = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="async_jobs_created",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "job_type", "status"], name="idx_asyncjob_school_type_stat"),
        ]

    def __str__(self):
        return f"{self.job_type} [{self.status}] @ {self.created_at:%Y-%m-%d %H:%M}"
