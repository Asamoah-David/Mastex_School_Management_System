"""
AI Comment Generation Views
============================
Provides views for generating and saving AI-powered teacher comments
that appear on student report cards.
"""
import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages

logger = logging.getLogger(__name__)


def _get_school(request):
    school = getattr(request.user, "school", None)
    if school:
        return school
    if request.user.is_superuser or getattr(request.user, "is_super_admin", False):
        from schools.models import School
        sid = request.session.get("current_school_id")
        if sid:
            return School.objects.filter(pk=sid).first()
    return None


def _build_student_summary(student, term, school):
    """Build a text summary of the student's performance for the AI prompt."""
    from academics.models import StudentResultSummary, AssessmentScore, ExamScore, GradingPolicy
    lines = []
    lines.append(f"Student: {student.user.get_full_name() or student.user.username}")
    lines.append(f"Class: {student.class_name or 'N/A'}")
    if term:
        lines.append(f"Term: {term.name}")

    # Get scores
    summaries = []
    if term:
        summaries = list(
            StudentResultSummary.objects.filter(student=student, term=term)
            .select_related("subject")
        )
    if summaries:
        lines.append("Subjects and scores:")
        for s in summaries:
            lines.append(
                f"  {s.subject.name}: CA={s.ca_score:.0f}, Exam={s.exam_score:.0f}, "
                f"Final={s.final_score:.0f}, Grade={s.grade}"
            )
        avg = sum(s.final_score for s in summaries) / len(summaries)
        lines.append(f"Overall average: {avg:.1f}")
    else:
        lines.append("No detailed scores available for this term.")

    # Attendance
    try:
        from operations.models import StudentAttendance
        att = StudentAttendance.objects.filter(student=student)
        if term and hasattr(term, "start_date") and term.start_date:
            att = att.filter(date__gte=term.start_date)
        total = att.count()
        present = att.filter(status="present").count()
        if total:
            lines.append(f"Attendance: {present}/{total} days ({present*100//total}%)")
    except Exception:
        pass

    return "\n".join(lines)


@login_required
def ai_comment_page(request, student_id=None):
    """Generate and save AI teacher comments for a student.
    
    Accepts student_id either as:
    - URL path param: /academics/ai-comment/<student_id>/
    - GET param: /academics/ai-comment/?student=<id>
    - POST param: student_id=<id>
    """
    from students.models import Student
    from academics.models import Term, AIStudentComment

    school = _get_school(request)
    if not school:
        messages.error(request, "No school found.")
        return redirect("home")

    user = request.user
    role = getattr(user, "role", None)
    if not (user.is_superuser or role in ("school_admin", "admin", "teacher", "hod", "deputy_head")):
        messages.error(request, "Access denied.")
        return redirect("home")

    # Resolve student_id from URL param, GET, or POST
    if student_id is None:
        student_id = request.GET.get("student") or request.POST.get("student_id")
    student = get_object_or_404(Student, pk=student_id, school=school)

    terms = Term.objects.filter(school=school).order_by("-name")
    saved_comment = AIStudentComment.objects.filter(student=student, school=school).order_by("-created_at").first()

    context = {
        "school": school,
        "student": student,
        "terms": terms,
        "saved_comment": saved_comment,
        "can_manage": True,
        "generated_comment": None,
        "error": None,
    }

    if request.method == "POST":
        action = request.POST.get("action", "generate")
        term_id = request.POST.get("term_id")
        instructions = request.POST.get("instructions", "")
        term = None
        if term_id:
            term = Term.objects.filter(pk=term_id, school=school).first()

        if action == "save":
            # Save the previously generated comment
            generated = request.POST.get("generated_comment", "").strip()
            if generated:
                AIStudentComment.objects.update_or_create(
                    student=student,
                    school=school,
                    term=term.name if term else "",
                    defaults={"content": generated, "generated_by": "ai"},
                )
                messages.success(request, "AI comment saved to report card.")
                return redirect(f"/academics/report-card/{student.id}/enhanced/")
            else:
                context["error"] = "No comment to save."
        else:
            # Generate comment via AI
            summary = _build_student_summary(student, term, school)
            prompt = (
                f"Write a short, professional, encouraging teacher comment (3-4 sentences) "
                f"for the following student report card.\n\n{summary}"
            )
            if instructions:
                prompt += f"\n\nAdditional instructions: {instructions}"
            prompt += (
                "\n\nThe comment should:\n"
                "- Be warm and encouraging\n"
                "- Mention specific academic strengths\n"
                "- Note any areas for improvement politely\n"
                "- Be suitable for parents to read\n"
                "- NOT include the student\'s name (it will be added separately)\n"
                "Output only the comment text, nothing else."
            )
            try:
                from ai_assistant.utils import ask_ai_with_context
                generated = ask_ai_with_context(
                    prompt=prompt,
                    school_name=school.name,
                    user_name=user.get_full_name() or user.username,
                    user_role=role or "teacher",
                )
                context["generated_comment"] = generated
            except Exception as exc:
                logger.warning("AI comment generation failed: %s", exc)
                context["error"] = f"AI generation failed: {exc}"

    return render(request, "academics/ai_comment.html", context)
