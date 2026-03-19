from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from accounts.models import User
from accounts.permissions import user_can_manage_school
from students.models import Student
from .utils import send_sms


def _user_can_manage_school(request):
    """Use shared permission helper for school-scoped messaging."""
    return user_can_manage_school(request.user)


def _send_email(to_email, subject, message):
    """Send email with error handling."""
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [to_email],
            fail_silently=False,
        )
        return True, None
    except Exception as e:
        return False, str(e)


@login_required
def send_message(request):
    """Send SMS or Email to parents or students with recipient preview."""
    if not _user_can_manage_school(request):
        return redirect("home")
    
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    # Get recipient counts for preview
    parents_count = User.objects.filter(school=school, role="parent").count()
    parents_with_phone = User.objects.filter(school=school, role="parent").exclude(phone__isnull=True).exclude(phone="").count()
    parents_with_email = User.objects.filter(school=school, role="parent").exclude(email__isnull=True).exclude(email="").count()
    
    students_count = Student.objects.filter(school=school).count()
    students_with_phone = Student.objects.filter(school=school).exclude(user__phone__isnull=True).exclude(user__phone="").count()
    students_with_email = Student.objects.filter(school=school).exclude(user__email__isnull=True).exclude(user__email="").count()
    
    # Preview recipients based on selection
    recipient_preview = None
    selected_type = request.GET.get("type", "parents")
    
    if selected_type == "parents":
        recipients = User.objects.filter(school=school, role="parent").select_related("school")
        recipient_preview = {
            "type": "Parents",
            "total": parents_count,
            "sms_count": parents_with_phone,
            "email_count": parents_with_email,
            "recipients": list(recipients.values("id", "first_name", "last_name", "phone", "email"))[:20]
        }
    elif selected_type == "students":
        recipients = Student.objects.filter(school=school).select_related("user")
        recipient_preview = {
            "type": "Students",
            "total": students_count,
            "sms_count": students_with_phone,
            "email_count": students_with_email,
            "recipients": [{"id": s.id, "name": s.user.get_full_name() or s.user.username, "phone": s.user.phone, "email": s.user.email} for s in recipients[:20]]
        }
    else:  # all
        recipient_preview = {
            "type": "All (Parents & Students)",
            "total": parents_count + students_count,
            "sms_count": parents_with_phone + students_with_phone,
            "email_count": parents_with_email + students_with_email,
            "recipients": []
        }
    
    context = {
        "school": school,
        "parents_count": parents_count,
        "parents_with_phone": parents_with_phone,
        "parents_with_email": parents_with_email,
        "students_count": students_count,
        "students_with_phone": students_with_phone,
        "students_with_email": students_with_email,
        "recipient_preview": recipient_preview,
        "selected_type": selected_type,
    }
    
    if request.method == "POST":
        recipient_type = request.POST.get("recipient_type")
        message_type = request.POST.get("message_type", "sms")
        subject = request.POST.get("subject", "Message from School")
        message = request.POST.get("message", "").strip()
        
        if not message:
            messages.error(request, "Please enter a message.")
            return render(request, "messaging/send_message.html", context)
        
        sent_count = 0
        failed_count = 0
        errors = []
        
        if recipient_type == "parents":
            parents = User.objects.filter(school=school, role="parent")
            for parent in parents:
                if message_type == "sms" and parent.phone:
                    try:
                        send_sms(parent.phone, message)
                        sent_count += 1
                    except Exception as e:
                        failed_count += 1
                        errors.append(f"SMS failed for {parent.username}: {str(e)}")
                elif message_type == "email" and parent.email:
                    success, error = _send_email(parent.email, subject, message)
                    if success:
                        sent_count += 1
                    else:
                        failed_count += 1
                        errors.append(f"Email failed for {parent.username}: {error}")
                        
        elif recipient_type == "students":
            students = Student.objects.filter(school=school).select_related("user")
            for student in students:
                if message_type == "sms" and student.user.phone:
                    try:
                        send_sms(student.user.phone, message)
                        sent_count += 1
                    except Exception as e:
                        failed_count += 1
                        errors.append(f"SMS failed for {student.user.username}: {str(e)}")
                elif message_type == "email" and student.user.email:
                    success, error = _send_email(student.user.email, subject, message)
                    if success:
                        sent_count += 1
                    else:
                        failed_count += 1
                        errors.append(f"Email failed for {student.user.username}: {error}")
                        
        elif recipient_type == "all":
            # Send to parents
            parents = User.objects.filter(school=school, role="parent")
            for parent in parents:
                if message_type == "sms" and parent.phone:
                    try:
                        send_sms(parent.phone, message)
                        sent_count += 1
                    except Exception as e:
                        failed_count += 1
                elif message_type == "email" and parent.email:
                    success, error = _send_email(parent.email, subject, message)
                    if success:
                        sent_count += 1
                    else:
                        failed_count += 1
            # Send to students
            students = Student.objects.filter(school=school).select_related("user")
            for student in students:
                if message_type == "sms" and student.user.phone:
                    try:
                        send_sms(student.user.phone, message)
                        sent_count += 1
                    except Exception as e:
                        failed_count += 1
                elif message_type == "email" and student.user.email:
                    success, error = _send_email(student.user.email, subject, message)
                    if success:
                        sent_count += 1
                    else:
                        failed_count += 1
        
        if sent_count > 0:
            msg_type = "SMS" if message_type == "sms" else "Email"
            messages.success(request, f"{msg_type} sent successfully to {sent_count} recipient(s).")
            if failed_count > 0:
                messages.warning(request, f"{failed_count} message(s) failed to send.")
        else:
            messages.error(request, "No messages could be sent. Please check recipients have valid phone numbers or email addresses.")
        
        return redirect("messaging:send_message")
    
    return render(request, "messaging/send_message.html", context)


@login_required
def message_history(request):
    """View message history (placeholder - could be extended to store in DB)."""
    if not _user_can_manage_school(request):
        return redirect("home")
    
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    return render(request, "messaging/message_history.html", {"school": school})
