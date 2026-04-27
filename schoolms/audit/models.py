from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    """Model to track important user actions for audit purposes."""
    
    ACTION_CHOICES = [
        ('create', 'Created'),
        ('update', 'Updated'),
        ('delete', 'Deleted'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('login_failed', 'Login Failed'),
        ('2fa_verified', '2FA Verified'),
        ('2fa_failed', '2FA Failed'),
        ('password_change', 'Password Changed'),
        ('view', 'Viewed'),
        ('export', 'Exported'),
        ('gdpr_export', 'GDPR Export'),
        ('import', 'Imported'),
        ('approve', 'Approved'),
        ('reject', 'Rejected'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text="User who performed the action"
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100, help_text="Name of the model affected")
    object_id = models.CharField(max_length=255, null=True, blank=True, help_text="ID of the affected object")
    object_repr = models.CharField(max_length=255, null=True, blank=True, help_text="String representation of the object")
    changes = models.JSONField(default=dict, blank=True, help_text="Dictionary of field changes")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['model_name', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['school', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user} {self.action} {self.model_name} at {self.timestamp}"

    @classmethod
    def log_action(cls, user, action, model_name, object_id=None, object_repr=None,
                   changes=None, request=None, school=None):
        """Create an audit log entry. Safe to call from signals and views."""
        kwargs = {
            'user': user,
            'action': action,
            'model_name': model_name,
            'object_id': str(object_id) if object_id else None,
            'object_repr': object_repr,
            'changes': changes or {},
        }
        if request:
            kwargs['ip_address'] = cls._get_client_ip(request)
            kwargs['user_agent'] = request.META.get('HTTP_USER_AGENT', '')[:500]
            kwargs['request_id'] = (
                getattr(request, 'request_id', None)
                or request.META.get('HTTP_X_REQUEST_ID', '')
                or ''
            )[:64]
        if school:
            kwargs['school'] = school
        elif user and hasattr(user, 'school'):
            kwargs['school'] = user.school
        return cls.objects.create(**kwargs)

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP, handling proxies safely."""
        from django.conf import settings as _s
        num_proxies = getattr(_s, 'NUM_PROXIES', 1)
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if xff:
            ips = [ip.strip() for ip in xff.split(',') if ip.strip()]
            if len(ips) >= num_proxies:
                return ips[-num_proxies]
            return ips[0]
        return request.META.get('REMOTE_ADDR', '')

    def delete(self, *args, **kwargs):
        """Block hard-delete: AuditLog rows are append-only (AUDIT_APPEND_ONLY=True)."""
        from django.conf import settings as _s
        if getattr(_s, 'AUDIT_APPEND_ONLY', True):
            raise PermissionError('AuditLog records are append-only and cannot be deleted.')
        super().delete(*args, **kwargs)


# ---------------------------------------------------------------------------
# GDPR data export requests (Fix #34)
# ---------------------------------------------------------------------------

class GDPRExportRequest(models.Model):
    """Tracks requests to export all personal data for a user (data portability / right of access)."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("ready", "Ready for download"),
        ("downloaded", "Downloaded"),
        ("expired", "Expired"),
        ("failed", "Failed"),
    ]

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="gdpr_export_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="gdpr_export_requests",
    )
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="gdpr_exports",
        help_text="The user whose data is being exported.",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    export_url = models.URLField(max_length=500, blank=True, help_text="Signed URL to the exported JSON file.")
    export_payload = models.JSONField(
        null=True, blank=True,
        help_text="Serialised personal-data dict; served as a FileResponse download.",
    )
    error_message = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Download link expiry.")

    class Meta:
        ordering = ["-requested_at"]
        verbose_name = "GDPR Export Request"
        verbose_name_plural = "GDPR Export Requests"
        indexes = [
            models.Index(fields=["school", "status"]),
        ]

    def __str__(self):
        return f"GDPR export for {self.subject_user} [{self.status}]"

    def mark_ready(self, export_url: str = "", export_payload: dict = None, expires_at=None):
        from django.utils import timezone as _tz
        self.status = "ready"
        if export_url:
            self.export_url = export_url
        if export_payload is not None:
            self.export_payload = export_payload
        self.completed_at = _tz.now()
        if expires_at:
            self.expires_at = expires_at
        self.save(update_fields=["status", "export_url", "export_payload", "completed_at", "expires_at"])
    
    def _log_state_change(self, new_status: str, actor=None):
        """Helper: log a GDPR export status transition to AuditLog."""
        AuditLog.log_action(
            user=actor or self.requested_by,
            action='gdpr_export',
            model_name='audit.gdprexportrequest',
            object_id=self.pk,
            object_repr=str(self),
            changes={'status': {'old': self.status, 'new': new_status}},
            school=self.school,
        )
