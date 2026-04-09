from django.contrib import admin
from .models import Conversation, Message, BroadcastNotification


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("subject", "created_at", "updated_at", "is_active")
    list_filter = ("is_active",)
    search_fields = ("subject",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "recipient", "subject", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = ("subject", "sender__username", "recipient__username")
    raw_id_fields = ("sender", "recipient", "conversation")


@admin.register(BroadcastNotification)
class BroadcastNotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "message_type", "sender", "is_sent", "sent_at", "created_at")
    list_filter = ("message_type", "is_sent")
    search_fields = ("title",)
    raw_id_fields = ("sender",)
