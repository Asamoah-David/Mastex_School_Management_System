"""
Advanced Analytics Features for Mastex SchoolOS
- Predictive Analytics
- Trend Analysis
- Online Classes Integration
- AI Student Comments
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from accounts.permissions import can_create_academic_content
from django.utils import timezone
from django.db.models import Avg as DB_Avg, Count, Q
from datetime import timedelta, datetime
from datetime import datetime as dt
import functools
import logging
import random
import uuid

logger = logging.getLogger(__name__)

from students.models import Student
from schools.models import School
from academics.models import Result, Term, Homework, Quiz, Subject, OnlineMeeting, AIStudentComment
from operations.models import StudentAttendance
from services.sms_service import SMSService
try:
    from notifications.models import Notification
except ImportError:
    Notification = None
from schools.features import is_feature_enabled
from accounts.decorators import admin_required, teacher_required


# ==================== ROLE CHECK DECORATOR ====================

def analytics_role_required(view_func):
    """Decorator to restrict analytics views to school_admin, teacher, hod, deputy_head"""
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        if can_create_academic_content(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'You do not have permission to access analytics features.')
        return redirect('home')
    return wrapper


# ==================== FEATURE CHECK HELPER ====================

def check_analytics_feature(request, feature_key='performance_analytics', fallback_url='home'):
    """Check if analytics feature is enabled for the school"""
    if request.user.is_superuser:
        return None  # Allow superusers
    
    if not is_feature_enabled(request, feature_key):
        messages.error(request, 'This feature is disabled for your school. Please contact the platform administrator.')
        return redirect(fallback_url)
    
    return None


# ==================== PREDICTIVE ANALYTICS ====================

@login_required
def predictive_analytics(request):
    """AI-powered student performance predictions."""
    if not can_create_academic_content(request.user):
        messages.error(request, 'You do not have permission to access analytics features.')
        return redirect('home')
    
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    # Check if feature is enabled for the school
    if not request.user.is_superuser and not is_feature_enabled(request, 'performance_analytics'):
        messages.error(request, 'Performance Analytics is disabled for your school.')
        return redirect('home')
    
    from django.db.models import FloatField, ExpressionWrapper, Case, When, Value

    # Single aggregate query: attendance stats + avg score per student
    students_qs = (
        Student.objects.filter(school=school, status='active')
        .select_related('user')
        .annotate(
            total_att=Count('attendances', distinct=True),
            present_att=Count(
                'attendances',
                filter=Q(attendances__status='present'),
                distinct=True,
            ),
            avg_score=DB_Avg('result__score'),
        )
    )

    risk_students = []
    for student in students_qs:
        total_days = student.total_att or 0
        present_days = student.present_att or 0
        attendance_rate = (present_days / total_days * 100) if total_days > 0 else 100.0
        avg_score = float(student.avg_score or 0)

        # Multi-feature weighted risk score
        risk_score = 0.0
        if attendance_rate < 80:
            risk_score += (80 - attendance_rate) * 0.6   # attendance weight 60%
        if avg_score < 50:
            risk_score += (50 - avg_score) * 0.4          # grade weight 40%

        if risk_score > 15:
            risk_students.append({
                'student': student,
                'risk_score': round(risk_score, 1),
                'attendance_rate': round(attendance_rate, 1),
                'avg_score': round(avg_score, 1),
                'risk_level': 'High' if risk_score > 35 else 'Medium',
            })

    risk_students.sort(key=lambda x: x['risk_score'], reverse=True)

    # School-wide avg for benchmarking
    school_avg = Result.objects.filter(school=school).aggregate(avg=DB_Avg('score'))['avg'] or 0

    # Class benchmarking: avg per class vs school avg
    from students.models import SchoolClass
    class_bench = list(
        Result.objects.filter(school=school)
        .values('student__school_class__name')
        .annotate(class_avg=DB_Avg('score'), total=Count('id'))
        .filter(student__school_class__isnull=False)
        .order_by('-class_avg')
    )

    context = {
        'school': school,
        'risk_students': risk_students[:20],
        'total_at_risk': len(risk_students),
        'school_avg': round(float(school_avg), 1),
        'class_benchmarks': class_bench[:15],
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

    results = (
        Result.objects.filter(student=student, deleted_at__isnull=True)
        .select_related("term")
        .order_by("term__start_date")
    )

    if not results.exists():
        return JsonResponse({"prediction": "Not enough data", "confidence": 0})

    scores = [r.score for r in results]
    n = len(scores)

    if n < 2:
        return JsonResponse({
            "student": student.user.get_full_name() or student.user.username,
            "current_avg": round(scores[0], 1),
            "predicted_score": round(scores[0], 1),
            "trend": "Stable",
            "confidence": 10,
            "r_squared": None,
            "recommendation": get_recommendation(scores[0]),
        })

    # Ordinary least-squares linear regression (no external deps)
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(scores) / n
    ss_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, scores))
    ss_xx = sum((x - x_mean) ** 2 for x in xs)
    slope = ss_xy / ss_xx if ss_xx else 0
    intercept = y_mean - slope * x_mean
    predicted_score = max(0.0, min(100.0, slope * n + intercept))  # next term

    # R² as confidence measure (0–100 scale)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, scores))
    ss_tot = sum((y - y_mean) ** 2 for y in scores)
    r_squared = 1 - ss_res / ss_tot if ss_tot else 0.0
    confidence = round(max(0.0, min(1.0, r_squared)) * 100, 1)

    trend_dir = "Improving" if slope > 0.5 else "Declining" if slope < -0.5 else "Stable"

    return JsonResponse({
        "student": student.user.get_full_name() or student.user.username,
        "current_avg": round(y_mean, 1),
        "predicted_score": round(predicted_score, 1),
        "trend": trend_dir,
        "confidence": confidence,
        "r_squared": round(r_squared, 3),
        "data_points": n,
        "recommendation": get_recommendation(predicted_score),
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
    if not can_create_academic_content(request.user):
        messages.error(request, 'You do not have permission to access analytics features.')
        return redirect('home')
    
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    # Check if feature is enabled for the school
    if not request.user.is_superuser and not is_feature_enabled(request, 'performance_analytics'):
        messages.error(request, 'Performance Analytics is disabled for your school.')
        return redirect('home')
    
    # Get terms
    terms = Term.objects.filter(school=school).order_by('-start_date')[:6]
    
    # Single batch query: average scores per term using annotate (eliminates N+1)
    from django.db.models import FloatField
    term_ids = list(terms.values_list('id', flat=True))
    term_agg = {
        row['term']: row
        for row in Result.objects.filter(school=school, term_id__in=term_ids)
        .values('term')
        .annotate(
            avg=DB_Avg('score'),
            total=Count('id'),
            pass_count=Count('id', filter=Q(score__gte=50)),
        )
    }
    term_scores = []
    for term in terms:
        agg = term_agg.get(term.pk, {})
        total = agg.get('total', 0) or 0
        avg = float(agg.get('avg') or 0)
        pass_count = agg.get('pass_count', 0) or 0
        term_scores.append({
            'term': term.name,
            'avg_score': round(avg, 1),
            'total_results': total,
            'pass_rate': round(pass_count / total * 100, 1) if total > 0 else 0,
            'start_date': term.start_date,
        })

    # Subject trends — single aggregate query
    subject_trends = list(
        Result.objects.filter(school=school)
        .values('subject__name')
        .annotate(avg_score=DB_Avg('score'), total=Count('id'))
        .filter(subject__isnull=False)
        .order_by('-avg_score')
    )
    subject_trends = [
        {'subject': r['subject__name'], 'avg_score': round(float(r['avg_score'] or 0), 1)}
        for r in subject_trends
    ]
    
    # Monthly trends (last 6 months)
    monthly_data = get_monthly_trends(school)
    
    # Class comparison
    class_comparison = get_class_comparison(school)
    
    context = {
        'school': school,
        'term_scores': term_scores,
        'subject_trends': subject_trends,
        'monthly_data': monthly_data,
        'class_comparison': class_comparison,
    }
    return render(request, 'academics/trend_analysis.html', context)


def get_monthly_trends(school):
    """Get monthly performance trends."""
    now = timezone.now()
    monthly_data = []
    
    for i in range(5, -1, -1):
        month_start = (now - timedelta(days=30 * i)).replace(day=1)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)
        
        results = Result.objects.filter(
            student__school=school,
            created_at__gte=month_start,
            created_at__lt=month_end
        )
        avg = results.aggregate(avg=DB_Avg('score'))['avg'] or 0
        
        monthly_data.append({
            'month': month_start.strftime('%b %Y'),
            'avg_score': round(avg, 1),
            'count': results.count()
        })
    
    return monthly_data


def get_class_comparison(school):
    """Get performance comparison by class."""
    from students.models import SchoolClass
    
    classes = SchoolClass.objects.filter(school=school)
    class_data = []
    
    for cls in classes:
        students = Student.objects.filter(school=school, class_name=cls.name)
        if students.exists():
            avg = Result.objects.filter(student__in=students).aggregate(avg=DB_Avg('score'))['avg'] or 0
            class_data.append({
                'class': cls.name,
                'avg_score': round(avg, 1),
                'student_count': students.count()
            })
    
    return sorted(class_data, key=lambda x: x['avg_score'], reverse=True)


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
    
    # Get chart type from request
    chart_type = request.GET.get('type', 'term')
    
    if chart_type == 'term':
        terms = Term.objects.filter(school=school).order_by('start_date')
        labels = []
        scores = []
        
        for term in terms:
            labels.append(term.name)
            avg = Result.objects.filter(student__school=school, term=term).aggregate(avg=DB_Avg('score'))['avg'] or 0
            scores.append(round(avg, 1))
        
        return JsonResponse({
            'labels': labels,
            'scores': scores,
            'title': 'Performance by Term'
        })
    
    elif chart_type == 'monthly':
        monthly_data = get_monthly_trends(school)
        return JsonResponse({
            'labels': [m['month'] for m in monthly_data],
            'scores': [m['avg_score'] for m in monthly_data],
            'title': 'Monthly Performance'
        })
    
    elif chart_type == 'class':
        class_data = get_class_comparison(school)
        return JsonResponse({
            'labels': [c['class'] for c in class_data],
            'scores': [c['avg_score'] for c in class_data],
            'title': 'Performance by Class'
        })
    
    elif chart_type == 'subject':
        subjects = Subject.objects.filter(school=school)
        labels = [s.name for s in subjects]
        scores = []
        for subject in subjects:
            avg = Result.objects.filter(student__school=school, subject=subject).aggregate(avg=DB_Avg('score'))['avg'] or 0
            scores.append(round(avg, 1))
        
        return JsonResponse({
            'labels': labels,
            'scores': scores,
            'title': 'Performance by Subject'
        })
    
    return JsonResponse({'error': 'Invalid chart type'}, status=400)


# ==================== ONLINE CLASSES ====================


def _online_classes_school(request):
    """School context for online class views (supports superuser current_school_id)."""
    school = getattr(request.user, "school", None)
    if request.user.is_superuser:
        school_id = request.session.get("current_school_id")
        if school_id:
            school = get_object_or_404(School, id=school_id)
    return school


def online_meetings_visible_to_user(user, school):
    """
    OnlineMeeting queryset visible to this user for the given school.
    Keeps list and join URLs consistent (prevents joining by guessing IDs).
    """
    meetings = OnlineMeeting.objects.filter(school=school)
    if user.is_superuser:
        return meetings

    user_role = getattr(user, "role", None)

    if user_role == "teacher":
        return meetings.filter(
            Q(teacher=user)
            | Q(target_audience="staff")
            | Q(target_audience="all")
        )
    if user_role == "student":
        student = Student.objects.filter(user=user, school=school).first()
        if student and student.class_name:
            return meetings.filter(
                Q(target_audience="students")
                | Q(target_audience="all")
                | Q(class_name=student.class_name)
                | Q(class_name="")
            )
        return meetings.filter(
            Q(target_audience="students")
            | Q(target_audience="all")
            | Q(class_name="")
        )
    if user_role == "parent":
        children = Student.objects.filter(parent=user, school=school)
        child_classes = [c.class_name for c in children if c.class_name]
        if child_classes:
            return meetings.filter(
                Q(target_audience="students")
                | Q(target_audience="all")
                | Q(class_name__in=child_classes)
                | Q(class_name="")
            )
        return meetings.filter(
            Q(target_audience="students")
            | Q(target_audience="all")
            | Q(class_name="")
        )
    if user_role in (
        "school_admin",
        "deputy_head",
        "hod",
        "accountant",
        "librarian",
        "school_nurse",
        "admin_assistant",
        "staff",
        "admission_officer",
        "board",
        "school_board",
    ):
        return meetings.filter(
            Q(target_audience="staff") | Q(target_audience="all")
        )
    # Fallback: only 'all' audience
    return meetings.filter(target_audience="all")


@login_required
def online_classes_page(request):
    """Online classes dashboard."""
    school = _online_classes_school(request)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    meetings = online_meetings_visible_to_user(request.user, school)
    
    now = timezone.now()
    live_meetings = meetings.filter(status='in_progress').order_by('scheduled_time')
    upcoming_meetings = meetings.filter(status='scheduled', scheduled_time__gte=now).order_by('scheduled_time')
    past_meetings = meetings.filter(Q(status='completed') | Q(status='cancelled') | (Q(status='scheduled') & Q(scheduled_time__lt=now))).order_by('-scheduled_time')[:10]
    
    # Get classes for dropdown (from students)
    classes = Student.objects.filter(school=school).values_list('class_name', flat=True).distinct()
    classes = [c for c in classes if c]
    
    # Get subjects for dropdown
    subjects = Subject.objects.filter(school=school).order_by('name')
    
    from accounts.permissions import is_school_leadership
    context = {
        'school': school,
        'live_meetings': live_meetings,
        'upcoming_meetings': upcoming_meetings,
        'past_meetings': past_meetings,
        'total_meetings': meetings.count(),
        'classes': classes,
        'subjects': subjects,
        'is_school_leadership': is_school_leadership(request.user),
    }
    return render(request, 'academics/online_classes.html', context)


@login_required
def create_meeting(request):
    """Create an online meeting (Zoom/Meet)."""
    from accounts.permissions import is_school_leadership
    user_role = getattr(request.user, 'role', '')
    if user_role not in ('teacher',) and not is_school_leadership(request.user) and not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

    school = _online_classes_school(request)
    
    if request.method == 'POST':
        if not school:
            return JsonResponse(
                {'success': False, 'error': 'No school associated with your account.'},
                status=400,
            )
        import json
        try:
            data = json.loads(request.body)
            
            # Parse the scheduled_time - it comes as a string from JSON
            scheduled_time_str = data.get('scheduled_time')
            if isinstance(scheduled_time_str, str):
                scheduled_time_str = scheduled_time_str.replace('T', ' ')[:16]
                naive_dt = dt.strptime(scheduled_time_str, '%Y-%m-%d %H:%M')
                scheduled_time = timezone.make_aware(naive_dt)
            else:
                scheduled_time = scheduled_time_str
            
            title = (data.get('title') or '').strip()
            if not title:
                return JsonResponse({'success': False, 'error': 'Title is required.'}, status=400)

            target_audience = data.get('target_audience', 'all')
            if target_audience not in ('students', 'staff', 'all'):
                target_audience = 'all'

            try:
                duration = max(15, int(data.get('duration', 60)))
            except (TypeError, ValueError):
                duration = 60

            # Create meeting in database
            meeting = OnlineMeeting.objects.create(
                school=school,
                teacher=request.user,
                title=title,
                description=data.get('description', ''),
                subject=data.get('subject', ''),
                class_name=data.get('class_name', ''),
                target_audience=target_audience,
                scheduled_time=scheduled_time,
                duration=duration,
                status='scheduled'
            )
            
            # Generate meeting link (placeholder - integrate with Zoom/Meet API)
            meeting_id = str(uuid.uuid4())[:8].upper()
            meeting.meeting_id = meeting_id
            # Jitsi Meet - free, no API needed
            meeting.meeting_link = f"https://meet.jit.si/mastex-{school.id}-{meeting_id}"
            meeting.host_url = f"https://meet.jit.si/mastex-{school.id}-{meeting_id}#config.startWithVideoMuted=false&config.prejoinPageEnabled=false"
            meeting.save()
            
            # Create in-app notifications for students/parents in the class
            try:
                create_meeting_notifications(meeting)
            except Exception:
                logger.warning("Failed to create meeting notifications", exc_info=True)
            
            # Send SMS notifications if requested
            send_sms_notification = data.get('send_sms', False)
            if send_sms_notification:
                try:
                    sms_result = send_online_class_sms(meeting, request.user)
                    # Include SMS status in response
                    sms_status = sms_result.get('sent_count', 0)
                except Exception:
                    # Log but don't fail the meeting creation
                    logger.warning("SMS notification failed for online class", exc_info=True)
                    sms_status = 0
            
            return JsonResponse({
                'success': True,
                'meeting': {
                    'id': meeting.id,
                    'title': meeting.title,
                    'meeting_id': meeting.meeting_id,
                    'meeting_link': meeting.meeting_link,
                    'scheduled_time': meeting.scheduled_time.strftime('%Y-%m-%d %H:%M'),
                    'duration': meeting.duration
                },
                'message': 'Meeting created successfully!'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    # GET request - redirect to the main page (creation is modal/AJAX only)
    return redirect('academics:online_classes')


@login_required
def join_meeting(request, meeting_id):
    """Join an online meeting."""
    school = _online_classes_school(request)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    # Get meeting
    meeting = get_object_or_404(OnlineMeeting, id=meeting_id, school=school)

    visible = online_meetings_visible_to_user(request.user, school)
    if not visible.filter(pk=meeting.pk).exists():
        messages.error(request, "You don't have access to this class session.")
        return redirect('academics:online_classes')
    
    # Update status if starting
    if meeting.status == 'scheduled' and meeting.scheduled_time <= timezone.now():
        meeting.status = 'in_progress'
        meeting.save()
    
    from accounts.permissions import is_school_leadership
    is_host = meeting.teacher == request.user
    context = {
        'school': school,
        'meeting': meeting,
        'join_url': meeting.meeting_link,
        'is_host': is_host,
        'can_end_meeting': is_host or request.user.is_superuser or is_school_leadership(request.user),
        'now': timezone.now(),
    }
    return render(request, 'academics/join_meeting.html', context)


@login_required
def end_meeting(request, meeting_id):
    """End an online meeting."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)
    
    school = _online_classes_school(request)
    if not school:
        return JsonResponse({'error': 'No school associated with your account.'}, status=400)
    meeting = get_object_or_404(OnlineMeeting, id=meeting_id, school=school)
    
    from accounts.permissions import is_school_leadership
    if meeting.teacher != request.user and not request.user.is_superuser and not is_school_leadership(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    meeting.status = 'completed'
    meeting.save()
    
    return JsonResponse({'success': True, 'message': 'Meeting ended'})


@login_required
def delete_meeting(request, meeting_id):
    """Delete a meeting."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)
    
    school = _online_classes_school(request)
    if not school:
        return JsonResponse({'error': 'No school associated with your account.'}, status=400)
    meeting = get_object_or_404(OnlineMeeting, id=meeting_id, school=school)
    
    from accounts.permissions import is_school_leadership
    if meeting.teacher != request.user and not request.user.is_superuser and not is_school_leadership(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    meeting.delete()
    
    return JsonResponse({'success': True, 'message': 'Meeting deleted'})


@login_required
def edit_meeting(request, meeting_id):
    """Edit an existing online meeting (host or school leadership only)."""
    import json
    school = _online_classes_school(request)
    if not school:
        return JsonResponse({'error': 'No school associated with your account.'}, status=400)
    meeting = get_object_or_404(OnlineMeeting, id=meeting_id, school=school)
    from accounts.permissions import is_school_leadership
    if meeting.teacher != request.user and not request.user.is_superuser and not is_school_leadership(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)
    try:
        data = json.loads(request.body)
        if 'title' in data and data['title'].strip():
            meeting.title = data['title'].strip()
        if 'description' in data:
            meeting.description = data.get('description', '')
        if 'subject' in data:
            meeting.subject = data.get('subject', '')
        if 'class_name' in data:
            meeting.class_name = data.get('class_name', '')
        if 'target_audience' in data and data['target_audience'] in ('students', 'staff', 'all'):
            meeting.target_audience = data['target_audience']
        if 'duration' in data:
            meeting.duration = max(15, int(data.get('duration', 60)))
        if 'recording_url' in data:
            meeting.recording_url = data.get('recording_url', '')
        if 'scheduled_time' in data:
            st_str = data['scheduled_time'].replace('T', ' ')[:16]
            naive_dt = dt.strptime(st_str, '%Y-%m-%d %H:%M')
            meeting.scheduled_time = timezone.make_aware(naive_dt)
        meeting.save()
        return JsonResponse({'success': True, 'message': 'Meeting updated.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==================== AI STUDENT COMMENTS ====================

@login_required
def ai_comment_page(request):
    """AI-generated student comments page."""
    if not can_create_academic_content(request.user):
        messages.error(request, 'You do not have permission to access analytics features.')
        return redirect('home')
    
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    # Check if feature is enabled for the school
    if not request.user.is_superuser and not is_feature_enabled(request, 'performance_analytics'):
        messages.error(request, 'Performance Analytics is disabled for your school.')
        return redirect('home')
    
    # Get students
    students = Student.objects.filter(school=school).select_related('user').order_by('user__last_name')
    
    # Get terms
    terms = Term.objects.filter(school=school).order_by('-start_date')
    
    # Get recent comments
    recent_comments = AIStudentComment.objects.filter(school=school).select_related('student', 'student__user')[:20]
    
    context = {
        'school': school,
        'students': students,
        'terms': terms,
        'recent_comments': recent_comments,
    }
    return render(request, 'academics/ai_comment.html', context)


@login_required
def generate_ai_comment(request):
    """Generate AI comment for a student."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)
    
    import json
    
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'error': 'No school found'}, status=400)
    
    try:
        data = json.loads(request.body)
        student_id = data.get('student_id')
        term = data.get('term', '')
        academic_year = data.get('academic_year', '2025/2026')
        comment_type = data.get('comment_type', 'overall')
        tone = data.get('tone', 'professional')
        
        student = get_object_or_404(Student, id=student_id, school=school)
        
        # Get student data for comment generation
        results = Result.objects.filter(student=student).order_by('-created_at')
        avg_score = results.aggregate(avg=DB_Avg('score'))['avg'] or 0
        
        # Get attendance
        attendance_records = StudentAttendance.objects.filter(student=student)
        total_days = attendance_records.count()
        present_days = attendance_records.filter(status='present').count()
        attendance_rate = round((present_days / total_days * 100), 1) if total_days > 0 else 100
        
        # Generate comment
        comment = generate_student_comment(student, avg_score, attendance_rate, comment_type, tone)
        
        # Save to database
        ai_comment = AIStudentComment.objects.create(
            student=student,
            school=school,
            term=term,
            academic_year=academic_year,
            comment_type=comment_type,
            tone=tone,
            content=comment,
            created_by=request.user
        )
        
        return JsonResponse({
            'success': True,
            'comment': {
                'id': ai_comment.id,
                'content': comment,
                'student': f"{student.user.get_full_name()}",
                'term': term,
                'avg_score': round(avg_score, 1),
                'attendance_rate': attendance_rate
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def generate_student_comment(student, avg_score, attendance_rate, comment_type, tone):
    """Generate AI-powered student comment."""
    student_name = student.user.get_full_name() or student.user.username
    
    # Determine performance level
    if avg_score >= 80:
        performance = "excellent"
        performance_text = "demonstrated outstanding performance"
    elif avg_score >= 70:
        performance = "good"
        performance_text = "shown good progress"
    elif avg_score >= 60:
        performance = "satisfactory"
        performance_text = "shown satisfactory performance"
    elif avg_score >= 50:
        performance = "needs improvement"
        performance_text = "needs to improve in some areas"
    else:
        performance = "poor"
        performance_text = "requires significant improvement"
    
    # Build comment based on tone
    if tone == 'encouraging':
        if avg_score >= 70:
            base = f"{student_name} has {performance_text} this term. Keep up the excellent work!"
        else:
            base = f"{student_name} has shown potential this term. With more dedication, greater achievements are within reach."
    elif tone == 'detailed':
        base = f"{student_name} achieved an average score of {avg_score:.1f}% with an attendance rate of {attendance_rate:.1f}%. "
        base += f"The student has {performance_text} this term."
        if avg_score < 60:
            base += f" Additional support and focused study are recommended."
        elif avg_score >= 80:
            base += f" The student is encouraged to maintain this standard."
    elif tone == 'concise':
        base = f"{student_name}: {avg_score:.1f}% average, {attendance_rate:.1f}% attendance. {performance.title()} performance."
    else:  # professional
        base = f"{student_name} has {performance_text} during this academic period. "
        if avg_score >= 70:
            base += "The student is a valuable member of the class."
        elif avg_score < 50:
            base += "A meeting with parents/guardians is recommended to discuss support strategies."
        else:
            base += "Continued effort will lead to improved results."
    
    # Add subject-specific comments
    if comment_type == 'academic':
        base += f" Overall academic performance stands at {avg_score:.1f}%."
    
    return base


@login_required
def save_comment(request):
    """Save a manually edited AI comment."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)
    
    import json
    
    try:
        data = json.loads(request.body)
        comment_id = data.get('comment_id')
        content = data.get('content')

        user = request.user
        school = getattr(user, 'school', None)
        filters = {"id": comment_id}
        if not user.is_superuser:
            if not school:
                return JsonResponse({'error': 'Unauthorized'}, status=403)
            filters["student__school"] = school

        comment = get_object_or_404(AIStudentComment, **filters)
        comment.content = content
        comment.save(update_fields=["content"])
        
        return JsonResponse({'success': True})
    except AIStudentComment.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Comment not found'}, status=404)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("save_comment error")
        return JsonResponse({'success': False, 'error': 'Server error'}, status=500)


# ==================== SMS NOTIFICATIONS FOR ONLINE CLASSES ====================

def create_meeting_notifications(meeting):
    """
    Create in-app notifications for students and parents when a new online class is scheduled.
    """
    if Notification is None:
        return
    
    notifications_created = 0
    
    # Get students in the class
    if meeting.class_name:
        students = Student.objects.filter(
            school=meeting.school,
            class_name=meeting.class_name
        ).select_related('user')
    else:
        students = Student.objects.filter(
            school=meeting.school
        ).select_related('user')
    
    # Create notification for each student
    for student in students:
        try:
            Notification.objects.create(
                user=student.user,
                title="New Online Class Scheduled",
                message=f"A new online class '{meeting.title}' has been scheduled for {meeting.class_name or 'all classes'} on {meeting.scheduled_time.strftime('%d %b at %H:%M')}. Subject: {meeting.subject or 'General'}",
                notification_type="info",
                link=f"/academics/online-classes/"
            )
            notifications_created += 1
            
            # Also notify parent if exists
            try:
                from students.models import StudentParent
                parent_links = StudentParent.objects.filter(student=student)
                for link in parent_links:
                    if link.parent:
                        Notification.objects.create(
                            user=link.parent,
                            title=f"Online Class for {student.user.get_full_name()}",
                            message=f"A new online class '{meeting.title}' has been scheduled for {student.user.get_full_name()} (Class: {meeting.class_name or 'all'}) on {meeting.scheduled_time.strftime('%d %b at %H:%M')}. Subject: {meeting.subject or 'General'}",
                            notification_type="info",
                            link=f"/academics/online-classes/"
                        )
                        notifications_created += 1
            except Exception:
                pass  # Parent notification is optional
        except Exception:
            logger.warning(
                "Failed to create online class notification for student",
                extra={"student_id": student.id},
                exc_info=True,
            )
    
    return notifications_created


def send_online_class_sms(meeting, user):
    """
    Send SMS notifications about an online class.
    - If user is School Admin/Deputy Head: notify ALL STAFF (teachers, HODs, accountants, librarians, etc.)
    - If user is Teacher: notify students and parents
    
    Returns a dict with 'sent_count' and 'failed_count'.
    """
    from accounts.models import User
    
    # Determine notification type based on user role
    user_role = user.role if hasattr(user, 'role') else 'teacher'
    is_staff_meeting = user_role in ['school_admin', 'deputy_head', 'hod']
    
    # Collect phone numbers based on role
    phone_numbers = set()
    
    if is_staff_meeting:
        # Get all staff members in the school (teacher, accountant, librarian, hod, etc.)
        staff_roles = ['teacher', 'accountant', 'librarian', 'hod', 'deputy_head', 
                       'admission_officer', 'school_nurse', 'admin_assistant', 'staff']
        
        staff_users = User.objects.filter(
            school=meeting.school,
            role__in=staff_roles,
            phone__isnull=False
        ).exclude(phone='')
        
        for staff_user in staff_users:
            if staff_user.phone:
                phone_numbers.add(staff_user.phone)
        
        # Message for staff meeting
        scheduled_date = meeting.scheduled_time.strftime('%d/%m/%Y')
        scheduled_time = meeting.scheduled_time.strftime('%H:%M')
        
        message = f"📹 STAFF MEETING\n\n"
        message += f"Title: {meeting.title}\n"
        if meeting.description:
            message += f"Details: {meeting.description[:50]}...\n" if len(meeting.description) > 50 else f"Details: {meeting.description}\n"
        message += f"Date: {scheduled_date}\n"
        message += f"Time: {scheduled_time}\n"
        message += f"Duration: {meeting.duration} min\n"
        message += f"\nJoin: {meeting.meeting_link}\n"
        message += f"- Mastex SchoolOS"
    else:
        # Get students in the class (if class_name is specified)
        if meeting.class_name:
            students = Student.objects.filter(
                school=meeting.school,
                class_name=meeting.class_name
            ).select_related('user')
        else:
            # If no class specified, notify all students in school
            students = Student.objects.filter(
                school=meeting.school
            ).select_related('user')
        
        for student in students:
            # Add student's phone if available
            if student.user.phone:
                phone_numbers.add(student.user.phone)
            
            # Get parent's phone
            try:
                from students.models import StudentParent
                parent_links = StudentParent.objects.filter(student=student)
                for link in parent_links:
                    if link.parent and link.parent.phone:
                        phone_numbers.add(link.parent.phone)
            except Exception:
                pass
        
        # Message for online class (students/parents)
        scheduled_date = meeting.scheduled_time.strftime('%d/%m/%Y')
        scheduled_time = meeting.scheduled_time.strftime('%H:%M')
        
        message = f"📹 ONLINE CLASS\n\n"
        message += f"Title: {meeting.title}\n"
        if meeting.subject:
            message += f"Subject: {meeting.subject}\n"
        message += f"Date: {scheduled_date}\n"
        message += f"Time: {scheduled_time}\n"
        message += f"Duration: {meeting.duration} min\n"
        message += f"\nJoin: {meeting.meeting_link}\n"
        message += f"- Mastex SchoolOS"
    

# ====================================================================================
# DS-3 — Cohort Analysis: track performance by admission year across terms
# ====================================================================================

@login_required
@analytics_role_required
def cohort_analysis(request):
    """Track how each admission-year cohort performs across successive academic terms.

    Returns a JSON payload (or HTML if ?format=html):
    {
      "cohorts": [
        {"year": 2022, "terms": [{"term": "Term 1 2022", "avg_score": 72.3, "count": 45}, ...]},
        ...
      ]
    }
    """
    school = getattr(request.user, "school", None)
    if request.user.is_superuser:
        school_id = request.session.get("current_school_id")
        if school_id:
            school = get_object_or_404(School, id=school_id)

    if not school:
        return JsonResponse({"error": "No school found"}, status=400)

    # Group students by admission year (from their created_at date)
    from django.db.models.functions import ExtractYear
    from django.db.models import F

    term_avgs = (
        Result.objects.filter(school=school, deleted_at__isnull=True, term__isnull=False)
        .annotate(
            admission_year=ExtractYear("student__user__date_joined"),
            term_label=F("term__name"),
            term_start=F("term__start_date"),
        )
        .values("admission_year", "term_label", "term_start")
        .annotate(avg_score=DB_Avg("score"), student_count=Count("student", distinct=True))
        .order_by("admission_year", "term_start")
    )

    cohorts: dict = {}
    for row in term_avgs:
        yr = row["admission_year"]
        if yr not in cohorts:
            cohorts[yr] = {"year": yr, "terms": []}
        cohorts[yr]["terms"].append({
            "term": row["term_label"],
            "avg_score": round(float(row["avg_score"] or 0), 1),
            "count": row["student_count"],
        })

    sorted_cohorts = sorted(cohorts.values(), key=lambda c: c["year"], reverse=True)

    if request.GET.get("format") == "html":
        return render(request, "academics/cohort_analysis.html", {
            "cohorts": sorted_cohorts,
            "school": school,
        })

    return JsonResponse({"cohorts": sorted_cohorts})


# ====================================================================================
# DS-4 — Subject Performance Heatmap: avg score per subject × term grid
# ====================================================================================

@login_required
@analytics_role_required
def subject_performance_heatmap(request):
    """Return subject × term average score matrix for heatmap visualisation.

    Response (JSON or HTML with ?format=html):
    {
      "subjects": ["Mathematics", "English", ...],
      "terms": ["Term 1 2024", "Term 2 2024", ...],
      "matrix": {
        "Mathematics": {"Term 1 2024": 72.3, "Term 2 2024": 68.1},
        ...
      },
      "school_avg": 70.5
    }
    """
    from django.db.models import F

    school = getattr(request.user, "school", None)
    if request.user.is_superuser:
        school_id = request.session.get("current_school_id")
        if school_id:
            school = get_object_or_404(School, id=school_id)

    if not school:
        return JsonResponse({"error": "No school found"}, status=400)

    # Single batch query: avg score per (subject, term)
    rows = (
        Result.objects.filter(school=school, deleted_at__isnull=True, term__isnull=False)
        .values(
            subject_name=F("subject__name"),
            term_label=F("term__name"),
            term_start=F("term__start_date"),
        )
        .annotate(avg_score=DB_Avg("score"))
        .order_by("term_start", "subject_name")
    )

    subjects_set: list = []
    terms_set: list = []
    matrix: dict = {}

    for row in rows:
        subj = row["subject_name"] or "Unknown"
        term = row["term_label"] or "Unknown"
        avg = round(float(row["avg_score"] or 0), 1)

        if subj not in subjects_set:
            subjects_set.append(subj)
        if term not in terms_set:
            terms_set.append(term)

        if subj not in matrix:
            matrix[subj] = {}
        matrix[subj][term] = avg

    school_avg = Result.objects.filter(school=school, deleted_at__isnull=True).aggregate(
        avg=DB_Avg("score")
    )["avg"] or 0

    payload = {
        "subjects": subjects_set,
        "terms": terms_set,
        "matrix": matrix,
        "school_avg": round(float(school_avg), 1),
    }

    if request.GET.get("format") == "html":
        return render(request, "academics/subject_heatmap.html", {**payload, "school": school})

    return JsonResponse(payload)


# ====================================================================================
# DS-1 — Attendance-to-Performance Correlation
# ====================================================================================

@login_required
@analytics_role_required
def attendance_performance_correlation(request):
    """Correlate attendance rate with average academic score per student per term.

    Returns: list of {student, attendance_rate, avg_score} sorted by attendance_rate.
    Pearson r and slope (no external deps) included for dashboard display.
    """
    school = getattr(request.user, "school", None)
    if request.user.is_superuser:
        school_id = request.session.get("current_school_id")
        if school_id:
            school = get_object_or_404(School, id=school_id)
    if not school:
        return JsonResponse({"error": "No school found"}, status=400)

    term_id = request.GET.get("term_id")
    term_qs = Term.objects.filter(school=school)
    if term_id:
        term_qs = term_qs.filter(pk=term_id)
    else:
        term_qs = term_qs.filter(is_current=True)
    term = term_qs.first()
    if not term:
        return JsonResponse({"error": "No term found"}, status=404)

    att_rows = (
        StudentAttendance.objects.filter(school=school, date__gte=term.start_date, date__lte=term.end_date)
        .values("student_id")
        .annotate(
            total=Count("id"),
            present=Count("id", filter=Q(status="present")),
        )
    )
    att_map = {r["student_id"]: round(r["present"] / r["total"] * 100, 1) if r["total"] else 0 for r in att_rows}

    result_rows = (
        Result.objects.filter(school=school, term=term, deleted_at__isnull=True)
        .values("student_id")
        .annotate(avg=DB_Avg("score"))
    )
    result_map = {r["student_id"]: round(float(r["avg"] or 0), 1) for r in result_rows}

    common_ids = set(att_map) & set(result_map)
    if len(common_ids) < 2:
        return JsonResponse({"error": "Insufficient overlapping data", "points": []})

    points = [
        {"student_id": sid, "attendance_rate": att_map[sid], "avg_score": result_map[sid]}
        for sid in common_ids
    ]
    points.sort(key=lambda p: p["attendance_rate"])

    xs = [p["attendance_rate"] for p in points]
    ys = [p["avg_score"] for p in points]
    n = len(xs)
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    ss_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    ss_xx = sum((x - x_mean) ** 2 for x in xs)
    ss_yy = sum((y - y_mean) ** 2 for y in ys)
    slope = ss_xy / ss_xx if ss_xx else 0
    pearson_r = ss_xy / ((ss_xx * ss_yy) ** 0.5) if ss_xx and ss_yy else 0

    return JsonResponse({
        "term": term.name,
        "points": points,
        "pearson_r": round(pearson_r, 3),
        "slope": round(slope, 3),
        "data_points": n,
    })


# ====================================================================================
# DS-2 — Z-Score Outlier Detection on Class Results
# ====================================================================================

@login_required
@analytics_role_required
def class_result_outliers(request):
    """Flag students whose score deviates >2σ from the class mean for a given term/subject.

    Query params: term_id (optional), subject_id (optional), threshold (default 2.0).
    Returns: {mean, std_dev, threshold, outliers: [{student_id, name, score, z_score}]}.
    """
    school = getattr(request.user, "school", None)
    if request.user.is_superuser:
        school_id = request.session.get("current_school_id")
        if school_id:
            school = get_object_or_404(School, id=school_id)
    if not school:
        return JsonResponse({"error": "No school found"}, status=400)

    term_id = request.GET.get("term_id")
    subject_id = request.GET.get("subject_id")
    threshold = float(request.GET.get("threshold", 2.0))

    qs = Result.objects.filter(school=school, deleted_at__isnull=True).select_related("student__user", "subject")
    if term_id:
        qs = qs.filter(term_id=term_id)
    else:
        current_term = Term.objects.filter(school=school, is_current=True).first()
        if current_term:
            qs = qs.filter(term=current_term)
    if subject_id:
        qs = qs.filter(subject_id=subject_id)

    records = list(qs.values("student_id", "score", "student__user__first_name", "student__user__last_name"))
    if len(records) < 3:
        return JsonResponse({"error": "Not enough data for outlier detection", "outliers": []})

    scores = [float(r["score"]) for r in records]
    n = len(scores)
    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / n
    std_dev = variance ** 0.5 if variance > 0 else 0

    outliers = []
    if std_dev > 0:
        for r in records:
            z = (float(r["score"]) - mean) / std_dev
            if abs(z) >= threshold:
                name = f"{r['student__user__first_name']} {r['student__user__last_name']}".strip()
                outliers.append({
                    "student_id": r["student_id"],
                    "name": name or f"Student #{r['student_id']}",
                    "score": float(r["score"]),
                    "z_score": round(z, 2),
                    "direction": "above" if z > 0 else "below",
                })
    outliers.sort(key=lambda o: abs(o["z_score"]), reverse=True)

    return JsonResponse({
        "mean": round(mean, 2),
        "std_dev": round(std_dev, 2),
        "threshold": threshold,
        "total_students": n,
        "outlier_count": len(outliers),
        "outliers": outliers,
    })
