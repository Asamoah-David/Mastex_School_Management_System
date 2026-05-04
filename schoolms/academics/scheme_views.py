"""
scheme_views.py — Assessment Scheme, Manual Exam, and Report-Card Score views.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import user_can_manage_school
from core.feature_access import feature_required
from core.utils import get_school as _get_school
from students.models import Student, SchoolClass

from .models import (
    AssessmentScheme,
    AssessmentSchemeItem,
    ManualExamScore,
    ManualExamStudentScore,
    StudentReportCardScore,
    Subject,
    Term,
    AcademicYear,
    Quiz,
)
from .services import SchemeBasedGradingService


def _require_manager(request, school):
    """Return a redirect response if the user cannot manage the school, else None."""
    if not school:
        return redirect("home")
    if not (request.user.is_superuser or user_can_manage_school(request.user)):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect("home")
    return None


def _get_user_school(request):
    return _get_school(request)


def _school_classes(school):
    names = set(SchoolClass.objects.filter(school=school).values_list("name", flat=True))
    names |= set(Student.objects.filter(school=school).exclude(class_name="").values_list("class_name", flat=True))
    return sorted(names, key=str.lower)


# ─────────────────────────────────────────────────────────────────────────────
# Assessment Scheme
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@feature_required("report_cards")
def assessment_scheme_list(request):
    school = _get_user_school(request)
    if not school:
        return redirect("home")
    schemes = AssessmentScheme.objects.filter(school=school).select_related("subject", "term").prefetch_related("items")
    return render(request, "academics/assessment_scheme_list.html", {
        "school": school,
        "schemes": schemes,
    })


@login_required
@feature_required("report_cards")
def assessment_scheme_create(request):
    school = _get_user_school(request)
    denied = _require_manager(request, school)
    if denied:
        return denied

    subjects = Subject.objects.filter(school=school).order_by("name")
    terms = Term.objects.filter(school=school).order_by("-is_current", "name")
    academic_years = AcademicYear.objects.filter(school=school).order_by("-start_date")
    classes = _school_classes(school)

    if request.method == "POST":
        class_name = request.POST.get("class_name", "").strip()
        subject_id = request.POST.get("subject_id")
        term_id = request.POST.get("term_id")
        academic_year_id = request.POST.get("academic_year_id") or None
        ca_weight = request.POST.get("ca_weight", "50")
        exam_weight = request.POST.get("exam_weight", "50")
        notes = request.POST.get("notes", "").strip()

        if not (class_name and subject_id and term_id):
            messages.error(request, "Class, subject, and term are required.")
        else:
            try:
                subject = Subject.objects.get(pk=subject_id, school=school)
                term = Term.objects.get(pk=term_id, school=school)
                academic_year = AcademicYear.objects.filter(pk=academic_year_id, school=school).first() if academic_year_id else None
                ca_w = float(ca_weight)
                exam_w = float(exam_weight)
                if round(ca_w + exam_w, 4) != 100.0:
                    raise ValueError("CA and exam weights must sum to 100.")
                scheme = AssessmentScheme.objects.create(
                    school=school,
                    class_name=class_name,
                    subject=subject,
                    term=term,
                    academic_year=academic_year,
                    ca_weight=ca_w,
                    exam_weight=exam_w,
                    notes=notes,
                    created_by=request.user,
                )
                messages.success(request, f"Assessment scheme created for {class_name} — {subject}.")
                return redirect("academics:assessment_scheme_detail", pk=scheme.pk)
            except AssessmentScheme.objects.model.DoesNotExist:
                messages.error(request, "Invalid subject or term.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Error creating scheme: {e}")

    return render(request, "academics/assessment_scheme_form.html", {
        "school": school,
        "subjects": subjects,
        "terms": terms,
        "academic_years": academic_years,
        "classes": classes,
        "editing": False,
    })


@login_required
@feature_required("report_cards")
def assessment_scheme_detail(request, pk):
    school = _get_user_school(request)
    if not school:
        return redirect("home")
    scheme = get_object_or_404(AssessmentScheme, pk=pk, school=school)
    items = scheme.items.all()

    from omr.models import OmrExam
    omr_exams = OmrExam.objects.filter(school=school).order_by("-date")
    quizzes = Quiz.objects.filter(school=school).order_by("-created_at")
    manual_exams = ManualExamScore.objects.filter(
        school=school, subject=scheme.subject, term=scheme.term, class_name=scheme.class_name
    )

    source_choices = AssessmentSchemeItem.SOURCE_TYPE_CHOICES
    category_choices = AssessmentSchemeItem.CATEGORY_CHOICES

    return render(request, "academics/assessment_scheme_detail.html", {
        "school": school,
        "scheme": scheme,
        "items": items,
        "omr_exams": omr_exams,
        "quizzes": quizzes,
        "manual_exams": manual_exams,
        "source_choices": source_choices,
        "category_choices": category_choices,
    })


@login_required
@feature_required("report_cards")
def assessment_scheme_edit(request, pk):
    school = _get_user_school(request)
    denied = _require_manager(request, school)
    if denied:
        return denied
    scheme = get_object_or_404(AssessmentScheme, pk=pk, school=school)
    subjects = Subject.objects.filter(school=school).order_by("name")
    terms = Term.objects.filter(school=school).order_by("-is_current", "name")
    academic_years = AcademicYear.objects.filter(school=school).order_by("-start_date")
    classes = _school_classes(school)

    if request.method == "POST":
        try:
            ca_w = float(request.POST.get("ca_weight", "50"))
            exam_w = float(request.POST.get("exam_weight", "50"))
            if round(ca_w + exam_w, 4) != 100.0:
                raise ValueError("CA and exam weights must sum to 100.")
            scheme.ca_weight = ca_w
            scheme.exam_weight = exam_w
            scheme.notes = request.POST.get("notes", "").strip()
            scheme.is_active = request.POST.get("is_active") == "on"
            academic_year_id = request.POST.get("academic_year_id") or None
            scheme.academic_year = AcademicYear.objects.filter(pk=academic_year_id, school=school).first() if academic_year_id else None
            scheme.save()
            messages.success(request, "Scheme updated.")
            return redirect("academics:assessment_scheme_detail", pk=scheme.pk)
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error updating scheme: {e}")

    return render(request, "academics/assessment_scheme_form.html", {
        "school": school,
        "scheme": scheme,
        "subjects": subjects,
        "terms": terms,
        "academic_years": academic_years,
        "classes": classes,
        "editing": True,
    })


@login_required
@feature_required("report_cards")
@require_POST
def assessment_scheme_delete(request, pk):
    school = _get_user_school(request)
    denied = _require_manager(request, school)
    if denied:
        return denied
    scheme = get_object_or_404(AssessmentScheme, pk=pk, school=school)
    scheme.delete()
    messages.success(request, "Scheme deleted.")
    return redirect("academics:assessment_scheme_list")


@login_required
@feature_required("report_cards")
@require_POST
def assessment_scheme_add_item(request, pk):
    school = _get_user_school(request)
    denied = _require_manager(request, school)
    if denied:
        return denied
    scheme = get_object_or_404(AssessmentScheme, pk=pk, school=school)
    try:
        source_type = request.POST.get("source_type", "")
        source_id = request.POST.get("source_id") or None
        category = request.POST.get("category", "")
        label = request.POST.get("label", "").strip()
        max_score = float(request.POST.get("max_score", "100"))
        order_index = int(request.POST.get("order_index", "0"))

        if not (source_type and category and label):
            messages.error(request, "Source type, category, and label are required.")
        else:
            AssessmentSchemeItem.objects.create(
                scheme=scheme,
                source_type=source_type,
                source_id=int(source_id) if source_id else None,
                category=category,
                label=label,
                max_score=max_score,
                order_index=order_index,
            )
            messages.success(request, f"Item '{label}' added to scheme.")
    except Exception as e:
        messages.error(request, f"Error adding item: {e}")
    return redirect("academics:assessment_scheme_detail", pk=scheme.pk)


@login_required
@feature_required("report_cards")
@require_POST
def assessment_scheme_remove_item(request, pk, item_pk):
    school = _get_user_school(request)
    denied = _require_manager(request, school)
    if denied:
        return denied
    scheme = get_object_or_404(AssessmentScheme, pk=pk, school=school)
    item = get_object_or_404(AssessmentSchemeItem, pk=item_pk, scheme=scheme)
    item.delete()
    messages.success(request, "Item removed.")
    return redirect("academics:assessment_scheme_detail", pk=scheme.pk)


# ─────────────────────────────────────────────────────────────────────────────
# Manual Exam
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@feature_required("report_cards")
def manual_exam_list(request):
    school = _get_user_school(request)
    if not school:
        return redirect("home")
    exams = ManualExamScore.objects.filter(school=school).select_related("subject", "term")
    return render(request, "academics/manual_exam_list.html", {
        "school": school,
        "exams": exams,
    })


@login_required
@feature_required("report_cards")
def manual_exam_create(request):
    school = _get_user_school(request)
    denied = _require_manager(request, school)
    if denied:
        return denied
    subjects = Subject.objects.filter(school=school).order_by("name")
    terms = Term.objects.filter(school=school).order_by("-is_current", "name")
    classes = _school_classes(school)

    if request.method == "POST":
        exam_title = request.POST.get("exam_title", "").strip()
        subject_id = request.POST.get("subject_id")
        term_id = request.POST.get("term_id")
        class_name = request.POST.get("class_name", "").strip()
        max_score = request.POST.get("max_score", "100")
        date = request.POST.get("date") or None
        notes = request.POST.get("notes", "").strip()

        if not (exam_title and subject_id and term_id and class_name):
            messages.error(request, "Title, subject, term, and class are required.")
        else:
            try:
                subject = Subject.objects.get(pk=subject_id, school=school)
                term = Term.objects.get(pk=term_id, school=school)
                exam = ManualExamScore.objects.create(
                    school=school,
                    exam_title=exam_title,
                    subject=subject,
                    term=term,
                    class_name=class_name,
                    max_score=float(max_score),
                    date=date,
                    notes=notes,
                    created_by=request.user,
                )
                messages.success(request, f"Manual exam '{exam_title}' created.")
                return redirect("academics:manual_exam_score_entry", pk=exam.pk)
            except Exception as e:
                messages.error(request, f"Error creating exam: {e}")

    return render(request, "academics/manual_exam_form.html", {
        "school": school,
        "subjects": subjects,
        "terms": terms,
        "classes": classes,
    })


@login_required
@feature_required("report_cards")
def manual_exam_score_entry(request, pk):
    school = _get_user_school(request)
    denied = _require_manager(request, school)
    if denied:
        return denied
    exam = get_object_or_404(ManualExamScore, pk=pk, school=school)
    students = Student.objects.filter(school=school, class_name=exam.class_name).order_by("admission_number")
    existing = {s.student_id: s for s in ManualExamStudentScore.objects.filter(exam=exam)}

    if request.method == "POST":
        saved = 0
        errors = []
        for student in students:
            key = f"score_{student.pk}"
            raw = request.POST.get(key, "").strip()
            if raw == "":
                continue
            try:
                score_val = float(raw)
                if score_val < 0 or score_val > exam.max_score:
                    errors.append(f"{student}: score {score_val} out of range (0–{exam.max_score}).")
                    continue
                obj, _ = ManualExamStudentScore.objects.update_or_create(
                    exam=exam,
                    student=student,
                    defaults={"score": score_val, "remarks": request.POST.get(f"remarks_{student.pk}", "").strip()},
                )
                try:
                    obj.full_clean()
                    obj.save()
                except Exception as exc:
                    errors.append(f"{student}: {exc}")
                    continue
                saved += 1
            except ValueError:
                errors.append(f"{student}: invalid score '{raw}'.")
        if errors:
            for err in errors:
                messages.warning(request, err)
        if saved:
            messages.success(request, f"{saved} score(s) saved.")
        return redirect("academics:manual_exam_score_entry", pk=exam.pk)

    rows = []
    for student in students:
        entry = existing.get(student.pk)
        rows.append({
            "student": student,
            "score": entry.score if entry else "",
            "remarks": entry.remarks if entry else "",
        })

    return render(request, "academics/manual_exam_score_entry.html", {
        "school": school,
        "exam": exam,
        "rows": rows,
    })


@login_required
@feature_required("report_cards")
@require_POST
def manual_exam_delete(request, pk):
    school = _get_user_school(request)
    denied = _require_manager(request, school)
    if denied:
        return denied
    exam = get_object_or_404(ManualExamScore, pk=pk, school=school)
    exam.delete()
    messages.success(request, "Manual exam deleted.")
    return redirect("academics:manual_exam_list")


# ─────────────────────────────────────────────────────────────────────────────
# Report Card Score Preview
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@feature_required("report_cards")
def report_card_score_list(request):
    school = _get_user_school(request)
    denied = _require_manager(request, school)
    if denied:
        return denied
    terms = Term.objects.filter(school=school).order_by("-is_current", "name")
    classes = _school_classes(school)

    selected_term_id = request.GET.get("term_id")
    selected_class = request.GET.get("class_name", "").strip()

    scores = StudentReportCardScore.objects.filter(school=school).select_related(
        "student__user", "subject", "term", "scheme"
    )
    if selected_term_id:
        scores = scores.filter(term_id=selected_term_id)
    if selected_class:
        scores = scores.filter(student__class_name=selected_class)

    return render(request, "academics/report_card_score_list.html", {
        "school": school,
        "terms": terms,
        "classes": classes,
        "scores": scores,
        "selected_term_id": selected_term_id,
        "selected_class": selected_class,
    })


@login_required
@feature_required("report_cards")
@require_POST
def report_card_score_calculate(request, scheme_pk):
    school = _get_user_school(request)
    denied = _require_manager(request, school)
    if denied:
        return denied
    scheme = get_object_or_404(AssessmentScheme, pk=scheme_pk, school=school)
    results = SchemeBasedGradingService.compute_for_class(scheme)
    messages.success(request, f"Calculated {len(results)} student report card score(s) for {scheme.class_name} — {scheme.subject}.")
    return redirect("academics:report_card_score_list")
