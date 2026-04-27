import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models
from students.models import Student
from schools.models import School
from accounts.models import User
from decimal import Decimal
from core.tenancy import SchoolScopedManager, SchoolScopedModel


class FeeStructure(SchoolScopedModel):
    """Defines fee types and amounts per class or school-wide."""

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    class_name = models.CharField(max_length=100, blank=True)
    school_class = models.ForeignKey(
        "students.SchoolClass", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fee_structures",
    )
    term = models.CharField(max_length=50, blank=True)  # e.g. "Term 1 2025" or empty for any
    term_fk = models.ForeignKey(
        "academics.Term",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fee_structures",
        help_text="Structured term FK. Prefer this over the legacy term CharField.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "class_name"]

    def __str__(self):
        scope = f" ({self.class_name})" if self.class_name else " (All)"
        return f"{self.name}{scope} - {self.amount} GHS"


class Fee(SchoolScopedModel):
    """Individual student fee with partial payment support."""

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
    due_date = models.DateField(
        null=True, blank=True,
        help_text="Date by which payment is expected. Used for reminders and overdue tracking.",
        db_index=True,
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive fees are archived and excluded from reminders.",
    )
    description = models.CharField(
        max_length=255, blank=True,
        help_text="Optional human-readable label (e.g. 'Term 1 School Fees 2025').",
    )
    paystack_payment_id = models.CharField(max_length=255, blank=True, null=True)
    paystack_reference = models.CharField(max_length=255, blank=True, null=True)
    deleted_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="Soft-delete timestamp. Non-null = archived fee.",
    )
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
            models.Index(fields=["school", "due_date", "is_active"], name="idx_fee_school_due_active"),
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

    @property
    def payment_status_display(self):
        """Human-readable payment status used in exports and templates."""
        if self.is_fully_paid:
            return "Paid"
        if (self.amount_paid or Decimal("0")) > 0:
            return "Partial"
        return "Unpaid"

    def save(self, *args, **kwargs):
        # Auto-update legacy paid field
        self.paid = self.is_fully_paid
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        """Soft-delete: archive instead of removing so payment history is preserved."""
        from django.utils import timezone
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save(update_fields=["deleted_at", "is_active"])

    def hard_delete(self):
        super().delete()

    def restore(self):
        self.deleted_at = None
        self.is_active = True
        self.save(update_fields=["deleted_at", "is_active"])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

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
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True,
        help_text="Denormalised for fast cross-school queries; kept in sync on save.",
    )
    paid_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Set when status transitions to completed.",
    )
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

    def save(self, *args, **kwargs):
        if not self.school_id and self.fee_id:
            try:
                self.school_id = Fee.objects.filter(pk=self.fee_id).values_list("school_id", flat=True).first()
            except Exception:
                pass
        from django.utils import timezone as _tz
        if self.status == "completed" and self.paid_at is None:
            self.paid_at = _tz.now()
        super().save(*args, **kwargs)

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
    content_type = models.ForeignKey(
        "contenttypes.ContentType",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        help_text="ContentType of the payment subject (Fee, CanteenPayment, BusPayment, etc.). Used with object_id to form a GenericForeignKey.",
    )
    content_object = GenericForeignKey("content_type", "object_id")
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
            models.Index(fields=["content_type", "object_id"], name="idx_paytx_ct_obj"),
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


# ---------------------------------------------------------------------------
# Bank / Paystack reconciliation (Fix #35)
# ---------------------------------------------------------------------------

class PaystackSettlement(models.Model):
    """Records Paystack settlement payouts (batch disbursements from Paystack to school bank).

    Populated from the Paystack Settlements API or settlement webhook.
    Reconciled against FeePayment rows to detect discrepancies.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("settled", "Settled"),
        ("failed", "Failed"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="paystack_settlements")
    settlement_id = models.CharField(max_length=100, unique=True, help_text="Paystack settlement ID.")
    batch_reference = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, help_text="Gross settlement amount in subunit / 100.")
    effective_amount = models.DecimalField(max_digits=14, decimal_places=2, help_text="Net after Paystack deductions.")
    settlement_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    transactions_count = models.PositiveIntegerField(default=0)
    raw_payload = models.JSONField(default=dict, blank=True, help_text="Raw Paystack settlement JSON for audit.")
    reconciled = models.BooleanField(default=False, db_index=True)
    reconciliation_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Paystack Settlement"
        verbose_name_plural = "Paystack Settlements"
        ordering = ["-settlement_date", "-id"]
        indexes = [
            models.Index(fields=["school", "settlement_date"], name="idx_pssettl_school_date"),
            models.Index(fields=["school", "reconciled"], name="idx_pssettl_school_rec"),
        ]

    def __str__(self):
        return f"Settlement {self.settlement_id} | {self.effective_amount} GHS | {self.settlement_date}"

    def reconcile(self):
        """Match this settlement's transactions against FeePayment records.

        Sets reconciled=True and appends a summary note.
        """
        from django.db.models import Sum
        matched = FeePayment.objects.filter(
            school=self.school,
            paystack_reference__isnull=False,
            status="completed",
            paid_at__date=self.settlement_date,
        ).aggregate(total=Sum("amount_paid"))["total"] or 0
        discrepancy = self.effective_amount - matched
        self.reconciled = True
        self.reconciliation_notes = (
            f"Matched GHS {matched:.2f} against settlement GHS {self.effective_amount:.2f}. "
            f"Discrepancy: GHS {discrepancy:.2f}."
        )
        self.save(update_fields=["reconciled", "reconciliation_notes"])


# ---------------------------------------------------------------------------
# M8 — Bank Account per school
# ---------------------------------------------------------------------------

class BankAccount(SchoolScopedModel):
    """School bank accounts for multi-account ledger tracking."""

    ACCOUNT_TYPES = [
        ("fees", "Fees Collection"),
        ("salary", "Salary Disbursement"),
        ("petty_cash", "Petty Cash"),
        ("investment", "Investment"),
        ("other", "Other"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="bank_accounts")
    account_name = models.CharField(max_length=200)
    bank_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50)
    branch = models.CharField(max_length=200, blank=True)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default="fees")
    currency = models.CharField(max_length=3, default="GHS")
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bank Account"
        verbose_name_plural = "Bank Accounts"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "account_number", "bank_name"],
                name="uniq_bankaccount_school_number_bank",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "account_type"], name="idx_bankacct_school_type"),
        ]

    def __str__(self):
        return f"{self.bank_name} — {self.account_number} ({self.get_account_type_display()})"


# ---------------------------------------------------------------------------
# M5/E7 — Fee Installment Plans and Discounts
# ---------------------------------------------------------------------------

class FeeInstallmentPlan(SchoolScopedModel):
    """Breaks a fee into scheduled installment payments.

    Links to a Fee record and defines due-date/amount per installment.
    """

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="installment_plans")
    fee = models.ForeignKey(
        "finance.Fee",
        on_delete=models.CASCADE,
        related_name="installment_plans",
    )
    installment_number = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("partial", "Partially Paid"),
            ("paid", "Paid"),
            ("overdue", "Overdue"),
        ],
        default="pending",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fee Installment"
        verbose_name_plural = "Fee Installments"
        ordering = ["installment_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["fee", "installment_number"],
                name="uniq_installment_fee_num",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "status", "due_date"], name="idx_install_school_status_due"),
        ]

    def __str__(self):
        return f"Installment {self.installment_number} for {self.fee} — due {self.due_date}"

    @property
    def balance(self):
        return self.amount_due - self.amount_paid


class FeeDiscount(SchoolScopedModel):
    """Scholarship, hardship, sibling or merit discounts applied to a Fee."""

    DISCOUNT_TYPES = [
        ("scholarship", "Scholarship"),
        ("sibling", "Sibling Discount"),
        ("merit", "Merit Award"),
        ("hardship", "Hardship Waiver"),
        ("staff_child", "Staff Child Benefit"),
        ("other", "Other"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="fee_discounts")
    fee = models.ForeignKey(
        "finance.Fee",
        on_delete=models.CASCADE,
        related_name="discounts",
    )
    discount_type = models.CharField(max_length=30, choices=DISCOUNT_TYPES)
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Percentage off the fee amount (0–100).",
    )
    fixed_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Fixed GHS amount to discount (used if percentage is blank).",
    )
    reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_discounts",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Fee Discount"
        verbose_name_plural = "Fee Discounts"
        indexes = [
            models.Index(fields=["school", "discount_type"], name="idx_feediscount_school_type"),
        ]

    def __str__(self):
        return f"{self.get_discount_type_display()} on {self.fee}"

    @property
    def discount_amount(self):
        if self.percentage:
            return (self.fee.amount * self.percentage / 100).quantize(Decimal("0.01"))
        return self.fixed_amount or Decimal("0")


# ---------------------------------------------------------------------------
# M4/E12 — Purchase Order module
# ---------------------------------------------------------------------------

class PurchaseOrder(SchoolScopedModel):
    """Formal procurement request from draft through supplier receipt.

    Workflow: draft → submitted → approved → ordered → received → paid | cancelled
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted for Approval"),
        ("approved", "Approved"),
        ("ordered", "Ordered from Supplier"),
        ("received", "Goods Received"),
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="purchase_orders")
    po_number = models.CharField(max_length=50, blank=True, help_text="Auto-generated reference")
    supplier_name = models.CharField(max_length=200)
    supplier_contact = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft", db_index=True)
    order_date = models.DateField(null=True, blank=True)
    expected_delivery_date = models.DateField(null=True, blank=True)
    actual_delivery_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"),
        help_text="VAT/tax rate as percentage (e.g. 15.00 for 15%).",
    )
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    grand_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
        help_text="total_amount + tax_amount",
    )
    currency = models.CharField(max_length=3, default="GHS")
    notes = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name="purchase_orders_requested",
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchase_orders_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    linked_expense = models.OneToOneField(
        "operations.Expense", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="purchase_order",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Purchase Order"
        verbose_name_plural = "Purchase Orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "status"], name="idx_po_school_status"),
        ]

    def __str__(self):
        return f"PO-{self.po_number or self.pk} | {self.supplier_name} | {self.status}"

    def save(self, *args, **kwargs):
        if not self.po_number:
            self.po_number = self._generate_po_number()
        super().save(*args, **kwargs)

    def _generate_po_number(self) -> str:
        """Generate sequential, collision-safe PO number: PO-{school_pk}-{year}-{seq}."""
        from django.utils import timezone as _tz
        year = _tz.now().year
        prefix = f"PO-{self.school_id}-{year}-"
        last = (
            PurchaseOrder.objects.filter(
                school_id=self.school_id,
                po_number__startswith=prefix,
            )
            .order_by("-po_number")
            .values_list("po_number", flat=True)
            .first()
        )
        seq = 1
        if last:
            try:
                seq = int(last.split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = PurchaseOrder.objects.filter(school_id=self.school_id).count() + 1
        return f"{prefix}{seq:04d}"

    def recalculate_total(self):
        from django.db.models import Sum
        total = self.items.aggregate(t=Sum("total_price"))["t"] or Decimal("0")
        self.total_amount = total
        self.tax_amount = (total * self.tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        self.grand_total = self.total_amount + self.tax_amount
        self.save(update_fields=["total_amount", "tax_amount", "grand_total"])


class PurchaseOrderItem(SchoolScopedModel):
    """Line item within a PurchaseOrder."""

    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="purchase_order_items")
    description = models.CharField(max_length=300)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=14, decimal_places=2)
    inventory_item = models.ForeignKey(
        "operations.InventoryItem",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="purchase_order_items",
    )
    received_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Purchase Order Item"
        verbose_name_plural = "Purchase Order Items"

    def __str__(self):
        return f"{self.description} × {self.quantity} @ GHS {self.unit_price}"

    def save(self, *args, **kwargs):
        self.total_price = Decimal(str(self.unit_price)) * self.quantity
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# E-4 — Central approval workflow engine
# ---------------------------------------------------------------------------

class ApprovalWorkflow(SchoolScopedModel):
    """Defines an approval pipeline for a given content type (e.g., Expense, PurchaseOrder).

    Steps are stored as an ordered JSON list: [{"step": 1, "role": "bursar", "label": "Finance Review"}, ...]
    """
    WORKFLOW_TYPES = [
        ("expense", "Expense Approval"),
        ("purchase_order", "Purchase Order Approval"),
        ("leave", "Leave Request Approval"),
        ("payroll", "Payroll Approval"),
        ("custom", "Custom"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="approval_workflows")
    name = models.CharField(max_length=150)
    workflow_type = models.CharField(max_length=30, choices=WORKFLOW_TYPES, default="custom", db_index=True)
    steps = models.JSONField(
        default=list,
        help_text=(
            "Ordered list of approval steps: "
            '[{"step": 1, "role": "bursar", "label": "Finance check"}]. '
            "Supported role values match User.role choices."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Approval Workflow"
        verbose_name_plural = "Approval Workflows"
        unique_together = [("school", "workflow_type")]
        ordering = ["school", "workflow_type"]

    def __str__(self):
        return f"{self.name} [{self.get_workflow_type_display()}]"


class WorkflowInstance(SchoolScopedModel):
    """Tracks a single object through an ApprovalWorkflow.

    ``content_type`` (FK → ContentType) + ``object_id`` form a real
    Django GenericForeignKey to the subject (Expense, PurchaseOrder, etc.).
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In Progress"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="workflow_instances")
    workflow = models.ForeignKey(ApprovalWorkflow, on_delete=models.PROTECT, related_name="instances")
    content_type = models.ForeignKey(
        "contenttypes.ContentType",
        on_delete=models.CASCADE,
        null=True,
        help_text="ContentType of the subject model.",
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    current_step = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    steps_snapshot = models.JSONField(
        default=list,
        help_text="Frozen copy of workflow.steps at the time this instance was created. "
                  "advance() uses this so edits to the parent workflow never corrupt in-flight approvals.",
    )
    initiated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="workflow_instances_initiated",
    )
    history = models.JSONField(
        default=list,
        help_text=(
            "Append-only list of step outcomes: "
            '[{"step": 1, "actor": 5, "action": "approved", "note": "", "ts": "..."}]'
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Workflow Instance"
        verbose_name_plural = "Workflow Instances"
        indexes = [
            models.Index(fields=["school", "status"], name="idx_wfinst_school_status"),
            models.Index(fields=["content_type", "object_id"], name="idx_wfinst_ct_obj"),
        ]

    def __str__(self):
        ct = self.content_type.model if self.content_type_id else "?"
        return f"WF#{self.pk} {ct}#{self.object_id} [{self.status}]"

    def save(self, *args, **kwargs):
        if not self.pk and not self.steps_snapshot:
            self.steps_snapshot = list(self.workflow.steps or [])
        super().save(*args, **kwargs)

    def advance(self, actor, action: str, note: str = "") -> bool:
        """Record a step outcome (approved/rejected) and advance or finalise the workflow.

        Uses steps_snapshot (frozen at creation) so edits to the parent workflow
        never corrupt in-flight approvals. Raises PermissionError on role mismatch.
        """
        from django.utils import timezone as _tz
        steps = self.steps_snapshot or self.workflow.steps or []
        if not getattr(actor, "is_superuser", False):
            step_def = next((s for s in steps if s.get("step") == self.current_step), None)
            if step_def:
                expected_role = step_def.get("role")
                if expected_role and getattr(actor, "role", None) != expected_role:
                    raise PermissionError(
                        f"Workflow step {self.current_step} requires role '{expected_role}'; "
                        f"actor has role '{getattr(actor, 'role', 'unknown')}'."
                    )
        step_record = {
            "step": self.current_step,
            "actor": actor.pk if actor else None,
            "action": action,
            "note": note,
            "ts": _tz.now().isoformat(),
        }
        self.history = list(self.history) + [step_record]
        if action == "rejected":
            self.status = "rejected"
        else:
            total_steps = len(steps)
            if self.current_step >= total_steps:
                self.status = "approved"
            else:
                self.current_step += 1
                self.status = "in_progress"
        self.save(update_fields=["current_step", "status", "history", "updated_at"])
        return self.status == "approved"


# ---------------------------------------------------------------------------
# E-6 — Fixed Asset register with straight-line depreciation
# ---------------------------------------------------------------------------

class FixedAsset(SchoolScopedModel):
    """School fixed assets with annual straight-line depreciation tracking."""

    ASSET_CATEGORIES = [
        ("land", "Land & Buildings"),
        ("furniture", "Furniture & Fittings"),
        ("it_equipment", "IT Equipment"),
        ("vehicles", "Vehicles"),
        ("lab_equipment", "Lab Equipment"),
        ("sports_equipment", "Sports Equipment"),
        ("other", "Other"),
    ]
    CONDITION_CHOICES = [
        ("excellent", "Excellent"),
        ("good", "Good"),
        ("fair", "Fair"),
        ("poor", "Poor"),
        ("written_off", "Written Off"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="fixed_assets")
    asset_tag = models.CharField(max_length=50, unique=True, help_text="Unique asset identifier (e.g. FA-2025-001)")
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=ASSET_CATEGORIES, default="other", db_index=True)
    description = models.TextField(blank=True)
    purchase_date = models.DateField()
    purchase_cost = models.DecimalField(max_digits=14, decimal_places=2)
    useful_life_years = models.PositiveSmallIntegerField(default=5, help_text="Estimated lifespan for straight-line depreciation.")
    salvage_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    current_book_value = models.DecimalField(max_digits=14, decimal_places=2, help_text="Updated annually by the depreciation task.")
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default="good", db_index=True)
    location = models.CharField(max_length=200, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    supplier = models.CharField(max_length=200, blank=True)
    currency = models.CharField(
        max_length=8, default="GHS",
        help_text="Purchase / valuation currency (ISO-4217). Inherited from school.currency by default.",
    )
    linked_purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assets", help_text="Procurement PO that brought this asset into service.",
    )
    is_active = models.BooleanField(default=True, help_text="False = disposed/written off.")
    disposal_date = models.DateField(null=True, blank=True)
    disposal_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fixed Asset"
        verbose_name_plural = "Fixed Assets"
        ordering = ["school", "category", "name"]
        indexes = [
            models.Index(fields=["school", "category"], name="idx_fasset_school_cat"),
            models.Index(fields=["school", "is_active"], name="idx_fasset_school_active"),
        ]

    def __str__(self):
        return f"[{self.asset_tag}] {self.name} ({self.school})"

    def save(self, *args, **kwargs):
        if not self.asset_tag:
            import uuid
            from django.utils import timezone as _tz
            year = _tz.now().year
            short_id = uuid.uuid4().hex[:8].upper()
            self.asset_tag = f"FA-{self.school_id}-{year}-{short_id}"
        if not self.pk:
            self.current_book_value = self.purchase_cost
        super().save(*args, **kwargs)

    @property
    def annual_depreciation(self) -> Decimal:
        """Straight-line depreciation per year."""
        if self.useful_life_years <= 0:
            return Decimal("0")
        return ((self.purchase_cost - self.salvage_value) / self.useful_life_years).quantize(Decimal("0.01"))

    def apply_annual_depreciation(self):
        """Reduce book value by one year's depreciation (call once per year)."""
        new_val = max(self.current_book_value - self.annual_depreciation, self.salvage_value)
        self.current_book_value = new_val
        if new_val <= self.salvage_value:
            self.condition = "written_off"
        self.save(update_fields=["current_book_value", "condition", "updated_at"])
