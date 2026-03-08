from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "school", "parent_type", "is_staff", "is_active")
    list_filter = ("role", "parent_type", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)
    filter_horizontal = ()

    fieldsets = BaseUserAdmin.fieldsets + (
        ("School & role", {"fields": ("role", "school", "phone", "parent_type")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("School & role", {"fields": ("role", "school", "phone", "parent_type")}),
    )
