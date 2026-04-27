from django.contrib import admin
from .models import AIChatSession, ConversationHistory, PromptTemplate


class ConversationHistoryInline(admin.TabularInline):
    model = ConversationHistory
    extra = 0
    readonly_fields = ("role", "content", "token_count", "created_at")
    can_delete = False
    max_num = 0
    ordering = ("created_at",)


@admin.register(AIChatSession)
class AIChatSessionAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "school", "total_tokens", "is_active", "created_at", "updated_at")
    list_select_related = ("user", "school")
    list_filter = ("school", "is_active")
    search_fields = ("title", "session_id", "user__username", "user__email")
    readonly_fields = ("session_id", "created_at", "updated_at", "total_tokens")
    raw_id_fields = ("user", "school")
    inlines = [ConversationHistoryInline]
    date_hierarchy = "created_at"

    actions = ["deactivate_sessions"]

    @admin.action(description="Deactivate selected sessions")
    def deactivate_sessions(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} session(s) deactivated.")


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "category", "is_active", "updated_at")
    list_select_related = ("school",)
    list_filter = ("is_active", "category", "school")
    search_fields = ("name", "description", "system_prompt")
    raw_id_fields = ("school",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("school", "name", "description", "category", "is_active")}),
        ("Prompts", {"fields": ("system_prompt", "user_prompt_template")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
