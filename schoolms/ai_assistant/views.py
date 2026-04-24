from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib import messages
from django.http import JsonResponse
import json
import logging

logger = logging.getLogger(__name__)


def _get_school(request):
    """Return the school associated with the current user/session."""
    school = getattr(request.user, "school", None)
    if school:
        return school
    if request.user.is_superuser or getattr(request.user, "is_super_admin", False):
        school_id = request.session.get("current_school_id")
        if school_id:
            try:
                from schools.models import School
                return School.objects.get(pk=school_id)
            except Exception:
                pass
    return None


# ── Page views ────────────────────────────────────────────────────────────────

@login_required
@ensure_csrf_cookie
def ai_assistant_page(request):
    """AI Assistant main page."""
    school = _get_school(request)
    return render(request, "ai_assistant/chatbot.html", {"school": school})


@login_required
@ensure_csrf_cookie
def chatbot_view(request):
    """Chatbot interface."""
    school = _get_school(request)
    return render(request, "ai_assistant/chatbot.html", {"school": school})


# ── AJAX endpoint ─────────────────────────────────────────────────────────────

@login_required
def chatbot_respond(request):
    """Handle chatbot AJAX responses.

    IMPORTANT: This view ALWAYS returns HTTP 200 with valid JSON.
    Errors are surfaced as {"response": "..."} (user-friendly message),
    never as HTTP error codes, so the browser fetch API never falls to
    the .catch() handler with a generic "something went wrong" message.
    """
    if request.method != "POST":
        return JsonResponse({"response": "Invalid request method. Please refresh the page."})

    # ── Parse incoming message ────────────────────────────────────────────────
    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()
    except (json.JSONDecodeError, ValueError):
        user_message = request.POST.get("message", "").strip()

    if not user_message:
        return JsonResponse({"response": "Please type a message and press Send. 😊"})

    # ── Build school context for the AI ──────────────────────────────────────
    school = _get_school(request)
    school_name = school.name if school else "your school"
    user_role = getattr(request.user, "role", "user")
    user_name = request.user.get_full_name() or request.user.username

    # ── Call AI (always returns a string, never raises) ───────────────────────
    try:
        from ai_assistant.utils import ask_ai_with_context
        response = ask_ai_with_context(
            prompt=user_message,
            school_name=school_name,
            user_name=user_name,
            user_role=user_role,
            school=school,
            user=request.user,
        )
    except Exception as exc:
        logger.warning("chatbot_respond: ask_ai_with_context raised %s", exc)
        # Even on unexpected failure, return a graceful message
        response = (
            "I'm having a momentary issue but I'm still here to help! 🤖 "
            "You can ask me about: paying fees, viewing results, checking attendance, "
            "homework, exams, library, transport, hostel, timetable, or contacting "
            f"{school_name}."
        )

    return JsonResponse({"response": response})


@login_required
def ai_chat(request):
    """AI Assistant full-page chat (non-AJAX fallback)."""
    school = _get_school(request)
    if request.method == "POST":
        user_message = request.POST.get("message", "").strip()
        if not user_message:
            messages.error(request, "Please enter a message.")
            return render(request, "ai_assistant/chatbot.html", {"school": school})

        try:
            from ai_assistant.utils import ask_ai_with_context
            school_name = school.name if school else "your school"
            ai_response = ask_ai_with_context(
                prompt=user_message,
                school_name=school_name,
                user_name=request.user.get_full_name() or request.user.username,
                user_role=getattr(request.user, "role", "user"),
                school=school,
                user=request.user,
            )
        except Exception as exc:
            logger.warning("ai_chat: %s", exc)
            ai_response = "I encountered an issue. Please try again."

        return render(request, "ai_assistant/chatbot.html", {
            "school": school,
            "user_message": user_message,
            "ai_response": ai_response,
        })

    return render(request, "ai_assistant/chatbot.html", {"school": school})
