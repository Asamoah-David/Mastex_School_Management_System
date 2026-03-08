from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
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


@login_required
def send_message(request):
    """Send SMS to parents or students."""
    if not _user_can_manage_school(request):
        return redirect("home")
    
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("home")
    
    if request.method == "POST":
        recipient_type = request.POST.get("recipient_type")
        message = request.POST.get("message", "").strip()
        
        if not message:
            messages.error(request, "Please enter a message.")
            return render(request, "messaging/send_message.html", {"school": school})
        
        recipients = []
        
        if recipient_type == "parents":
            parents = User.objects.filter(school=school, role="parent", phone__isnull=False).exclude(phone="")
            for parent in parents:
                if parent.phone:
                    try:
                        send_sms(parent.phone, message)
                        recipients.append(parent.username)
                    except Exception as e:
                        messages.error(request, f"Failed to send to {parent.username}: {str(e)}")
        elif recipient_type == "students":
            students = Student.objects.filter(school=school, user__phone__isnull=False).select_related("user")
            for student in students:
                if student.user.phone:
                    try:
                        send_sms(student.user.phone, message)
                        recipients.append(student.user.username)
                    except Exception as e:
                        messages.error(request, f"Failed to send to {student.user.username}: {str(e)}")
        elif recipient_type == "all":
            # Send to parents
            parents = User.objects.filter(school=school, role="parent", phone__isnull=False).exclude(phone="")
            for parent in parents:
                if parent.phone:
                    try:
                        send_sms(parent.phone, message)
                        recipients.append(parent.username)
                    except Exception as e:
                        pass
            # Send to students
            students = Student.objects.filter(school=school, user__phone__isnull=False).select_related("user")
            for student in students:
                if student.user.phone:
                    try:
                        send_sms(student.user.phone, message)
                        recipients.append(student.user.username)
                    except Exception as e:
                        pass
        
        if recipients:
            messages.success(request, f"Message sent to {len(recipients)} recipients.")
        else:
            messages.error(request, "No recipients found with phone numbers.")
        
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
