from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
import json

@login_required
def ai_chat(request):
    """AI Assistant chat interface."""
    if request.method == "POST":
        user_message = request.POST.get("message", "").strip()
        if not user_message:
            messages.error(request, "Please enter a message.")
            return render(request, "ai_assistant/chat.html")
        
        try:
            from ai_assistant.utils import ask_ai
            response = ask_ai(user_message)
            return render(request, "ai_assistant/chat.html", {
                "user_message": user_message,
                "ai_response": response
            })
        except Exception as e:
            messages.error(request, f"AI Error: {str(e)}")
            return render(request, "ai_assistant/chat.html")
    
    return render(request, "ai_assistant/chat.html")
