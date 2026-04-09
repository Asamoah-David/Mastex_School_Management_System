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

STAFF_ROLES = (
    "school_admin", "deputy_head", "hod", "teacher",
    "accountant", "librarian", "admission_officer",
    "school_nurse", "admin_assistant", "staff",
)

MANAGEMENT_ROLES = (
    "school_admin", "deputy_head", "hod",
)

ACADEMIC_ROLES = (
    "school_admin", "deputy_head", "hod", "teacher",
)

PARENT_TYPE_CHOICES = (
    ('father', 'Father'),
    ('mother', 'Mother'),
    ('guardian', 'Guardian'),
    ('other', 'Other'),
)


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="parent", db_index=True)
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    parent_type = models.CharField(max_length=20, choices=PARENT_TYPE_CHOICES, blank=True, null=True)

    class Meta(AbstractUser.Meta):
        verbose_name = "User"
        verbose_name_plural = "Users"
        indexes = [
            models.Index(fields=["school", "role"], name="idx_user_school_role"),
        ]
    # Teachers can be assigned to specific subjects
    assigned_subjects = models.ManyToManyField('academics.Subject', blank=True, related_name='assigned_teachers')
    # Secondary roles - allows users to have multiple roles (e.g., teacher + librarian)
    # Stores role strings as comma-separated values for simplicity
    secondary_roles = models.TextField(blank=True, default='', help_text="Comma-separated list of secondary role values")
    # Profile photo
    profile_photo = models.URLField(max_length=500, null=True, blank=True)
    # Gender
    gender = models.CharField(max_length=10, choices=[('male', 'Male'), ('female', 'Female')], blank=True, null=True)
    # Force password change on first login for auto-created accounts
    must_change_password = models.BooleanField(default=False)
    
    def __str__(self):
        name = self.get_full_name() or self.username
        return f"{name} ({self.get_role_display()})"

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
        return self.role in [
            'school_admin', 'deputy_head', 'hod', 'teacher',
            'accountant', 'librarian', 'admission_officer',
            'school_nurse', 'admin_assistant', 'staff',
        ]
    
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
    
    # Secondary roles helper methods
    @property
    def get_secondary_roles_list(self):
        """Get secondary roles as a list of role strings"""
        if not self.secondary_roles:
            return []
        return [r.strip() for r in self.secondary_roles.split(',') if r.strip()]
    
    @property
    def secondary_roles_display(self):
        """Get human-readable list of secondary roles"""
        if not self.secondary_roles:
            return []
        roles = []
        for r in self.get_secondary_roles_list:
            for choice in ROLE_CHOICES:
                if choice[0] == r:
                    roles.append(choice[1])
                    break
        return roles
    
    def has_role(self, role_value):
        """Check if user has a specific role (primary or secondary)"""
        if self.role == role_value:
            return True
        return role_value in self.get_secondary_roles_list
    
    def set_secondary_roles(self, roles_list):
        """Set secondary roles from a list of role values"""
        self.secondary_roles = ','.join(roles_list)
    
    def add_secondary_role(self, role_value):
        """Add a secondary role"""
        roles = self.get_secondary_roles_list
        if role_value not in roles and role_value != self.role:
            roles.append(role_value)
            self.secondary_roles = ','.join(roles)
    
    def remove_secondary_role(self, role_value):
        """Remove a secondary role"""
        roles = self.get_secondary_roles_list
        if role_value in roles:
            roles.remove(role_value)
            self.secondary_roles = ','.join(roles)
