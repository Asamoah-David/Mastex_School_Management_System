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
    Falls back to predefined responses if API is unavailable.
    """
    client = _get_client()
    
    # Define fallback responses for common school-related questions
    fallback_responses = {
        "fee": "To pay school fees, please log into your parent or student portal and navigate to the Fees section. You can make payments online using Paystack or visit the school office.",
        "fees": "To pay school fees, please log into your parent or student portal and navigate to the Fees section. You can make payments online using Paystack or visit the school office.",
        "result": "To view results, go to your portal and click on 'Academics' > 'My Results'. If you're a parent, you can view your child's results from the parent dashboard.",
        "results": "To view results, go to your portal and click on 'Academics' > 'My Results'. If you're a parent, you can view your child's results from the parent dashboard.",
        "attendance": "To check attendance, visit your student portal and go to 'Attendance' in the sidebar. Parents can view their child's attendance from the parent dashboard.",
        "homework": "You can access homework from your student portal under 'Academics' > 'Homework'. Submit assignments directly through the portal.",
        "contact": "You can contact the school through the messaging feature in your portal, or visit the school in person during office hours.",
        "exam": "Online exams are available in your portal under 'Academics' > 'Online Exams'. Make sure to read the instructions before starting.",
        "library": "Visit the school library catalog from your portal to search for books. You can also check your borrowed books under 'My Books'.",
        "transport": "Bus routes and transport information can be found in your portal under 'Transport' or 'Operations' > 'Bus'.",
        "hostel": "Hostel information is available in your portal under 'Operations' > 'Hostel'.",
        "timetable": "Your class timetable is available in your portal under 'Academics' > 'Timetable'.",
    }
    
    # Check if we can use the real AI
    if client is None:
        # Try to find a matching fallback response
        prompt_lower = prompt.lower()
        for key, response in fallback_responses.items():
            if key in prompt_lower:
                return response
        
        return "I'm here to help with school-related questions! You can ask me about: paying fees, viewing results, checking attendance, homework, exams, library, transport, hostel, timetable, or contacting the school. How can I assist you today?"
    
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
        # Fall back to predefined responses on rate limit
        return "I'm experiencing high demand right now. Please try again in a moment. For quick help, you can also check your portal for school information."
    except groq.APIConnectionError as e:
        # Fall back on connection errors
        return "I'm having trouble connecting right now. Please check your internet connection and try again. You can also find help in your school portal."
    except Exception as e:
        # Fall back on any other error
        return "I'm here to help! Ask me about paying fees, viewing results, checking attendance, homework, exams, library, transport, or other school matters."
