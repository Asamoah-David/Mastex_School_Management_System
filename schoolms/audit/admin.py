import csv
import json

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse

from .models import AuditLog, GDPRExportRequest


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'user', 'action', 'model_name', 'object_repr', 'school']
    list_filter = ['action', 'model_name', 'timestamp', 'school']
    search_fields = ['user__username', 'model_name', 'object_repr', 'ip_address']
    readonly_fields = ['user', 'action', 'model_name', 'object_id', 'object_repr', 
                      'changes', 'ip_address', 'user_agent', 'timestamp', 'school']
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']
    actions = ['export_as_csv']

    @admin.action(description='Export selected rows to CSV (compliance / ERP archive)')
    def export_as_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="audit_log_export.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'timestamp', 'username', 'action', 'model_name', 'object_id', 'object_repr',
            'school', 'ip_address', 'user_agent', 'changes_json',
        ])
        for obj in queryset.iterator(chunk_size=500):
            ch = obj.changes if isinstance(obj.changes, str) else json.dumps(obj.changes or {}, ensure_ascii=False)
            writer.writerow([
                obj.timestamp.isoformat() if obj.timestamp else '',
                obj.user.get_username() if obj.user_id else '',
                obj.action,
                obj.model_name,
                obj.object_id or '',
                (obj.object_repr or '')[:500],
                obj.school.name if obj.school_id else '',
                obj.ip_address or '',
                (obj.user_agent or '')[:500],
                (ch or '')[:8000],
            ])
        return response
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        if getattr(settings, "AUDIT_APPEND_ONLY", False):
            return False
        return request.user.is_superuser


@admin.register(GDPRExportRequest)
class GDPRExportRequestAdmin(admin.ModelAdmin):
    list_display = ("subject_user", "school", "status", "requested_at", "completed_at", "expires_at")
    list_filter = ("status", "school")
    search_fields = ("subject_user__username", "subject_user__email", "school__name")
    readonly_fields = ("requested_at", "completed_at", "export_url", "error_message")
    raw_id_fields = ("subject_user", "requested_by", "school")
    date_hierarchy = "requested_at"

    def has_add_permission(self, request):
        return False
