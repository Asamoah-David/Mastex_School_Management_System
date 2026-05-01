from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from accounts.models import User
from students.models import Student
from schools.models import School
from core.tenancy import SchoolScopedModel


class LibraryBook(SchoolScopedModel):
    """Library book catalog"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    isbn = models.CharField(max_length=20)
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=100)
    publisher = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=50, blank=True)  # Fiction, Science, etc.
    total_copies = models.PositiveIntegerField(default=1)
    available_copies = models.PositiveIntegerField(default=1)
    shelf_location = models.CharField(max_length=50, blank=True)  # e.g., "A-12"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("school", "isbn")

    def __str__(self):
        return f"{self.title} by {self.author}"


class LibraryIssue(SchoolScopedModel):
    """Track book borrowing."""
    STATUS_CHOICES = (
        ('issued', 'Issued'),
        ('returned', 'Returned'),
        ('overdue', 'Overdue'),
        ('lost', 'Lost'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    book = models.ForeignKey(LibraryBook, on_delete=models.CASCADE)
    issue_date = models.DateField()
    due_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='issued')
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="issued_books")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-issue_date"]
        indexes = [
            models.Index(fields=["school", "student"], name="idx_libissue_school_stu"),
            models.Index(fields=["school", "return_date"], name="idx_libissue_school_ret"),
        ]
        constraints = [
            # Prevent two concurrent active (issued/overdue) issues of the same
            # book to the same student. Returned or lost records can coexist.
            models.UniqueConstraint(
                fields=["student", "book"],
                condition=models.Q(status__in=["issued", "overdue"]),
                name="uniq_active_libissue_student_book",
            ),
        ]

    def __str__(self):
        return f"{self.student} - {self.book.title}"

    def clean(self):
        super().clean()
        # Enforce school consistency across FK targets. Prevents silent
        # cross-tenant mixing via admin / forms / bulk imports.
        if self.school_id and self.book_id:
            b_school = getattr(self.book, "school_id", None)
            if b_school is not None and b_school != self.school_id:
                raise ValidationError({"book": "Book must belong to the same school as the issue."})
        if self.school_id and self.student_id:
            s_school = getattr(self.student, "school_id", None)
            if s_school is not None and s_school != self.school_id:
                raise ValidationError({"student": "Student must belong to the same school as the issue."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class LibraryFine(SchoolScopedModel):
    """Track overdue book fines per borrowing record.

    Fine accrues per day overdue (school-configurable fine_per_day rate).
    Supports full and partial payment and manual waiver by librarian.
    """

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("partial", "Partially Paid"),
        ("paid", "Paid"),
        ("waived", "Waived"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="library_fines")
    issue = models.OneToOneField(
        LibraryIssue,
        on_delete=models.CASCADE,
        related_name="fine",
        help_text="Borrowing record this fine is attached to.",
    )
    fine_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Total fine charged (days_overdue × fine_per_day).",
    )
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    waived_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="waived_library_fines",
    )
    waiver_reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "status"], name="idx_libfine_school_status"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(fine_amount__gte=0), name="chk_libfine_amount_nonneg"),
            models.CheckConstraint(check=models.Q(amount_paid__gte=0), name="chk_libfine_paid_nonneg"),
        ]

    def __str__(self):
        return f"Fine #{self.pk} – {self.issue.student} – GHS {self.fine_amount} ({self.status})"

    @property
    def balance(self):
        return max(self.fine_amount - self.amount_paid, Decimal("0"))

    def mark_paid(self, amount, recorded_by=None):
        """Credit a payment toward this fine and update status."""
        from django.utils import timezone
        amt = Decimal(str(amount or 0))
        if amt <= 0:
            return
        self.amount_paid = min(self.amount_paid + amt, self.fine_amount)
        if self.amount_paid >= self.fine_amount:
            self.status = "paid"
        else:
            self.status = "partial"
        self.save(update_fields=["amount_paid", "status", "updated_at"])

    def waive(self, user, reason=""):
        self.status = "waived"
        self.waived_by = user
        self.waiver_reason = reason[:300]
        self.save(update_fields=["status", "waived_by", "waiver_reason", "updated_at"])


# ---------------------------------------------------------------------------
# Signals: keep LibraryBook.available_copies in sync with active issues
# ---------------------------------------------------------------------------

def _refresh_book_copies(book_id):
    """Recompute and save available_copies for the given book PK."""
    if not book_id:
        return
    try:
        book = LibraryBook.objects.get(pk=book_id)
    except LibraryBook.DoesNotExist:
        return
    active_count = LibraryIssue.objects.filter(
        book_id=book_id, status__in=["issued", "overdue"]
    ).count()
    available = max(0, book.total_copies - active_count)
    LibraryBook.objects.filter(pk=book_id).update(available_copies=available)


@receiver(post_save, sender=LibraryIssue)
def _library_issue_post_save(sender, instance, **kwargs):
    _refresh_book_copies(instance.book_id)


@receiver(post_delete, sender=LibraryIssue)
def _library_issue_post_delete(sender, instance, **kwargs):
    _refresh_book_copies(instance.book_id)
