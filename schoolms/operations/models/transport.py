from django.db import models
from accounts.models import User
from students.models import Student
from schools.models import School
from django.core.exceptions import ValidationError


class BusRoute(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)  # e.g. "Route A - North"
    fee_per_term = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.name} - {self.school.name}"


class BusPayment(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    route = models.ForeignKey(BusRoute, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    term_period = models.CharField(max_length=50, blank=True)
    paid = models.BooleanField(default=False)
    payment_date = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)  # Paystack reference
    payment_status = models.CharField(max_length=20, default='pending')  # pending, completed, failed

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["school", "student"], name="idx_bus_school_stu"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["payment_reference"],
                condition=models.Q(payment_reference__isnull=False)
                & ~models.Q(payment_reference=""),
                name="uniq_buspayment_payment_reference_nonempty",
            ),
        ]

    def __str__(self):
        return f"{self.student} - {self.amount} GHS (Bus)"

    def clean(self):
        super().clean()
        if self.route_id and self.school_id and getattr(self.route, "school_id", None) != self.school_id:
            raise ValidationError({"route": "Route must belong to the same school as the payment."})
        if self.student_id and self.school_id and getattr(self.student, "school_id", None) != self.school_id:
            raise ValidationError({"student": "Student must belong to the same school as the payment."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Textbook(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    isbn = models.CharField(max_length=20, blank=True)

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
