from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Conversation(models.Model):
    """A conversation thread between users."""
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, null=True, blank=True,
        related_name="conversations",
    )
    subject = models.CharField(max_length=255, blank=True)
    participants = models.ManyToManyField(User, related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Conversation"
        verbose_name_plural = "Conversations"
        indexes = [
            models.Index(fields=["school", "updated_at"], name="idx_conv_school_updated"),
        ]

    def __str__(self):
        return self.subject or f"Conversation {self.id}"


class Message(models.Model):
    """A message within a conversation."""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        indexes = [
            models.Index(fields=["recipient", "is_read"], name="idx_msg_recipient_read"),
        ]

    def __str__(self):
        return f"{self.sender} to {self.recipient}: {self.subject[:50]}"


class BroadcastNotification(models.Model):
    """Broadcast notifications sent to multiple users."""
    MESSAGE_TYPE_CHOICES = [
        ('announcement', 'Announcement'),
        ('alert', 'Alert'),
        ('reminder', 'Reminder'),
    ]
    
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, null=True, blank=True,
        related_name="broadcast_notifications",
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default='announcement')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='broadcasts_sent')
    recipients = models.ManyToManyField(User, related_name='broadcasts_received', blank=True)
    target_class = models.CharField(max_length=50, blank=True, help_text="Target class for class-wide broadcasts")
    target_role = models.CharField(max_length=50, blank=True, help_text="Target role for role-based broadcasts")
    is_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title