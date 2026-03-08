from django.contrib import admin
from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("admission_number", "user", "school", "parent")
    list_filter = ("school",)
    search_fields = ("admission_number", "user__username", "user__email")
    raw_id_fields = ("user", "parent")
