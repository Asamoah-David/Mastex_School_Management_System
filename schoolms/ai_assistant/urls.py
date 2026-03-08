from django.urls import path
from .views import ai_chat

app_name = "ai_assistant"

urlpatterns = [
    path("chat/", ai_chat, name="chat"),
]
