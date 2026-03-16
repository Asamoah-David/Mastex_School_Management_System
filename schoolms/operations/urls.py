from django.urls import path
from . import views

app_name = "operations"

urlpatterns = [
    # Student Attendance
    path("attendance/", views.attendance_list, name="attendance_list"),
    path("attendance/mark/", views.attendance_mark, name="attendance_mark"),
    path("attendance/delete/<int:pk>/", views.attendance_delete, name="attendance_delete"),
    
    # Teacher Attendance
    path("teacher-attendance/", views.teacher_attendance_list, name="teacher_attendance_list"),
    path("teacher-attendance/mark/", views.teacher_attendance_mark, name="teacher_attendance_mark"),
    
    # Academic Calendar
    path("calendar/", views.calendar_list, name="calendar"),
    path("calendar/create/", views.calendar_create, name="calendar_create"),
    path("calendar/delete/<int:pk>/", views.calendar_delete, name="calendar_delete"),
    
    # Canteen
    path("canteen/", views.canteen_list, name="canteen_list"),
    path("canteen/create/", views.canteen_create, name="canteen_create"),
    path("canteen/payments/", views.canteen_payments, name="canteen_payments"),
    path("canteen/delete/<int:pk>/", views.canteen_item_delete, name="canteen_item_delete"),
    
    # Bus
    path("bus/", views.bus_list, name="bus_list"),
    path("bus/create/", views.bus_create, name="bus_create"),
    path("bus/payments/", views.bus_payments, name="bus_payments"),
    path("bus/delete/<int:pk>/", views.bus_route_delete, name="bus_route_delete"),
    
    # Textbooks
    path("textbooks/", views.textbook_list, name="textbook_list"),
    path("textbooks/create/", views.textbook_create, name="textbook_create"),
    path("textbooks/sales/", views.textbook_sales, name="textbook_sales"),
    path("textbooks/delete/<int:pk>/", views.textbook_delete, name="textbook_delete"),

    # Announcements
    path("announcements/", views.announcement_list, name="announcement_list"),
    path("announcements/create/", views.announcement_create, name="announcement_create"),
    path("announcements/delete/<int:pk>/", views.announcement_delete, name="announcement_delete"),

    # Staff Leave
    path("staff-leave/", views.staff_leave_list, name="staff_leave_list"),
    path("staff-leave/create/", views.staff_leave_create, name="staff_leave_create"),
    path("staff-leave/<int:pk>/review/", views.staff_leave_review, name="staff_leave_review"),

    # Activity Log
    path("activity-log/", views.activity_log_list, name="activity_log_list"),
]
