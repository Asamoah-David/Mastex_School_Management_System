from django.contrib.auth.models import AbstractUser
from django.db import models
from schools.models import School

ROLE_CHOICES = (
    ('super_admin', 'Super Admin'),
    # School Administration
    ('school_admin', 'Headteacher/Admin'),
    ('deputy_head', 'Deputy Headteacher'),
    ('hod', 'Head of Department'),
    # Teachers
    ('teacher', 'Teacher'),
    # Administration Staff
    ('accountant', 'Accountant/Bursar'),
    ('librarian', 'Librarian'),
    ('admission_officer', 'Admission Officer'),
    ('school_nurse', 'School Nurse'),
    ('admin_assistant', 'Admin Assistant'),
    ('staff', 'Staff'),
    # Parents & Students
    ('student', 'Student'),
    ('parent', 'Parent'),
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
    # Teachers can be assigned to specific subjects
    assigned_subjects = models.ManyToManyField('academics.Subject', blank=True, related_name='assigned_teachers')
    
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
    
    @property
    def is_class_teacher(self):
        """Check if this user is a class teacher of any class"""
        if self.role != 'teacher':
            return False
        return hasattr(self, 'classes_taught') and self.classes_taught.exists()
    
    @property
    def assigned_classes(self):
        """Get list of class names this teacher is assigned to as class teacher"""
        if not hasattr(self, 'classes_taught'):
            return []
        return list(self.classes_taught.values_list('name', flat=True))
