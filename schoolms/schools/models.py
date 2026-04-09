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
    
    # Paystack fields for school fees
    paystack_subaccount_code = models.CharField(max_length=100, blank=True, null=True, help_text="Paystack subaccount code for receiving school fees")
    paystack_bank_name = models.CharField(max_length=100, blank=True, null=True)
    paystack_account_number = models.CharField(max_length=20, blank=True, null=True)
    paystack_account_name = models.CharField(max_length=255, blank=True, null=True)

    logo_url = models.URLField(max_length=500, blank=True)
    academic_year = models.CharField(max_length=50, blank=True)  # e.g. "2024/2025"

    class Meta:
        ordering = ["name"]
        verbose_name = "School"
        verbose_name_plural = "Schools"

    def __str__(self):
        return self.name

    @property
    def is_subscription_active(self):
        """Check if subscription is currently active."""
        if self.subscription_status == 'active':
            if self.subscription_end_date:
                return self.subscription_end_date > timezone.now()
            return True
        return False

    @property
    def days_until_expiry(self):
        """Days until subscription expires."""
        if self.subscription_end_date:
            delta = self.subscription_end_date - timezone.now()
            return max(0, delta.days)
        return None


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
