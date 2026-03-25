from django.urls import path
from . import views

app_name = "academics"

urlpatterns = [
    path("results/upload/", views.result_upload, name="result_upload"),
    path("results/", views.result_list, name="result_list"),
    path("results/<int:pk>/edit/", views.result_edit, name="result_edit"),
    path("results/<int:pk>/delete/", views.result_delete, name="result_delete"),
    path("report-cards/", views.report_card_generator, name="report_card_generator"),
    path("report-cards/export-zip/", views.report_cards_export_zip, name="report_cards_export_zip"),
    path("grades/", views.grade_boundary_list, name="grade_boundary_list"),
    path("grades/create/", views.grade_boundary_create, name="grade_boundary_create"),
    path("homework/", views.homework_list, name="homework_list"),
    path("homework/create/", views.homework_create, name="homework_create"),
    path("homework/<int:pk>/edit/", views.homework_edit, name="homework_edit"),
    path("homework/<int:pk>/delete/", views.homework_delete, name="homework_delete"),
    path("exam-schedule/", views.exam_schedule_list, name="exam_schedule_list"),
    path("exam-schedule/create/", views.exam_schedule_create, name="exam_schedule_create"),
    path("exam-schedule/<int:pk>/edit/", views.exam_schedule_edit, name="exam_schedule_edit"),
    path("exam-schedule/<int:pk>/delete/", views.exam_schedule_delete, name="exam_schedule_delete"),
    path("timetable/", views.timetable_list, name="timetable_list"),
    path("timetable/create/", views.timetable_create, name="timetable_create"),
    path("timetable/<int:pk>/delete/", views.timetable_delete, name="timetable_delete"),
    path("timetable/my/", views.timetable_my, name="timetable_my"),
    path("report-card/<int:student_id>/", views.report_card_view, name="report_card"),
    path("report-card/<int:student_id>/pdf/", views.report_card_pdf, name="report_card_pdf"),
    
    # Quiz URLs
    path("quizzes/", views.quiz_list, name="quiz_list"),
    path("quizzes/create/", views.quiz_create, name="quiz_create"),
    path("quizzes/<int:pk>/", views.quiz_detail, name="quiz_detail"),
    path("quizzes/<int:pk>/edit/", views.quiz_edit, name="quiz_edit"),
    path("quizzes/<int:pk>/delete/", views.quiz_delete, name="quiz_delete"),
    path("quizzes/<int:pk>/add-question/", views.quiz_add_question, name="quiz_add_question"),
    path("quizzes/<int:pk>/take/", views.quiz_take, name="quiz_take"),
    path("quizzes/<int:pk>/result/", views.quiz_result, name="quiz_result"),
    
    # Analytics
    path("analytics/", views.performance_analytics, name="performance_analytics"),
    
    # NEW: Comprehensive Grading System URLs
    path("grading-policy/", views.grading_policy_view, name="grading_policy"),
    path("grading-policy/update/", views.grading_policy_update, name="grading_policy_update"),
    path("assessment-types/", views.assessment_type_list, name="assessment_type_list"),
    path("assessment-types/create/", views.assessment_type_create, name="assessment_type_create"),
    path("assessment-scores/", views.assessment_score_list, name="assessment_score_list"),
    path("assessment-scores/upload/", views.assessment_score_upload, name="assessment_score_upload"),
    path("exam-scores/", views.exam_score_list, name="exam_score_list"),
    path("exam-scores/upload/", views.exam_score_upload, name="exam_score_upload"),
    path("rankings/", views.class_rankings, name="class_rankings"),
    path("result-summary/generate/", views.generate_result_summary, name="generate_result_summary"),
    path("enhanced-report-card/<int:student_id>/", views.enhanced_report_card, name="enhanced_report_card"),
    path("enhanced-report-card/<int:student_id>/pdf/", views.enhanced_report_card_pdf, name="enhanced_report_card_pdf"),
]
