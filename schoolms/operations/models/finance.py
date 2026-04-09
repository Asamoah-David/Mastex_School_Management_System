from django.db import models
from accounts.models import User
from schools.models import School


class ExpenseCategory(models.Model):
    """Categories for school expenses"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    class Meta:
        verbose_name_plural = "Expense Categories"
    
    def __str__(self):
        return f"{self.name} - {self.school.name}"


class Expense(models.Model):
    """School expenses tracking"""
    PAYMENT_METHODS = (
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('mobile_money', 'Mobile Money'),
        ('cheque', 'Cheque'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    expense_date = models.DateField()
    vendor = models.CharField(max_length=200, blank=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    receipt_number = models.CharField(max_length=50, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_expenses')
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_expenses')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-expense_date"]
        indexes = [
            models.Index(fields=["school", "expense_date"], name="idx_expense_school_date"),
        ]
    
    def __str__(self):
        return f"{self.description} - {self.amount} ({self.expense_date})"


class Budget(models.Model):
    """School budget planning"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True)
    academic_year = models.CharField(max_length=20)  # e.g., "2024/2025"
    term = models.CharField(max_length=20, blank=True)  # e.g., "Term 1"
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2)
    spent_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    @property
    def remaining(self):
        return self.allocated_amount - self.spent_amount
    
    def __str__(self):
        cat = self.category.name if self.category else "Uncategorized"
        return f"{cat} - {self.academic_year}"
