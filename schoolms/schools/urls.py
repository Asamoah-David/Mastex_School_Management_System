from django.urls import path
from . import views

app_name = "schools"

urlpatterns = [
    path("list/", views.school_list, name="school_list"),
    path("features/<int:pk>/", views.school_features, name="school_features"),
    path("settings/", views.school_settings, name="school_settings"),
]
