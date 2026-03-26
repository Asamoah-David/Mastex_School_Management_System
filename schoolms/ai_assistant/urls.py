from django.urls import path
from . import views

app_name = "ai_assistant"

urlpatterns = [
    path("", views.ai_assistant_page, name="ai_assistant_page"),
    path("chatbot/", views.chatbot_view, name="chatbot"),
    path("chatbot/respond/", views.chatbot_respond, name="chatbot_respond"),
]
