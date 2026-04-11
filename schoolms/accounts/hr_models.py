"""
Staff HR: contracts, role-change audit trail, formal teaching assignments, payroll lines.

Complements User.role, secondary_roles, assigned_subjects M2M, and SchoolClass.class_teacher.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from schools.models import School


class StaffContract(models.Model):
    """Employment contract / engagement record for a staff member."""

    CONTRACT_TYPES = (
        ("permanent", "Permanent"),
        ("fixed_term", "Fixed term"),
        ("temporary", "Temporary"),
        ("probation", "Probation"),
        ("consultant", "Consultant / part-time"),
    )
    STATUS_CHOICES = (
        ("draft", "Draft"),
        ("active", "Active"),
        ("expired", "Expired"),
        ("terminated", "Terminated"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="staff_contracts")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_contracts",
    )
    contract_type = models.CharField(max_length=20, choices=CONTRACT_TYPES, default="fixed_term")
    job_title = models.CharField(max_length=120, blank=True, help_text="e.g. Senior Mathematics Teacher")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text="Leave empty for open-ended.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date", "-id"]
        indexes = [
            models.Index(fields=["school", "user", "status"], name="idx_staffcontract_school_user"),
        ]

    def __str__(self):
        return f"{self.user} · {self.get_contract_type_display()} ({self.status})"

    def refresh_status_by_date(self):
        """Set expired if end_date passed and was active."""
        if self.status != "active" or not self.end_date:
            return
        if self.end_date < timezone.now().date():
            self.status = "expired"
            self.save(update_fields=["status", "updated_at"])


class StaffRoleChangeLog(models.Model):
    """Audit trail when primary or secondary roles change."""

    KIND_PRIMARY = "primary"
    KIND_SECONDARY = "secondary"
    KIND_CHOICES = (
        (KIND_PRIMARY, "Primary role"),
        (KIND_SECONDARY, "Secondary roles"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="staff_role_logs")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_role_change_logs",
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    change_kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    from_value = models.CharField(max_length=200, blank=True, help_text="Previous role key or CSV of secondary roles")
    to_value = models.CharField(max_length=200, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["-changed_at", "-id"]
        indexes = [
            models.Index(fields=["school", "user"], name="idx_staffrolelog_school_user"),
        ]

    def __str__(self):
        return f"{self.user} {self.change_kind} @ {self.changed_at:%Y-%m-%d}"


class StaffTeachingAssignment(models.Model):
    """
    Formal subject + class allocation (who teaches what to which class).
    Optionally syncs User.assigned_subjects when created/ended.
    """

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="staff_teaching_assignments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_teaching_assignments",
    )
    subject = models.ForeignKey("academics.Subject", on_delete=models.CASCADE, related_name="staff_assignments")
    class_name = models.CharField(max_length=100, help_text="Must match a class name in your school (e.g. Form 1A).")
    academic_year = models.CharField(max_length=32, blank=True, help_text="e.g. 2025/2026")
    effective_from = models.DateField(null=True, blank=True)
    effective_until = models.DateField(null=True, blank=True, help_text="Empty means current / ongoing.")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "class_name", "subject__name"]
        indexes = [
            models.Index(fields=["school", "user", "is_active"], name="idx_staffteach_school_user_act"),
        ]

    def __str__(self):
        return f"{self.user} → {self.subject} @ {self.class_name}"


class StaffPayrollPayment(models.Model):
    """Salary / stipend payment line for staff (internal records; not student fee payments)."""

    METHOD_CHOICES = (
        ("bank", "Bank transfer"),
        ("cash", "Cash"),
        ("mobile_money", "Mobile money"),
        ("cheque", "Cheque"),
        ("other", "Other"),
    )
    PAYSTACK_STATUS_CHOICES = (
        ("", "Not sent via Paystack"),
        ("pending", "Transfer queued / processing"),
        ("success", "Transfer successful"),
        ("failed", "Transfer failed"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="staff_payroll_payments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_payroll_payments",
    )
    period_label = models.CharField(max_length=64, help_text="e.g. January 2026, Week 3")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default="GHS")
    paid_on = models.DateField()
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="bank")
    reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Paystack Transfer (outgoing) — debits platform Paystack balance; see PAYSTACK_STAFF_TRANSFERS_ENABLED
    paystack_status = models.CharField(max_length=16, choices=PAYSTACK_STATUS_CHOICES, blank=True, default="")
    paystack_transfer_code = models.CharField(max_length=64, blank=True, default="")
    paystack_failure_reason = models.TextField(blank=True)
    recipient_snapshot = models.CharField(
        max_length=200,
        blank=True,
        help_text="Masked payout destination at time of transfer (audit)",
    )

    class Meta:
        ordering = ["-paid_on", "-id"]
        indexes = [
            models.Index(fields=["school", "user", "paid_on"], name="idx_staffpay_school_user_date"),
            models.Index(fields=["reference"], name="idx_staffpay_reference"),
        ]

    def __str__(self):
        return f"{self.user} {self.period_label} {self.amount} {self.currency}"
