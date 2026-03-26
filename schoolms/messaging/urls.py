from django.urls import path
from . import views
from . import bulk_sms_views

app_name = "messaging"

urlpatterns = [
    path("send/", views.send_message, name="send_message"),
    path("history/", views.message_history, name="message_history"),
    
    # Chat
    path("chat/", views.chat_view, name="chat_view"),
    path("messages/<int:contact_id>/", views.get_messages, name="get_messages"),
    
    # Bulk SMS
    path("bulk-sms/", bulk_sms_views.bulk_sms_page, name="bulk_sms_page"),
    path("bulk-sms/send/", bulk_sms_views.send_bulk_sms, name="send_bulk_sms"),
    path("bulk-sms/history/", bulk_sms_views.sms_history, name="sms_history"),
]
