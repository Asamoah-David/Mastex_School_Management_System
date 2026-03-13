from django.contrib import admin
from .models import Fee, FeeStructure


@admin.register(Fee)
class FeeAdmin(admin.ModelAdmin):
    list_display = ("student", "school", "amount", "paid", "created_at")
    list_filter = ("paid", "school")
    search_fields = ("student__admission_number", "student__user__username")
    raw_id_fields = ("student",)


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ("name", "amount", "class_name", "term", "school", "is_active")
    list_filter = ("school",)
