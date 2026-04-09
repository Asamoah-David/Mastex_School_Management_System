from django.db import models
from accounts.models import User
from students.models import Student
from schools.models import School


class CanteenItem(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
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
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="canteen_payments_recorded")
    payment_reference = models.CharField(max_length=100, blank=True)  # Paystack reference
    payment_status = models.CharField(max_length=20, default='pending')  # pending, completed, failed

    class Meta:
        ordering = ["-payment_date"]
        indexes = [
            models.Index(fields=["school", "student"], name="idx_canteen_school_stu"),
        ]

    def __str__(self):
        return f"{self.student} - {self.amount} GHS ({self.payment_date})"
