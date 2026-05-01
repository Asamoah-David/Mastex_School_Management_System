from django.contrib import admin
from .models import JobPosting, JobApplication, InterviewSchedule


class JobApplicationInline(admin.TabularInline):
    model = JobApplication
    extra = 0
    fields = ("reference", "full_name", "email", "payment_status", "status", "submitted_at")
    readonly_fields = ("reference", "full_name", "email", "payment_status", "status", "submitted_at")
    show_change_link = True
    can_delete = False


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = ("title", "school", "job_type", "deadline", "slots_available", "application_fee", "is_active")
    list_select_related = ("school", "created_by")
    list_filter = ("school", "job_type", "is_active")
    search_fields = ("title", "reference_code", "school__name")
    readonly_fields = ("reference_code", "created_at", "updated_at")
    raw_id_fields = ("created_by",)
    inlines = [JobApplicationInline]
    actions = ["activate_jobs", "deactivate_jobs"]

    @admin.action(description="Activate selected job postings")
    def activate_jobs(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, "Jobs activated.")

    @admin.action(description="Deactivate selected job postings")
    def deactivate_jobs(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, "Jobs deactivated.")


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ("reference", "full_name", "email", "job", "payment_status", "status", "submitted_at")
    list_select_related = ("job", "job__school", "reviewed_by")
    list_filter = ("payment_status", "status", "job__school")
    search_fields = ("reference", "full_name", "email", "phone", "job__title")
    readonly_fields = ("reference", "paystack_reference", "amount_paid", "applied_at", "submitted_at")
    raw_id_fields = ("reviewed_by",)
    date_hierarchy = "applied_at"
    actions = ["shortlist", "reject"]

    @admin.action(description="Shortlist selected applications")
    def shortlist(self, request, queryset):
        queryset.filter(payment_status="paid").update(status="shortlisted")
        self.message_user(request, "Applications shortlisted.")

    @admin.action(description="Reject selected applications")
    def reject(self, request, queryset):
        queryset.update(status="rejected")
        self.message_user(request, "Applications rejected.")


@admin.register(InterviewSchedule)
class InterviewScheduleAdmin(admin.ModelAdmin):
    list_display = ("application", "interview_date", "interview_time", "mode", "notified_at")
    list_select_related = ("application", "application__job", "scheduled_by")
    list_filter = ("mode", "interview_date")
    search_fields = ("application__full_name", "application__reference", "application__job__title")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("scheduled_by",)
    date_hierarchy = "interview_date"
