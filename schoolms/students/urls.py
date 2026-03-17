from django.urls import path
from .views import (
    parent_dashboard,
    student_list,
    student_detail,
    student_register,
    student_delete,
    student_reactivate,
    promote_students,
    class_list,
    class_create,
    announcements_list,
    fees_list,
    results_list,
    parent_child_detail,
    absence_request_create,
    my_absence_requests,
    parent_absence_request_create,
    parent_absence_requests,
    absence_requests_review,
    absence_request_decide,
)

app_name = "students"

urlpatterns = [
    path("parent-dashboard/", parent_dashboard, name="parent_dashboard"),
    path("announcements/", announcements_list, name="announcements_list"),
    path("fees/", fees_list, name="fees_list"),
    path("results/", results_list, name="results_list"),
    path("children/<int:pk>/", parent_child_detail, name="parent_child_detail"),
    path("list/", student_list, name="student_list"),
    path("detail/<int:pk>/", student_detail, name="student_detail"),
    path("register/", student_register, name="student_register"),
    path("delete/<int:pk>/", student_delete, name="student_delete"),
    path("reactivate/<int:pk>/", student_reactivate, name="student_reactivate"),
    path("promote/", promote_students, name="promote_students"),
    path("classes/", class_list, name="class_list"),
    path("classes/create/", class_create, name="class_create"),
    # Student absence requests
    path("absence/request/", absence_request_create, name="absence_request_create"),
    path("absence/my/", my_absence_requests, name="my_absence_requests"),
    # Parent absence requests (for linked children)
    path("absence/children/request/", parent_absence_request_create, name="parent_absence_request_create"),
    path("absence/children/", parent_absence_requests, name="parent_absence_requests"),
    path("absence/review/", absence_requests_review, name="absence_requests_review"),
    path(
        "absence/<int:pk>/<str:decision>/",
        absence_request_decide,
        name="absence_request_decide",
    ),
]
