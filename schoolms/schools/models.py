from django.db import models

class School(models.Model):
    name = models.CharField(max_length=255)
    subdomain = models.SlugField(unique=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    flutterwave_tx_ref = models.CharField(max_length=255, blank=True, null=True)

    logo_url = models.URLField(max_length=500, blank=True)
    academic_year = models.CharField(max_length=50, blank=True)  # e.g. "2024/2025"

    def __str__(self):
        return self.name


class SchoolFeature(models.Model):
    """
    Platform-managed feature flags per school.
    If a feature row doesn't exist, it is treated as enabled (default-on).
    """

    FEATURE_CHOICES = (
        ("hostel", "Hostel"),
        ("library", "Library"),
        ("inventory", "Inventory"),
        ("messaging", "Messaging"),
        ("ai_assistant", "AI Assistant"),
        ("finance_admin", "Finance (admin tools)"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="features")
    key = models.CharField(max_length=40, choices=FEATURE_CHOICES)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("school", "key")
        ordering = ["key"]

    def __str__(self):
        return f"{self.school.name}: {self.key}={'on' if self.enabled else 'off'}"
