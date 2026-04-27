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
from core.tenancy import SchoolScopedModel


class StaffContract(SchoolScopedModel):
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
    base_salary = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Agreed gross salary per payment period (e.g. monthly).",
    )
    salary_currency = models.CharField(max_length=8, default="GHS")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date", "-id"]
        indexes = [
            models.Index(fields=["school", "user", "status"], name="idx_staffcontract_school_user"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "user"],
                condition=models.Q(status="active"),
                name="uniq_staffcontract_one_active_per_school_user",
            ),
            models.CheckConstraint(
                check=models.Q(end_date__isnull=True) | models.Q(end_date__gt=models.F("start_date")),
                name="chk_staffcontract_end_after_start",
            ),
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


class StaffRoleChangeLog(SchoolScopedModel):
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


class StaffTeachingAssignment(SchoolScopedModel):
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
    school_class = models.ForeignKey(
        "students.SchoolClass",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_teaching_assignments",
        help_text="Structured class FK (takes precedence over class_name for filtering).",
    )
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


class StaffPayrollPayment(SchoolScopedModel):
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
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Amount actually disbursed (net pay).")
    gross_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Gross salary before statutory deductions (PAYE, SSNIT). Populated by payroll engine.",
    )
    net_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Net take-home after all deductions. Should equal amount when using the payroll engine.",
    )
    deductions_breakdown = models.JSONField(
        default=dict, blank=True,
        help_text="Gross-to-net breakdown: ssnit_employee, paye, total_deductions, etc.",
    )
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
    payroll_run = models.ForeignKey(
        "accounts.PayrollRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
        help_text="The payroll run batch this payment belongs to.",
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


# ---------------------------------------------------------------------------
# Leave management — policy + balance ledger (Fix #24)
# ---------------------------------------------------------------------------

class LeavePolicy(SchoolScopedModel):
    """Defines leave entitlements per school (e.g. 21 days annual per year)."""

    LEAVE_TYPES = (
        ("annual", "Annual / Vacation"),
        ("sick", "Sick Leave"),
        ("maternity", "Maternity Leave"),
        ("paternity", "Paternity Leave"),
        ("compassionate", "Compassionate Leave"),
        ("study", "Study / Exam Leave"),
        ("unpaid", "Unpaid Leave"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="leave_policies")
    leave_type = models.CharField(max_length=30, choices=LEAVE_TYPES)
    days_per_year = models.PositiveSmallIntegerField(default=21)
    carry_over_max_days = models.PositiveSmallIntegerField(
        default=0,
        help_text="Max days that can roll to next year; 0 = no carry-over.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Leave Policy"
        verbose_name_plural = "Leave Policies"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "leave_type"],
                condition=models.Q(is_active=True),
                name="uniq_leavepolicy_school_type_active",
            ),
        ]

    def __str__(self):
        return f"{self.school.name} | {self.get_leave_type_display()} ({self.days_per_year} days)"


class LeaveBalance(SchoolScopedModel):
    """Running leave balance per staff member per leave type per academic year.

    Updated atomically on leave approval and at year-rollover.
    """

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="leave_balances")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leave_balances",
    )
    leave_type = models.CharField(
        max_length=30,
        choices=LeavePolicy.LEAVE_TYPES,
    )
    academic_year = models.CharField(
        max_length=9,
        help_text="e.g. 2025/2026",
    )
    allocated_days = models.DecimalField(
        max_digits=5, decimal_places=1, default=0,
        help_text="Total days allocated for this year (from policy + any manual adjustments).",
    )
    used_days = models.DecimalField(
        max_digits=5, decimal_places=1, default=0,
        help_text="Days consumed by approved leave requests.",
    )
    carried_over = models.DecimalField(
        max_digits=5, decimal_places=1, default=0,
        help_text="Days carried over from previous year.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Leave Balance"
        verbose_name_plural = "Leave Balances"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "user", "leave_type", "academic_year"],
                name="uniq_leavebalance_user_type_year",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "user"], name="idx_leavebal_school_user"),
        ]

    def __str__(self):
        return f"{self.user} | {self.leave_type} | {self.academic_year} | bal={self.remaining}"

    @property
    def remaining(self):
        return (self.allocated_days + self.carried_over - self.used_days).quantize(
            Decimal("0.1")
        )

    def deduct(self, days: Decimal):
        """Deduct approved leave days; raises ValueError if insufficient balance."""
        days = Decimal(str(days))
        if self.remaining < days:
            raise ValueError(
                f"Insufficient leave balance: {self.remaining} days remaining, {days} requested."
            )
        self.used_days = (self.used_days + days).quantize(Decimal("0.1"))
        self.save(update_fields=["used_days", "updated_at"])

    def restore(self, days: Decimal):
        """Restore days when leave is cancelled or rejected."""
        days = Decimal(str(days))
        self.used_days = max(Decimal("0"), self.used_days - days).quantize(Decimal("0.1"))
        self.save(update_fields=["used_days", "updated_at"])


# ---------------------------------------------------------------------------
# Payroll run / cycle model (Fix #25)
# ---------------------------------------------------------------------------

class PayrollRun(SchoolScopedModel):
    """Groups all staff payroll payments for a single period into a run.

    A run moves through: draft → processing → completed | failed.
    Individual StaffPayrollPayment rows are linked via payroll_run FK.
    """

    STATUS_CHOICES = (
        ("draft", "Draft"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="payroll_runs")
    period_label = models.CharField(max_length=64, help_text="e.g. 'January 2026'")
    pay_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft", db_index=True)
    total_gross = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_paye = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_ssnit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    staff_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="payroll_runs_created",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Payroll Run"
        verbose_name_plural = "Payroll Runs"
        ordering = ["-pay_date", "-id"]
        indexes = [
            models.Index(fields=["school", "status"], name="idx_payrollrun_school_status"),
        ]

    def __str__(self):
        return f"{self.school.name} | {self.period_label} [{self.status}]"

    def recalculate_totals(self):
        """Aggregate StaffPayrollPayment rows attached to this run.

        JSONField key sums are done in Python to stay compatible with both
        SQLite (dev) and PostgreSQL (prod) without fragile Cast expressions.
        """
        from django.db.models import Sum
        qs = self.payments.aggregate(
            g=Sum("gross_amount"), n=Sum("net_amount"), count=models.Count("id"),
        )
        self.total_gross = qs["g"] or Decimal("0")
        self.total_net = qs["n"] or Decimal("0")
        self.staff_count = qs["count"] or 0

        total_paye = Decimal("0")
        total_ssnit = Decimal("0")
        for row in self.payments.values_list("deductions_breakdown", flat=True):
            if isinstance(row, dict):
                try:
                    total_paye += Decimal(str(row.get("paye") or 0))
                except Exception:
                    pass
                try:
                    total_ssnit += Decimal(str(row.get("ssnit_employee") or 0))
                except Exception:
                    pass
        self.total_paye = total_paye
        self.total_ssnit = total_ssnit
        self.save(update_fields=["total_gross", "total_net", "total_paye", "total_ssnit", "staff_count"])


# ---------------------------------------------------------------------------
# M7 — Staff Performance Review
# ---------------------------------------------------------------------------

class StaffPerformanceReview(SchoolScopedModel):
    """Annual/term performance appraisal cycle for staff members.

    Reviewer records scores per category and an overall rating.
    """

    RATING_CHOICES = [
        (1, "Unsatisfactory"),
        (2, "Needs Improvement"),
        (3, "Meets Expectations"),
        (4, "Exceeds Expectations"),
        (5, "Outstanding"),
    ]

    REVIEW_PERIOD_CHOICES = [
        ("annual", "Annual"),
        ("term1", "Term 1"),
        ("term2", "Term 2"),
        ("term3", "Term 3"),
        ("probation", "Probation Review"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="performance_reviews")
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="performance_reviews",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="reviews_conducted",
    )
    review_period = models.CharField(max_length=20, choices=REVIEW_PERIOD_CHOICES, default="annual")
    academic_year = models.CharField(max_length=9, help_text="e.g. 2025/2026")

    # Scored categories (1–5)
    punctuality_score = models.PositiveSmallIntegerField(null=True, blank=True, choices=RATING_CHOICES)
    teaching_quality_score = models.PositiveSmallIntegerField(null=True, blank=True, choices=RATING_CHOICES)
    communication_score = models.PositiveSmallIntegerField(null=True, blank=True, choices=RATING_CHOICES)
    initiative_score = models.PositiveSmallIntegerField(null=True, blank=True, choices=RATING_CHOICES)
    teamwork_score = models.PositiveSmallIntegerField(null=True, blank=True, choices=RATING_CHOICES)

    overall_rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES, null=True, blank=True)
    strengths = models.TextField(blank=True)
    areas_for_improvement = models.TextField(blank=True)
    goals_next_period = models.TextField(blank=True)
    reviewer_notes = models.TextField(blank=True)
    staff_acknowledgement = models.BooleanField(default=False)
    staff_comments = models.TextField(blank=True)

    is_finalised = models.BooleanField(default=False, db_index=True)
    finalised_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Staff Performance Review"
        verbose_name_plural = "Staff Performance Reviews"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "staff", "review_period", "academic_year"],
                name="uniq_staffreview_school_staff_period_year",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "academic_year"], name="idx_staffreview_school_year"),
        ]

    def __str__(self):
        return f"{self.staff} — {self.review_period} {self.academic_year} (rating: {self.overall_rating})"

    @property
    def average_score(self):
        scores = [
            s for s in [
                self.punctuality_score, self.teaching_quality_score,
                self.communication_score, self.initiative_score, self.teamwork_score
            ] if s is not None
        ]
        return round(sum(scores) / len(scores), 2) if scores else None
