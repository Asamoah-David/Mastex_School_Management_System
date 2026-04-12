import secrets

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
