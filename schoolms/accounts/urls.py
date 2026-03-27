from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (
    login_view,
    logout_view,
    profile,
    edit_profile,
    dashboard,
    school_dashboard,
    staff_list,
    staff_detail,
    staff_register,
    staff_delete,
    staff_reactivate,
    staff_change_role,
    parent_list,
    parent_register,
    parent_detail,
    parent_delete,
    parent_reactivate,
    user_management,
    reset_user_password,
    superuser_edit_credentials,
)
from .forms import SecurePasswordResetForm, PasswordResetConfirmForm

app_name = "accounts"

urlpatterns = [
    # Password reset URLs - Using secure form with validation
    path("password_reset/", auth_views.PasswordResetView.as_view(
        template_name="registration/password_reset_form.html",
        email_template_name="registration/password_reset_email.html",
        subject_template_name="registration/password_reset_subject.txt",
        form_class=SecurePasswordResetForm,
        success_url='/accounts/password_reset/done/'
    ), name="password_reset"),
    path("password_reset/done/", auth_views.PasswordResetDoneView.as_view(
        template_name="registration/password_reset_done.html"
    ), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="registration/password_reset_confirm.html",
        form_class=PasswordResetConfirmForm,
        success_url='/accounts/reset/done/'
    ), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="registration/password_reset_complete.html"
    ), name="password_reset_complete"),
    
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("profile/", profile, name="profile"),
    path("profile/edit/", edit_profile, name="edit_profile"),
    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(template_name="registration/password_change_form.html"),
        name="password_change",
    ),
    path(
        "password/change/done/",
        auth_views.PasswordChangeDoneView.as_view(template_name="registration/password_change_done.html"),
        name="password_change_done",
    ),
    path("dashboard/", dashboard, name="dashboard"),
    path("school-dashboard/", school_dashboard, name="school_dashboard"),
    path("users/", user_management, name="user_management"),
    path("staff/", staff_list, name="staff_list"),
    path("staff/register/", staff_register, name="staff_register"),
    path("staff/<int:pk>/", staff_detail, name="staff_detail"),
    path("staff/<int:pk>/delete/", staff_delete, name="staff_delete"),
    path("staff/<int:pk>/reactivate/", staff_reactivate, name="staff_reactivate"),
    path("staff/<int:pk>/change-role/", staff_change_role, name="staff_change_role"),
    path("parents/", parent_list, name="parent_list"),
    path("parents/register/", parent_register, name="parent_register"),
    path("parents/<int:pk>/", parent_detail, name="parent_detail"),
    path("parents/<int:pk>/delete/", parent_delete, name="parent_delete"),
    path("parents/<int:pk>/reactivate/", parent_reactivate, name="parent_reactivate"),
    # Admin-led password reset and credential changes
    path("users/<int:pk>/reset-password/", reset_user_password, name="reset_user_password"),
    path(
        "superuser/users/<int:pk>/credentials/",
        superuser_edit_credentials,
        name="superuser_edit_credentials",
    ),
]
