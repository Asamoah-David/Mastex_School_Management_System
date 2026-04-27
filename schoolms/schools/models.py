from datetime import datetime, time, date

from django.core.cache import cache
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
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
    currency = models.CharField(
        max_length=3,
        default="GHS",
        help_text="ISO 4217 currency code for this school (e.g. GHS, NGN, KES, ZAR).",
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

    ai_monthly_token_cap = models.PositiveIntegerField(
        default=0,
        help_text="Maximum AI tokens allowed per school per calendar month. 0 = unlimited.",
    )

    @staticmethod
    def _feature_cache_key(school_pk):
        return f"school_features:{school_pk}"

    def _load_feature_map(self) -> dict:
        """Load all feature flags for this school in a single DB query and cache them."""
        key = self._feature_cache_key(self.pk)
        feature_map = cache.get(key)
        if feature_map is None:
            feature_map = dict(self.features.values_list("key", "enabled"))
            cache.set(key, feature_map, 300)
        return feature_map

    def has_feature(self, key: str) -> bool:
        """Return whether a feature flag is enabled for this school.

        Missing rows are treated as **enabled** (default-on) to avoid
        breaking existing schools during flag rollout. Results are cached
        school-wide in Django's cache backend (300 s TTL) — one DB query
        per school per 5 minutes regardless of how many flags are checked.
        """
        return self._load_feature_map().get(key, True)

    def has_features(self, *keys: str) -> bool:
        """Return True only when ALL listed feature keys are enabled."""
        feature_map = self._load_feature_map()
        return all(feature_map.get(k, True) for k in keys)

    def invalidate_feature_cache(self):
        """Purge the shared cache entry so the next request re-fetches from DB."""
        cache.delete(self._feature_cache_key(self.pk))

    def plan_features(self):
        """Return the set of feature keys included in this school's subscription plan."""
        return PLAN_FEATURE_MAP.get(self.subscription_plan, set())

    def enforce_plan_features(self):
        """Disable features not included in the current plan, enable included ones.

        Called when a school's subscription_plan changes. Does not touch
        features that are not in any plan definition (platform-toggled only).
        """
        allowed = self.plan_features()
        for tier_key in _ALL_PLAN_KEYS:
            enabled = tier_key in allowed
            SchoolFeature.objects.update_or_create(
                school=self, key=tier_key,
                defaults={"enabled": enabled},
            )
        self.invalidate_feature_cache()


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


# ---------------------------------------------------------------------------
# Plan → Feature mapping (Fix #23: enforce feature tier by subscription plan)
# ---------------------------------------------------------------------------

_BASIC_FEATURES = frozenset([
    "attendance", "results", "fee_management", "announcements", "student_enrollment",
    "staff_management", "academics", "homework", "timetable",
])
_STANDARD_FEATURES = _BASIC_FEATURES | frozenset([
    "exams", "library", "messaging", "expenses", "budgets", "canteen", "textbooks",
    "admission", "health_records", "discipline", "academic_calendar", "school_events",
    "leave_management", "teacher_attendance", "performance_analytics", "quiz",
    "online_payments", "id_cards", "certificates", "documents", "alumni",
])
_PREMIUM_FEATURES = _STANDARD_FEATURES | frozenset([
    "hostel", "bus_transport", "inventory", "ai_assistant", "sports", "clubs",
    "pt_meetings", "online_exams", "finance_admin", "staff_paystack_transfers",
    "staff_management",
])

PLAN_FEATURE_MAP = {
    "basic": _BASIC_FEATURES,
    "standard": _STANDARD_FEATURES,
    "premium": _PREMIUM_FEATURES,
}
_ALL_PLAN_KEYS = _PREMIUM_FEATURES


# ---------------------------------------------------------------------------
# Signals: invalidate feature cache when SchoolFeature rows change
# ---------------------------------------------------------------------------

@receiver(post_save, sender=SchoolFeature)
@receiver(post_delete, sender=SchoolFeature)
def _invalidate_school_feature_cache(sender, instance, **kwargs):
    cache.delete(School._feature_cache_key(instance.school_id))


# ---------------------------------------------------------------------------
# SchoolNetwork — multi-campus / school-chain support (Fix #29)
# ---------------------------------------------------------------------------

class SchoolNetwork(models.Model):
    """Groups multiple School tenants under one owner organisation.

    Use cases:
    - A school group/chain operating several campuses.
    - Cross-campus reporting for a network owner.
    """
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    owner_email = models.EmailField(blank=True)
    logo_url = models.URLField(max_length=500, blank=True)
    schools = models.ManyToManyField(
        School,
        blank=True,
        related_name="networks",
        help_text="Schools that belong to this network.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "School Network"
        verbose_name_plural = "School Networks"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def school_count(self):
        return self.schools.count()
