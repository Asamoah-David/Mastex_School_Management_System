from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from accounts.models import User
from schools.models import School
from core.tenancy import SchoolScopedModel


class ExpenseCategory(SchoolScopedModel):
    """Categories for school expenses"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    class Meta:
        verbose_name_plural = "Expense Categories"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"],
                name="uniq_expensecategory_school_name",
            ),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.school.name}"


class Expense(SchoolScopedModel):
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
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Gross amount including tax.")
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="VAT/tax rate as percentage (e.g. 15.00 = 15%).",
    )
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Computed VAT amount.")
    net_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Amount before tax (amount - tax_amount).",
    )
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

    budget = models.ForeignKey(
        'Budget', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='expenses',
        help_text="Budget this expense is charged against. Budget.spent_amount auto-updates.",
    )
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
    academic_year = models.CharField(max_length=20)  # legacy label, e.g., "2024/2025"
    academic_year_fk = models.ForeignKey(
        "academics.AcademicYear",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="budgets",
        help_text="Structured academic year (prefer over the legacy CharField).",
    )
    term = models.CharField(max_length=20, blank=True)  # legacy label
    term_fk = models.ForeignKey(
        "academics.Term",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="budgets",
        help_text="Structured term (prefer over the legacy CharField).",
    )
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2)
    spent_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(allocated_amount__gte=0),
                name="chk_budget_allocated_nonneg",
            ),
            models.CheckConstraint(
                check=models.Q(spent_amount__gte=0),
                name="chk_budget_spent_nonneg",
            ),
        ]

    @property
    def remaining(self):
        return self.allocated_amount - self.spent_amount

    def refresh_spent_amount(self):
        """Recalculate spent_amount from approved/paid Expense rows linked to this budget."""
        from django.db.models import Sum
        total = (
            Expense.objects.filter(
                budget=self,
                status__in=["approved", "paid"],
            ).aggregate(t=Sum("amount"))["t"]
            or 0
        )
        type(self).objects.filter(pk=self.pk).update(spent_amount=total)
        self.spent_amount = total
    
    def __str__(self):
        cat = self.category.name if self.category else "Uncategorized"
        return f"{cat} - {self.academic_year}"


# ---------------------------------------------------------------------------
# Signals: keep Budget.spent_amount in sync automatically
# ---------------------------------------------------------------------------

_COUNTABLE_STATUSES = frozenset(["approved", "paid"])


@receiver(post_save, sender=Expense)
def _sync_budget_on_expense_save(sender, instance, **kwargs):
    """Re-aggregate budget spent_amount when an expense is saved."""
    if instance.budget_id:
        try:
            instance.budget.refresh_spent_amount()
        except Budget.DoesNotExist:
            pass


@receiver(post_delete, sender=Expense)
def _sync_budget_on_expense_delete(sender, instance, **kwargs):
    """Re-aggregate budget spent_amount when an expense is deleted."""
    if instance.budget_id:
        try:
            instance.budget.refresh_spent_amount()
        except Budget.DoesNotExist:
            pass
