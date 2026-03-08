from django.urls import path
from .views import (
    login_view, logout_view, dashboard, 
    staff_list, staff_detail, staff_register,
    parent_list, parent_register, parent_detail,
    user_management
)

app_name = "accounts"

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("dashboard/", dashboard, name="dashboard"),
    path("users/", user_management, name="user_management"),
    path("staff/", staff_list, name="staff_list"),
    path("staff/register/", staff_register, name="staff_register"),
    path("staff/<int:pk>/", staff_detail, name="staff_detail"),
    path("parents/", parent_list, name="parent_list"),
    path("parents/register/", parent_register, name="parent_register"),
    path("parents/<int:pk>/", parent_detail, name="parent_detail"),
]
