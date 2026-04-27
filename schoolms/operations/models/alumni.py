from django.db import models
from students.models import Student
from schools.models import School
from core.tenancy import SchoolScopedModel


class Alumni(SchoolScopedModel):
    """Track past students (alumni)"""
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, related_name='alumni_record')
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    # If student record is deleted, keep alumni info
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    admission_number = models.CharField(max_length=50)
    class_name = models.CharField(max_length=50)
    school_class = models.ForeignKey(
        "students.SchoolClass", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="alumni",
    )
    graduation_year = models.IntegerField()
    graduation_date = models.DateField(null=True, blank=True)
    
    # Post-graduation info
    current_occupation = models.CharField(max_length=200, blank=True)
    current_institution = models.CharField(max_length=200, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    
    # Membership
    is_active_member = models.BooleanField(default=True)
    membership_year = models.IntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.graduation_year})"


class AlumniEvent(SchoolScopedModel):
    """Alumni association events"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    event_date = models.DateTimeField()
    location = models.CharField(max_length=200)
    is_annual = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-event_date"]
    
    def __str__(self):
        return f"{self.title} - {self.event_date.year}"
