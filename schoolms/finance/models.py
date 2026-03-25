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
    """Individual student fee with partial payment support."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # Total fee amount
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # Amount paid so far
    paid = models.BooleanField(default=False)  # Legacy field - kept for compatibility
    stripe_payment_id = models.CharField(max_length=255, blank=True, null=True)
    flutterwave_tx_ref = models.CharField(max_length=255, blank=True, null=True)
    paystack_payment_id = models.CharField(max_length=255, blank=True, null=True)
    paystack_reference = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def remaining_balance(self):
        """Calculate remaining balance."""
        return max(0, float(self.amount) - float(self.amount_paid))

    @property
    def is_fully_paid(self):
        """Check if fee is fully paid."""
        return float(self.amount_paid) >= float(self.amount)

    @property
    def payment_percentage(self):
        """Calculate percentage paid."""
        if float(self.amount) == 0:
            return 100
        return min(100, round((float(self.amount_paid) / float(self.amount)) * 100, 1))

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
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paystack_payment_id = models.CharField(max_length=255, blank=True, null=True)
    paystack_reference = models.CharField(max_length=255, blank=True, null=True)
    payment_method = models.CharField(max_length=50, blank=True)  # e.g., "card", "mobile_money", "bank_transfer"
    status = models.CharField(max_length=20, default="pending")  # pending, completed, failed
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment of GHS {self.amount} for {self.fee.student}"
