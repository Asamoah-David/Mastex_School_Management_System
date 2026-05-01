from django.db import models
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
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)  # e.g. "Lunch", "Snack"
    payment_date = models.DateField(auto_now_add=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="canteen_payments_recorded")
    payment_reference = models.CharField(max_length=100, blank=True)  # Paystack reference
    payment_status = models.CharField(max_length=20, default='pending')  # pending, completed, failed

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
