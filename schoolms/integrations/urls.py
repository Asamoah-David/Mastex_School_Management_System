from django.urls import path

from integrations import api_views

app_name = "integrations"

urlpatterns = [
    path("me/", api_views.MeAPIView.as_view(), name="v1_me"),
    path("staff-leave/", api_views.StaffLeaveListAPIView.as_view(), name="v1_staff_leave"),
    path("expenses/", api_views.ExpenseListAPIView.as_view(), name="v1_expenses"),
    path("attendance/today/", api_views.TodayAttendanceSummaryAPIView.as_view(), name="v1_attendance_today"),
]
