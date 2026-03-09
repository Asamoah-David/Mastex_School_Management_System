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
    path("canteen/payments/", views.canteen_payments, name="canteen_payments"),
    path("canteen/delete/<int:pk>/", views.canteen_item_delete, name="canteen_item_delete"),
    
    # Bus
    path("bus/", views.bus_list, name="bus_list"),
    path("bus/payments/", views.bus_payments, name="bus_payments"),
    path("bus/delete/<int:pk>/", views.bus_route_delete, name="bus_route_delete"),
    
    # Textbooks
    path("textbooks/", views.textbook_list, name="textbook_list"),
    path("textbooks/sales/", views.textbook_sales, name="textbook_sales"),
    path("textbooks/delete/<int:pk>/", views.textbook_delete, name="textbook_delete"),
]
