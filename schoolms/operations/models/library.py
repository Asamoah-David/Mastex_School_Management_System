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

    def __str__(self):
        return f"{self.student} - {self.book.title}"
