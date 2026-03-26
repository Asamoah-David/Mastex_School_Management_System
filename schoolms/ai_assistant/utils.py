import groq
from django.conf import settings


def _get_client():
    """
    Lazily configure and return the Groq client.
    """
    api_key = getattr(settings, "GROQ_API_KEY", "") or ""
    if not api_key:
        return None
    return groq.Groq(api_key=api_key)


def ask_ai(prompt):
    """
    Call the AI assistant using Groq (Llama model).

    - If no API key is configured, return a friendly message instead of raising.
    - Wrap network / API errors so they don't cause 500s.
    """
    client = _get_client()
    if client is None:
        return "AI assistant is not configured yet. Please contact the administrator."

    try:
        chat_completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a helpful school management assistant. Provide clear, concise, and educational responses."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1024
        )
        return chat_completion.choices[0].message.content
    except groq.RateLimitError as e:
        return f"AI rate limit exceeded. Please try again in a moment."
    except groq.APIConnectionError as e:
        return f"AI connection error. Please check your internet connection."
    except Exception as e:
        return f"AI error: {str(e)}"
