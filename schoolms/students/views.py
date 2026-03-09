from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.hashers import make_password
from django.contrib import messages

from .models import Student
from accounts.models import User
from schools.models import School


def _user_can_manage_school(request):
    if request.user.is_superuser:
        return True
    return request.user.role in ("admin", "teacher") and getattr(request.user, "school_id", None)


@login_required
def parent_dashboard(request):
    try:
        from finance.models import Fee
        from academics.models import Result, ExamType, Term
        
        children = Student.objects.filter(parent=request.user).select_related("school", "user")
        
        # Handle case with no children
        if not children:
            return render(request, "students/parent_dashboard.html", {
                "children": [],
                "fees_by_child": {},
                "results_by_child": {},
                "stats_by_child": {},
                "terms": [],
                "exam_types": [],
            })
        
        # Get fees for all children
        children_ids = [c.id for c in children]
        fees = Fee.objects.filter(student_id__in=children_ids).select_related("student", "student__user").order_by("-created_at")
        
        # Group fees by child
        fees_by_child = {}
        for fee in fees:
            child_id = fee.student_id
            if child_id not in fees_by_child:
                fees_by_child[child_id] = []
            fees_by_child[child_id].append(fee)
        
        # Get results for all children
        results_by_child = {}
        results = Result.objects.filter(student_id__in=children_ids).select_related("student", "subject", "exam_type", "term")
        
        for result in results:
            child_id = result.student_id
            if child_id not in results_by_child:
                results_by_child[child_id] = []
            results_by_child[child_id].append(result)
        
        # Calculate average and position for each child
        stats_by_child = {}
        for child in children:
            child_results = results_by_child.get(child.id, [])
            if child_results:
                total = sum(r.score for r in child_results)
                avg = total / len(child_results)
                # Calculate position
                all_students_in_class = Student.objects.filter(school=child.school, class_name=child.class_name).values_list('id', flat=True)
                scores = []
                for sid in all_students_in_class:
                    rlist = Result.objects.filter(student_id=sid)
                    if rlist:
                        avg_score = sum(r.score for r in rlist) / len(rlist)
                        scores.append((sid, avg_score))
                scores.sort(key=lambda x: x[1], reverse=True)
                position = next((i+1 for i, (sid, _) in enumerate(scores) if sid == child.id), None)
                stats_by_child[child.id] = {"average": round(avg, 1), "position": position, "total_subjects": len(child_results)}
            else:
                stats_by_child[child.id] = {"average": None, "position": None, "total_subjects": 0}
        
        # Get available terms and exam types
        schools = [c.school for c in children]
        terms = Term.objects.filter(school__in=schools).order_by("-is_current", "-id") if schools else []
        exam_types = ExamType.objects.filter(school__in=schools) if schools else []
        
        return render(request, "students/parent_dashboard.html", {
            "children": children,
            "fees_by_child": fees_by_child,
            "results_by_child": results_by_child,
            "stats_by_child": stats_by_child,
            "terms": terms,
            "exam_types": exam_types,
        })
    except Exception as e:
        # If any error, still show the page with empty data
        return render(request, "students/parent_dashboard.html", {
            "children": [],
            "fees_by_child": {},
            "results_by_child": {},
            "stats_by_child": {},
            "terms": [],
            "exam_types": [],
        })


@login_required
def portal(request):
    """Single portal URL: parents see children; students see own dashboard."""
    if request.user.role == "parent":
        return parent_dashboard(request)
    if request.user.role == "student":
        try:
            student = Student.objects.get(user=request.user)
            # Get results for this student
            from academics.models import Result, ExamType, Term
            results = Result.objects.filter(student=student).select_related("subject", "exam_type", "term").order_by("-id")
            
            # Calculate average and position
            stats = {}
            if results:
                total = sum(r.score for r in results)
                avg = total / len(results)
                # Calculate position in class
                all_students = Student.objects.filter(school=student.school, class_name=student.class_name).values_list('id', flat=True)
                scores = []
                for sid in all_students:
                    rlist = Result.objects.filter(student_id=sid)
                    if rlist:
                        avg_score = sum(r.score for r in rlist) / len(rlist)
                        scores.append((sid, avg_score))
                scores.sort(key=lambda x: x[1], reverse=True)
                position = next((i+1 for i, (sid, _) in enumerate(scores) if sid == student.id), None)
                stats = {"average": round(avg, 1), "position": position, "total_subjects": len(results)}
            else:
                stats = {"average": None, "position": None, "total_subjects": 0}
            
            # Get available terms and exam types
            terms = Term.objects.filter(school=student.school).order_by("-is_current", "-id")
            exam_types = ExamType.objects.filter(school=student.school)
            
            return render(request, "students/student_portal.html", {
                "student": student,
                "results": results,
                "stats": stats,
                "terms": terms,
                "exam_types": exam_types,
            })
        except Student.DoesNotExist:
            return render(request, "students/student_portal.html", {"student": None})
    return redirect("home")


@login_required
def student_list(request):
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    students = Student.objects.filter(school=school).select_related("user", "parent").order_by("class_name", "admission_number")
    
    # Group students by class
    students_by_class = {}
    for student in students:
        class_name = student.class_name or "Unassigned"
        if class_name not in students_by_class:
            students_by_class[class_name] = []
        students_by_class[class_name].append(student)
    
    return render(request, "students/student_list.html", {"students": students, "students_by_class": students_by_class, "school": school})


@login_required
def student_detail(request, pk):
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    student = get_object_or_404(Student, pk=pk, school=school)
    return render(request, "students/student_detail.html", {"student": student})


@login_required
def student_register(request):
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        password = request.POST.get("password", "")
        admission_number = request.POST.get("admission_number", "").strip()
        class_name = request.POST.get("class_name", "").strip()
        parent_id = request.POST.get("parent") or None
        if username and admission_number and password:
            if not User.objects.filter(username=username).exists():
                user = User.objects.create(
                    username=username,
                    email=email or f"{username}@school.local",
                    first_name=first_name,
                    last_name=last_name,
                    password=make_password(password),
                    role="student",
                    school=school,
                )
                Student.objects.create(
                    school=school,
                    user=user,
                    admission_number=admission_number,
                    class_name=class_name,
                    parent_id=parent_id or None,
                )
                return redirect("students:student_list")
    parents = User.objects.filter(school=school, role="parent").order_by("username")
    return render(request, "students/student_register.html", {"school": school, "parents": parents})


@login_required
def student_delete(request, pk):
    """Delete a student."""
    if not _user_can_manage_school(request):
        return redirect("home")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    student = get_object_or_404(Student, pk=pk, school=school)
    
    if request.method == "POST":
        # Also delete the associated user
        user = student.user
        student.delete()
        user.delete()
        messages.success(request, f"Student '{user.get_full_name() or user.username}' has been deleted.")
        return redirect("students:student_list")
    
    return render(request, "students/confirm_delete.html", {
        "object": student,
        "type": "student",
        "cancel_url": "students:student_list"
    })
