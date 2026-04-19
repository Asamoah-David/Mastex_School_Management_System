"""Fix enhanced_report_card view and add AIStudentComment model."""
import pathlib, re

BASE = pathlib.Path(__file__).resolve().parent.parent / "schoolms"


# ─────────────────────────────────────────────────────────────────────────────
# 1.  Add AIStudentComment model to academics/models.py if missing
# ─────────────────────────────────────────────────────────────────────────────
models_path = BASE / "academics" / "models.py"
models_text = models_path.read_text(encoding="utf-8")

if "AIStudentComment" not in models_text:
    addition = '''

# ── AI-generated teacher comments (auto-added) ───────────────────────────────
class AIStudentComment(models.Model):
    """Stores AI-generated teacher comments for student report cards."""
    student = models.ForeignKey(
        "students.Student", on_delete=models.CASCADE, related_name="ai_comments"
    )
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="ai_comments"
    )
    term = models.CharField(max_length=100, blank=True, default="")
    content = models.TextField()
    generated_by = models.CharField(max_length=50, default="ai")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"AI Comment for {self.student} – {self.term}"
'''
    models_path.write_text(models_text + addition, encoding="utf-8")
    print("  Added AIStudentComment to academics/models.py")
else:
    print("  AIStudentComment already in academics/models.py")


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Patch GradingPolicy.get_active_policy classmethod if missing
# ─────────────────────────────────────────────────────────────────────────────
models_text2 = models_path.read_text(encoding="utf-8")
if "get_active_policy" not in models_text2:
    # Find GradingPolicy class and add a classmethod
    insert_after = "class GradingPolicy(models.Model):"
    if insert_after in models_text2:
        replacement = insert_after + '''
    @classmethod
    def get_active_policy(cls, school):
        """Return the active grading policy for a school, or a default."""
        policy = cls.objects.filter(school=school, is_default=True).first()
        if not policy:
            policy = cls.objects.filter(school=school).first()
        if not policy:
            # Return a default-like object
            class _Default:
                ca_weight = 50.0
                exam_weight = 50.0
                pass_mark = 50.0
            return _Default()
        return policy
'''
        models_text2 = models_text2.replace(insert_after, replacement, 1)
        models_path.write_text(models_text2, encoding="utf-8")
        print("  Added get_active_policy to GradingPolicy")
    else:
        print("  WARNING: GradingPolicy class not found")
else:
    print("  get_active_policy already exists")


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Add get_grade_for_score function if missing
# ─────────────────────────────────────────────────────────────────────────────
models_text3 = models_path.read_text(encoding="utf-8")
if "get_grade_for_score" not in models_text3:
    fn = '''

def get_grade_for_score(school, score):
    """Map a numeric score to a letter grade."""
    try:
        s = float(score)
    except (ValueError, TypeError):
        return "N/A"
    if s >= 80: return "A"
    if s >= 70: return "B"
    if s >= 60: return "C"
    if s >= 50: return "D"
    return "F"
'''
    models_path.write_text(models_text3 + fn, encoding="utf-8")
    print("  Added get_grade_for_score to academics/models.py")
else:
    print("  get_grade_for_score already exists")


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Write / replace enhanced_report_card view in academics/views.py
# ─────────────────────────────────────────────────────────────────────────────
views_path = BASE / "academics" / "views.py"
views_text = views_path.read_text(encoding="utf-8")

NEW_VIEW = '''

# ── enhanced_report_card (rewritten to fix 500 errors) ───────────────────────
@login_required
def enhanced_report_card(request, student_id):
    """Show enhanced report card with CA/Exam breakdown, AI comments, download link."""
    from students.models import Student
    from academics.models import (
        Term, AssessmentScore, ExamScore,
        StudentResultSummary, GradingPolicy,
        AIStudentComment,
    )
    try:
        from academics.models import get_grade_for_score
    except ImportError:
        def get_grade_for_score(school, score):
            try:
                s = float(score)
            except Exception:
                return "N/A"
            if s >= 80: return "A"
            if s >= 70: return "B"
            if s >= 60: return "C"
            if s >= 50: return "D"
            return "F"

    school = getattr(request.user, "school", None)
    if not school:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("No school found.")

    student = get_object_or_404(Student, pk=student_id, school=school)

    user = request.user
    role = getattr(user, "role", None)
    can_manage = user.is_superuser or role in (
        "school_admin", "admin", "teacher", "hod", "deputy_head", "accountant"
    )
    is_own = role == "student" and student.user_id == user.id
    is_parent_of = role == "parent" and getattr(student, "parent_id", None) == user.id
    if not (can_manage or is_own or is_parent_of):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")

    # Term
    term_id = request.GET.get("term")
    term = None
    if term_id:
        term = Term.objects.filter(pk=term_id, school=school).first()
    if not term:
        term = Term.objects.filter(school=school, is_current=True).first()

    # Grading policy
    try:
        policy = GradingPolicy.get_active_policy(school)
        ca_weight = float(policy.ca_weight)
        exam_weight = float(policy.exam_weight)
    except Exception:
        ca_weight, exam_weight = 50.0, 50.0

    # Subject rows
    subject_rows = []
    try:
        summaries = []
        if term:
            summaries = list(
                StudentResultSummary.objects.filter(student=student, term=term)
                .select_related("subject").order_by("subject__name")
            )
        if summaries:
            for s in summaries:
                final_num = float(s.final_score) if s.final_score else 0
                grade = s.grade or get_grade_for_score(school, final_num)
                subject_rows.append({
                    "subject": s.subject.name,
                    "ca": round(s.ca_score, 1) if s.ca_score else "—",
                    "exam": round(s.exam_score, 1) if s.exam_score else "—",
                    "final": round(final_num, 1),
                    "final_num": final_num,
                    "grade": grade,
                    "remarks": _get_remarks(final_num),
                })
        else:
            # Fallback: compute from raw scores
            from academics.models import Subject
            subjects = Subject.objects.filter(school=school).order_by("name")
            for subj in subjects:
                assessments = AssessmentScore.objects.filter(
                    student=student, subject=subj, term=term
                ) if term else AssessmentScore.objects.filter(student=student, subject=subj)
                exam_obj = ExamScore.objects.filter(
                    student=student, subject=subj, term=term
                ).first() if term else ExamScore.objects.filter(student=student, subject=subj).first()
                if not assessments.exists() and not exam_obj:
                    continue
                ca_scores = []
                for a in assessments:
                    try:
                        ca_scores.append(float(a.normalized_score))
                    except Exception:
                        try:
                            ca_scores.append(float(a.score))
                        except Exception:
                            pass
                ca_avg = round(sum(ca_scores) / len(ca_scores), 1) if ca_scores else 0.0
                try:
                    exam_score = float(exam_obj.normalized_score) if exam_obj else 0.0
                except Exception:
                    try:
                        exam_score = float(exam_obj.score) if exam_obj else 0.0
                    except Exception:
                        exam_score = 0.0
                exam_score = round(exam_score, 1)
                final_num = round((ca_avg * ca_weight / 100) + (exam_score * exam_weight / 100), 1)
                grade = get_grade_for_score(school, final_num)
                subject_rows.append({
                    "subject": subj.name,
                    "ca": ca_avg,
                    "exam": exam_score,
                    "final": final_num,
                    "final_num": final_num,
                    "grade": grade,
                    "remarks": _get_remarks(final_num),
                })
        # Legacy fallback
        if not subject_rows:
            from academics.models import Result
            for r in Result.objects.filter(student=student).select_related("subject").order_by("subject__name"):
                try:
                    fn = float(r.percentage)
                except Exception:
                    fn = 0
                subject_rows.append({
                    "subject": r.subject.name,
                    "ca": "—", "exam": "—",
                    "final": fn, "final_num": fn,
                    "grade": r.grade,
                    "remarks": _get_remarks(fn),
                })
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("enhanced_report_card score query failed: %s", exc)

    # Stats
    overall_avg = None
    term_gpa = None
    term_position = None
    numeric_finals = [r["final_num"] for r in subject_rows if isinstance(r.get("final_num"), (int, float))]
    if numeric_finals:
        overall_avg = round(sum(numeric_finals) / len(numeric_finals), 1)
    try:
        from academics.services import GradingService
        if term and student.class_name:
            rankings = GradingService.calculate_class_rankings(student.class_name, term, school)
            term_position = rankings.get(student.id)
        gpa = GradingService.calculate_term_gpa(student, term) if term else None
        if gpa:
            term_gpa = round(float(gpa), 2)
    except Exception:
        pass

    # Attendance
    attendance_text = "N/A"
    try:
        from operations.models import StudentAttendance
        att = StudentAttendance.objects.filter(student=student)
        if term and hasattr(term, "start_date") and term.start_date:
            att = att.filter(date__gte=term.start_date)
        if term and hasattr(term, "end_date") and term.end_date:
            att = att.filter(date__lte=term.end_date)
        total = att.count()
        present = att.filter(status="present").count()
        if total:
            pct = round(present / total * 100)
            attendance_text = f"{present}/{total} days ({pct}%)"
    except Exception:
        pass

    # AI Comment
    ai_comment = None
    try:
        ai_qs = AIStudentComment.objects.filter(student=student, school=school)
        if term:
            ai_qs_term = ai_qs.filter(term=term.name)
            ai_comment = ai_qs_term.order_by("-created_at").first() or ai_qs.order_by("-created_at").first()
        else:
            ai_comment = ai_qs.order_by("-created_at").first()
    except Exception:
        pass

    terms_for_selector = Term.objects.filter(school=school).order_by("-name")

    return render(request, "academics/enhanced_report_card.html", {
        "school": school,
        "student": student,
        "term": term,
        "terms": terms_for_selector,
        "subject_rows": subject_rows,
        "ca_weight": int(ca_weight),
        "exam_weight": int(exam_weight),
        "overall_avg": overall_avg,
        "term_gpa": term_gpa,
        "term_position": term_position,
        "attendance_text": attendance_text,
        "ai_comment": ai_comment,
        "can_manage": can_manage,
    })


def _get_remarks(score):
    try:
        s = float(score)
    except (ValueError, TypeError):
        return "—"
    if s >= 80: return "Excellent"
    if s >= 70: return "Very Good"
    if s >= 60: return "Good"
    if s >= 50: return "Pass"
    if s > 0:   return "Needs Improvement"
    return "—"
'''

# Only add if not already there or replace old stub
if "def enhanced_report_card(" not in views_text:
    views_path.write_text(views_text + NEW_VIEW, encoding="utf-8")
    print("  Added enhanced_report_card to academics/views.py")
else:
    # Replace the existing broken function
    # Find the function
    pattern = r'(\n# ── enhanced_report_card.*?(?=\n@login_required|\nclass |\ndef [a-z]|\Z))'
    match = re.search(pattern, views_text, re.DOTALL)
    if match:
        views_path.write_text(views_text[:match.start()] + NEW_VIEW + views_text[match.end():], encoding="utf-8")
        print("  Replaced enhanced_report_card in academics/views.py")
    else:
        # Try simpler replacement of function
        func_start = views_text.find("\ndef enhanced_report_card(")
        if func_start == -1:
            func_start = views_text.find("\n@login_required\ndef enhanced_report_card(")
        if func_start != -1:
            # Find next function/class at same indent level
            next_func = views_text.find("\ndef ", func_start + 10)
            next_dec = views_text.find("\n@", func_start + 10)
            if next_func == -1: next_func = len(views_text)
            if next_dec == -1: next_dec = len(views_text)
            end = min(next_func, next_dec)
            views_path.write_text(views_text[:func_start] + NEW_VIEW + views_text[end:], encoding="utf-8")
            print("  Replaced enhanced_report_card in academics/views.py (pattern 2)")
        else:
            views_path.write_text(views_text + NEW_VIEW, encoding="utf-8")
            print("  Appended enhanced_report_card to academics/views.py")

print("\nFix script complete.")
