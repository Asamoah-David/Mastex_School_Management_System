from django.contrib import admin
from .models import Student, SchoolClass, StudentAchievement, StudentActivity, StudentDiscipline, AbsenceRequest


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "class_teacher", "capacity")
    list_select_related = ("school", "class_teacher")
    list_filter = ("school",)
    search_fields = ("name",)
    raw_id_fields = ("class_teacher",)


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
