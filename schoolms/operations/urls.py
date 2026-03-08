from django.urls import path
from . import views

app_name = "operations"

urlpatterns = [
    path("attendance/", views.attendance_list, name="attendance_list"),
    path("attendance/mark/", views.attendance_mark, name="attendance_mark"),
    path("canteen/", views.canteen_list, name="canteen_list"),
    path("canteen/payments/", views.canteen_payments, name="canteen_payments"),
    path("bus/", views.bus_list, name="bus_list"),
    path("bus/payments/", views.bus_payments, name="bus_payments"),
    path("textbooks/", views.textbook_list, name="textbook_list"),
    path("textbooks/sales/", views.textbook_sales, name="textbook_sales"),
]
