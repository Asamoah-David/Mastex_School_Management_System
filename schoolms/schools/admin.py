from django.contrib import admin
from .models import School


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "subdomain", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "subdomain")
    prepopulated_fields = {"subdomain": ("name",)}
    list_editable = ("is_active",)
    ordering = ("-created_at",)
