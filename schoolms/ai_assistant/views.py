from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
import json


# Wrapper functions for URL patterns
@login_required
def ai_assistant_page(request):
    """AI Assistant main page."""
    return render(request, "ai_assistant/chatbot.html")


@login_required
def chatbot_view(request):
    """Chatbot interface."""
    return render(request, "ai_assistant/chatbot.html")


@login_required
def chatbot_respond(request):
    """Handle chatbot AJAX responses."""
    if request.method == "POST":
        try:
            # Try to parse as JSON first (AJAX)
            try:
                data = json.loads(request.body)
                user_message = data.get("message", "").strip()
            except (json.JSONDecodeError, ValueError):
                user_message = request.POST.get("message", "").strip()
            
            if not user_message:
                return JsonResponse({"error": "Please enter a message"}, status=400)
            
            from ai_assistant.utils import ask_ai
            response = ask_ai(user_message)
            return JsonResponse({"response": response})
        except Exception as e:
            import traceback
            error_detail = f"{str(e)}\n{traceback.format_exc()}"
            return JsonResponse({"error": f"Server error: {str(e)}"}, status=500)
    
    return JsonResponse({"error": "Invalid method"}, status=400)


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
