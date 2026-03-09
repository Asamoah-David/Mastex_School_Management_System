from django.contrib.auth.models import AbstractUser
from django.db import models
from schools.models import School

ROLE_CHOICES = (
    ('super_admin', 'Super Admin'),
    ('school_admin', 'School Admin'),
    ('teacher', 'Teacher'),
    ('student', 'Student'),
    ('parent', 'Parent'),
    ('staff', 'Staff'),
)

PARENT_TYPE_CHOICES = (
    ('father', 'Father'),
    ('mother', 'Mother'),
    ('guardian', 'Guardian'),
    ('other', 'Other'),
)

class User(AbstractUser):
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="parent")
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    parent_type = models.CharField(max_length=20, choices=PARENT_TYPE_CHOICES, blank=True, null=True)
    
    @property
    def is_super_admin(self):
        return self.role == 'super_admin' or self.is_superuser
    
    @property
    def is_school_admin(self):
        return self.role == 'school_admin'
    
    @property
    def is_teacher(self):
        return self.role == 'teacher'
    
    @property
    def is_parent(self):
        return self.role == 'parent'
    
    @property
    def is_student(self):
        return self.role == 'student'
    
    @property
    def is_staff_member(self):
        return self.role in ['teacher', 'staff', 'school_admin']
