from django.contrib.auth.models import AbstractUser
from django.db import models
from schools.models import School

ROLE_CHOICES = (
    ('admin', 'Admin'),
    ('teacher', 'Teacher'),
    ('student', 'Student'),
    ('parent', 'Parent'),
)

class User(AbstractUser):
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="admin")
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True)