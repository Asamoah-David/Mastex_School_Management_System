from django.urls import path
from .views import login_view, dashboard

app_name = "accounts"

urlpatterns = [
    path("login/", login_view, name="login"),
    path("dashboard/", dashboard, name="dashboard"),
]
