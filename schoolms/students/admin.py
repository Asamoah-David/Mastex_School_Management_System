from django.contrib import admin
from django.db.models import Count
from .models import (
    Student, SchoolClass, StudentAchievement, StudentActivity,
    StudentDiscipline, AbsenceRequest, StudentGuardian, StudentClearance,
    LearningPlan,
)


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "class_teacher", "capacity", "student_count")
    list_select_related = ("school", "class_teacher")
    list_filter = ("school",)
    search_fields = ("name",)
    raw_id_fields = ("class_teacher",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_student_count=Count("students", distinct=True))

    def student_count(self, obj):
        return obj._student_count
    student_count.short_description = "Students"
    student_count.admin_order_field = "_student_count"


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("admission_number", "user", "class_name", "status", "school", "parent")
    list_select_related = ("user", "school", "parent")
    list_filter = ("school", "status", "class_name")
    search_fields = ("admission_number", "user__username", "user__first_name", "user__last_name", "user__email")
    raw_id_fields = ("user", "parent")
    list_editable = ("status",)


@admin.register(StudentAchievement)
class StudentAchievementAdmin(admin.ModelAdmin):
    list_display = ("student", "title", "achievement_type", "date_achieved", "school")
    list_select_related = ("student", "student__user", "school")
    list_filter = ("school", "achievement_type")
    search_fields = ("title", "student__user__first_name", "student__user__last_name")
    raw_id_fields = ("student",)


@admin.register(StudentActivity)
class StudentActivityAdmin(admin.ModelAdmin):
    list_display = ("student", "activity_name", "activity_type", "position", "start_date")
    list_select_related = ("student", "student__user")
    list_filter = ("school", "activity_type")
    raw_id_fields = ("student",)


@admin.register(StudentDiscipline)
class StudentDisciplineAdmin(admin.ModelAdmin):
    list_display = ("student", "title", "incident_type", "incident_date")
    list_select_related = ("student", "student__user")
    list_filter = ("school", "incident_type")
    raw_id_fields = ("student", "reported_by")


@admin.register(AbsenceRequest)
class AbsenceRequestAdmin(admin.ModelAdmin):
    list_display = ("student", "date", "status", "created_at")
    list_select_related = ("student", "student__user")
    list_filter = ("school", "status")
    raw_id_fields = ("student", "submitted_by", "decided_by")


class StudentGuardianInline(admin.TabularInline):
    model = StudentGuardian
    extra = 0
    fields = ("guardian", "relationship", "is_primary", "can_pickup", "emergency_contact")
    raw_id_fields = ("guardian",)


@admin.register(StudentGuardian)
class StudentGuardianAdmin(admin.ModelAdmin):
    list_display = ("student", "guardian", "relationship", "is_primary", "can_pickup", "emergency_contact")
    list_select_related = ("student", "student__user", "guardian")
    list_filter = ("relationship", "is_primary", "can_pickup", "emergency_contact")
    search_fields = (
        "student__admission_number",
        "student__user__first_name",
        "student__user__last_name",
        "guardian__first_name",
        "guardian__last_name",
    )
    raw_id_fields = ("student", "guardian")


@admin.register(StudentClearance)
class StudentClearanceAdmin(admin.ModelAdmin):
    list_display = ("student", "fees_cleared", "library_cleared", "id_card_returned", "is_complete_display", "updated_at")

    def is_complete_display(self, obj):
        return obj.is_complete
    is_complete_display.boolean = True
    is_complete_display.short_description = "Complete"
    list_select_related = ("student", "student__user")
    list_filter = ("fees_cleared", "library_cleared")
    search_fields = ("student__admission_number", "student__user__first_name", "student__user__last_name")
    raw_id_fields = ("student", "updated_by")


@admin.register(LearningPlan)
class LearningPlanAdmin(admin.ModelAdmin):
    list_display = ("student", "plan_type", "status", "academic_year", "start_date", "review_date", "parent_acknowledged", "school")
    list_select_related = ("student", "student__user", "school")
    list_filter = ("school", "plan_type", "status", "academic_year", "parent_acknowledged")
    search_fields = ("student__user__first_name", "student__user__last_name", "student__admission_number")
    raw_id_fields = ("student", "created_by", "last_updated_by")
    readonly_fields = ("created_at", "updated_at", "parent_acknowledged_at")
    fieldsets = (
        (None, {
            "fields": ("school", "student", "plan_type", "status", "academic_year"),
        }),
        ("Dates", {
            "fields": ("start_date", "review_date", "end_date"),
        }),
        ("Plan Content", {
            "fields": ("goals", "accommodations", "support_resources", "progress_notes"),
        }),
        ("Parental Acknowledgement", {
            "fields": ("parent_acknowledged", "parent_acknowledged_at"),
        }),
        ("Audit", {
            "fields": ("created_by", "last_updated_by", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
