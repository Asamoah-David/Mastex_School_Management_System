from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
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
        constraints = [
            models.UniqueConstraint(
                fields=["phone"],
                condition=models.Q(phone__isnull=False) & ~models.Q(phone=""),
                name="uniq_user_phone_nonempty",
            ),
        ]
    # Teachers can be assigned to specific subjects
    assigned_subjects = models.ManyToManyField('academics.Subject', blank=True, related_name='assigned_teachers')
    # Secondary roles managed via UserSecondaryRole through-model (ARCH-5).
    # Profile photo
    profile_photo = models.URLField(max_length=500, null=True, blank=True)
    # Gender
    gender = models.CharField(max_length=10, choices=[('male', 'Male'), ('female', 'Female')], blank=True, null=True)
    # Force password change on first login for auto-created accounts
    must_change_password = models.BooleanField(default=False)
    # In-app setup checklist (staff); dismiss hides the banner until next product bump if desired
    setup_checklist_dismissed = models.BooleanField(default=False)
    # Two-factor authentication (TOTP via pyotp)
    totp_secret = models.CharField(max_length=64, blank=True, default="", help_text="Base32 TOTP secret. Empty = 2FA not set up.")
    totp_enabled = models.BooleanField(default=False, help_text="True when 2FA has been verified and activated by the user.")
    totp_backup_codes = models.TextField(blank=True, default="", help_text="Newline-separated one-time backup codes (hashed).")

    PAYROLL_MOMO_NETWORK_CHOICES = (
        ("", "—"),
        ("MTN", "MTN Mobile Money"),
        ("VOD", "Telecel Cash"),
        ("ATL", "AirtelTigo Money"),
    )
    payroll_momo_number = models.CharField(
        max_length=15,
        blank=True,
        default="",
        help_text="Digits only — used for Paystack mobile-money salary payouts",
    )
    payroll_momo_network = models.CharField(
        max_length=4,
        choices=PAYROLL_MOMO_NETWORK_CHOICES,
        blank=True,
        default="",
    )
    payroll_bank_account_name = models.CharField(max_length=120, blank=True, default="")
    payroll_bank_account_number = models.CharField(max_length=20, blank=True, default="")
    payroll_bank_code = models.CharField(
        max_length=12,
        blank=True,
        default="",
        help_text="Paystack Ghana bank code for transfers (see Paystack dashboard / bank list)",
    )
    paystack_recipient_momo = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Cached Paystack RCP for mobile-money payouts",
    )
    paystack_recipient_bank = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Cached Paystack RCP for bank (NUBAN) payouts",
    )
    
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
        """True if this user is set as class teacher (homeroom) on any class."""
        if self.role not in ACADEMIC_ROLES:
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
    
    # ── Secondary roles helpers (backed by UserSecondaryRole through-model) ──

    def _get_secondary_roles_set(self):
        """Fetch secondary roles from DB once and cache on the instance."""
        if not hasattr(self, '_secondary_roles_cache'):
            try:
                self._secondary_roles_cache = frozenset(
                    self.secondary_role_entries.values_list('role', flat=True)
                )
            except Exception:
                self._secondary_roles_cache = frozenset()
        return self._secondary_roles_cache

    @property
    def get_secondary_roles_list(self):
        """Return secondary roles as a list of role strings (DB-backed)."""
        if not self.pk:
            return []
        return list(self._get_secondary_roles_set())

    @property
    def secondary_roles_display(self):
        """Return human-readable labels for all secondary roles."""
        role_map = {k: v for k, v in ROLE_CHOICES}
        return [role_map.get(r, r) for r in self.get_secondary_roles_list]

    def has_role(self, role_value):
        """True if role_value matches primary role OR any secondary role."""
        if self.role == role_value:
            return True
        if not self.pk:
            return False
        return role_value in self._get_secondary_roles_set()

    def set_secondary_roles(self, roles_list):
        """Replace all secondary roles with roles_list. Requires saved User (pk)."""
        self.__dict__.pop('_secondary_roles_cache', None)
        if not self.pk:
            return
        valid = {choice[0] for choice in ROLE_CHOICES}
        clean = [r for r in (roles_list or []) if r and r in valid and r != self.role]
        self.secondary_role_entries.all().delete()
        if clean:
            UserSecondaryRole.objects.bulk_create(
                [UserSecondaryRole(user=self, role=r) for r in dict.fromkeys(clean)],
                ignore_conflicts=True,
            )

    def add_secondary_role(self, role_value):
        """Add a single secondary role. No-op if already present or equals primary."""
        if not self.pk or role_value == self.role:
            return
        UserSecondaryRole.objects.get_or_create(user=self, role=role_value)

    def remove_secondary_role(self, role_value):
        """Remove a single secondary role."""
        if not self.pk:
            return
        self.secondary_role_entries.filter(role=role_value).delete()

    def clean(self):
        super().clean()

    @property
    def profile_completeness(self) -> int:
        """UX-5: Return profile completeness as a percentage (0–100).

        Checks presence of: first_name, last_name, email, phone,
        profile_photo, school, role (non-default).
        """
        checks = [
            bool(self.first_name and self.first_name.strip()),
            bool(self.last_name and self.last_name.strip()),
            bool(self.email and "@" in self.email),
            bool(self.phone),
            bool(self.profile_photo),
            bool(self.school_id),
            self.role != "parent",
        ]
        done = sum(1 for c in checks if c)
        return round(done / len(checks) * 100)


class PasswordResetRequest(models.Model):
    """Track password reset token requests for rate limiting and audit.

    Prevents password-reset spray attacks by recording every request and
    exposing a ``recent_count_for_email()`` helper that views can use to
    enforce a per-email cap (e.g. max 5 requests per hour).
    """

    user = models.ForeignKey(
        'accounts.User',
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name='password_reset_requests',
    )
    email = models.EmailField(
        help_text="Email address the reset was requested for (snapshot at request time).",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="When the token expires (typically 1 hour).")
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the reset link was consumed. Null = not yet used.",
    )

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["email", "requested_at"], name="idx_pwreset_email_requested"),
            models.Index(fields=["ip_address", "requested_at"], name="idx_pwreset_ip_requested"),
        ]
        verbose_name = "Password Reset Request"
        verbose_name_plural = "Password Reset Requests"

    def __str__(self):
        return f"PasswordReset for {self.email} @ {self.requested_at}"

    @classmethod
    def recent_count_for_email(cls, email: str, window_minutes: int = 60) -> int:
        """How many reset requests have been made for this email in the last N minutes."""
        from django.utils import timezone
        from datetime import timedelta
        since = timezone.now() - timedelta(minutes=window_minutes)
        return cls.objects.filter(email__iexact=email, requested_at__gte=since).count()

    @classmethod
    def recent_count_for_ip(cls, ip: str, window_minutes: int = 60) -> int:
        """How many reset requests have been made from this IP in the last N minutes."""
        from django.utils import timezone
        from datetime import timedelta
        since = timezone.now() - timedelta(minutes=window_minutes)
        return cls.objects.filter(ip_address=ip, requested_at__gte=since).count()


class UserSecondaryRole(models.Model):
    """DB-backed secondary roles for staff users (ARCH-5).

    Replaces the deprecated secondary_roles TextField with a proper through-table
    so secondary roles are queryable at the DB level without fragile icontains hacks.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="secondary_role_entries",
    )
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, db_index=True)

    class Meta:
        unique_together = [("user", "role")]
        verbose_name = "User Secondary Role"
        verbose_name_plural = "User Secondary Roles"
        indexes = [
            models.Index(fields=["user", "role"], name="idx_user_secondary_role"),
        ]

    def __str__(self):
        return f"{self.user_id} — {self.role}"

    def clean(self):
        valid = {choice[0] for choice in ROLE_CHOICES}
        if self.role not in valid:
            raise ValidationError({"role": f"Invalid role: {self.role}"})
        user_role = getattr(self.user, "role", None)
        if user_role and self.role == user_role:
            raise ValidationError({"role": "Secondary role cannot duplicate the user's primary role."})


# Staff HR (contracts, role audit, teaching allocation, payroll) — see hr_models.py
from .hr_models import StaffContract, StaffPayrollPayment, StaffRoleChangeLog, StaffTeachingAssignment  # noqa: E402,F401
