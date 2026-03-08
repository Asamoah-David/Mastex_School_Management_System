from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import login_view, dashboard

app_name = "accounts"

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", LogoutView.as_view(next_page="/accounts/login/"), name="logout"),
    path("dashboard/", dashboard, name="dashboard"),
]
