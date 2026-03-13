from django.db import models
from students.models import Student
from schools.models import School


class FeeStructure(models.Model):
    """Defines fee types and amounts per class or school-wide."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)  # e.g. "Tuition", "Development Levy"
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    class_name = models.CharField(max_length=100, blank=True)  # Empty = applies to all classes
    term = models.CharField(max_length=50, blank=True)  # e.g. "Term 1 2025" or empty for any
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "class_name"]

    def __str__(self):
        scope = f" ({self.class_name})" if self.class_name else " (All)"
        return f"{self.name}{scope} - {self.amount} GHS"


class Fee(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    amount = models.FloatField()
    paid = models.BooleanField(default=False)
    stripe_payment_id = models.CharField(max_length=255, blank=True, null=True)
    flutterwave_tx_ref = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student} - {self.amount} GHS"