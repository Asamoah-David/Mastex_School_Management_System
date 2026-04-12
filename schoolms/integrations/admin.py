from django.contrib import admin

from integrations.models import SchoolWebhookEndpoint


@admin.register(SchoolWebhookEndpoint)
class SchoolWebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "url_short", "is_active", "notify_staff_leave", "notify_expense", "created_at")
    list_filter = ("is_active", "notify_staff_leave", "notify_expense", "school")
    search_fields = ("name", "url", "school__name")
    raw_id_fields = ("school",)
    readonly_fields = ("created_at", "updated_at")

    @staticmethod
    def url_short(obj):
        u = obj.url or ""
        return u[:64] + ("…" if len(u) > 64 else "")

    fieldsets = (
        (None, {"fields": ("school", "name", "url", "signing_secret", "is_active")}),
        ("Events", {"fields": ("notify_staff_leave", "notify_expense")}),
        ("Meta", {"fields": ("created_at", "updated_at")}),
    )
