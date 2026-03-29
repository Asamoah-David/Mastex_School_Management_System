"""
Bulk SMS Views for Mastex SchoolOS
Send SMS to multiple recipients at once
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone

from students.models import Student
from schools.models import School
from services.sms_service import send_sms


@login_required
def bulk_sms_page(request):
    """Bulk SMS page for sending messages to parents."""
    school = getattr(request.user, 'school', None)
    
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    # Get classes for filtering
    classes = Student.objects.filter(school=school).values_list('class_name', flat=True).distinct()
    
    # Count recipients
    all_parents = Student.objects.filter(school=school, parent__isnull=False).exclude(parent__phone='').select_related('parent', 'user').count()
    all_students = Student.objects.filter(school=school).count()
    
    context = {
        'school': school,
        'classes': [c for c in classes if c],
        'total_parents': all_parents,
        'total_students': all_students,
    }
    return render(request, 'messaging/bulk_sms.html', context)


@login_required
def get_recipients(request):
    """Get list of recipients based on filter."""
    school = getattr(request.user, 'school', None)
    
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'error': 'No school found'}, status=400)
    
    recipient_type = request.GET.get('type')  # 'all_parents', 'class_parents', 'all_students', 'class_students'
    class_name = request.GET.get('class')
    
    recipients = []
    
    if recipient_type == 'all_parents':
        students = Student.objects.filter(school=school, parent__isnull=False).exclude(parent__phone='').select_related('parent', 'user')
        for student in students:
            if student.parent and student.parent.phone:
                recipients.append({
                    'name': student.parent.get_full_name() or student.parent.username,
                    'phone': student.parent.phone,
                    'student': student.user.get_full_name() or student.user.username,
                    'class': student.class_name,
                    'type': 'parent'
                })
    
    elif recipient_type == 'class_parents' and class_name:
        students = Student.objects.filter(school=school, class_name=class_name, parent__isnull=False).exclude(parent__phone='').select_related('parent', 'user')
        for student in students:
            if student.parent and student.parent.phone:
                recipients.append({
                    'name': student.parent.get_full_name() or student.parent.username,
                    'phone': student.parent.phone,
                    'student': student.user.get_full_name() or student.user.username,
                    'class': student.class_name,
                    'type': 'parent'
                })
    
    elif recipient_type == 'all_students':
        students = Student.objects.filter(school=school, user__phone__isnull=False).exclude(user__phone='').select_related('user')
        for student in students:
            if student.user and student.user.phone:
                recipients.append({
                    'name': student.user.get_full_name() or student.user.username,
                    'phone': student.user.phone,
                    'student': None,
                    'class': student.class_name,
                    'type': 'student'
                })
    
    elif recipient_type == 'class_students' and class_name:
        students = Student.objects.filter(school=school, class_name=class_name, user__phone__isnull=False).exclude(user__phone='').select_related('user')
        for student in students:
            if student.user and student.user.phone:
                recipients.append({
                    'name': student.user.get_full_name() or student.user.username,
                    'phone': student.user.phone,
                    'student': None,
                    'class': student.class_name,
                    'type': 'student'
                })
    
    return JsonResponse({
        'recipients': recipients,
        'count': len(recipients)
    })


@login_required
def send_bulk_sms(request):
    """Send SMS to selected recipients."""
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
        recipients = data.get('recipients', [])
        message = data.get('message', '').strip()
        
        if not message:
            return JsonResponse({'success': False, 'error': 'Message cannot be empty'}, status=400)
        
        if len(message) > 160:
            return JsonResponse({'success': False, 'error': 'Message too long (max 160 characters)'}, status=400)
        
        if not recipients:
            return JsonResponse({'success': False, 'error': 'No recipients selected'}, status=400)
        
        # Send SMS to each recipient
        success_count = 0
        failed_count = 0
        failed_numbers = []
        
        for recipient in recipients:
            phone = recipient.get('phone', '')
            if phone:
                try:
                    result = send_sms(phone, message, school_name=school.name)
                    if result.get('success'):
                        success_count += 1
                    else:
                        failed_count += 1
                        failed_numbers.append(phone)
                except Exception as e:
                    failed_count += 1
                    failed_numbers.append(phone)
        
        return JsonResponse({
            'success': True,
            'sent': success_count,
            'failed': failed_count,
            'failed_numbers': failed_numbers[:5],  # First 5 failed numbers
            'message': f"SMS sent to {success_count} recipients. {failed_count} failed."
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid data format'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def sms_history(request):
    """View SMS history for the school."""
    school = getattr(request.user, 'school', None)
    
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    # For now, we'll show a simple template
    # In production, you'd have an SMSLog model
    context = {
        'school': school,
    }
    return render(request, 'messaging/sms_history.html', context)
