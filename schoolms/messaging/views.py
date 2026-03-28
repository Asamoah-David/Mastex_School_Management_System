from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from accounts.models import User
from accounts.permissions import user_can_manage_school
from students.models import Student, SchoolClass
from .utils import send_sms


def _user_can_manage_school(request):
    """Use shared permission helper for school-scoped messaging."""
    return user_can_manage_school(request.user)


def _send_email(to_email, subject, message):
    """Send email with error handling and clear error messages."""
    # Check if email is configured
    email_user = getattr(settings, 'EMAIL_HOST_USER', None)
    email_password = getattr(settings, 'EMAIL_HOST_PASSWORD', None)
    
    if not email_user or email_user == "":
        return False, "Email not configured. Please set EMAIL_HOST_USER in environment variables."
    
    if not email_password or email_password == "":
        return False, "Email password not configured. Please set EMAIL_HOST_PASSWORD in environment variables. Note: For Gmail, use an App Password, not your regular password."
    
    # Validate recipient email
    if not to_email or '@' not in str(to_email):
        return False, f"Invalid recipient email: {to_email}"
    
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
        error_msg = str(e)
        
        # Provide more helpful error messages for common issues
        if "SMTP" in error_msg and "authentication" in error_msg.lower():
            return False, "Email authentication failed. Check your EMAIL_HOST_USER and EMAIL_HOST_PASSWORD. For Gmail, you need an App Password (16 characters)."
        elif "SMTP" in error_msg and "connection" in error_msg.lower():
            return False, "Cannot connect to email server. Check your network and email server settings."
        elif "SMTP" in error_msg and "timeout" in error_msg.lower():
            return False, "Email server connection timed out. Please try again later."
        elif "Invalid Gmail" in error_msg or "Username and Password not accepted" in error_msg:
            return False, "Gmail authentication failed. Use an App Password, not your regular Gmail password. Go to Google Account > Security > App Passwords to generate one."
        
        return False, error_msg


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
    
    # Teacher counts
    teachers_count = User.objects.filter(school=school, role="teacher").count()
    teachers_with_phone = User.objects.filter(school=school, role="teacher").exclude(phone__isnull=True).exclude(phone="").count()
    teachers_with_email = User.objects.filter(school=school, role="teacher").exclude(email__isnull=True).exclude(email="").count()
    
    # Get classes for filtering
    classes = SchoolClass.objects.filter(school=school).order_by('name')
    selected_class = request.GET.get("class")
    
    # Preview recipients based on selection
    recipient_preview = None
    selected_type = request.GET.get("type", "parents")
    
    # Apply class filter if selected
    class_filter = None
    if selected_class:
        try:
            class_filter = SchoolClass.objects.get(school=school, pk=selected_class)
        except SchoolClass.DoesNotExist:
            pass
    
    if selected_type == "parents":
        # Filter parents by class if selected (parents whose children are in that class)
        if class_filter:
            parent_ids = Student.objects.filter(school=school, class_name=class_filter.name).values_list('parent_id', flat=True).distinct()
            recipients = User.objects.filter(pk__in=parent_ids)
            class_parents_count = recipients.count()
            class_parents_phone = recipients.exclude(phone__isnull=True).exclude(phone="").count()
            class_parents_email = recipients.exclude(email__isnull=True).exclude(email="").count()
            recipient_preview = {
                "type": f"Parents - {class_filter.name}",
                "total": class_parents_count,
                "sms_count": class_parents_phone,
                "email_count": class_parents_email,
                "recipients": list(recipients.values("id", "first_name", "last_name", "phone", "email"))[:20]
            }
        else:
            recipients = User.objects.filter(school=school, role="parent").select_related("school")
            recipient_preview = {
                "type": "All Parents",
                "total": parents_count,
                "sms_count": parents_with_phone,
                "email_count": parents_with_email,
                "recipients": list(recipients.values("id", "first_name", "last_name", "phone", "email"))[:20]
            }
    elif selected_type == "students":
        # Filter students by class
        if class_filter:
            students = Student.objects.filter(school=school, class_name=class_filter.name).select_related("user")
            class_students_count = students.count()
            class_students_phone = students.exclude(user__phone__isnull=True).exclude(user__phone="").count()
            class_students_email = students.exclude(user__email__isnull=True).exclude(user__email="").count()
            recipient_preview = {
                "type": f"Students - {class_filter.name}",
                "total": class_students_count,
                "sms_count": class_students_phone,
                "email_count": class_students_email,
                "recipients": [{"id": s.id, "name": s.user.get_full_name() or s.user.username, "phone": s.user.phone, "email": s.user.email} for s in students[:20]]
            }
        else:
            recipients = Student.objects.filter(school=school).select_related("user")
            recipient_preview = {
                "type": "All Students",
                "total": students_count,
                "sms_count": students_with_phone,
                "email_count": students_with_email,
                "recipients": [{"id": s.id, "name": s.user.get_full_name() or s.user.username, "phone": s.user.phone, "email": s.user.email} for s in recipients[:20]]
            }
    elif selected_type == "teachers":
        recipients = User.objects.filter(school=school, role="teacher").select_related("school")
        recipient_preview = {
            "type": "All Teachers",
            "total": teachers_count,
            "sms_count": teachers_with_phone,
            "email_count": teachers_with_email,
            "recipients": list(recipients.values("id", "first_name", "last_name", "phone", "email"))[:20]
        }
    else:  # all
        recipient_preview = {
            "type": "All (Parents, Students & Teachers)",
            "total": parents_count + students_count + teachers_count,
            "sms_count": parents_with_phone + students_with_phone + teachers_with_phone,
            "email_count": parents_with_email + students_with_email + teachers_with_email,
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
        "teachers_count": teachers_count,
        "teachers_with_phone": teachers_with_phone,
        "teachers_with_email": teachers_with_email,
        "classes": classes,
        "selected_class": selected_class,
        "class_filter": class_filter,
        "recipient_preview": recipient_preview,
        "selected_type": selected_type,
    }
    
    if request.method == "POST":
        recipient_type = request.POST.get("recipient_type")
        message_type = request.POST.get("message_type", "sms")
        subject = request.POST.get("subject", "Message from School")
        message = request.POST.get("message", "").strip()
        send_class = request.POST.get("send_class")  # Get selected class from form
        
        # Get class filter for sending
        send_class_filter = None
        if send_class:
            try:
                send_class_filter = SchoolClass.objects.get(school=school, pk=send_class)
            except SchoolClass.DoesNotExist:
                pass
        
        if not message:
            messages.error(request, "Please enter a message.")
            return render(request, "messaging/send_message.html", context)
        
        sent_count = 0
        failed_count = 0
        errors = []
        
        if recipient_type == "parents":
            # Filter by class if selected
            if send_class_filter:
                parent_ids = Student.objects.filter(school=school, class_name=send_class_filter.name).values_list('parent_id', flat=True).distinct()
                parents = User.objects.filter(pk__in=parent_ids)
            else:
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
            # Filter by class if selected
            if send_class_filter:
                students = Student.objects.filter(school=school, class_name=send_class_filter.name).select_related("user")
            else:
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
                        
        elif recipient_type == "teachers":
            teachers = User.objects.filter(school=school, role="teacher")
            for teacher in teachers:
                if message_type == "sms" and teacher.phone:
                    try:
                        send_sms(teacher.phone, message)
                        sent_count += 1
                    except Exception as e:
                        failed_count += 1
                        errors.append(f"SMS failed for {teacher.username}: {str(e)}")
                elif message_type == "email" and teacher.email:
                    success, error = _send_email(teacher.email, subject, message)
                    if success:
                        sent_count += 1
                    else:
                        failed_count += 1
                        errors.append(f"Email failed for {teacher.username}: {error}")
                        
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
            # Send to teachers
            teachers = User.objects.filter(school=school, role="teacher")
            for teacher in teachers:
                if message_type == "sms" and teacher.phone:
                    try:
                        send_sms(teacher.phone, message)
                        sent_count += 1
                    except Exception as e:
                        failed_count += 1
                elif message_type == "email" and teacher.email:
                    success, error = _send_email(teacher.email, subject, message)
                    if success:
                        sent_count += 1
                    else:
                        failed_count += 1
        
        if sent_count > 0 or failed_count > 0:
            msg_type = "SMS" if message_type == "sms" else "Email"
            if sent_count > 0:
                messages.success(request, f"{msg_type} sent successfully to {sent_count} recipient(s).")
            if failed_count > 0:
                # Show error details
                error_summary = f"{failed_count} message(s) failed to send."
                if errors:
                    error_summary += f" First error: {errors[0]}"
                messages.error(request, error_summary)
        else:
            messages.error(request, "No recipients found. Please ensure parents/students/teachers have valid phone numbers and emails.")
        
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


@login_required
def chat_view(request):
    """Parent-Teacher chat interface (placeholder - uses timetable_generator functions)."""
    from academics.timetable_generator import chat_page
    return chat_page(request)


@login_required
def get_messages(request, contact_id):
    """Get messages with a contact."""
    from academics.timetable_generator import get_messages as _get_messages
    return _get_messages(request, contact_id)
