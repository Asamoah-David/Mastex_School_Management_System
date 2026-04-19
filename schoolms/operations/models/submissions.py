from django.db import models
from accounts.models import User
from students.models import Student


class AssignmentSubmission(models.Model):
    """Track online assignment submissions"""
    STATUS_CHOICES = (
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
        ('returned', 'Returned'),
    )
    homework = models.ForeignKey('academics.Homework', on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='assignment_submissions')
    submission_text = models.TextField(blank=True)
    file_path = models.CharField(max_length=255, blank=True)  # Path to uploaded file
    file = models.FileField(upload_to="assignment_submissions/%Y/%m/%d/", null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    notes = models.TextField(blank=True, default="")
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='graded_submissions')
    graded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ("homework", "student")
        ordering = ["-submitted_at"]
    
    def __str__(self):
        return f"{self.student} - {self.homework.title}"
