from django.urls import path
from . import views

app_name = "omr"

urlpatterns = [
    path("", views.omr_dashboard, name="dashboard"),
    path("create/", views.omr_exam_create, name="exam_create"),
    path("<int:pk>/", views.omr_exam_detail, name="exam_detail"),
    path("<int:pk>/delete/", views.omr_exam_delete, name="exam_delete"),

    # Answer key
    path("<int:pk>/answer-key/upload/", views.omr_answer_key_upload, name="answer_key_upload"),
    path("<int:pk>/answer-key/review/", views.omr_answer_key_review, name="answer_key_review"),

    # Student sheets
    path("<int:pk>/students/upload/", views.omr_student_upload, name="student_upload"),
    path("<int:pk>/students/review/", views.omr_student_review, name="student_review"),
    path("<int:pk>/students/bulk/", views.omr_bulk_upload, name="bulk_upload"),

    # Results
    path("<int:pk>/results/", views.omr_results, name="results"),
    path("<int:pk>/results/export/", views.omr_export_csv, name="export_csv"),
    path("<int:pk>/analysis/", views.omr_analysis, name="analysis"),

    # Individual result
    path("result/<int:result_pk>/", views.omr_result_detail, name="result_detail"),
    path("result/<int:result_pk>/delete/", views.omr_result_delete, name="result_delete"),

    # Printable sheet
    path("sheet/<str:template_id>/", views.omr_printable_sheet, name="printable_sheet"),

    # Section B — manual mark entry
    path("<int:pk>/section-b/", views.omr_section_b_entry, name="section_b_entry"),
]
