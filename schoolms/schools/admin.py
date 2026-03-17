from django.contrib import admin
from .models import School, SchoolFeature


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "subdomain", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "subdomain")
    prepopulated_fields = {"subdomain": ("name",)}
    list_editable = ("is_active",)
    ordering = ("-created_at",)


@admin.register(SchoolFeature)
class SchoolFeatureAdmin(admin.ModelAdmin):
    list_display = ("school", "key", "enabled", "updated_at")
    list_filter = ("enabled", "key", "school")
    search_fields = ("school__name", "key")
    ordering = ("school__name", "key")
