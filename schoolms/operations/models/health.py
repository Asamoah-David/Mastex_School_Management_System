from django.db import models
from accounts.models import User
from students.models import Student
from schools.models import School


class StudentHealth(models.Model):
    """
    Canonical health record for a student.
    NOTE: Student model also has inline health fields (blood_group, allergies, etc.)
    which are legacy. StudentHealth is the canonical source for health data.
    New health reads/writes should use this model via student.health_record.
    """
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name="health_record")
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    blood_type = models.CharField(max_length=5, blank=True)  # A+, A-, B+, B-, O+, O-, AB+, AB-
    allergies = models.TextField(blank=True)  # List of allergies
    medical_conditions = models.TextField(blank=True)  # e.g., Asthma, Diabetes
    medications = models.TextField(blank=True)  # Current medications
    emergency_contact = models.CharField(max_length=20, blank=True)  # Emergency phone
    emergency_contact_name = models.CharField(max_length=100, blank=True)  # Emergency contact name
    doctor_name = models.CharField(max_length=100, blank=True)
    doctor_phone = models.CharField(max_length=20, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Health Record - {self.student}"


class HealthVisit(models.Model):
    """Track student health clinic visits."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    visit_date = models.DateTimeField(auto_now_add=True)
    complaint = models.TextField()  # Reason for visit
    diagnosis = models.TextField(blank=True)
    treatment = models.TextField(blank=True)
    visited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    is_follow_up = models.BooleanField(default=False)
    
    class Meta:
        ordering = ["-visit_date"]
    
    def __str__(self):
        return f"{self.student} - {self.visit_date.date()}"
