from django.urls import path
from .views import parent_dashboard, student_list, student_detail, student_register, student_delete

app_name = "students"

urlpatterns = [
    path("parent-dashboard/", parent_dashboard, name="parent_dashboard"),
    path("list/", student_list, name="student_list"),
    path("detail/<int:pk>/", student_detail, name="student_detail"),
    path("register/", student_register, name="student_register"),
    path("delete/<int:pk>/", student_delete, name="student_delete"),
]
