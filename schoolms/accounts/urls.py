from django.urls import path
from accounts.superadmin_views import superadmin_metrics

from django.contrib.auth import views as auth_views
from .views import (
    login_view,
    logout_view,
    sms_otp_reset_request,
    sms_otp_reset_confirm,
    profile,
    edit_profile,
    dismiss_setup_checklist,
    force_password_change,
    dashboard,
    school_dashboard,
    staff_list,
    staff_detail,
    staff_register,
    staff_delete,
    staff_reactivate,
    staff_change_role,
    staff_manage_secondary_roles,
    parent_list,
    parent_register,
    parent_detail,
    parent_edit,
    parent_delete,
    parent_reactivate,
    user_management,
    reset_user_password,
    superuser_edit_credentials,
    global_search,
    teacher_dashboard,
)
from .forms import SecurePasswordResetForm, PasswordResetConfirmForm
from . import hr_views, totp_views

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
    path("force-password-change/", force_password_change, name="force_password_change"),
    path("profile/", profile, name="profile"),
    path("profile/edit/", edit_profile, name="edit_profile"),
    path("setup-checklist/dismiss/", dismiss_setup_checklist, name="dismiss_setup_checklist"),
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
    path("teacher-dashboard/", teacher_dashboard, name="teacher_dashboard"),
    path("search/", global_search, name="global_search"),
    path("users/", user_management, name="user_management"),
    path("staff/", staff_list, name="staff_list"),
    path("staff/payroll-register/", hr_views.staff_payroll_register, name="staff_payroll_register"),
    path("staff/payroll-bulk/", hr_views.staff_payroll_bulk_record, name="staff_payroll_bulk_record"),
    path(
        "staff/payroll/payment/<int:payment_id>/payslip/",
        hr_views.staff_payroll_payslip,
        name="staff_payroll_payslip",
    ),
    path("my-payroll/", hr_views.staff_my_payroll, name="staff_my_payroll"),
    path("staff/<int:pk>/payroll-export/", hr_views.staff_payroll_export_user, name="staff_payroll_export_user"),
    path("staff/<int:pk>/payroll/disburse/", hr_views.staff_payroll_disburse, name="staff_payroll_disburse"),
    path("staff/<int:pk>/payout-profile/", hr_views.staff_payout_profile_save, name="staff_payout_profile_save"),
    path("staff/register/", staff_register, name="staff_register"),
    path("staff/<int:pk>/", staff_detail, name="staff_detail"),
    path("staff/<int:pk>/delete/", staff_delete, name="staff_delete"),
    path("staff/<int:pk>/reactivate/", staff_reactivate, name="staff_reactivate"),
    path("staff/<int:pk>/change-role/", staff_change_role, name="staff_change_role"),
    path("staff/<int:pk>/secondary-roles/", staff_manage_secondary_roles, name="staff_manage_secondary_roles"),
    path("staff/<int:pk>/hr/contract/", hr_views.staff_hr_contract_add, name="staff_hr_contract_add"),
    path(
        "staff/<int:pk>/hr/contract/<int:contract_id>/status/",
        hr_views.staff_hr_contract_set_status,
        name="staff_hr_contract_set_status",
    ),
    path("staff/<int:pk>/hr/teaching/", hr_views.staff_hr_teaching_add, name="staff_hr_teaching_add"),
    path(
        "staff/<int:pk>/hr/teaching/<int:assignment_id>/end/",
        hr_views.staff_hr_teaching_end,
        name="staff_hr_teaching_end",
    ),
    path("staff/<int:pk>/hr/payroll/", hr_views.staff_hr_payroll_add, name="staff_hr_payroll_add"),
    path("staff/<int:pk>/hr/subjects/", hr_views.staff_assign_subjects_save, name="staff_assign_subjects_save"),
    path("staff/<int:pk>/hr/homeroom/", hr_views.staff_assign_homeroom_save, name="staff_assign_homeroom_save"),
    path("parents/", parent_list, name="parent_list"),
    path("parents/register/", parent_register, name="parent_register"),
    path("parents/<int:pk>/", parent_detail, name="parent_detail"),
    path("parents/<int:pk>/edit/", parent_edit, name="parent_edit"),
    path("parents/<int:pk>/delete/", parent_delete, name="parent_delete"),
    path("parents/<int:pk>/reactivate/", parent_reactivate, name="parent_reactivate"),
    # Admin-led password reset and credential changes
    path("users/<int:pk>/reset-password/", reset_user_password, name="reset_user_password"),
    path(
        "superuser/users/<int:pk>/credentials/",
        superuser_edit_credentials,
        name="superuser_edit_credentials",
    ),
    path('super/metrics/', superadmin_metrics, name='superadmin_metrics'),
    path('password-reset/sms/', sms_otp_reset_request, name='sms_otp_reset_request'),
    path('password-reset/sms/confirm/', sms_otp_reset_confirm, name='sms_otp_reset_confirm'),
    # Two-Factor Authentication (TOTP)
    path("2fa/setup/", totp_views.setup_2fa, name="2fa_setup"),
    path("2fa/disable/", totp_views.disable_2fa_view, name="2fa_disable"),
    path("2fa/challenge/", totp_views.login_challenge, name="2fa_challenge"),
    path("2fa/backup/", totp_views.use_backup_code, name="2fa_backup"),
    # Leave policies & balances
    path("hr/leave-policies/", hr_views.leave_policy_list, name="leave_policy_list"),
    path("hr/leave-balances/", hr_views.leave_balance_list, name="leave_balance_list"),
    path("hr/my-leave/", hr_views.my_leave_balance, name="my_leave_balance"),
    # Payroll runs
    path("hr/payroll-runs/", hr_views.payroll_run_list, name="payroll_run_list"),
    path("hr/payroll-runs/create/", hr_views.payroll_run_create, name="payroll_run_create"),
    path("hr/payroll-runs/<int:pk>/", hr_views.payroll_run_detail, name="payroll_run_detail"),
    # Performance reviews
    path("hr/performance-reviews/", hr_views.performance_review_list, name="performance_review_list"),
    path("hr/performance-reviews/create/", hr_views.performance_review_create, name="performance_review_create"),
]
