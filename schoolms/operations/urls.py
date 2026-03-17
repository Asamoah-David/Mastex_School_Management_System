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

    # Library
    path("library/", views.library_catalog, name="library_catalog"),
    path("library/manage/", views.library_manage, name="library_manage"),
    path("library/books/create/", views.library_book_create, name="library_book_create"),
    path("library/books/<int:pk>/delete/", views.library_book_delete, name="library_book_delete"),
    path("library/issues/", views.library_issues, name="library_issues"),
    path("library/issues/create/", views.library_issue_create, name="library_issue_create"),
    path("library/issues/<int:pk>/return/", views.library_issue_return, name="library_issue_return"),
    path("library/my-issues/", views.library_my_issues, name="library_my_issues"),

    # Hostel
    path("hostels/", views.hostel_list, name="hostel_list"),
    path("hostels/create/", views.hostel_create, name="hostel_create"),
    path("hostels/<int:pk>/rooms/", views.hostel_rooms, name="hostel_rooms"),
    path("hostels/<int:pk>/rooms/create/", views.hostel_room_create, name="hostel_room_create"),
    path("hostels/assignments/", views.hostel_assignments, name="hostel_assignments"),
    path("hostels/assignments/create/", views.hostel_assignment_create, name="hostel_assignment_create"),
    path("hostels/assignments/<int:pk>/end/", views.hostel_assignment_end, name="hostel_assignment_end"),
    path("hostels/fees/", views.hostel_fees, name="hostel_fees"),
    path("hostels/fees/create/", views.hostel_fee_create, name="hostel_fee_create"),
    path("hostels/fees/<int:pk>/mark-paid/", views.hostel_fee_mark_paid, name="hostel_fee_mark_paid"),
    path("hostels/my/", views.hostel_my, name="hostel_my"),
]
