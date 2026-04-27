from decimal import Decimal

from django.db import models, transaction
from django.core.exceptions import ValidationError
from accounts.models import User
from students.models import Student
from schools.models import School
from core.tenancy import SchoolScopedModel


class BusRoute(SchoolScopedModel):
    PAYMENT_FREQUENCY_CHOICES = [
        ('term', 'Per Term'),
        ('weekly', 'Weekly'),
        ('daily', 'Daily'),
    ]
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)  # e.g. "Route A - North"
    fee_per_term = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_frequency = models.CharField(max_length=10, choices=PAYMENT_FREQUENCY_CHOICES, default='term')

    def __str__(self):
        return f"{self.name} - {self.school.name}"


class BusPayment(SchoolScopedModel):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    route = models.ForeignKey(BusRoute, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text="Running total of partial payments credited so far.",
    )
    term_period = models.CharField(max_length=50, blank=True)
    daily_units = models.PositiveIntegerField(
        default=0,
        help_text="For daily routes: number of days covered by this payment.",
    )
    paid = models.BooleanField(default=False)
    payment_date = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_status = models.CharField(max_length=20, default='pending')
    payment_history = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["school", "student"], name="idx_bus_school_stu"),
            models.Index(
                fields=["school", "payment_status", "-payment_date", "-id"],
                name="idx_bus_school_status_date",
            ),
            models.Index(
                fields=["student", "payment_status", "-id"],
                name="idx_bus_student_status",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["payment_reference"],
                condition=models.Q(payment_reference__isnull=False)
                & ~models.Q(payment_reference=""),
                name="uniq_buspayment_payment_reference_nonempty",
            ),
            models.CheckConstraint(
                check=models.Q(amount_paid__gte=0),
                name="chk_buspayment_amount_paid_nonneg",
            ),
        ]

    def __str__(self):
        return f"{self.student} - {self.amount} GHS (Bus)"

    def clean(self):
        super().clean()
        if self.school_id and self.student_id:
            s_school = getattr(self.student, "school_id", None)
            if s_school is not None and s_school != self.school_id:
                raise ValidationError({"student": "Student must belong to the same school as the payment."})
        if self.school_id and self.route_id:
            r_school = getattr(self.route, "school_id", None)
            if r_school is not None and r_school != self.school_id:
                raise ValidationError({"route": "Bus route must belong to the same school as the payment."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def balance(self):
        return max(self.amount - (self.amount_paid or Decimal("0")), Decimal("0"))

    @property
    def payment_status_display(self):
        if self.paid:
            return "Paid"
        if (self.amount_paid or Decimal("0")) > 0:
            return f"Partial ({self.amount_paid}/{self.amount})"
        return "Unpaid"

    def add_payment(self, amount, payment_reference=None, recorded_by=None):
        """Atomically record a (partial) bus fee payment."""
        from django.utils import timezone
        amt = Decimal(str(amount or 0))
        if amt <= 0:
            return False
        with transaction.atomic():
            bp = BusPayment.objects.select_for_update().get(pk=self.pk)
            bp.amount_paid = (bp.amount_paid or Decimal("0")) + amt
            if payment_reference and not bp.payment_reference:
                bp.payment_reference = payment_reference
            bp.payment_date = timezone.now().date()
            record = {"amount": str(amt), "date": str(bp.payment_date), "reference": payment_reference or ""}
            if bp.payment_history is None:
                bp.payment_history = []
            bp.payment_history.append(record)
            BusPaymentLedger.objects.create(
                bus_payment=bp,
                amount=amt,
                payment_reference=payment_reference or "",
                recorded_by=recorded_by if getattr(recorded_by, "is_authenticated", False) else None,
            )
            if bp.amount_paid >= (bp.amount or Decimal("0")):
                bp.paid = True
                bp.payment_status = "completed"
            elif bp.amount_paid > 0:
                bp.payment_status = "partial"
            bp.save(update_fields=[
                "amount_paid", "payment_reference", "payment_date",
                "payment_history", "paid", "payment_status",
            ])
            self.amount_paid = bp.amount_paid
            self.payment_reference = bp.payment_reference
            self.payment_date = bp.payment_date
            self.payment_history = bp.payment_history
            self.paid = bp.paid
            self.payment_status = bp.payment_status
        return True

    def clean(self):
        super().clean()
        if self.route_id and self.school_id and getattr(self.route, "school_id", None) != self.school_id:
            raise ValidationError({"route": "Route must belong to the same school as the payment."})
        if self.student_id and self.school_id and getattr(self.student, "school_id", None) != self.school_id:
            raise ValidationError({"student": "Student must belong to the same school as the payment."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class BusPaymentLedger(models.Model):
    """Immutable audit ledger rows for bus fee payments."""
    bus_payment = models.ForeignKey(BusPayment, on_delete=models.CASCADE, related_name="ledger_entries")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_reference = models.CharField(max_length=100, blank=True, default="", db_index=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-payment_date", "-id"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="chk_buspayledger_amount_positive",
            ),
        ]

    def __str__(self):
        return f"BusPayment#{self.bus_payment_id} +{self.amount}"


class Textbook(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200, blank=True)
    isbn = models.CharField(max_length=20, blank=True)
    subject = models.CharField(max_length=100, blank=True)
    class_level = models.CharField(max_length=50, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    publisher = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.title} - {self.school.name}"


class TextbookSale(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    textbook = models.ForeignKey(Textbook, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    sale_date = models.DateField(auto_now_add=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="textbook_sales_recorded")
    payment_reference = models.CharField(max_length=100, blank=True)  # Paystack reference
    payment_status = models.CharField(max_length=20, default='pending')  # pending, completed, failed

    class Meta:
        ordering = ["-sale_date"]
        indexes = [
            models.Index(fields=["school", "student"], name="idx_txtsale_school_stu"),
            models.Index(
                fields=["student", "payment_status", "-id"],
                name="idx_tbook_stu_status",
            ),
            models.Index(
                fields=["school", "payment_status", "-id"],
                name="idx_tbook_school_status",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["payment_reference"],
                condition=models.Q(payment_reference__isnull=False)
                & ~models.Q(payment_reference=""),
                name="uniq_textbooksale_payment_reference_nonempty",
            ),
        ]

    def __str__(self):
        return f"{self.student} - {self.textbook.title} x{self.quantity}"

    def clean(self):
        super().clean()
        if self.textbook_id and self.school_id and getattr(self.textbook, "school_id", None) != self.school_id:
            raise ValidationError({"textbook": "Textbook must belong to the same school as the sale."})
        if self.student_id and self.school_id and getattr(self.student, "school_id", None) != self.school_id:
            raise ValidationError({"student": "Student must belong to the same school as the sale."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
