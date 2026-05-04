from django.contrib import admin
from .models import OmrExam, OmrResult, OmrExamSectionB


class OmrResultInline(admin.TabularInline):
    model = OmrResult
    extra = 0
    fields = ("student_name", "class_name", "score", "total_questions", "percentage", "correct_count", "wrong_count")
    readonly_fields = fields
    can_delete = True
    show_change_link = True


@admin.register(OmrExam)
class OmrExamAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "class_name", "date", "template_type", "total_questions", "answer_key_confirmed", "result_count", "school")
    list_filter = ("template_type", "answer_key_confirmed", "school")
    search_fields = ("title", "subject", "class_name")
    readonly_fields = ("created_at", "updated_at", "result_count")
    inlines = [OmrResultInline]

    def result_count(self, obj):
        return obj.result_count
    result_count.short_description = "Results"


@admin.register(OmrResult)
class OmrResultAdmin(admin.ModelAdmin):
    list_display = ("get_student_display_name", "exam", "score", "total_questions", "percentage", "correct_count", "wrong_count", "blank_count", "created_at")
    list_filter = ("exam__template_type", "school")
    search_fields = ("student_name", "exam__title", "class_name")
    readonly_fields = ("created_at", "per_question_result", "detected_answers", "answer_key")


@admin.register(OmrExamSectionB)
class OmrExamSectionBAdmin(admin.ModelAdmin):
    list_display = ("get_student_display_name", "exam", "section_b_score", "section_b_max_score", "section_a_effective", "total_raw_score", "total_percentage", "school")
    list_filter = ("school", "exam")
    search_fields = ("student_name", "exam__title")
    readonly_fields = ("created_at", "updated_at", "section_a_effective", "total_raw_score", "total_max_score", "total_percentage")
