from django.contrib import admin
from .models import Fee


@admin.register(Fee)
class FeeAdmin(admin.ModelAdmin):
    list_display = ("student", "school", "amount", "paid", "created_at")
    list_filter = ("paid", "school")
    search_fields = ("student__admission_number", "student__user__username")
    raw_id_fields = ("student",)
