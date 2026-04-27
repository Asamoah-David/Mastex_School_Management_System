from django.contrib import admin
from .models import (
    AcademicYear, Subject, Result, Timetable, ExamType, Term, GradeBoundary,
    Homework, HomeworkSubmission, ExamSchedule, Quiz, QuizAttempt,
    AssessmentType, AssessmentScore, ExamScore, GradingPolicy,
    OnlineMeeting, AIStudentComment, StudentTranscript,
)


class TermInline(admin.TabularInline):
    model = Term
    extra = 0
    fields = ("name", "is_current", "start_date", "end_date")
    show_change_link = True


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "start_date", "end_date", "is_current")
    list_select_related = ("school",)
    list_filter = ("school", "is_current")
    search_fields = ("name",)
    inlines = [TermInline]
    actions = ["mark_current"]

    @admin.action(description="Mark selected as current year (auto-unsets others)")
    def mark_current(self, request, queryset):
        for ay in queryset:
            ay.is_current = True
            ay.save()
        self.message_user(request, f"{queryset.count()} academic year(s) set as current.")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "is_core", "credit_weight")
    list_select_related = ("school",)
    list_filter = ("school", "is_core")
    search_fields = ("name",)


@admin.register(ExamType)
class ExamTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "school")
    list_select_related = ("school",)
    list_filter = ("school",)
    search_fields = ("name",)


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "is_current", "start_date", "end_date")
    list_select_related = ("school",)
    list_filter = ("school", "is_current")
    search_fields = ("name",)


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "exam_type", "term", "score", "grade", "created_at")
    list_select_related = (
        "student",
        "student__user",
        "student__school",
        "subject",
        "exam_type",
        "term",
    )
    list_filter = ("subject__school", "exam_type", "term")
    search_fields = ("student__user__first_name", "student__user__last_name", "student__admission_number")
    raw_id_fields = ("student", "created_by")
    date_hierarchy = "created_at"


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = ("class_name", "subject", "teacher", "day_of_week", "start_time", "end_time", "school")
    list_select_related = ("subject", "teacher", "school")
    list_filter = ("school", "day_of_week")
    search_fields = ("class_name", "subject__name")


@admin.register(GradeBoundary)
class GradeBoundaryAdmin(admin.ModelAdmin):
    list_display = ("grade", "min_score", "max_score", "school")
    list_select_related = ("school",)
    list_filter = ("school",)


@admin.register(Homework)
class HomeworkAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "class_name", "due_date", "school")
    list_select_related = ("subject", "school")
    list_filter = ("school", "class_name")
    search_fields = ("title", "subject__name")
    raw_id_fields = ("created_by",)


@admin.register(HomeworkSubmission)
class HomeworkSubmissionAdmin(admin.ModelAdmin):
    list_display = ("homework", "student", "submitted_at", "grade")
    list_select_related = ("homework", "homework__subject", "student", "student__user")
    list_filter = ("homework__school",)
    raw_id_fields = ("student", "homework")


@admin.register(ExamSchedule)
class ExamScheduleAdmin(admin.ModelAdmin):
    list_display = ("subject", "term", "class_name", "exam_date", "start_time", "end_time", "school")
    list_select_related = ("subject", "term", "school")
    list_filter = ("school", "term")
    search_fields = ("subject__name", "class_name")


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "class_name", "is_active", "due_date", "school")
    list_select_related = ("subject", "school")
    list_filter = ("school", "is_active")
    search_fields = ("title",)
    raw_id_fields = ("created_by",)


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("student", "quiz", "score", "is_completed", "started_at")
    list_select_related = ("student", "student__user", "quiz", "quiz__subject")
    list_filter = ("is_completed", "is_passed")
    raw_id_fields = ("student", "quiz")


## StudentClass is deprecated — use students.SchoolClass instead


@admin.register(AssessmentType)
class AssessmentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "is_active")
    list_select_related = ("school",)
    list_filter = ("school", "is_active")


@admin.register(AssessmentScore)
class AssessmentScoreAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "assessment_type", "score", "max_score", "term", "date")
    list_select_related = (
        "student",
        "student__user",
        "subject",
        "assessment_type",
        "term",
    )
    list_filter = ("assessment_type", "term")
    raw_id_fields = ("student",)


@admin.register(ExamScore)
class ExamScoreAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "score", "max_score", "term")
    list_select_related = ("student", "student__user", "subject", "term")
    list_filter = ("term",)
    raw_id_fields = ("student",)


@admin.register(GradingPolicy)
class GradingPolicyAdmin(admin.ModelAdmin):
    list_display = ("school", "pass_mark", "use_custom_grades", "use_weighted_averages")
    list_select_related = ("school",)


@admin.register(OnlineMeeting)
class OnlineMeetingAdmin(admin.ModelAdmin):
    list_display = ("title", "teacher", "class_name", "scheduled_time", "status", "school")
    list_select_related = ("teacher", "school")
    list_filter = ("school", "status")
    search_fields = ("title",)
    raw_id_fields = ("teacher",)


@admin.register(AIStudentComment)
class AIStudentCommentAdmin(admin.ModelAdmin):
    list_display = ("student", "term", "comment_type", "tone", "created_at")
    list_select_related = ("student", "student__user")
    list_filter = ("comment_type", "tone")
    raw_id_fields = ("student", "created_by")


@admin.register(StudentTranscript)
class StudentTranscriptAdmin(admin.ModelAdmin):
    list_display = ("student", "school", "academic_year", "term", "average_score", "gpa", "class_rank", "is_published")
    list_filter = ("school", "is_published", "academic_year")
    search_fields = ("student__user__first_name", "student__user__last_name", "student__admission_number")
    list_select_related = ("student", "student__user", "school", "academic_year", "term")
    readonly_fields = ("generated_at",)
    raw_id_fields = ("student", "school", "academic_year", "term")
    date_hierarchy = "generated_at"
    actions = ["publish_transcripts", "unpublish_transcripts"]

    @admin.action(description="Publish selected transcripts")
    def publish_transcripts(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f"{updated} transcript(s) published.")

    @admin.action(description="Unpublish selected transcripts")
    def unpublish_transcripts(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"{updated} transcript(s) unpublished.")
