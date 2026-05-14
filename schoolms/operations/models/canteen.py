from django.db import models
from decimal import Decimal
from accounts.models import User
from students.models import Student
from schools.models import School
from django.core.exceptions import ValidationError


class CanteenItem(models.Model):
    CATEGORY_CHOICES = [
        ('breakfast', 'Breakfast'),
        ('lunch', 'Lunch'),
        ('snacks', 'Snacks'),
        ('beverages', 'Beverages'),
        ('other', 'Other'),
    ]
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - {self.school.name}"


class CanteenPayment(models.Model):
    PAYMENT_FREQUENCY_CHOICES = [
        ('single', 'Single Payment'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('term', 'Per Term'),
    ]
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)  # e.g. "Lunch", "Snack"
    payment_date = models.DateField(auto_now_add=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="canteen_payments_recorded")
    payment_reference = models.CharField(max_length=100, blank=True)  # Paystack reference
    payment_status = models.CharField(max_length=20, default='pending')  # pending, completed, failed
    
    # NEW FIELDS for daily/partial payments
    payment_frequency = models.CharField(max_length=10, choices=PAYMENT_FREQUENCY_CHOICES, default='single')
    daily_units = models.PositiveIntegerField(
        default=0,
        help_text="For daily frequency: number of days covered by this payment."
    )
    amount_paid = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal("0"),
        help_text="Running total of partial payments credited so far."
    )
    payment_history = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-payment_date"]
        indexes = [
            models.Index(fields=["school", "student"], name="idx_canteen_school_stu"),
            models.Index(
                fields=["student", "payment_status", "-payment_date"],
                name="idx_cant_stu_status",
            ),
            models.Index(
                fields=["school", "payment_status", "-payment_date"],
                name="idx_cant_school_status",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["payment_reference"],
                condition=models.Q(payment_reference__isnull=False)
                & ~models.Q(payment_reference=""),
                name="uniq_canteenpayment_payment_reference_nonempty",
            ),
        ]

    def __str__(self):
        return f"{self.student} - {self.amount} GHS ({self.payment_date})"

    def clean(self):
        super().clean()
        if self.student_id and self.school_id and getattr(self.student, "school_id", None) != self.school_id:
            raise ValidationError({"student": "Student must belong to the same school as the payment."})

    @property
    def balance(self):
        return max(self.amount - (self.amount_paid or Decimal("0")), Decimal("0"))

    @property
    def payment_status_display(self):
        # CanteenPayment has no `paid` boolean (unlike BusPayment / HostelFee);
        # status is tracked via the `payment_status` string field.
        if self.payment_status == "completed":
            return "Paid"
        if (self.amount_paid or Decimal("0")) > 0:
            return f"Partial ({self.amount_paid}/{self.amount})"
        return "Unpaid"

    def add_payment(self, amount, payment_reference=None, recorded_by=None):
        """Atomically record a (partial) canteen payment."""
        from django.utils import timezone
        from decimal import Decimal
        from django.db import transaction

        amt = Decimal(str(amount or 0))
        if amt <= 0:
            return False
        with transaction.atomic():
            cp = CanteenPayment.objects.select_for_update().get(pk=self.pk)
            cp.amount_paid = (cp.amount_paid or Decimal("0")) + amt
            if payment_reference and not cp.payment_reference:
                cp.payment_reference = payment_reference
            cp.payment_date = timezone.now().date()
            record = {"amount": str(amt), "date": str(cp.payment_date), "reference": payment_reference or ""}
            if cp.payment_history is None:
                cp.payment_history = []
            cp.payment_history.append(record)

            if cp.amount_paid >= (cp.amount or Decimal("0")):
                cp.payment_status = "completed"
            elif cp.amount_paid > 0:
                cp.payment_status = "partial"
            cp.save(update_fields=[
                "amount_paid", "payment_reference", "payment_date",
                "payment_history", "payment_status",
            ])
            return True

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# F15 — Canteen Pre-Order System
# ---------------------------------------------------------------------------

class CanteenOrder(models.Model):
    """A student's pre-order for canteen items on a specific date.

    Orders must be placed by the configured cut-off time the previous day.
    On-day walk-in orders use ``order_type='walkin'`` and have no items rows
    — they are just treated as legacy CanteenPayment records.
    """

    ORDER_STATUS = (
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("ready", "Ready for Collection"),
        ("collected", "Collected"),
        ("cancelled", "Cancelled"),
    )
    ORDER_TYPES = (
        ("preorder", "Pre-Order"),
        ("walkin", "Walk-In"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="canteen_orders")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="canteen_orders")
    order_date = models.DateField(db_index=True, help_text="Date for which the food is being ordered.")
    order_type = models.CharField(max_length=10, choices=ORDER_TYPES, default="preorder")
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default="pending", db_index=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment = models.OneToOneField(
        CanteenPayment, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="canteen_order",
        help_text="Linked payment once the order is paid.",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Canteen Order"
        verbose_name_plural = "Canteen Orders"
        ordering = ["-order_date", "-created_at"]
        indexes = [
            models.Index(fields=["school", "order_date", "status"], name="idx_corder_school_date_status"),
            models.Index(fields=["student", "order_date"], name="idx_corder_stu_date"),
        ]

    def __str__(self):
        return f"{self.student} — {self.order_date} ({self.status})"

    def recalculate_total(self):
        from django.db.models import Sum
        total = self.items.aggregate(t=Sum("line_total"))["t"] or 0
        self.total_amount = total
        self.save(update_fields=["total_amount"])


class CanteenOrderItem(models.Model):
    """A single line in a CanteenOrder — one menu item with quantity."""

    order = models.ForeignKey(CanteenOrder, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(CanteenItem, on_delete=models.CASCADE, related_name="order_items")
    quantity = models.PositiveSmallIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Canteen Order Item"
        verbose_name_plural = "Canteen Order Items"
        unique_together = ("order", "item")

    def __str__(self):
        return f"{self.item.name} × {self.quantity} @ GHS {self.unit_price}"

    def save(self, *args, **kwargs):
        self.unit_price = self.item.price
        self.line_total = self.unit_price * self.quantity
        super().save(*args, **kwargs)
