from django.contrib import admin
from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "notification_type", "is_read", "created_at")
    list_select_related = ("user",)
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("user__username", "title", "message")
    raw_id_fields = ("user",)
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "email_enabled", "sms_enabled", "push_enabled", "updated_at")
    list_select_related = ("user",)
    raw_id_fields = ("user",)
