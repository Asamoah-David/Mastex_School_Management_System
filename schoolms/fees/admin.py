from django.contrib import admin
from .models import SubscriptionPlan, SchoolSubscription, PaymentReminder


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    """DEPRECATED model — read-only display only; new records are blocked."""
    list_display = ("name", "price", "duration_days", "max_students", "max_staff", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("name", "description", "price", "duration_days", "max_students", "max_staff", "features", "is_active", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SchoolSubscription)
class SchoolSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("school", "plan", "status", "started_at", "expires_at", "auto_renew")
    list_filter = ("status", "plan")
    list_select_related = ("school", "plan")
    search_fields = ("school__name",)
    readonly_fields = ("started_at", "created_at", "updated_at")


@admin.register(PaymentReminder)
class PaymentReminderAdmin(admin.ModelAdmin):
    list_display = ("student", "fee", "reminder_type", "reminder_date", "sent", "sent_at")
    list_filter = ("reminder_type", "sent")
    list_select_related = ("student", "fee")
    readonly_fields = ("created_at",)
