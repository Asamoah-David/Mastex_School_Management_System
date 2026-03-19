from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "school", "parent_type", "is_staff", "is_active", "date_joined")
    list_filter = ("role", "parent_type", "is_staff", "is_active", "school")
    search_fields = ("username", "email", "first_name", "last_name", "phone")
    ordering = ("-date_joined",)
    filter_horizontal = ()

    fieldsets = BaseUserAdmin.fieldsets + (
        ("School & Role", {"fields": ("role", "school", "phone", "parent_type")}),
        ("Permissions", {"fields": ("is_super_admin",)}),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("School & Role", {"fields": ("role", "school", "phone", "parent_type")}),
        ("Permissions", {"fields": ("is_super_admin", "is_staff", "is_active")}),
    )
    
    # Make role editable in list view
    list_editable = ("role", "is_staff", "is_active")
    
    actions = ["activate_users", "deactivate_users", "change_to_teacher", "change_to_parent"]

    @admin.action(description="Activate selected users")
    def activate_users(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"{queryset.count()} user(s) activated.")

    @admin.action(description="Deactivate selected users")
    def deactivate_users(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} user(s) deactivated.")

    @admin.action(description="Change role to Teacher")
    def change_to_teacher(self, request, queryset):
        updated = queryset.update(role="teacher")
        self.message_user(request, f"{updated} user(s) changed to Teacher role.")

    @admin.action(description="Change role to Parent")
    def change_to_parent(self, request, queryset):
        updated = queryset.update(role="parent")
        self.message_user(request, f"{updated} user(s) changed to Parent role.")
