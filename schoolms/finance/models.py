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
