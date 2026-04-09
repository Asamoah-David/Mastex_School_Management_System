from django.db import models
from accounts.models import User
from students.models import Student
from schools.models import School


class StudentDocument(models.Model):
    """Store student documents"""
    DOCUMENT_TYPES = (
        ('birth_certificate', 'Birth Certificate'),
        ('report_card', 'Report Card'),
        ('medical', 'Medical Certificate'),
        ('transfer_letter', 'Transfer Letter'),
        ('passport_photo', 'Passport Photo'),
        ('parent_id', 'Parent ID'),
        ('other', 'Other'),
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='documents')
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES)
    title = models.CharField(max_length=200)
    file_path = models.CharField(max_length=255)  # Path to stored file
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateField(null=True, blank=True)  # For documents that expire
    
    class Meta:
        ordering = ["-uploaded_at"]
    
    def __str__(self):
        return f"{self.student} - {self.get_document_type_display()}"
