from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from accounts.models import User
from accounts.permissions import user_can_manage_school
from students.models import Student, SchoolClass
from schools.models import School
from .utils import send_sms
from .models import OutboundCommLog


from core.utils import can_manage as _user_can_manage_school, get_school
from core.pagination import paginate


def _send_email(to_email, subject, message):
    """Send email using SendGrid API."""
    # Try SendGrid first
    sendgrid_key = getattr(settings, 'SENDGRID_API_KEY', None)
    if sendgrid_key and sendgrid_key != "":
        try:
            from services.sendgrid_email import send_email as sendgrid_send_email
            sendgrid_send_email(to_email, subject, message)
            return True, None
        except Exception as e:
            return False, str(e)
    
    # Fallback: try SMTP
    from django.core.mail import send_mail
    email_user = getattr(settings, 'EMAIL_HOST_USER', None)
    email_password = getattr(settings, 'EMAIL_HOST_PASSWORD', None)
    
    if not email_user or email_user == "":
        return False, "Email not configured. Please set SENDGRID_API_KEY or EMAIL_HOST_USER in environment variables."
    
    if not email_password or email_password == "":
        return False, "Email password not configured. Please set EMAIL_HOST_PASSWORD in environment variables."
    
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
        return False, str(e)


@login_required
def send_message(request):
    """Send SMS or Email to parents or students with recipient preview."""
    import logging
    logger = logging.getLogger(__name__)

    if not _user_can_manage_school(request):
        logger.debug("send_message: user not authorized: %s", request.user)
        return redirect("home")

    school = get_school(request)
    if not school and request.user.is_superuser:
        sid = request.session.get("current_school_id")
        if sid:
            school = School.objects.filter(pk=sid).first()
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

        if sent_count or failed_count:
            try:
                OutboundCommLog.objects.create(
                    school=school,
                    sender=request.user,
                    channel=message_type if message_type in ("sms", "email") else "sms",
                    subject=subject if message_type == "email" else "",
                    message_preview=(message[:2000] if message else ""),
                    sent_count=sent_count,
                    failed_count=failed_count,
                    recipient_summary=(
                        f"{recipient_type}"
                        + (f" · class {send_class_filter.name}" if send_class_filter else "")
                    )[:255],
                )
            except Exception:
                logger.exception("OutboundCommLog create failed")
        
        return redirect("messaging:send_message")
    
    return render(request, "messaging/send_message.html", context)


@login_required
def message_history(request):
    """View message history (placeholder - could be extended to store in DB)."""
    if not _user_can_manage_school(request):
        return redirect("home")

    school = get_school(request)
    if not school and request.user.is_superuser:
        sid = request.session.get("current_school_id")
        if sid:
            school = School.objects.filter(pk=sid).first()
    if not school:
        return redirect("home")

    qs = (
        OutboundCommLog.objects.filter(school=school)
        .select_related("sender")
        .order_by("-created_at")
    )
    page_obj = paginate(request, qs, per_page=50)
    return render(
        request,
        "messaging/message_history.html",
        {"school": school, "logs": page_obj, "page_obj": page_obj},
    )


@login_required
def chat_view(request):
    """Parent-Teacher chat interface with real DB persistence."""
    from .models import Conversation, Message as ChatMessage

    user = request.user
    school = get_school(request)
    if not school and user.is_superuser:
        sid = request.session.get("current_school_id")
        if sid:
            school = School.objects.filter(pk=sid).first()
    if not school:
        return redirect("home")

    conversations = Conversation.objects.filter(participants=user).prefetch_related("participants")
    active_conv_id = request.GET.get("conv")
    active_conv = None
    chat_messages = []
    contact = None

    if active_conv_id:
        active_conv = Conversation.objects.filter(id=active_conv_id, participants=user).first()
        if active_conv:
            chat_messages = list(
                ChatMessage.objects.filter(conversation=active_conv)
                .select_related("sender")
                .order_by("created_at")[:200]
            )
            ChatMessage.objects.filter(conversation=active_conv, recipient=user, is_read=False).update(is_read=True)
            contact = active_conv.participants.exclude(id=user.id).first()

    if request.method == "POST" and active_conv:
        body = request.POST.get("body", "").strip()
        if body and contact:
            ChatMessage.objects.create(
                conversation=active_conv,
                sender=user,
                recipient=contact,
                body=body,
            )
            return redirect(f"/messaging/chat/?conv={active_conv.id}")

    if request.method == "POST" and not active_conv:
        recipient_id = request.POST.get("recipient")
        body = request.POST.get("body", "").strip()
        if recipient_id and body:
            from accounts.models import User as _User
            try:
                recipient = _User.objects.get(id=recipient_id, school=school)
            except _User.DoesNotExist:
                recipient = None
            if recipient:
                conv = Conversation.objects.create(subject="", school=school)
                conv.participants.add(user, recipient)
                ChatMessage.objects.create(
                    conversation=conv, sender=user, recipient=recipient, body=body,
                )
                return redirect(f"/messaging/chat/?conv={conv.id}")

    contacts = []
    role = getattr(user, "role", None)
    if role == "parent":
        contacts = list(User.objects.filter(school=school, role="teacher").order_by("first_name")[:50])
    elif role == "teacher":
        contacts = list(User.objects.filter(school=school, role="parent").order_by("first_name")[:50])
    elif role in ("school_admin", "super_admin") or user.is_superuser:
        contacts = list(
            User.objects.filter(school=school)
            .exclude(pk=user.pk)
            .filter(role__in=["teacher", "parent", "school_admin"])
            .order_by("first_name", "last_name")[:100]
        )

    return render(request, "messaging/chat.html", {
        "conversations": conversations,
        "active_conv": active_conv,
        "chat_messages": chat_messages,
        "contact": contact,
        "contacts": contacts,
        "school": school,
    })


@login_required
def get_messages(request, contact_id):
    """Get messages with a contact as JSON for AJAX."""
    from django.http import JsonResponse
    from .models import Conversation, Message as ChatMessage

    user = request.user
    try:
        target = User.objects.get(id=contact_id)
    except User.DoesNotExist:
        return JsonResponse({"messages": []})

    conv = Conversation.objects.filter(participants=user).filter(participants=target).first()
    if not conv:
        return JsonResponse({"messages": []})

    msgs = ChatMessage.objects.filter(conversation=conv).order_by("created_at").values(
        "id", "sender__first_name", "sender__last_name", "body", "created_at", "is_read"
    )[:200]

    return JsonResponse({"messages": list(msgs)}, json_dumps_params={"default": str})


@login_required
def superuser_send_message(request):
    """Superuser can send SMS or Email to school admins across all schools or a specific school."""
    import logging
    from accounts.permissions import is_super_admin

    logger = logging.getLogger(__name__)

    if not (request.user.is_superuser or is_super_admin(request.user)):
        return redirect("home")
    
    # Get all schools for selection
    all_schools = School.objects.all().order_by('name')
    
    # Get selected school from form
    selected_school_id = request.GET.get("school")
    target_school = None
    if selected_school_id:
        try:
            target_school = School.objects.get(id=selected_school_id)
        except School.DoesNotExist:
            pass
    
    # If no school selected, show all schools option
    if request.method == "POST":
        recipient_type = request.POST.get("recipient_type")  # "all_schools" or specific school ID
        message_type = request.POST.get("message_type", "sms")
        subject = request.POST.get("subject", "Message from Mastex SchoolOS")
        message = request.POST.get("message", "").strip()
        
        if not message:
            messages.error(request, "Please enter a message.")
            return render(request, "messaging/superuser_send_message.html", {
                "all_schools": all_schools,
                "selected_school_id": selected_school_id
            })
        
        sent_count = 0
        failed_count = 0
        errors = []
        
        # Get schools to send to
        if recipient_type == "all_schools":
            schools_to_send = all_schools
        else:
            # Specific school
            try:
                schools_to_send = [School.objects.get(id=recipient_type)]
            except School.DoesNotExist:
                messages.error(request, "Invalid school selected.")
                return render(request, "messaging/superuser_send_message.html", {
                    "all_schools": all_schools,
                    "selected_school_id": selected_school_id
                })
        
        for target in schools_to_send:
            school_admins = User.objects.filter(school=target, role="school_admin")
            
            logger.debug("Sending to %s admins in %s", school_admins.count(), target.name)

            for admin in school_admins:
                if message_type == "sms" and admin.phone:
                    try:
                        send_sms(admin.phone, message)
                        sent_count += 1
                        logger.debug("SMS sent to %s", admin.username)
                    except Exception as e:
                        failed_count += 1
                        error_msg = f"SMS failed for {admin.username}: {str(e)}"
                        errors.append(error_msg)
                        logger.warning("%s", error_msg)

                elif message_type == "email" and admin.email:
                    success, error = _send_email(admin.email, subject, message)
                    if success:
                        sent_count += 1
                        logger.debug("Email sent to %s", admin.username)
                    else:
                        failed_count += 1
                        error_msg = f"Email failed for {admin.username}: {error}"
                        errors.append(error_msg)
                        logger.warning("%s", error_msg)
        
        msg_type = "SMS" if message_type == "sms" else "Email"
        
        if sent_count > 0:
            messages.success(request, f"{msg_type} sent to {sent_count} admin(s) across {len(schools_to_send)} school(s).")
        
        if failed_count > 0:
            error_details = " | ".join(errors[:3])  # Show first 3 errors
            messages.error(request, f"{failed_count} message(s) failed. Errors: {error_details}")
        
        if sent_count == 0 and failed_count == 0:
            messages.warning(request, "No school admins found with valid phone/email addresses.")
        
        return redirect("messaging:superuser_send_message")
    
    context = {
        "all_schools": all_schools,
        "selected_school_id": selected_school_id,
        "target_school": target_school
    }
    return render(request, "messaging/superuser_send_message.html", context)
