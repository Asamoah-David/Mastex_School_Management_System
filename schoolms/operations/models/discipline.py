from django.db import models
from accounts.models import User
from students.models import Student
from schools.models import School


class DisciplineIncident(models.Model):
    """Track student disciplinary incidents"""
    SEVERITY_CHOICES = (
        ('minor', 'Minor'),
        ('moderate', 'Moderate'),
        ('serious', 'Serious'),
        ('severe', 'Severe'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='discipline_incidents')
    incident_date = models.DateTimeField()
    incident_type = models.CharField(max_length=100)  # e.g., "Fighting", "Late Submission"
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='minor')
    description = models.TextField()
    action_taken = models.TextField(blank=True)
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reported_incidents')
    status = models.CharField(max_length=20, default='pending')  # pending, resolved, appealed
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-incident_date"]
    
    def __str__(self):
        return f"{self.student} - {self.incident_type} ({self.severity})"


class BehaviorPoint(models.Model):
    """Track positive behavior points/rewards"""
    POINT_TYPES = (
        ('positive', 'Positive'),
        ('negative', 'Negative'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='behavior_points')
    point_type = models.CharField(max_length=20, choices=POINT_TYPES)
    points = models.IntegerField()  # Can be positive or negative
    reason = models.CharField(max_length=200)
    awarded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='awarded_points')
    awarded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-awarded_at"]
    
    def __str__(self):
        return f"{self.student} - {self.points} points ({self.reason})"
