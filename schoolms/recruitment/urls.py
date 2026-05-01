from django.urls import path
from . import views

app_name = "recruitment"

urlpatterns = [
    # --- Public ---
    path("", views.job_list, name="job_list"),
    path("<int:pk>/", views.job_detail, name="job_detail"),
    path("<int:pk>/apply/", views.job_apply, name="job_apply"),
    path("apply/<str:ref>/pay/", views.job_pay, name="job_pay"),
    path("apply/callback/", views.job_pay_callback, name="job_pay_callback"),
    path("apply/<str:ref>/submitted/", views.application_submitted, name="application_submitted"),
    path("track/", views.track_application, name="track_application"),

    # --- School admin ---
    path("manage/", views.school_job_list, name="school_job_list"),
    path("manage/create/", views.school_job_create, name="school_job_create"),
    path("manage/<int:pk>/edit/", views.school_job_edit, name="school_job_edit"),
    path("manage/<int:pk>/toggle/", views.school_job_toggle, name="school_job_toggle"),
    path("manage/<int:job_pk>/applicants/", views.school_applicant_list, name="school_applicant_list"),
    path("manage/application/<int:pk>/", views.school_application_detail, name="school_application_detail"),
    path("manage/application/<int:pk>/shortlist/", views.school_application_shortlist, name="school_application_shortlist"),
    path("manage/application/<int:pk>/reject/", views.school_application_reject, name="school_application_reject"),
    path("manage/application/<int:pk>/hire/", views.school_application_hire, name="school_application_hire"),
    path("manage/application/<int:pk>/action/", views.school_application_action, name="school_application_action"),
    path("manage/application/<int:pk>/schedule/", views.school_schedule_interview, name="school_schedule_interview"),

    # --- Platform super admin ---
    path("platform/dashboard/", views.platform_dashboard, name="platform_dashboard"),
]
