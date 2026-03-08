from django.urls import path
from . import views

app_name = "operations"

urlpatterns = [
    path("attendance/", views.attendance_list, name="attendance_list"),
    path("attendance/mark/", views.attendance_mark, name="attendance_mark"),
    path("attendance/delete/<int:pk>/", views.attendance_delete, name="attendance_delete"),
    path("canteen/", views.canteen_list, name="canteen_list"),
    path("canteen/payments/", views.canteen_payments, name="canteen_payments"),
    path("canteen/delete/<int:pk>/", views.canteen_item_delete, name="canteen_item_delete"),
    path("bus/", views.bus_list, name="bus_list"),
    path("bus/payments/", views.bus_payments, name="bus_payments"),
    path("bus/delete/<int:pk>/", views.bus_route_delete, name="bus_route_delete"),
    path("textbooks/", views.textbook_list, name="textbook_list"),
    path("textbooks/sales/", views.textbook_sales, name="textbook_sales"),
    path("textbooks/delete/<int:pk>/", views.textbook_delete, name="textbook_delete"),
]
