import secrets
from django.utils import timezone

from django.db import models

from schools.models import School


class SchoolWebhookEndpoint(models.Model):
    """
    Outbound HTTPS webhook subscriptions for a school (Slack, Zapier, internal ETL).
    Signing: HMAC-SHA256 hex of raw JSON body with ``signing_secret`` (X-Mastex-Signature header).
    """

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="webhook_endpoints")
    name = models.CharField(max_length=120, help_text="Label for admins (e.g. Finance Slack)")
    url = models.URLField(max_length=500)
    signing_secret = models.CharField(
        max_length=128,
        blank=True,
        help_text="Leave blank to auto-generate. Store securely — used to sign webhook payloads.",
    )
    is_active = models.BooleanField(default=True)
    notify_staff_leave = models.BooleanField(default=True, help_text="Leave submitted / reviewed")
    notify_expense = models.BooleanField(default=True, help_text="Expense created or updated")
    notify_fee_payment = models.BooleanField(default=False, help_text="Fee payment completed")
    notify_admission_status = models.BooleanField(default=False, help_text="Admission status changed (approved/rejected)")
    notify_attendance = models.BooleanField(default=False, help_text="Attendance marked for a class")
    notify_result_published = models.BooleanField(default=False, help_text="Exam result published")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "is_active"], name="idx_webhook_school_active"),
        ]

    def __str__(self):
        return f"{self.name} ({self.school.name})"

    def save(self, *args, **kwargs):
        if not self.signing_secret:
            self.signing_secret = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def secret_tail(self) -> str:
        return self.signing_secret[-8:] if self.signing_secret else ""


class WebhookDeliveryAttempt(models.Model):
    """Persistent ledger of outbound webhook deliveries.

    One row is created per endpoint/event dispatch and updated as retry attempts
    occur. This gives operations a durable trace for troubleshooting and allows
    future workers to resume retries from DB state.
    """

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("delivered", "Delivered"),
        ("failed", "Failed"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="webhook_delivery_attempts")
    endpoint = models.ForeignKey(
        SchoolWebhookEndpoint,
        on_delete=models.CASCADE,
        related_name="delivery_attempts",
    )
    event_type = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    attempt_count = models.PositiveIntegerField(default=0)
    last_http_status = models.PositiveIntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_retry_at"], name="idx_wh_attempt_status_retry"),
            models.Index(fields=["school", "event_type", "created_at"], name="idx_wh_attempt_school_event"),
        ]

    def __str__(self):
        return f"{self.event_type} -> {self.endpoint_id} ({self.status})"

    def mark_delivered(self, *, http_status: int | None = None):
        self.status = "delivered"
        self.last_http_status = http_status
        self.last_error = ""
        self.next_retry_at = None
        self.delivered_at = timezone.now()

    def mark_failed(self, *, message: str, http_status: int | None = None, next_retry_at=None):
        self.status = "failed"
        self.last_http_status = http_status
        self.last_error = (message or "")[:2000]
        self.next_retry_at = next_retry_at
