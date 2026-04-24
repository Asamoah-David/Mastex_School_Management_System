"""
AI Assistant Utilities
======================
Provides ask_ai() and ask_ai_with_context() which always return a string
(never raise exceptions) so the chatbot endpoint always responds with a
valid message.
"""
import logging

logger = logging.getLogger(__name__)


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Lazily configure and return the Groq client. Returns None if unavailable."""
    try:
        import groq
        from django.conf import settings
        api_key = getattr(settings, "GROQ_API_KEY", "") or ""
        if not api_key:
            return None
        return groq.Groq(api_key=api_key)
    except Exception:
        return None


# ── Fallback knowledge base ───────────────────────────────────────────────────

_FALLBACK = {
    "fee": "To pay school fees, log into your parent or student portal and navigate to the Fees section. You can make payments online via Paystack or visit the school's finance office. Partial / instalment payments are also supported — just choose your amount when paying.",
    "fees": "To pay school fees, log into your parent or student portal and navigate to the Fees section. You can make payments online via Paystack or visit the school's finance office. Partial / instalment payments are also supported.",
    "pay": "You can pay any fee (school fees, bus, hostel, canteen, textbook) from your portal. Navigate to the relevant section and click 'Pay'. Partial payments are accepted — enter any amount up to the balance.",
    "payment": "Payments can be made online via Paystack directly from your portal. After a successful payment a receipt is automatically generated and available for download as PDF.",
    "receipt": "Receipts are automatically generated after each payment. Go to your portal → Payments → Payment History, then click 'Download Receipt' to get a PDF copy.",
    "result": "To view results, go to your portal and click 'Academics' → 'My Results'. Parents can see their child's results from the parent dashboard under 'Academics'.",
    "results": "To view results, navigate to Academics → My Results in your portal. Report cards (including CA breakdown and exam scores) are downloadable as PDF.",
    "report": "Report cards show your CA score (50%), Exam score (50%), final weighted grade, and AI-generated teacher comments. Download the PDF from Academics → Report Cards.",
    "grade": "Grades are calculated as 50% Continuous Assessment (CA) + 50% End-of-Term Exam by default. Your school admin can adjust these weights.",
    "attendance": "To check attendance, visit your student portal and go to 'Attendance'. Parents can view their child's attendance from the parent dashboard.",
    "homework": "Access homework from your student portal under Academics → Homework. Submit assignments directly through the portal before the due date.",
    "exam": "Online exams are available in your portal under Academics → Online Exams. Read all instructions carefully before starting. Your results are shown immediately after submission.",
    "quiz": "Quizzes are found under Academics → Quizzes in your portal. You can attempt a quiz based on the number of attempts your teacher has allowed.",
    "contact": "Contact the school through the Messaging feature in your portal, or visit the school in person during office hours.",
    "library": "Visit the school library catalog from your portal to search for and borrow books. Check your borrowed books under Operations → Library → My Issues.",
    "transport": "Bus routes and transport information are in your portal under Operations → Bus. You can pay for bus service daily, weekly, or for the full term.",
    "bus": "Bus payments can be made daily, weekly, or for the full term. Go to Operations → Bus → My Bus to see your route and make a payment.",
    "hostel": "Hostel information and fees are under Operations → Hostel in your portal. Instalment payments are supported — pay as much as you can afford each time.",
    "timetable": "Your class timetable is available under Academics → Timetable in your portal.",
    "canteen": "Canteen services are managed under Operations → Canteen. You can pay for meals per visit or in advance.",
    "textbook": "Textbook information is under Operations → Textbooks. You can pay for books individually.",
    "admission": "Admission applications can be submitted online through the Admissions portal. Upload all required documents and wait for approval notification.",
    "password": "To reset your password, click 'Forgot Password' on the login page and enter your registered email address.",
    "login": "Go to your school's Mastex portal URL and enter your username and password. Contact admin if you need your login credentials.",
    "announcement": "School announcements are displayed on your dashboard and under Operations → Announcements.",
    "certificate": "Academic certificates and awards are available under Operations → Certificates in your portal.",
}


# ── Public API ────────────────────────────────────────────────────────────────

def ask_ai(prompt: str) -> str:
    """Call the AI. Falls back to built-in responses if Groq is unavailable.
    Always returns a string, never raises.
    """
    return ask_ai_with_context(prompt)


def build_school_context(school=None, user=None) -> str:
    """Build a brief live-data snippet to inject into the AI system prompt."""
    lines = []
    try:
        if school:
            lines.append(f"School: {school.name}")
            if school.academic_year:
                lines.append(f"Academic year: {school.academic_year}")
        if user and getattr(user, "role", None) in ("parent", "student"):
            from students.models import Student
            from finance.models import Fee
            from django.db.models import Sum
            students = Student.objects.filter(
                school=school, status="active"
            ).filter(
                parent=user
            ) if getattr(user, "role", None) == "parent" else Student.objects.filter(user=user, school=school)
            if students.exists():
                unpaid = Fee.objects.filter(
                    student__in=students, paid=False
                ).aggregate(total=Sum("amount"))["total"] or 0
                paid = Fee.objects.filter(
                    student__in=students, paid=True
                ).aggregate(total=Sum("amount_paid"))["total"] or 0
                lines.append(f"Unpaid fees: GHS {unpaid:.2f}")
                lines.append(f"Total paid this year: GHS {paid:.2f}")
        from academics.models import Term
        if school:
            current = Term.objects.filter(school=school, is_current=True).first()
            if current:
                lines.append(f"Current term: {current.name}")
    except Exception:
        pass
    return "\n".join(lines)


def ask_ai_with_context(
    prompt: str,
    school_name: str = "your school",
    user_name: str = "",
    user_role: str = "user",
    school=None,
    user=None,
) -> str:
    """Context-aware AI response. Always returns a string, never raises."""

    client = _get_groq_client()
    live_ctx = build_school_context(school=school, user=user)

    # ── 1. Try Groq LLM ──────────────────────────────────────────────────────
    if client is not None:
        try:
            system_prompt = (
                f"You are a friendly and helpful school management assistant for {school_name}. "
                "You help students, parents, and staff with questions about the school system. "
                "Keep responses concise (max 3 paragraphs), clear, and supportive. "
                "If the user asks about fees, mention that partial payments are accepted. "
                "If the user asks about report cards, mention the CA+Exam breakdown and PDF download. "
                "Always be encouraging and professional."
            )
            if user_name:
                system_prompt += f" The user's name is {user_name} and their role is {user_role}."
            if live_ctx:
                system_prompt += f"\n\nLive school data:\n{live_ctx}"

            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=512,
            )
            return completion.choices[0].message.content

        except Exception as exc:
            logger.info("Groq API unavailable (%s), using fallback", type(exc).__name__)

    # ── 2. Keyword-based fallback ────────────────────────────────────────────
    prompt_lower = prompt.lower()
    for key, response in _FALLBACK.items():
        if key in prompt_lower:
            return response

    # ── 3. Generic helpful response ──────────────────────────────────────────
    return (
        f"Hello! I'm the {school_name} school assistant. 😊 I can help you with:\n\n"
        "📚 **Academics** – Results, report cards, homework, exams, quizzes, timetable\n"
        "💰 **Payments** – School fees, bus, hostel, canteen, textbook payments & receipts\n"
        "📋 **Operations** – Attendance, library, transport, hostel, announcements\n"
        "🔐 **Account** – Login issues, password reset, profile\n\n"
        "What would you like to know about?"
    )
