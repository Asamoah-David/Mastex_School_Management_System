from django.urls import path
from . import views

app_name = "schools"

urlpatterns = [
    path("list/", views.school_list, name="school_list"),
    path("<int:pk>/features/", views.school_features, name="school_features"),
    path("settings/", views.school_settings, name="school_settings"),
    # Stripe webhook for automatic school subscription status updates
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
]
