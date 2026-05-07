from django.contrib import admin

from .models import AsyncJob


@admin.register(AsyncJob)
class AsyncJobAdmin(admin.ModelAdmin):
    list_display = ("id", "job_type", "status", "school", "celery_task_id", "created_at", "completed_at")
    list_filter = ("status", "job_type")
    search_fields = ("celery_task_id", "error_message")
    readonly_fields = ("created_at", "started_at", "completed_at")
    raw_id_fields = ("school", "created_by")
