"""
Advanced Analytics Features for Mastex SchoolOS
- Predictive Analytics
- Trend Analysis
- Online Classes Integration
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Avg, Count, Q
from datetime import timedelta
import random

from students.models import Student
from schools.models import School
from academics.models import Result, Term, Homework, Quiz, Subject
from operations.models import StudentAttendance


# ==================== PREDICTIVE ANALYTICS ====================

@login_required
def predictive_analytics(request):
    """AI-powered student performance predictions."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    # Get students at risk
    students = Student.objects.filter(school=school).select_related('user')
    
    risk_students = []
    for student in students:
        # Calculate risk score based on attendance and grades
        attendance_records = StudentAttendance.objects.filter(student=student)
        total_days = attendance_records.count()
        present_days = attendance_records.filter(status='present').count()
        attendance_rate = (present_days / total_days * 100) if total_days > 0 else 100
        
        # Get average score
        results = Result.objects.filter(student=student)
        avg_score = results.aggregate(avg=Avg('score'))['avg'] or 0
        
        # Calculate risk (lower attendance + lower grades = higher risk)
        risk_score = 0
        if attendance_rate < 80:
            risk_score += 50 - attendance_rate
        if avg_score < 50:
            risk_score += 50 - avg_score
        
        if risk_score > 20:
            risk_students.append({
                'student': student,
                'risk_score': risk_score,
                'attendance_rate': attendance_rate,
                'avg_score': avg_score,
                'risk_level': 'High' if risk_score > 40 else 'Medium'
            })
    
    # Sort by risk
    risk_students.sort(key=lambda x: x['risk_score'], reverse=True)
    
    context = {
        'school': school,
        'risk_students': risk_students[:20],
        'total_at_risk': len(risk_students),
    }
    return render(request, 'academics/predictive_analytics.html', context)


@login_required
def predict_student_performance(request, student_id):
    """Predict a single student's performance."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'error': 'No school found'}, status=400)
    
    student = get_object_or_404(Student, id=student_id, school=school)
    
    # Get historical data
    results = Result.objects.filter(student=student).order_by('-term__start_date')
    
    if not results.exists():
        return JsonResponse({
            'prediction': 'Not enough data',
            'confidence': 0
        })
    
    # Simple prediction based on trend
    recent_scores = [r.score for r in results[:5]]
    avg_score = sum(recent_scores) / len(recent_scores)
    
    # Calculate trend
    if len(recent_scores) >= 2:
        trend = recent_scores[0] - recent_scores[-1]  # Comparing first vs last
    else:
        trend = 0
    
    # Predict next term
    predicted_score = avg_score + (trend * 0.3)  # Weighted trend
    
    # Confidence based on data available
    confidence = min(len(recent_scores) * 20, 100)
    
    return JsonResponse({
        'student': student.user.get_full_name() or student.user.username,
        'current_avg': round(avg_score, 1),
        'predicted_score': round(predicted_score, 1),
        'trend': 'Improving' if trend > 0 else 'Declining' if trend < 0 else 'Stable',
        'confidence': confidence,
        'recommendation': get_recommendation(predicted_score)
    })


def get_recommendation(score):
    """Get learning recommendation based on score."""
    if score >= 80:
        return "Excellent performance! Consider advanced challenges."
    elif score >= 60:
        return "Good progress. Focus on weak areas."
    elif score >= 40:
        return "Needs improvement. Consider extra tutoring."
    else:
        return "At risk. Urgent intervention recommended."


# ==================== TREND ANALYSIS ====================

@login_required
def trend_analysis(request):
    """Analyze performance trends over time."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    # Get terms
    terms = Term.objects.filter(school=school).order_by('-start_date')[:4]
    
    # Calculate average scores per term
    term_scores = []
    for term in terms:
        results = Result.objects.filter(student__school=school, term=term)
        avg = results.aggregate(avg=Avg('score'))['avg'] or 0
        term_scores.append({
            'term': term.name,
            'avg_score': round(avg, 1),
            'total_results': results.count()
        })
    
    # Subject trends
    subjects = Subject.objects.filter(school=school)
    subject_trends = []
    for subject in subjects:
        avg = Result.objects.filter(student__school=school, subject=subject).aggregate(avg=Avg('score'))['avg'] or 0
        subject_trends.append({
            'subject': subject.name,
            'avg_score': round(avg, 1)
        })
    
    context = {
        'school': school,
        'term_scores': term_scores,
        'subject_trends': subject_trends,
    }
    return render(request, 'academics/trend_analysis.html', context)


@login_required
def get_trend_data(request):
    """Get trend data for charts."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'error': 'No school found'}, status=400)
    
    terms = Term.objects.filter(school=school).order_by('start_date')
    
    labels = []
    scores = []
    
    for term in terms:
        labels.append(term.name)
        avg = Result.objects.filter(student__school=school, term=term).aggregate(avg=Avg('score'))['avg'] or 0
        scores.append(round(avg, 1))
    
    return JsonResponse({
        'labels': labels,
        'scores': scores
    })


# ==================== ONLINE CLASSES ====================

@login_required
def online_classes_page(request):
    """Online classes dashboard."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    context = {
        'school': school,
    }
    return render(request, 'academics/online_classes.html', context)


@login_required
def create_meeting(request):
    """Create an online meeting (Zoom/Meet)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)
    
    import json
    try:
        data = json.loads(request.body)
        
        # In production, integrate with Zoom/Google Meet API
        meeting = {
            'id': random.randint(100000, 999999),
            'topic': data.get('topic'),
            'start_time': data.get('start_time'),
            'duration': data.get('duration', 60),
            'join_url': f"https://meet.google.com/abc-defg-hij",  # Placeholder
            'host_url': f"https://meet.google.com/abc-defg-hij",  # Placeholder
        }
        
        return JsonResponse({
            'success': True,
            'meeting': meeting,
            'message': 'Meeting created successfully!'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def join_meeting(request, meeting_id):
    """Join an online meeting."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    # In production, verify meeting exists and user has access
    join_url = f"https://meet.google.com/abc-defg-hij"
    
    context = {
        'school': school,
        'meeting_id': meeting_id,
        'join_url': join_url,
    }
    return render(request, 'academics/join_meeting.html', context)
