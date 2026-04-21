import uuid

from django.conf import settings
from django.db import models
from students.models import Student
from schools.models import School
from accounts.models import User
from decimal import Decimal
from core.tenancy import SchoolScopedManager


class FeeStructure(models.Model):
    """Defines fee types and amounts per class or school-wide."""
    objects = models.Manager()
    scoped = SchoolScopedManager()

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    class_name = models.CharField(max_length=100, blank=True)
    school_class = models.ForeignKey(
        "students.SchoolClass", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fee_structures",
    )
    term = models.CharField(max_length=50, blank=True)  # e.g. "Term 1 2025" or empty for any
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "class_name"]

    def __str__(self):
        scope = f" ({self.class_name})" if self.class_name else " (All)"
        return f"{self.name}{scope} - {self.amount} GHS"


class Fee(models.Model):
    """Individual student fee with partial payment support."""
    objects = models.Manager()
    scoped = SchoolScopedManager()

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    fee_structure = models.ForeignKey(
        FeeStructure, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fees", help_text="Fee type this charge originated from",
    )
    term = models.ForeignKey(
        "academics.Term", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fees", help_text="Academic term this fee belongs to",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid = models.BooleanField(default=False)
    paystack_payment_id = models.CharField(max_length=255, blank=True, null=True)
    paystack_reference = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Fee"
        verbose_name_plural = "Fees"
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gte=0),
                name="chk_fee_amount_nonnegative",
            ),
            models.CheckConstraint(
                check=models.Q(amount_paid__gte=0),
                name="chk_fee_amount_paid_nonnegative",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "student"], name="idx_fee_school_student"),
            models.Index(fields=["school", "paid"], name="idx_fee_school_paid"),
            models.Index(fields=["student", "paid"], name="idx_fee_student_paid"),
        ]

    @property
    def remaining_balance(self):
        """Calculate remaining balance."""
        amount = self.amount or Decimal("0")
        paid = self.amount_paid or Decimal("0")
        remaining = amount - paid
        if remaining <= 0:
            return Decimal("0.00")
        return remaining.quantize(Decimal("0.01"))

    @property
    def is_fully_paid(self):
        """Check if fee is fully paid."""
        amount = self.amount or Decimal("0")
        paid = self.amount_paid or Decimal("0")
        return paid >= amount

    @property
    def payment_percentage(self):
        """Calculate percentage paid."""
        amount = self.amount or Decimal("0")
        paid = self.amount_paid or Decimal("0")
        if amount <= 0:
            return 100
        pct = (paid / amount) * Decimal("100")
        if pct <= 0:
            return 0
        if pct >= 100:
            return 100
        return float(pct.quantize(Decimal("0.1")))

    def save(self, *args, **kwargs):
        # Auto-update legacy paid field
        self.paid = self.is_fully_paid
        super().save(*args, **kwargs)

    def __str__(self):
        status = "PAID" if self.is_fully_paid else f"GHS {self.remaining_balance} remaining"
        return f"{self.student} - {self.amount} GHS ({status})"


class FeePayment(models.Model):
    """Track individual payments for partial payments."""
    fee = models.ForeignKey(Fee, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Net amount credited to the fee balance (excluding processing uplift).",
    )
    gross_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total charged on Paystack (includes uplift when pass-fee-to-payer is on).",
    )
    paystack_payment_id = models.CharField(max_length=255, blank=True, null=True)
    paystack_reference = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    receipt_no = models.CharField(max_length=64, blank=True, default="", db_index=True)
    payment_method = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, default="pending", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    payer_notified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when payer SMS/email was sent; prevents duplicate notices from webhook+callback.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Fee Payment"
        verbose_name_plural = "Fee Payments"
        constraints = [
            models.UniqueConstraint(
                fields=["paystack_reference"],
                condition=models.Q(paystack_reference__isnull=False),
                name="uniq_feepayment_paystack_reference_nonnull",
            ),
        ]

    def __str__(self):
        return f"Payment of GHS {self.amount} for {self.fee.student}"


class PaymentTransaction(models.Model):
    """Provider-level payment ledger for idempotency and reconciliation across domains."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    PROVIDER_CHOICES = [
        ("paystack", "Paystack"),
        ("manual", "Manual"),
        ("offline", "Offline"),
    ]

    REVIEW_STATUS_CHOICES = [
        ("open", "Open"),
        ("reviewed", "Reviewed"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES, default="paystack")
    reference = models.CharField(max_length=255, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="GHS")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    payment_type = models.CharField(max_length=50, blank=True, default="")
    object_id = models.CharField(max_length=64, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    review_status = models.CharField(
        max_length=20,
        choices=REVIEW_STATUS_CHOICES,
        default="open",
        db_index=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_payment_transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "created_at"], name="idx_paytx_school_created"),
            models.Index(fields=["provider", "status"], name="idx_paytx_provider_status"),
            models.Index(fields=["school", "status", "created_at"], name="idx_paytx_s_st_cr"),
            models.Index(fields=["school", "payment_type", "created_at"], name="idx_paytx_school_type_created"),
        ]

    def __str__(self):
        return f"{self.provider}:{self.reference} ({self.status})"


class SubscriptionPayment(models.Model):
    """Track school subscription payments (Paystack) for audit and idempotency."""

    objects = models.Manager()
    scoped = SchoolScopedManager()

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="subscription_payments")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="subscription_payments")
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Net amount credited to the platform subscription (excluding processing uplift).",
    )
    gross_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total charged on Paystack (includes uplift when pass-fee-to-payer is on).",
    )
    paystack_payment_id = models.CharField(max_length=255, blank=True, null=True)
    paystack_reference = models.CharField(max_length=255, db_index=True)
    payment_method = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Subscription Payment"
        verbose_name_plural = "Subscription Payments"
        constraints = [
            models.UniqueConstraint(
                fields=["paystack_reference"],
                name="uniq_subscriptionpayment_paystack_reference",
            ),
        ]

    def __str__(self):
        return f"Subscription payment {self.paystack_reference} — {self.school.name}"


# ---------------------------------------------------------------------------
#  School Funds Ledger — Phase 2 of school-owned payout architecture
# ---------------------------------------------------------------------------

class SchoolFundsLedgerEntry(models.Model):
    """
    Append-only financial ledger for school funds.

    Every state transition (collected → cleared → available → reserved → paid_out)
    is recorded as a separate row.  Rows are **never updated or deleted** in
    production (AUDIT_APPEND_ONLY).

    ``direction`` is ``credit`` (funds in / increase) or ``debit``
    (funds out / decrease).  The ``state`` field identifies *which* balance
    bucket the entry affects.
    """

    DIRECTION_CHOICES = [
        ("credit", "Credit"),
        ("debit", "Debit"),
    ]

    STATE_CHOICES = [
        ("collected", "Collected"),
        ("cleared", "Cleared"),
        ("available", "Available"),
        ("reserved", "Reserved"),
        ("paid_out", "Paid Out"),
    ]

    SOURCE_TYPE_CHOICES = [
        ("fee_payment", "Fee Payment"),
        ("settlement", "Settlement / Reconciliation"),
        ("payout_reserve", "Payout Reserve"),
        ("payout_execute", "Payout Execution"),
        ("payout_release", "Payout Release (fail/cancel)"),
        ("adjustment", "Manual Adjustment"),
    ]

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="funds_ledger_entries"
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Always positive.  Direction is set by the ``direction`` field.",
    )
    direction = models.CharField(max_length=6, choices=DIRECTION_CHOICES)
    state = models.CharField(max_length=12, choices=STATE_CHOICES)
    source_type = models.CharField(max_length=24, choices=SOURCE_TYPE_CHOICES)
    reference = models.CharField(
        max_length=255, db_index=True,
        help_text="Paystack reference, payout-request id, or adjustment ticket.",
    )
    description = models.CharField(max_length=500, blank=True, default="")
    currency = models.CharField(max_length=8, default="GHS")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "School Funds Ledger Entry"
        verbose_name_plural = "School Funds Ledger Entries"
        indexes = [
            models.Index(
                fields=["school", "state", "created_at"],
                name="idx_fundsle_school_state_ts",
            ),
            models.Index(
                fields=["school", "source_type", "created_at"],
                name="idx_fundsle_school_src_ts",
            ),
            models.Index(fields=["reference"], name="idx_fundsle_reference"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="chk_fundsle_amount_positive",
            ),
        ]

    def __str__(self):
        return (
            f"{self.school_id} {self.direction} {self.amount} "
            f"{self.currency} [{self.state}] ref={self.reference}"
        )

    def save(self, *args, **kwargs):
        if self.pk and not kwargs.pop("_allow_update", False):
            raise ValueError(
                "SchoolFundsLedgerEntry is append-only. "
                "Do not update existing rows."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(
            "SchoolFundsLedgerEntry is append-only. Do not delete rows."
        )


class SchoolFundsBalance(models.Model):
    """
    Denormalized running totals derived from ``SchoolFundsLedgerEntry``.

    One row per school.  Updated atomically inside the same
    ``transaction.atomic()`` block that creates the ledger entry.
    """

    school = models.OneToOneField(
        School, on_delete=models.CASCADE, related_name="funds_balance"
    )
    collected_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cleared_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    available_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    reserved_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    paid_out_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "School Funds Balance"
        verbose_name_plural = "School Funds Balances"
        constraints = [
            models.CheckConstraint(
                check=models.Q(collected_total__gte=0),
                name="chk_fundsbal_collected_gte0",
            ),
            models.CheckConstraint(
                check=models.Q(cleared_total__gte=0),
                name="chk_fundsbal_cleared_gte0",
            ),
            models.CheckConstraint(
                check=models.Q(available_total__gte=0),
                name="chk_fundsbal_available_gte0",
            ),
            models.CheckConstraint(
                check=models.Q(reserved_total__gte=0),
                name="chk_fundsbal_reserved_gte0",
            ),
            models.CheckConstraint(
                check=models.Q(paid_out_total__gte=0),
                name="chk_fundsbal_paidout_gte0",
            ),
        ]

    def __str__(self):
        return (
            f"Balance {self.school}: avail={self.available_total} "
            f"reserved={self.reserved_total}"
        )


# ---------------------------------------------------------------------------
#  Staff Payout Request — maker-checker approval workflow
# ---------------------------------------------------------------------------

def _generate_payout_ref():
    return f"PO-{uuid.uuid4().hex[:16].upper()}"


class StaffPayoutRequest(models.Model):
    """
    Payout request for a single staff member from a school's own funds.

    Lifecycle:  pending_approval → approved → funds_reserved → (execution TBD)
                pending_approval → rejected
                approved / funds_reserved → cancelled

    Maker-checker: ``requested_by`` creates the request; ``approved_by``
    approves it.  DB constraint prevents self-approval.
    """

    STATUS_CHOICES = [
        ("pending_approval", "Pending Approval"),
        ("approved", "Approved"),
        ("funds_reserved", "Funds Reserved"),
        ("executing", "Executing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("rejected", "Rejected"),
    ]

    ROUTE_CHOICES = [
        ("momo", "Mobile Money"),
        ("bank", "Bank Transfer"),
    ]

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="staff_payout_requests",
    )
    staff_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="payout_requests_received",
    )
    reference = models.CharField(
        max_length=64, unique=True, default=_generate_payout_ref, db_index=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default="GHS")
    period_label = models.CharField(
        max_length=64, help_text="e.g. January 2026, Week 3",
    )
    route = models.CharField(max_length=8, choices=ROUTE_CHOICES)
    reason = models.CharField(max_length=200, blank=True, default="")

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending_approval",
        db_index=True,
    )

    # Maker-checker
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="payout_requests_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payout_requests_approved",
    )
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payout_requests_rejected",
    )
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payout_requests_cancelled",
    )

    # Fund reservation tracking
    funds_reserved_at = models.DateTimeField(null=True, blank=True)
    ledger_reference = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Reference used in SchoolFundsLedgerEntry for the reservation.",
    )

    # Audit timestamps
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    rejection_reason = models.CharField(max_length=500, blank=True, default="")
    cancellation_reason = models.CharField(max_length=500, blank=True, default="")
    failure_reason = models.TextField(blank=True, default="")

    # Snapshot for audit
    recipient_snapshot = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["-requested_at"]
        verbose_name = "Staff Payout Request"
        verbose_name_plural = "Staff Payout Requests"
        indexes = [
            models.Index(
                fields=["school", "status", "requested_at"],
                name="idx_payoutreq_school_status_ts",
            ),
            models.Index(
                fields=["school", "staff_user", "period_label"],
                name="idx_payoutreq_school_staff_per",
            ),
        ]
        constraints = [
            # Maker-checker: approver must differ from requester
            models.CheckConstraint(
                check=~models.Q(approved_by=models.F("requested_by"))
                | models.Q(approved_by__isnull=True),
                name="chk_payoutreq_maker_checker",
            ),
            # Amount must be positive
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="chk_payoutreq_amount_positive",
            ),
        ]

    def __str__(self):
        return f"Payout {self.reference} {self.status} {self.amount} {self.currency}"
