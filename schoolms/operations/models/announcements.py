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

    def __str__(self):
        return f"{self.staff.get_full_name()} - {self.start_date} to {self.end_date} ({self.status})"


class ActivityLog(models.Model):
    """Audit trail for important actions."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="activity_logs")
    action = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} - {self.user} at {self.created_at}"
