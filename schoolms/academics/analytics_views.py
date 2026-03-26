"""
Performance Analytics Views for Mastex SchoolOS
Interactive charts and data analysis for student performance
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from students.models import Student
from academics.models import Result, Term, ExamType
from operations.models import StudentAttendance
from schools.models import School


@login_required
def performance_dashboard(request):
    """Main performance analytics dashboard."""
    school = getattr(request.user, 'school', None)
    
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    # Get current term
    current_term = Term.objects.filter(school=school, is_current=True).first()
    
    # Get classes
    classes = Student.objects.filter(school=school).values_list('class_name', flat=True).distinct()
    
    context = {
        'school': school,
        'classes': [c for c in classes if c],
        'current_term': current_term,
    }
    return render(request, 'academics/performance_dashboard.html', context)


@login_required
def get_class_performance(request, class_name):
    """Get performance data for a specific class."""
    school = getattr(request.user, 'school', None)
    
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'error': 'No school found'}, status=400)
    
    # Get term from query params
    term_id = request.GET.get('term')
    term = None
    if term_id:
        term = get_object_or_404(Term, id=term_id, school=school)
    
    # Get students in class
    students = Student.objects.filter(school=school, class_name=class_name).select_related('user')
    
    # Get results
    results_query = Result.objects.filter(student__in=students)
    if term:
        results_query = results_query.filter(term=term)
    
    results = results_query.select_related('subject', 'exam_type', 'student', 'student__user')
    
    # Calculate statistics
    total_students = students.count()
    students_with_results = results.values('student').distinct().count()
    
    if results.exists():
        avg_score = results.aggregate(avg=Avg('score'))['avg'] or 0
        highest_score = results.order_by('-score').first()
        lowest_score = results.order_by('score').first()
        
        # Pass/Fail counts
        passed = results.filter(score__gte=50).count()
        failed = results.filter(score__lt=50).count()
    else:
        avg_score = 0
        highest_score = None
        lowest_score = None
        passed = 0
        failed = 0
    
    # Get performance by subject
    subject_performance = results.values('subject__name').annotate(
        avg_score=Avg('score'),
        total_students=Count('student', distinct=True)
    ).order_by('subject__name')
    
    # Get performance trend (by exam type)
    exam_type_performance = results.values('exam_type__name').annotate(
        avg_score=Avg('score'),
        total_exams=Count('id')
    ).order_by('exam_type__name')
    
    # Get attendance data
    attendance_query = StudentAttendance.objects.filter(student__in=students)
    if term:
        # Filter by term dates if available
        attendance_query = attendance_query.filter(date__gte=term.start_date, date__lte=term.end_date)
    
    total_days = attendance_query.count()
    present_days = attendance_query.filter(status='present').count()
    attendance_rate = (present_days / total_days * 100) if total_days > 0 else 0
    
    return JsonResponse({
        'class_name': class_name,
        'total_students': total_students,
        'students_with_results': students_with_results,
        'statistics': {
            'average_score': round(avg_score, 1),
            'highest_score': highest_score.score if highest_score else None,
            'highest_student': highest_score.student.user.get_full_name() if highest_score else None,
            'lowest_score': lowest_score.score if lowest_score else None,
            'lowest_student': lowest_score.student.user.get_full_name() if lowest_score else None,
            'passed': passed,
            'failed': failed,
            'pass_rate': round((passed / (passed + failed) * 100) if (passed + failed) > 0 else 0, 1),
        },
        'subject_performance': list(subject_performance),
        'exam_type_performance': list(exam_type_performance),
        'attendance': {
            'total_days': total_days,
            'present_days': present_days,
            'attendance_rate': round(attendance_rate, 1),
        }
    })


@login_required
def get_student_performance(request, student_id):
    """Get detailed performance data for a specific student."""
    school = getattr(request.user, 'school', None)
    
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'error': 'No school found'}, status=400)
    
    student = get_object_or_404(Student, id=student_id, school=school)
    
    # Get term from query params
    term_id = request.GET.get('term')
    term = None
    if term_id:
        term = get_object_or_404(Term, id=term_id, school=school)
    
    # Get results
    results_query = Result.objects.filter(student=student)
    if term:
        results_query = results_query.filter(term=term)
    
    results = results_query.select_related('subject', 'exam_type').order_by('-exam_type__created_at')
    
    # Calculate overall statistics
    if results.exists():
        avg_score = results.aggregate(avg=Avg('score'))['avg'] or 0
        total_subjects = results.values('subject').distinct().count()
        best_subject = results.values('subject__name').annotate(avg=Avg('score')).order_by('-avg').first()
        worst_subject = results.values('subject__name').annotate(avg=Avg('score')).order_by('avg').first()
    else:
        avg_score = 0
        total_subjects = 0
        best_subject = None
        worst_subject = None
    
    # Get performance by term
    term_performance = Result.objects.filter(student=student).values(
        'term__name'
    ).annotate(
        avg_score=Avg('score'),
        total_exams=Count('id')
    ).order_by('term__name')
    
    # Get performance by subject
    subject_performance = results.values('subject__name').annotate(
        avg_score=Avg('score'),
        total_exams=Count('id')
    ).order_by('-avg_score')
    
    # Get attendance data
    attendance_query = StudentAttendance.objects.filter(student=student)
    if term:
        attendance_query = attendance_query.filter(date__gte=term.start_date, date__lte=term.end_date)
    
    total_days = attendance_query.count()
    present_days = attendance_query.filter(status='present').count()
    late_days = attendance_query.filter(status='late').count()
    absent_days = attendance_query.filter(status='absent').count()
    attendance_rate = (present_days / total_days * 100) if total_days > 0 else 0
    
    # Get individual exam results
    exam_results = []
    for r in results[:20]:  # Last 20 exams
        exam_results.append({
            'subject': r.subject.name if r.subject else 'N/A',
            'exam_type': r.exam_type.name if r.exam_type else 'N/A',
            'score': r.score,
            'grade': calculate_grade(r.score),
            'term': r.term.name if r.term else 'N/A',
            'date': r.exam_type.created_at.strftime('%Y-%m-%d') if r.exam_type and r.exam_type.created_at else None,
        })
    
    return JsonResponse({
        'student': {
            'id': student.id,
            'name': student.user.get_full_name() or student.user.username,
            'admission_number': student.admission_number,
            'class_name': student.class_name,
        },
        'statistics': {
            'average_score': round(avg_score, 1),
            'total_subjects': total_subjects,
            'best_subject': best_subject['subject__name'] if best_subject else None,
            'best_subject_score': round(best_subject['avg'], 1) if best_subject else None,
            'worst_subject': worst_subject['subject__name'] if worst_subject else None,
            'worst_subject_score': round(worst_subject['avg'], 1) if worst_subject else None,
        },
        'term_performance': list(term_performance),
        'subject_performance': list(subject_performance),
        'attendance': {
            'total_days': total_days,
            'present_days': present_days,
            'late_days': late_days,
            'absent_days': absent_days,
            'attendance_rate': round(attendance_rate, 1),
        },
        'recent_exams': exam_results,
    })


@login_required
def get_school_statistics(request):
    """Get overall school statistics."""
    school = getattr(request.user, 'school', None)
    
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'error': 'No school found'}, status=400)
    
    # Get all students
    students = Student.objects.filter(school=school)
    total_students = students.count()
    
    # Get results for current term
    current_term = Term.objects.filter(school=school, is_current=True).first()
    
    results_query = Result.objects.filter(student__in=students)
    if current_term:
        results_query = results_query.filter(term=current_term)
    
    # Class performance
    class_performance = students.values('class_name').annotate(
        total_students=Count('id'),
        avg_score=Avg('result__score', filter=Result.objects.filter(student__in=students))
    ).order_by('class_name')
    
    # Gender performance
    male_students = students.filter(user__gender='male')
    female_students = students.filter(user__gender='female')
    
    male_avg = Result.objects.filter(student__in=male_students).aggregate(avg=Avg('score'))['avg'] or 0
    female_avg = Result.objects.filter(student__in=female_students).aggregate(avg=Avg('score'))['avg'] or 0
    
    # Subject popularity (most tested subjects)
    subject_popularity = results_query.values('subject__name').annotate(
        total_exams=Count('id'),
        avg_score=Avg('score')
    ).order_by('-total_exams')[:10]
    
    # Pass rates by class
    pass_rates = []
    for class_name in students.values_list('class_name', flat=True).distinct():
        class_students = students.filter(class_name=class_name)
        class_results = Result.objects.filter(student__in=class_students)
        if current_term:
            class_results = class_results.filter(term=current_term)
        
        passed = class_results.filter(score__gte=50).count()
        total = class_results.count()
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        pass_rates.append({
            'class': class_name,
            'pass_rate': round(pass_rate, 1),
            'total_students': class_students.count(),
        })
    
    return JsonResponse({
        'total_students': total_students,
        'current_term': current_term.name if current_term else None,
        'class_performance': list(class_performance),
        'gender_performance': {
            'male_avg': round(male_avg, 1),
            'female_avg': round(female_avg, 1),
        },
        'subject_popularity': list(subject_popularity),
        'pass_rates': pass_rates,
    })


def calculate_grade(score):
    """Calculate grade based on score."""
    if score >= 90:
        return 'A+'
    elif score >= 80:
        return 'A'
    elif score >= 70:
        return 'B+'
    elif score >= 60:
        return 'B'
    elif score >= 50:
        return 'C'
    elif score >= 40:
        return 'D'
    else:
        return 'F'
