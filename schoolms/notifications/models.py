from django.db import models
from django.conf import settings

class Notification(models.Model):
    TYPE_CHOICES = [
        ('info', 'Information'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('payment', 'Payment'),
        ('attendance', 'Attendance'),
        ('result', 'Result'),
        ('message', 'Message'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='info')
    link = models.CharField(max_length=500, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username}: {self.title}"
    
    @classmethod
    def create_notification(cls, user, title, message, notification_type='info', link=None):
        """Helper method to create a notification"""
        return cls.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
            link=link
        )
    
    @classmethod
    def get_unread_count(cls, user):
        """Get count of unread notifications for a user"""
        return cls.objects.filter(user=user, is_read=False).count()
    
    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        self.save()
    
    def mark_all_as_read(cls, user):
        """Mark all notifications as read for a user"""
        cls.objects.filter(user=user, is_read=False).update(is_read=True)
