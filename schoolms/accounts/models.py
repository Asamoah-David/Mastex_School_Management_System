from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from schools.models import School
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

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
    # Secondary roles - allows users to have multiple roles (e.g., teacher + librarian)
    secondary_roles = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='primary_role_of')
    # Profile photo
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
    
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
    
    # Login rate limiting fields
    failed_login_attempts = models.PositiveIntegerField(default=0, help_text="Number of consecutive failed login attempts")
    lockout_until = models.DateTimeField(null=True, blank=True, help_text="Timestamp when account lockout expires")
    last_failed_login = models.DateTimeField(null=True, blank=True, help_text="Timestamp of last failed login attempt")
    
    def is_locked_out(self):
        """Check if user account is currently locked out"""
        if self.lockout_until and self.lockout_until > timezone.now():
            return True
        return False
    
    def get_lockout_remaining_seconds(self):
        """Get remaining lockout time in seconds"""
        if self.lockout_until and self.lockout_until > timezone.now():
            delta = self.lockout_until - timezone.now()
            return max(0, int(delta.total_seconds()))
        return 0
    
    def increment_failed_login(self):
        """Increment failed login counter and potentially lock out"""
        from django.conf import settings
        now = timezone.now()
        
        # Reset if more than 30 minutes since last attempt
        if self.last_failed_login and (now - self.last_failed_login).total_seconds() > 1800:
            self.failed_login_attempts = 0
        
        self.failed_login_attempts += 1
        self.last_failed_login = now
        
        # Lock out after 5 failed attempts (15 minutes)
        if self.failed_login_attempts >= 5:
            self.lockout_until = now + timezone.timedelta(minutes=15)
        
        self.save(update_fields=['failed_login_attempts', 'last_failed_login', 'lockout_until'])
    
    def reset_failed_logins(self):
        """Reset failed login counter on successful login"""
        self.failed_login_attempts = 0
        self.lockout_until = None
        self.last_failed_login = None
        self.save(update_fields=['failed_login_attempts', 'lockout_until', 'last_failed_login'])
    
    def set_password_reset_token(self):
        """
        Generate a password reset token for this user.
        This is called internally by the password reset form.
        Note: Django's default token generator handles this automatically
        when using the built-in password reset views.
        """
        # The token is generated on-the-fly when needed, so no storage needed.
        # This method is here for extensibility if you want to track reset requests.
        pass
    
    def get_password_reset_token_data(self):
        """
        Get data for generating password reset token.
        Returns uid and token for use in password reset URLs.
        """
        uid = urlsafe_base64_encode(force_bytes(self.pk))
        token = default_token_generator.make_token(self)
        return {'uid': uid, 'token': token}
