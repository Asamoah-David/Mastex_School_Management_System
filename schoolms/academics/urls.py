from django.urls import path
from . import views

app_name = "academics"

urlpatterns = [
    path("results/upload/", views.result_upload, name="result_upload"),
    path("results/", views.result_list, name="result_list"),
]
