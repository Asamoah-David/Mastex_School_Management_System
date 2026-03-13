from django.urls import path
from . import views

app_name = "finance"

urlpatterns = [
    path("pay/<int:fee_id>/", views.pay_with_flutterwave, name="pay_with_flutterwave"),
    path("flutterwave-callback/", views.flutterwave_callback, name="flutterwave_callback"),
    path("flutterwave-webhook/", views.flutterwave_webhook, name="flutterwave_webhook"),
    path("fee-structure/", views.fee_structure_list, name="fee_structure_list"),
    path("fee-structure/create/", views.fee_structure_create, name="fee_structure_create"),
    # School-facing fee management for marking offline payments as paid
    path("fees/", views.fee_list, name="fee_list"),
]
