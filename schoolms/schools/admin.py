from django.contrib import admin
from django.db.models import Count, Q
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
            staff_count=Count('user', filter=Q(role__in=['admin', 'teacher'])),
            student_count=Count('student'),
            parent_count=Count('user', filter=Q(role='parent'))
        )
    
    def staff_count(self, obj):
        return getattr(obj, 'staff_count', 0)
    staff_count.short_description = "Staff"
    
    def student_count(self, obj):
        return getattr(obj, 'student_count', 0)
    student_count.short_description = "Students"
    
    def parent_count(self, obj):
        return getattr(obj, 'parent_count', 0)
    parent_count.short_description = "Parents"
