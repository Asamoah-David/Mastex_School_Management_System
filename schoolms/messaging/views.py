from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from accounts.models import User
from students.models import Student
from .utils import send_sms


def _user_can_manage_school(request):
    """Check if user can manage school."""
    if not request.user.is_authenticated:
        return False
    if request.user.is_superuser:
        return True
    return request.user.role in ("admin", "teacher") and getattr(request.user, "school_id", None)


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
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


@login_required
def send_message(request):
    """Send SMS or Email to parents or students."""
    if not _user_can_manage_school(request):
        return redirect("home")
    
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    if request.method == "POST":
        recipient_type = request.POST.get("recipient_type")
        message_type = request.POST.get("message_type", "sms")  # sms or email
        subject = request.POST.get("subject", "Message from School")
        message = request.POST.get("message", "").strip()
        
        if not message:
            messages.error(request, "Please enter a message.")
            return render(request, "messaging/send_message.html", {"school": school})
        
        recipients = []
        
        if recipient_type == "parents":
            parents = User.objects.filter(school=school, role="parent")
            for parent in parents:
                if message_type == "sms" and parent.phone:
                    try:
                        send_sms(parent.phone, message)
                        recipients.append(parent.username)
                    except Exception as e:
                        pass
                elif message_type == "email" and parent.email:
                    if _send_email(parent.email, subject, message):
                        recipients.append(parent.username)
        elif recipient_type == "students":
            students = Student.objects.filter(school=school).select_related("user")
            for student in students:
                if message_type == "sms" and student.user.phone:
                    try:
                        send_sms(student.user.phone, message)
                        recipients.append(student.user.username)
                    except Exception as e:
                        pass
                elif message_type == "email" and student.user.email:
                    if _send_email(student.user.email, subject, message):
                        recipients.append(student.user.username)
        elif recipient_type == "all":
            # Send to parents
            parents = User.objects.filter(school=school, role="parent")
            for parent in parents:
                if message_type == "sms" and parent.phone:
                    try:
                        send_sms(parent.phone, message)
                        recipients.append(parent.username)
                    except Exception as e:
                        pass
                elif message_type == "email" and parent.email:
                    if _send_email(parent.email, subject, message):
                        recipients.append(parent.username)
            # Send to students
            students = Student.objects.filter(school=school).select_related("user")
            for student in students:
                if message_type == "sms" and student.user.phone:
                    try:
                        send_sms(student.user.phone, message)
                        recipients.append(student.user.username)
                    except Exception as e:
                        pass
                elif message_type == "email" and student.user.email:
                    if _send_email(student.user.email, subject, message):
                        recipients.append(student.user.username)
        
        if recipients:
            msg_type = "SMS" if message_type == "sms" else "Email"
            messages.success(request, f"{msg_type} sent to {len(recipients)} recipients.")
        else:
            messages.error(request, "No recipients found.")
        
        return redirect("messaging:send_message")
    
    return render(request, "messaging/send_message.html", {"school": school})


@login_required
def message_history(request):
    """View message history (placeholder - could be extended to store in DB)."""
    if not _user_can_manage_school(request):
        return redirect("home")
    
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    return render(request, "messaging/message_history.html", {"school": school})
