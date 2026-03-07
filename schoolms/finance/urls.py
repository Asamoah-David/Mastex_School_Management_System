from django.urls import path
from . import views

app_name = "finance"

urlpatterns = [
    path("pay/<int:fee_id>/", views.pay_with_flutterwave, name="pay_with_flutterwave"),
    path("flutterwave-callback/", views.flutterwave_callback, name="flutterwave_callback"),
    path("flutterwave-webhook/", views.flutterwave_webhook, name="flutterwave_webhook"),
]
