from django.urls import path
from . import views

app_name = "academics"

urlpatterns = [
    path("results/upload/", views.result_upload, name="result_upload"),
    path("results/", views.result_list, name="result_list"),
    path("grades/", views.grade_boundary_list, name="grade_boundary_list"),
    path("grades/create/", views.grade_boundary_create, name="grade_boundary_create"),
    path("homework/", views.homework_list, name="homework_list"),
    path("homework/create/", views.homework_create, name="homework_create"),
    path("exam-schedule/", views.exam_schedule_list, name="exam_schedule_list"),
    path("exam-schedule/create/", views.exam_schedule_create, name="exam_schedule_create"),
    path("report-card/<int:student_id>/", views.report_card_view, name="report_card"),
]
