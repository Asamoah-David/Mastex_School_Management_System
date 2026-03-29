"""
QR Code Scanner Views for Attendance
Teachers can scan student and staff ID cards to mark attendance
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth.decorators import login_required

from students.models import Student
from operations.models import StudentAttendance, TeacherAttendance
from accounts.models import User
from schools.models import School
from core.qr_utils import validate_qr_data, validate_staff_qr_data, generate_student_qr_base64, generate_staff_qr_base64


@login_required
def qr_attendance_scanner(request):
    """QR Code scanner page for marking attendance."""
    # Get user's school
    school = getattr(request.user, 'school', None)
    
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    # Get classes for the dropdown
    classes = Student.objects.filter(school=school).values_list('class_name', flat=True).distinct()
    
    context = {
        'school': school,
        'classes': [c for c in classes if c],
    }
    return render(request, 'operations/qr_attendance_scanner.html', context)


@login_required
def qr_attendance_class(request, class_name):
    """Get students for a specific class for QR attendance."""
    school = getattr(request.user, 'school', None)
    
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'error': 'No school found'}, status=400)
    
    students = Student.objects.filter(
        school=school, 
        class_name=class_name
    ).select_related('user').order_by('admission_number')
    
    students_data = []
    for student in students:
        students_data.append({
            'id': student.id,
            'name': student.user.get_full_name() or student.user.username,
            'admission_number': student.admission_number,
            'class_name': student.class_name,
        })
    
    return JsonResponse({'students': students_data})


@csrf_exempt
@require_http_methods(["POST"])
def qr_mark_attendance(request):
    """
    Mark attendance via QR code scan.
    Supports both student and staff QR codes.
    Called via AJAX from the scanner page.
    """
    import json
    from django.utils.dateparse import parse_date
    
    try:
        data = json.loads(request.body)
        qr_data = data.get('qr_data', '')
        attendance_status = data.get('status', 'present')
        attendance_date = data.get('date', timezone.now().date().isoformat())
        attendance_type = data.get('type', 'student')  # 'student' or 'staff'
        
        school = getattr(request.user, 'school', None)
        if request.user.is_superuser:
            school_id = request.session.get('current_school_id')
            if school_id:
                school = get_object_or_404(School, id=school_id)
        
        if not school:
            return JsonResponse({'success': False, 'error': 'No school found'}, status=400)
        
        attendance_date_obj = parse_date(attendance_date)
        
        # Check if it's a staff QR code first
        if qr_data.startswith('MASEXTICKET:STAFF:'):
            # Handle staff attendance
            parsed = validate_staff_qr_data(qr_data)
            if not parsed['valid']:
                return JsonResponse({
                    'success': False, 
                    'error': f"Invalid staff QR code: {parsed.get('error', 'Unknown error')}"
                }, status=400)
            
            # Find staff member
            try:
                staff = User.objects.get(
                    id=parsed['staff_id'],
                    school=school
                )
            except User.DoesNotExist:
                return JsonResponse({
                    'success': False, 
                    'error': 'Staff member not found in this school'
                }, status=404)
            
            # Check if already marked
            existing = TeacherAttendance.objects.filter(
                teacher=staff,
                date=attendance_date_obj
            ).first()
            
            if existing:
                existing.status = attendance_status
                existing.marked_by = request.user
                existing.save()
                action = 'updated'
            else:
                TeacherAttendance.objects.create(
                    teacher=staff,
                    date=attendance_date_obj,
                    status=attendance_status,
                    marked_by=request.user,
                    school=school
                )
                action = 'created'
            
            return JsonResponse({
                'success': True,
                'action': action,
                'type': 'staff',
                'staff': {
                    'name': staff.get_full_name() or staff.username,
                    'username': staff.username,
                    'role': staff.get_role_display() or staff.role,
                },
                'status': attendance_status,
                'message': f"Staff attendance marked as {attendance_status}!"
            })
        
        else:
            # Handle student attendance (original logic)
            parsed = validate_qr_data(qr_data)
            if not parsed['valid']:
                return JsonResponse({
                    'success': False, 
                    'error': f"Invalid QR code: {parsed.get('error', 'Unknown error')}"
                }, status=400)
            
            # Find student
            try:
                student = Student.objects.select_related('user', 'school').get(
                    id=parsed['student_id'],
                    school=school
                )
            except Student.DoesNotExist:
                return JsonResponse({
                    'success': False, 
                    'error': 'Student not found in this school'
                }, status=404)
            
            # Check if already marked
            existing = StudentAttendance.objects.filter(
                student=student,
                date=attendance_date_obj
            ).first()
            
            if existing:
                existing.status = attendance_status
                existing.marked_by = request.user
                existing.save()
                action = 'updated'
            else:
                StudentAttendance.objects.create(
                    student=student,
                    date=attendance_date_obj,
                    status=attendance_status,
                    marked_by=request.user
                )
                action = 'created'
            
            return JsonResponse({
                'success': True,
                'action': action,
                'type': 'student',
                'student': {
                    'name': student.user.get_full_name() or student.user.username,
                    'admission_number': student.admission_number,
                    'class_name': student.class_name,
                },
                'status': attendance_status,
                'message': f"Attendance marked as {attendance_status}!"
            })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def student_qr_preview(request, student_id):
    """
    Generate QR code preview for a student.
    Useful for testing or showing students their QR codes.
    """
    school = getattr(request.user, 'school', None)
    
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'error': 'No school found'}, status=400)
    
    try:
        student = Student.objects.get(id=student_id, school=school)
    except Student.DoesNotExist:
        return JsonResponse({'error': 'Student not found'}, status=404)
    
    qr_base64 = generate_student_qr_base64(student)
    
    return JsonResponse({
        'student': {
            'id': student.id,
            'name': student.user.get_full_name() or student.user.username,
            'admission_number': student.admission_number,
            'class_name': student.class_name,
        },
        'qr_code': f"data:image/png;base64,{qr_base64}"
    })


@login_required
def bulk_qr_codes(request, class_name):
    """Generate QR codes for all students in a class."""
    school = getattr(request.user, 'school', None)
    
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school found.')
        return redirect('home')
    
    students = Student.objects.filter(
        school=school,
        class_name=class_name
    ).select_related('user').order_by('admission_number')
    
    qr_codes = []
    for student in students:
        qr_base64 = generate_student_qr_base64(student)
        qr_codes.append({
            'student_id': student.id,
            'name': student.user.get_full_name() or student.user.username,
            'admission_number': student.admission_number,
            'qr_code': f"data:image/png;base64,{qr_base64}"
        })
    
    context = {
        'school': school,
        'class_name': class_name,
        'qr_codes': qr_codes,
        'total_students': len(qr_codes),
    }
    return render(request, 'operations/bulk_qr_codes.html', context)


@login_required
def attendance_qr_summary(request):
    """Summary page showing QR attendance stats for today."""
    school = getattr(request.user, 'school', None)
    
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school found.')
        return redirect('home')
    
    today = timezone.now().date()
    
    # Get attendance for today
    attendance_today = StudentAttendance.objects.filter(
        date=today
    ).select_related('student', 'student__user').order_by('-created_at')
    
    # Count by status
    stats = {
        'present': attendance_today.filter(status='present').count(),
        'absent': attendance_today.filter(status='absent').count(),
        'late': attendance_today.filter(status='late').count(),
        'excused': attendance_today.filter(status='excused').count(),
        'total': attendance_today.count(),
    }
    
    # Get all students count
    total_students = Student.objects.filter(school=school).count()
    
    context = {
        'school': school,
        'date': today,
        'stats': stats,
        'total_students': total_students,
        'attendance_records': attendance_today[:50],  # Latest 50
    }
    return render(request, 'operations/attendance_qr_summary.html', context)
