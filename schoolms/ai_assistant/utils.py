from openai import OpenAI
from django.conf import settings


def _get_client():
    """
    Lazily create an OpenAI client and guard against missing configuration.
    """
    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def ask_ai(prompt):
    """
    Call the AI assistant safely.

    - If no API key is configured, return a friendly message instead of raising.
    - Wrap network / API errors so they don't cause 500s.
    """
    client = _get_client()
    if client is None:
        return "AI assistant is not configured yet. Please contact the administrator."

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI error: {str(e)}"
