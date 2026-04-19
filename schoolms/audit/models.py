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
        ('view', 'Viewed'),
        ('export', 'Exported'),
        ('import', 'Imported'),
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
        """Helper method to create an audit log entry."""
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
            kwargs['request_id'] = (getattr(request, 'request_id', None) or request.META.get('HTTP_X_REQUEST_ID', '') or '')[:64]
        
        if school:
            kwargs['school'] = school
        elif hasattr(user, 'school'):
            kwargs['school'] = user.school
        
        return cls.objects.create(**kwargs)
    
    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request, handling proxies."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
