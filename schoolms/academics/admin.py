from django.contrib import admin
from .models import Subject, Result, Timetable, ExamType, Term


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "school")
    list_filter = ("school",)


@admin.register(ExamType)
class ExamTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "school")
    list_filter = ("school",)


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "is_current")
    list_filter = ("school",)


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "exam_type", "term", "score", "grade")
    list_filter = ("subject__school", "exam_type", "term")
    raw_id_fields = ("student",)


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = ("class_name", "subject", "day", "start_time", "end_time", "school")
    list_filter = ("school", "day")
