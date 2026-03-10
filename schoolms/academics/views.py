from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q

from students.models import Student
from schools.models import School
from .models import Subject, ExamType, Term, Result


def _get_school(request):
    """Get current user's school."""
    if not request.user.is_authenticated:
        return None
    return getattr(request.user, "school", None)


def _user_can_manage_school(request):
    """Check if user can manage school (admin or teacher)."""
    if request.user.is_superuser:
        return True
    return request.user.role in ("admin", "teacher") and getattr(request.user, "school_id", None)


@login_required
def result_upload(request):
    """Upload student results - for teachers."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    
    # Only admins and teachers can upload results
    if not _user_can_manage_school(request):
        return redirect("home")
    
    # Get query parameters
    class_name = request.GET.get("class")
    subject_id = request.GET.get("subject")
    exam_type_id = request.GET.get("exam_type")
    term_id = request.GET.get("term")
    
    # Get filter options
    classes = Student.objects.filter(school=school).values_list("class_name", flat=True).distinct()
    classes = [c for c in classes if c]
    subjects = Subject.objects.filter(school=school).order_by("name")
    exam_types = ExamType.objects.filter(school=school).order_by("name")
    terms = Term.objects.filter(school=school).order_by("-is_current", "-id")
    
    # Get students filtered by class
    students = []
    if class_name:
        students = Student.objects.filter(school=school, class_name=class_name).select_related("user").order_by("admission_number")
    
    # Process form submission - handle multiple students at once
    if request.method == "POST":
        subject_id = request.POST.get("subject")
        exam_type_id = request.POST.get("exam_type")
        term_id = request.POST.get("term")
        
        if subject_id and exam_type_id and term_id:
            try:
                subject = Subject.objects.get(id=subject_id, school=school)
                exam_type = ExamType.objects.get(id=exam_type_id, school=school)
                term = Term.objects.get(id=term_id, school=school)
                
                saved_count = 0
                # Loop through all POST data to find score inputs
                for key, value in request.POST.items():
                    if key.startswith("score_student_") and value.strip():
                        student_id = key.replace("score_student_", "")
                        try:
                            score = float(value)
                            if 0 <= score <= 100:
                                student = Student.objects.get(id=student_id, school=school)
                                
                                # Check if result already exists
                                existing = Result.objects.filter(
                                    student=student,
                                    subject=subject,
                                    exam_type=exam_type,
                                    term=term
                                ).first()
                                
                                if existing:
                                    existing.score = score
                                    existing.save()
                                else:
                                    Result.objects.create(
                                        student=student,
                                        subject=subject,
                                        exam_type=exam_type,
                                        term=term,
                                        score=score
                                    )
                                saved_count += 1
                        except (Student.DoesNotExist, ValueError):
                            continue
                
                if saved_count > 0:
                    messages.success(request, f"Successfully saved {saved_count} score(s)")
                
                return redirect(request.get_full_path())
                
            except (Subject.DoesNotExist, ExamType.DoesNotExist, Term.DoesNotExist) as e:
                messages.error(request, "Invalid selection. Please try again.")
    
    # Get existing results for display
    existing_results = {}
    if class_name and subject_id and exam_type_id and term_id:
        results = Result.objects.filter(
            student__school=school,
            student__class_name=class_name,
            subject_id=subject_id,
            exam_type_id=exam_type_id,
            term_id=term_id
        )
        existing_results = {r.student_id: r.score for r in results}
    
    context = {
        "school": school,
        "classes": classes,
        "subjects": subjects,
        "exam_types": exam_types,
        "terms": terms,
        "students": students,
        "selected_class": class_name,
        "selected_subject": subject_id,
        "selected_exam_type": exam_type_id,
        "selected_term": term_id,
        "existing_results": existing_results,
    }
    
    return render(request, "academics/result_upload.html", context)


@login_required
def result_list(request):
    """View all results with filtering."""
    school = _get_school(request)
    if not school:
        return redirect("home")
    
    if not _user_can_manage_school(request):
        return redirect("home")
    
    # Get filter parameters
    class_name = request.GET.get("class")
    subject_id = request.GET.get("subject")
    term_id = request.GET.get("term")
    
    # Base query
    results = Result.objects.filter(student__school=school).select_related(
        "student", "student__user", "subject", "exam_type", "term"
    )
    
    # Apply filters
    if class_name:
        results = results.filter(student__class_name=class_name)
    if subject_id:
        results = results.filter(subject_id=subject_id)
    if term_id:
        results = results.filter(term_id=term_id)
    
    # Order by student and term
    results = results.order_by("student__admission_number", "term__name", "subject__name")
    
    # Get filter options
    classes = Student.objects.filter(school=school).values_list("class_name", flat=True).distinct()
    classes = [c for c in classes if c]
    subjects = Subject.objects.filter(school=school).order_by("name")
    terms = Term.objects.filter(school=school).order_by("-is_current", "-id")
    
    context = {
        "school": school,
        "results": results,
        "classes": classes,
        "subjects": subjects,
        "terms": terms,
        "selected_class": class_name,
        "selected_subject": subject_id,
        "selected_term": term_id,
    }
    
    return render(request, "academics/result_list.html", context)
