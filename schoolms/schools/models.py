from datetime import datetime, time, date

from django.db import models
from django.utils import timezone


class School(models.Model):
    name = models.CharField(max_length=255)
    subdomain = models.SlugField(unique=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    # Subscription status
    SUBSCRIPTION_STATUS_CHOICES = [
        ('trial', 'Trial'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    subscription_status = models.CharField(max_length=20, choices=SUBSCRIPTION_STATUS_CHOICES, default='trial')
    subscription_start_date = models.DateTimeField(null=True, blank=True)
    subscription_end_date = models.DateTimeField(null=True, blank=True)
    subscription_type = models.CharField(max_length=20, blank=True, default='monthly')  # monthly, yearly
    subscription_amount = models.DecimalField(max_digits=12, decimal_places=2, default=1500, help_text="Monthly subscription fee in GHS")
    
    # Paystack fields for school fees (subaccount is created automatically from bank details).
    paystack_subaccount_code = models.CharField(max_length=100, blank=True, null=True, help_text="Paystack subaccount code (created automatically)")
    paystack_bank_name = models.CharField(max_length=100, blank=True, null=True)
    paystack_bank_code = models.CharField(max_length=20, blank=True, null=True, help_text="Paystack bank code (from list_banks)")
    paystack_account_number = models.CharField(max_length=20, blank=True, null=True)
    paystack_account_name = models.CharField(max_length=255, blank=True, null=True)

    PAYOUT_SETUP_STATUS_CHOICES = [
        ("inactive", "Not set up"),
        ("pending", "Pending verification"),
        ("active", "Active"),
        ("failed", "Failed"),
        ("unsupported_bank", "Unsupported bank"),
        ("pending_manual_review", "Pending manual review"),
    ]
    paystack_subaccount_status = models.CharField(
        max_length=32, choices=PAYOUT_SETUP_STATUS_CHOICES, default="inactive"
    )
    paystack_subaccount_last_error = models.TextField(blank=True, default="")
    paystack_subaccount_last_synced_at = models.DateTimeField(null=True, blank=True)

    PLAN_CHOICES = [
        ("basic", "Basic"),
        ("standard", "Standard"),
        ("premium", "Premium"),
    ]
    subscription_plan = models.CharField(
        max_length=20, choices=PLAN_CHOICES, default="basic",
        help_text="Feature tier for this school's subscription.",
    )

    logo_url = models.URLField(max_length=500, blank=True)
    logo = models.ImageField(
        upload_to="school_logos/%Y/", blank=True, null=True,
        help_text="Upload school logo (PNG/JPG). Takes precedence over logo_url if set.",
    )
    academic_year = models.CharField(max_length=50, blank=True)  # e.g. "2024/2025"
    timezone = models.CharField(
        max_length=50,
        default="Africa/Accra",
        help_text="IANA timezone (e.g. Africa/Accra, Africa/Lagos, Africa/Nairobi).",
    )
    subscription_grace_days = models.PositiveSmallIntegerField(
        default=7,
        help_text="Days after subscription_end_date before access is fully blocked (read-only / renew flows still allowed).",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "School"
        verbose_name_plural = "Schools"

    def __str__(self):
        return self.name

    def _normalize_subscription_dt(self, value):
        if not value:
            return value
        if isinstance(value, date) and not isinstance(value, datetime):
            value = datetime.combine(value, time.min)
        if timezone.is_naive(value):
            return timezone.make_aware(value)
        return value

    def save(self, *args, **kwargs):
        self.subscription_start_date = self._normalize_subscription_dt(self.subscription_start_date)
        self.subscription_end_date = self._normalize_subscription_dt(self.subscription_end_date)
        super().save(*args, **kwargs)

    @property
    def logo_display(self):
        """Canonical logo URL: uploaded file takes precedence over logo_url."""
        if self.logo:
            try:
                return self.logo.url
            except Exception:
                pass
        return self.logo_url or ""

    @property
    def is_subscription_active(self):
        """Check if subscription is currently active."""
        if self.subscription_status == 'active':
            if self.subscription_end_date:
                return self.subscription_end_date > timezone.now()
            return True
        return False

    @property
    def is_payout_setup_active(self) -> bool:
        """School can receive fee payments only when Paystack subaccount is active."""
        return bool(self.paystack_subaccount_code) and self.paystack_subaccount_status == "active"

    @property
    def days_until_expiry(self):
        """Days until subscription expires."""
        if self.subscription_end_date:
            delta = self.subscription_end_date - timezone.now()
            return max(0, delta.days)
        return None


class SchoolEmailBranding(models.Model):
    """
    Per-school outbound email customisation.
    Applied by email templates via school.email_branding (OneToOne reverse accessor).
    """
    school = models.OneToOneField(
        School, on_delete=models.CASCADE, related_name="email_branding"
    )
    header_color = models.CharField(
        max_length=20, default="#1a73e8",
        help_text="Hex colour for email header background (e.g. #1a73e8).",
    )
    logo_override_url = models.URLField(
        max_length=500, blank=True,
        help_text="If set, overrides the school logo in emails.",
    )
    footer_text = models.TextField(
        blank=True,
        help_text="Custom footer for all outbound emails (HTML allowed).",
    )
    reply_to_email = models.EmailField(
        blank=True,
        help_text="Reply-to address for all outbound emails. Defaults to school.email.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "School Email Branding"
        verbose_name_plural = "School Email Branding"

    def __str__(self):
        return f"Email branding – {self.school.name}"

    def get_reply_to(self):
        return self.reply_to_email or self.school.email or ""


class SchoolFeature(models.Model):
    """
    Platform-managed feature flags per school.
    If a feature row doesn't exist, it is treated as enabled (default-on).
    """

    FEATURE_CHOICES = (
        # Existing features
        ("hostel", "Hostel"),
        ("library", "Library"),
        ("inventory", "Inventory"),
        ("messaging", "Messaging"),
        ("ai_assistant", "AI Assistant"),
        ("finance_admin", "Finance (admin tools)"),
        # Academics
        ("exams", "Exams & Assessments"),
        ("homework", "Homework"),
        ("quiz", "Online Quizzes"),
        ("results", "Results & Report Cards"),
        ("timetable", "Timetable"),
        ("performance_analytics", "Performance Analytics"),
        # Admissions & Students
        ("admission", "Admissions"),
        ("student_enrollment", "Student Enrollment"),
        # Operations
        ("attendance", "Student Attendance"),
        ("teacher_attendance", "Teacher Attendance"),
        ("bus_transport", "Bus Transport"),
        ("canteen", "Canteen"),
        ("textbooks", "Textbooks"),
        ("certificates", "Certificates"),
        ("id_cards", "ID Cards"),
        ("health_records", "Health Records"),
        ("discipline", "Discipline & Behavior"),
        ("academic_calendar", "Academic Calendar"),
        ("school_events", "School Events"),
        ("sports", "Sports"),
        ("clubs", "Clubs & Activities"),
        ("pt_meetings", "Parent-Teacher Meetings"),
        ("alumni", "Alumni"),
        ("documents", "Documents"),
        ("announcements", "Announcements"),
        ("online_exams", "Online Exams"),
        # Finance
        ("fee_management", "Fee Management"),
        ("online_payments", "Online Payments"),
        ("expenses", "Expenses"),
        ("budgets", "Budgets"),
        # HR
        ("staff_management", "Staff Management"),
        ("leave_management", "Leave Management"),
        ("staff_paystack_transfers", "Staff payroll (Paystack transfers)"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="features")
    key = models.CharField(max_length=40, choices=FEATURE_CHOICES)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("school", "key")
        ordering = ["key"]
        verbose_name = "School Feature"
        verbose_name_plural = "School Features"

    def __str__(self):
        return f"{self.school.name}: {self.key}={'on' if self.enabled else 'off'}"
