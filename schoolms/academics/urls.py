from django.urls import path
from . import views

app_name = "academics"

urlpatterns = [
    path("results/upload/", views.result_upload, name="result_upload"),
    path("results/", views.result_list, name="result_list"),
    path("report-cards/", views.report_card_generator, name="report_card_generator"),
    path("report-cards/export-zip/", views.report_cards_export_zip, name="report_cards_export_zip"),
    path("grades/", views.grade_boundary_list, name="grade_boundary_list"),
    path("grades/create/", views.grade_boundary_create, name="grade_boundary_create"),
    path("homework/", views.homework_list, name="homework_list"),
    path("homework/create/", views.homework_create, name="homework_create"),
    path("exam-schedule/", views.exam_schedule_list, name="exam_schedule_list"),
    path("exam-schedule/create/", views.exam_schedule_create, name="exam_schedule_create"),
    path("timetable/", views.timetable_list, name="timetable_list"),
    path("timetable/create/", views.timetable_create, name="timetable_create"),
    path("timetable/<int:pk>/delete/", views.timetable_delete, name="timetable_delete"),
    path("timetable/my/", views.timetable_my, name="timetable_my"),
    path("report-card/<int:student_id>/", views.report_card_view, name="report_card"),
    path("report-card/<int:student_id>/pdf/", views.report_card_pdf, name="report_card_pdf"),
]
