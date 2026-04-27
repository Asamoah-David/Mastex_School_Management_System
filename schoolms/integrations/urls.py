from django.urls import path

from integrations import api_views

app_name = "integrations"

urlpatterns = [
    # Identity
    path("me/", api_views.MeAPIView.as_view(), name="v1_me"),
    # Auth
    path("auth/logout/", api_views.JWTLogoutAPIView.as_view(), name="v1_jwt_logout"),
    # Staff / HR
    path("staff-leave/", api_views.StaffLeaveListAPIView.as_view(), name="v1_staff_leave"),
    path("expenses/", api_views.ExpenseListAPIView.as_view(), name="v1_expenses"),
    # Attendance
    path("attendance/today/", api_views.TodayAttendanceSummaryAPIView.as_view(), name="v1_attendance_today"),
    # Students
    path("students/", api_views.StudentListAPIView.as_view(), name="v1_students"),
    path("students/<int:student_id>/transcripts/", api_views.StudentTranscriptAPIView.as_view(), name="v1_student_transcripts"),
    # Finance
    path("fees/status/", api_views.FeeStatusAPIView.as_view(), name="v1_fees_status"),
    # Academics
    path("results/", api_views.ResultListAPIView.as_view(), name="v1_results"),
    path("timetable/", api_views.TimetableAPIView.as_view(), name="v1_timetable"),
    # Privacy
    path("gdpr/export/", api_views.GDPRExportRequestAPIView.as_view(), name="v1_gdpr_export"),
    path("gdpr/export/<int:export_id>/download/", api_views.GDPRExportDownloadAPIView.as_view(), name="v1_gdpr_download"),
]
