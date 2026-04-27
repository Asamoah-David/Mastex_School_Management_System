from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("get/", views.get_notifications, name="get"),
    path("<int:notification_id>/read/", views.mark_as_read, name="mark_read"),
    path("read-all/", views.mark_all_as_read, name="mark_all_read"),
    path("<int:notification_id>/delete/", views.delete_notification, name="delete"),
    path("bulk-dismiss/", views.bulk_dismiss_notifications, name="bulk_dismiss"),
    path("snooze/", views.snooze_notifications, name="snooze"),
    path("preferences/", views.update_notification_preferences, name="preferences"),
    path("dashboard-summary/", views.dashboard_summary, name="dashboard_summary"),
]
