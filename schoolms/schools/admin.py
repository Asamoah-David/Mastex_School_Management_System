from django.contrib import admin
from django.db import models
from django.db.models import Count
from .models import School


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "subdomain", "staff_count", "student_count", "parent_count", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "subdomain")
    prepopulated_fields = {"subdomain": ("name",)}
    list_editable = ("is_active",)
    ordering = ("-created_at",)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            staff_count=Count('user', filter=models.Q(user__role__in=['admin', 'teacher'])),
            student_count=Count('student'),
            parent_count=Count('user', filter=models.Q(user__role='parent'))
        )
    
    def staff_count(self, obj):
        return obj.staff_count
    staff_count.short_description = "Staff"
    
    def student_count(self, obj):
        return obj.student_count
    student_count.short_description = "Students"
    
    def parent_count(self, obj):
        return obj.parent_count
    parent_count.short_description = "Parents"


# Import models for the query
from django.db import models
