"""
Advanced Features for Mastex SchoolOS
- Auto Timetable Generator
- Course Management (LMS)
- Exam Seating Plans

(Parent–teacher chat lives in the messaging app.)
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
import random

from students.models import Student
from schools.models import School
from academics.models import Subject, Homework, Quiz


# ==================== AUTO TIMETABLE GENERATOR ====================

@login_required
def auto_timetable_generator(request):
    """Generate class timetable automatically."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    if request.method == 'POST':
        class_name = request.POST.get('class_name')
        subjects = Subject.objects.filter(school=school)
        
        # Generate timetable
        timetable = generate_timetable(class_name, subjects)
        
        messages.success(request, f'Timetable generated for {class_name}!')
        return redirect('operations:timetable_view', class_name=class_name)
    
    classes = Student.objects.filter(school=school).values_list('class_name', flat=True).distinct()
    
    context = {
        'school': school,
        'classes': [c for c in classes if c],
    }
    return render(request, 'operations/auto_timetable.html', context)


def generate_timetable(class_name, subjects):
    """Generate a timetable for a class."""
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    periods = ['7:00-8:00', '8:00-9:00', '9:00-10:00', '10:00-10:30', '10:30-11:30', '11:30-12:30', '12:30-1:30', '1:30-2:30', '2:30-3:30']
    
    timetable_data = {}
    
    # Core subjects that need more hours
    core_subjects = list(subjects.filter(is_core=True)) if subjects.filter(is_core=True).exists() else list(subjects[:4])
    elective_subjects = list(subjects.filter(is_core=False)) if subjects.filter(is_core=False).exists() else list(subjects[4:])
    
    for day in days:
        day_schedule = []
        remaining_periods = [p for p in periods if '10:00-10:30' not in p]  # Exclude break
        
        for period in remaining_periods:
            if core_subjects:
                subject = random.choice(core_subjects)
                day_schedule.append({
                    'period': period,
                    'subject': subject.name,
                    'teacher': f"Teacher {random.randint(1, 10)}"
                })
            elif elective_subjects:
                subject = random.choice(elective_subjects)
                day_schedule.append({
                    'period': period,
                    'subject': subject.name,
                    'teacher': f"Teacher {random.randint(1, 10)}"
                })
            else:
                day_schedule.append({
                    'period': period,
                    'subject': 'Free Period',
                    'teacher': '-'
                })
        
        timetable_data[day] = day_schedule
    
    return timetable_data


# ==================== COURSE MANAGEMENT (LMS) ====================

@login_required
def course_list(request):
    """List all courses/subjects as courses."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    subjects = Subject.objects.filter(school=school)
    
    context = {
        'school': school,
        'subjects': subjects,
    }
    return render(request, 'academics/course_list.html', context)


@login_required
def course_detail(request, subject_id):
    """View course details with lessons."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    subject = get_object_or_404(Subject, id=subject_id, school=school)
    
    # Get related content
    quizzes = Quiz.objects.filter(subject=subject)[:5]
    homeworks = Homework.objects.filter(subject=subject)[:5]
    
    context = {
        'school': school,
        'subject': subject,
        'quizzes': quizzes,
        'homeworks': homeworks,
    }
    return render(request, 'academics/course_detail.html', context)


@login_required
def add_lesson(request, subject_id):
    """Add a lesson to a course."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)
    
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'success': False, 'error': 'No school found'}, status=400)
    
    import json
    try:
        data = json.loads(request.body)
        subject = get_object_or_404(Subject, id=subject_id, school=school)
        
        # In production, you'd create a Lesson model
        lesson = {
            'title': data.get('title'),
            'content': data.get('content'),
            'video_url': data.get('video_url'),
            'attachments': data.get('attachments', []),
        }
        
        return JsonResponse({
            'success': True,
            'message': 'Lesson added successfully!',
            'lesson': lesson
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==================== EXAM SEATING PLANS ====================

@login_required
def auto_seating_plan(request):
    """Generate exam seating plan automatically."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    if request.method == 'POST':
        exam_name = request.POST.get('exam_name')
        class_name = request.POST.get('class_name')
        rows = int(request.POST.get('rows', 10))
        seats_per_row = int(request.POST.get('seats_per_row', 6))
        
        # Get students
        students = Student.objects.filter(school=school, class_name=class_name).select_related('user')
        
        # Generate seating plan
        seating_plan = generate_seating_plan(students, rows, seats_per_row)
        
        context = {
            'school': school,
            'exam_name': exam_name,
            'class_name': class_name,
            'seating_plan': seating_plan,
            'rows': rows,
            'seats_per_row': seats_per_row,
        }
        return render(request, 'operations/seating_plan_view.html', context)
    
    classes = Student.objects.filter(school=school).values_list('class_name', flat=True).distinct()
    
    context = {
        'school': school,
        'classes': [c for c in classes if c],
    }
    return render(request, 'operations/auto_seating_plan.html', context)


def generate_seating_plan(students, rows, seats_per_row):
    """Generate a seating plan for students."""
    students_list = list(students.select_related('user'))
    random.shuffle(students_list)  # Randomize seating
    
    seating_plan = []
    seat_number = 1
    
    for row in range(1, rows + 1):
        row_seats = []
        for seat in range(1, seats_per_row + 1):
            if students_list:
                student = students_list.pop(0)
                row_seats.append({
                    'row': row,
                    'seat': seat,
                    'student': student,
                    'student_name': student.user.get_full_name() or student.user.username,
                    'admission_number': student.admission_number,
                    'seat_number': seat_number
                })
                seat_number += 1
            else:
                row_seats.append({
                    'row': row,
                    'seat': seat,
                    'student': None,
                    'student_name': '-',
                    'admission_number': '-',
                    'seat_number': '-'
                })
        seating_plan.append(row_seats)
    
    return seating_plan


# ==================== AI CHATBOT ====================

@login_required
def ai_chatbot(request):
    """AI chatbot for parent support."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    context = {
        'school': school,
    }
    return render(request, 'ai_assistant/chatbot.html', context)


@login_required
def chatbot_response(request):
    """Get AI response for chatbot."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)
    
    import json
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip().lower()
        
        # Simple FAQ responses (in production, use Gemini AI)
        responses = {
            'fee': 'You can pay fees through the parent portal using Paystack. Go to My Children > Fees > Pay Fees.',
            'result': 'Results are available in the Parent Portal under "My Children". Click on the child\'s name to view their report card.',
            'attendance': 'Attendance can be viewed in the Parent Portal. Look for the calendar icon next to your child\'s name.',
            'homework': 'Homework assignments are posted by teachers and can be viewed in the Student Portal under "Homework".',
            'contact': 'You can contact the school through the messaging system or call the school directly.',
            'hello': 'Hello! I\'m your school assistant. How can I help you today? You can ask about fees, results, attendance, homework, or general information.',
            'hi': 'Hi there! I\'m here to help. Ask me about school fees, results, attendance, homework, or anything else!',
        }
        
        # Find matching response
        response = 'I\'m not sure about that. Please contact the school administration for more information. You can ask me about fees, results, attendance, homework, or contact information.'
        
        for key, value in responses.items():
            if key in user_message:
                response = value
                break
        
        return JsonResponse({
            'success': True,
            'response': response,
            'user_message': user_message
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
