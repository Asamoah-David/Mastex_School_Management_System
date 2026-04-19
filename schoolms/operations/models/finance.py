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
    """School expenses tracking with an explicit approval state machine.

    States:
        draft      -- being edited by the recorder, not yet submitted.
        submitted  -- pending review by a finance approver.
        approved   -- approved for payment (immutable except for voiding).
        rejected   -- rejected with ``rejection_reason``.
        paid       -- posted/paid out to vendor.
        void       -- cancelled after approval/paid (audit-trail preserved).

    Legacy rows (created before this field existed) default to ``approved``
    when ``approved_by`` is set, else ``submitted``. The data migration
    back-fills the ``status`` column accordingly.
    """

    PAYMENT_METHODS = (
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('mobile_money', 'Mobile Money'),
        ('cheque', 'Cheque'),
    )
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid'),
        ('void', 'Void'),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    expense_date = models.DateField()
    vendor = models.CharField(max_length=200, blank=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    receipt_number = models.CharField(max_length=50, blank=True)

    # Approval lifecycle (new)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='submitted', db_index=True,
        help_text="Approval lifecycle state.",
    )
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_expenses')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='rejected_expenses',
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=500, blank=True, default="")
    voided_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='voided_expenses',
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=500, blank=True, default="")
    paid_at = models.DateTimeField(null=True, blank=True)

    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_expenses')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expense_date"]
        indexes = [
            models.Index(fields=["school", "expense_date"], name="idx_expense_school_date"),
            models.Index(fields=["school", "status"], name="idx_expense_school_status"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gte=0),
                name="chk_expense_amount_nonnegative",
            ),
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
