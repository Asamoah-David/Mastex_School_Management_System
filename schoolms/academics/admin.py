from django.contrib import admin
from .models import Subject, Result, Timetable


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "school")
    list_filter = ("school",)


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "score")
    list_filter = ("subject__school",)
    raw_id_fields = ("student",)


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = ("class_name", "subject", "day", "start_time", "end_time", "school")
    list_filter = ("school", "day")
