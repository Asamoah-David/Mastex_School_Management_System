from django.core.exceptions import ValidationError
from django.db import models
from accounts.models import User
from students.models import Student
from schools.models import School


class LibraryBook(models.Model):
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


class LibraryIssue(models.Model):
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
