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
        ('inventory_alert', 'Inventory Alert'),
        ('leave_approved', 'Leave Approved'),
        ('purchase_order', 'Purchase Order'),
        ('subscription', 'Subscription'),
        ('fee_reminder', 'Fee Reminder'),
        ('academic_event', 'Academic Event'),
        ('contract_expiry', 'Contract Expiry'),
        ('installment_overdue', 'Installment Overdue'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        help_text="School context for tenant-scoped queries and reporting.",
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='info')
    link = models.CharField(max_length=500, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="When set, the notification is eligible for auto-purge after this timestamp.",
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        indexes = [
            models.Index(fields=["user", "is_read"], name="idx_notif_user_read"),
            models.Index(fields=["school", "created_at"], name="idx_notif_school_created"),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.title}"

    @classmethod
    def create_notification(cls, user, title, message, notification_type='info', link=None, include_school=True, school=None):
        """Helper method to create a notification.

        ``school`` overrides ``user.school`` when explicitly provided.
        ``include_school=False`` suppresses the [School Name] prefix.
        """
        resolved_school = school if school is not None else getattr(user, 'school', None)
        if include_school and resolved_school:
            title = f"[{resolved_school.name}] {title}"
        notif = cls.objects.create(
            user=user,
            school=resolved_school,
            title=title,
            message=message,
            notification_type=notification_type,
            link=link
        )
        cls._invalidate_count_cache(user.pk)
        return notif
    
    @classmethod
    def get_unread_count(cls, user):
        """Get count of unread notifications for a user (cache-first)."""
        from django.core.cache import cache
        uid = user.pk if hasattr(user, 'pk') else user
        key = f"notif_count:{uid}"
        count = cache.get(key)
        if count is None:
            count = cls.objects.filter(user_id=uid, is_read=False).count()
            cache.set(key, count, 60)
        return count
    
    def mark_as_read(self):
        """Mark notification as read."""
        self.is_read = True
        self.save(update_fields=["is_read"])
        self._invalidate_count_cache(self.user_id)
    
    @classmethod
    def mark_all_as_read(cls, user):
        """Mark all notifications as read for a user."""
        cls.objects.filter(user=user, is_read=False).update(is_read=True)
        cls._invalidate_count_cache(user.pk if hasattr(user, "pk") else user)

    @staticmethod
    def _invalidate_count_cache(user_pk):
        from django.core.cache import cache
        cache.delete(f"notif_count:{user_pk}")


class NotificationPreference(models.Model):
    """User notification preferences — controls which notification types reach the user."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    push_enabled = models.BooleanField(default=True)

    payment_alerts = models.BooleanField(default=True)
    attendance_alerts = models.BooleanField(default=True)
    result_alerts = models.BooleanField(default=True)
    message_alerts = models.BooleanField(default=True)
    announcement_alerts = models.BooleanField(default=True)

    fee_reminder_alerts = models.BooleanField(default=True)
    academic_event_alerts = models.BooleanField(default=True)
    contract_expiry_alerts = models.BooleanField(default=True)
    installment_overdue_alerts = models.BooleanField(default=True)
    inventory_alerts = models.BooleanField(default=True)
    leave_alerts = models.BooleanField(default=True)
    purchase_order_alerts = models.BooleanField(default=True)
    subscription_alerts = models.BooleanField(default=True)

    muted_until = models.DateTimeField(
        null=True, blank=True,
        help_text="Snooze all in-app notifications until this timestamp.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    _TYPE_FIELD_MAP = {
        "payment": "payment_alerts",
        "attendance": "attendance_alerts",
        "result": "result_alerts",
        "message": "message_alerts",
        "info": "announcement_alerts",
        "fee_reminder": "fee_reminder_alerts",
        "academic_event": "academic_event_alerts",
        "contract_expiry": "contract_expiry_alerts",
        "installment_overdue": "installment_overdue_alerts",
        "inventory_alert": "inventory_alerts",
        "leave_approved": "leave_alerts",
        "purchase_order": "purchase_order_alerts",
        "subscription": "subscription_alerts",
    }

    def __str__(self):
        return f"Preferences for {self.user.username}"

    def allows(self, notification_type: str) -> bool:
        """Return True if the user has not muted this notification type."""
        from django.utils import timezone
        if self.muted_until and self.muted_until > timezone.now():
            return False
        field = self._TYPE_FIELD_MAP.get(notification_type)
        if field:
            return bool(getattr(self, field, True))
        return True

    @classmethod
    def get_or_create_preferences(cls, user):
        """Get or create notification preferences for a user."""
        return cls.objects.get_or_create(user=user)[0]
