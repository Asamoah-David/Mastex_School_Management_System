from django.db import models
from accounts.models import User
from schools.models import School


class Announcement(models.Model):
    """School announcements visible to parents/students/staff."""
    TARGET_CHOICES = (
        ("all", "Everyone"),
        ("parents", "Parents"),
        ("students", "Students"),
        ("staff", "Staff Only"),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    content = models.TextField()
    target_audience = models.CharField(max_length=20, choices=TARGET_CHOICES, default="all")
    is_pinned = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="announcements_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]
        indexes = [
            models.Index(fields=["school", "target_audience", "is_pinned"], name="idx_ann_school_aud_pin"),
        ]

    def __str__(self):
        return self.title


class StaffLeave(models.Model):
    """Staff leave requests and tracking."""
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )
    LEAVE_TYPE_CHOICES = (
        ("sick", "Sick leave"),
        ("annual", "Annual leave"),
        ("personal", "Personal leave"),
        ("emergency", "Emergency"),
        ("maternity", "Maternity"),
        ("paternity", "Paternity"),
        ("study", "Study leave"),
        ("other", "Other"),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    staff = models.ForeignKey(User, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    covering_teacher = models.CharField(max_length=200, blank=True)
    contact_during_leave = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="leave_reviews")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["school", "staff"], name="idx_leave_school_staff"),
        ]

    @property
    def days_requested(self):
        """Number of calendar days (inclusive) for this leave request."""
        if self.start_date and self.end_date:
            return max(1, (self.end_date - self.start_date).days + 1)
        return 0

    def _get_leave_balance(self):
        """Return the LeaveBalance for this staff member if one exists."""
        try:
            from accounts.hr_models import LeaveBalance
            from academics.models import AcademicYear
            year = AcademicYear.objects.filter(school=self.school, is_current=True).first()
            if not year:
                return None
            label = f"{year.start_date.year}/{year.end_date.year}"
            leave_type = self.leave_type if self.leave_type in dict(
                [("annual","Annual / Vacation"),("sick","Sick Leave"),("maternity","Maternity Leave"),
                 ("paternity","Paternity Leave"),("study","Study / Exam Leave")]
            ) else "annual"
            return LeaveBalance.objects.filter(
                school=self.school, user=self.staff, leave_type=leave_type, academic_year=label
            ).first()
        except Exception:
            return None

    def save(self, *args, **kwargs):
        old_status = None
        if self.pk:
            try:
                old_status = StaffLeave.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            except Exception:
                pass

        super().save(*args, **kwargs)

        # Deduct balance when approved; restore when cancelled/rejected after approval
        # ValueError (insufficient balance) is re-raised so callers know approval was blocked.
        try:
            if old_status != "approved" and self.status == "approved":
                balance = self._get_leave_balance()
                if balance:
                    balance.deduct(self.days_requested)
            elif old_status == "approved" and self.status in ("rejected", "pending"):
                balance = self._get_leave_balance()
                if balance:
                    balance.restore(self.days_requested)
        except ValueError:
            raise
        except Exception:
            pass

    def __str__(self):
        return f"{self.staff.get_full_name()} - {self.start_date} to {self.end_date} ({self.status})"


class ActivityLog(models.Model):
    """DEPRECATED — use audit.AuditLog directly for all new code.

    This model is retained for backward-compatibility only. New rows written
    here are automatically mirrored to AuditLog so both systems stay in sync
    during the transition period.
    """
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="activity_logs")
    action = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Activity Log (Deprecated)"
        verbose_name_plural = "Activity Logs (Deprecated — use Audit Logs)"

    def __str__(self):
        return f"{self.action} - {self.user} at {self.created_at}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        try:
            from audit.models import AuditLog
            AuditLog.log_action(
                user=self.user,
                action='update' if not self._state.adding else 'create',
                model_name='operations.activitylog',
                object_id=self.pk,
                object_repr=str(self)[:255],
                changes={'action': self.action, 'details': self.details[:500]},
                school=self.school,
            )
        except Exception:
            pass
