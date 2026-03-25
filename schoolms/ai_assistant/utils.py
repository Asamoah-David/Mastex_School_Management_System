import google.generativeai as genai
from django.conf import settings


def _get_model():
    """
    Lazily configure and return the Gemini model.
    """
    api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.0-flash")


def ask_ai(prompt):
    """
    Call the AI assistant using Google Gemini 2.5 Flash.

    - If no API key is configured, return a friendly message instead of raising.
    - Wrap network / API errors so they don't cause 500s.
    """
    model = _get_model()
    if model is None:
        return "AI assistant is not configured yet. Please contact the administrator."

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI error: {str(e)}"
