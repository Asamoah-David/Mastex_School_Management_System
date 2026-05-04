"""
Recruitment Portal Views
Public: job listings, apply, pay, track
School admin: manage postings, review applicants, schedule interviews
Super admin: platform dashboard
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import is_super_admin, user_can_manage_school
from finance.paystack_service import PaystackService
from schools.features import is_feature_enabled
from schools.models import School
from recruitment.models import JobPosting, JobApplication, InterviewSchedule, QUAL_RANK, QUALIFICATION_CHOICES

logger = logging.getLogger(__name__)
paystack_service = PaystackService()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _send_email(subject, body, recipients):
    if not recipients:
        return
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    if not from_email:
        return
    try:
        send_mail(subject, body, from_email, recipients, fail_silently=True)
    except Exception:
        logger.exception("Recruitment email failed")


def _send_sms_notice(phone, message):
    try:
        from messaging.utils import send_sms
        send_sms(phone, message)
    except Exception:
        logger.exception("Recruitment SMS failed")


def _school_or_403(request):
    school = getattr(request.user, "school", None)
    if not school:
        raise Http404("School not found")
    return school


# ---------------------------------------------------------------------------
# PUBLIC VIEWS — no login required
# ---------------------------------------------------------------------------

def job_list(request):
    """Public job board — lists all active, open postings across all schools."""
    qs = (
        JobPosting.objects.filter(is_active=True, deadline__gte=timezone.now().date())
        .select_related("school")
        .annotate(app_count=Count("applications", filter=Q(applications__payment_status="paid")))
        .order_by("-created_at")
    )
    job_type = request.GET.get("type", "")
    school_id = request.GET.get("school", "")
    q = request.GET.get("q", "").strip()

    if job_type:
        qs = qs.filter(job_type=job_type)
    if school_id:
        qs = qs.filter(school_id=school_id)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(subjects__icontains=q))

    schools = School.objects.filter(is_active=True).order_by("name")
    return render(request, "recruitment/job_list.html", {
        "jobs": qs,
        "schools": schools,
        "job_types": JobPosting.JOB_TYPES,
        "type_filter": job_type,
        "school_filter": school_id,
        "q": q,
    })


def job_detail(request, pk):
    """Public job detail page."""
    job = get_object_or_404(
        JobPosting.objects.select_related("school"),
        pk=pk, is_active=True,
    )
    return render(request, "recruitment/job_detail.html", {"job": job})


def job_apply(request, pk):
    """Public application form — no login required."""
    job = get_object_or_404(JobPosting, pk=pk, is_active=True)
    if not job.is_open:
        messages.error(request, "This position is no longer accepting applications.")
        return redirect("recruitment:job_detail", pk=pk)

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        phone = request.POST.get("phone", "").strip()
        nationality = request.POST.get("nationality", "").strip()
        gender = request.POST.get("gender", "")
        dob_raw = request.POST.get("date_of_birth", "")
        qualification = request.POST.get("highest_qualification", "degree")
        try:
            years_exp = max(0, int(request.POST.get("years_experience", 0) or 0))
        except (ValueError, TypeError):
            years_exp = 0
        current_employer = request.POST.get("current_employer", "").strip()
        subjects_taught = request.POST.get("subjects_taught", "").strip()
        cover_letter = request.POST.get("cover_letter", "").strip()
        referees = request.POST.get("referees", "").strip()
        cv_file = request.FILES.get("cv_upload")

        errors = []
        if not full_name:
            errors.append("Full name is required.")
        if not email:
            errors.append("Email address is required.")
        if not phone:
            errors.append("Phone number is required.")
        if not cover_letter:
            errors.append("Cover letter / motivation is required.")
        if email and JobApplication.objects.filter(job=job, email=email, payment_status="paid").exists():
            errors.append("A paid application from this email already exists for this position.")
        # Minimum qualification check
        if job.min_qualification:
            req_rank = QUAL_RANK.get(job.min_qualification, 0)
            app_rank = QUAL_RANK.get(qualification, 0)
            if req_rank > 0 and app_rank < req_rank:
                req_label = dict(QUALIFICATION_CHOICES).get(job.min_qualification, job.min_qualification)
                errors.append(f"This position requires a minimum qualification of {req_label}.")
        # Minimum years of experience check
        if job.min_years_experience and years_exp < job.min_years_experience:
            errors.append(f"This position requires at least {job.min_years_experience} year(s) of experience.")
        # CV file validation
        if cv_file:
            allowed_exts = (".pdf", ".doc", ".docx")
            import os
            ext = os.path.splitext(cv_file.name)[1].lower()
            if ext not in allowed_exts:
                errors.append("CV must be a PDF, DOC, or DOCX file.")
            elif cv_file.size > 5 * 1024 * 1024:
                errors.append("CV file must be 5 MB or smaller.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "recruitment/job_apply.html", {
                "job": job, "post": request.POST,
            })

        import datetime
        dob = None
        if dob_raw:
            try:
                dob = datetime.date.fromisoformat(dob_raw)
            except ValueError:
                pass

        app = JobApplication.objects.create(
            job=job,
            full_name=full_name,
            email=email,
            phone=phone,
            nationality=nationality,
            gender=gender,
            date_of_birth=dob,
            highest_qualification=qualification,
            years_experience=years_exp,
            current_employer=current_employer,
            subjects_taught=subjects_taught,
            cover_letter=cover_letter,
            referees=referees,
            cv_upload=cv_file,
        )
        return redirect("recruitment:job_pay", ref=app.reference)

    return render(request, "recruitment/job_apply.html", {"job": job})


def job_pay(request, ref):
    """Paystack payment page — GHS 50 to PLATFORM (no subaccount)."""
    app = get_object_or_404(JobApplication, reference=ref)
    if app.payment_status == "paid":
        return redirect("recruitment:application_submitted", ref=ref)

    fee = app.job.application_fee
    callback_url = request.build_absolute_uri(
        reverse("recruitment:job_pay_callback")
    )
    paystack_ref = f"JOBAPP_{app.reference}_{uuid.uuid4().hex[:6].upper()}"
    metadata = {
        "application_reference": app.reference,
        "job_title": app.job.title,
        "school_name": app.job.school.name,
        "applicant_name": app.full_name,
        "payment_type": "job_application_fee",
    }
    result = paystack_service.initialize_payment(
        email=app.email,
        amount=float(fee),
        callback_url=callback_url,
        reference=paystack_ref,
        metadata=metadata,
        # No subaccount — payment lands in platform account
    )
    if result.get("status") and result.get("data", {}).get("authorization_url"):
        app.paystack_reference = paystack_ref
        app.save(update_fields=["paystack_reference"])
        return redirect(result["data"]["authorization_url"])

    messages.error(request, "Payment gateway error. Please try again.")
    return render(request, "recruitment/job_pay.html", {"app": app, "fee": fee})


def job_pay_callback(request):
    """Paystack callback — verify and mark application as submitted."""
    ref = request.GET.get("reference", "")
    if not ref:
        messages.error(request, "Invalid payment reference.")
        return redirect("recruitment:job_list")

    app = JobApplication.objects.filter(paystack_reference=ref).first()
    if not app:
        messages.error(request, "Application not found for this reference.")
        return redirect("recruitment:job_list")

    if app.payment_status == "paid":
        return redirect("recruitment:application_submitted", ref=app.reference)

    result = paystack_service.verify_payment(ref)
    if result.get("status") and result.get("data", {}).get("status") == "success":
        paid_kobo = result["data"].get("amount", 0)
        paid_ghs = Decimal(str(paid_kobo)) / Decimal("100")
        app.payment_status = "paid"
        app.amount_paid = paid_ghs
        app.status = "submitted"
        app.submitted_at = timezone.now()
        app.save(update_fields=["payment_status", "amount_paid", "status", "submitted_at"])

        # Notify applicant
        _send_email(
            subject=f"Application Received — {app.job.title} at {app.job.school.name}",
            body=(
                f"Dear {app.full_name},\n\n"
                f"Your application for '{app.job.title}' at {app.job.school.name} has been received.\n"
                f"Application Reference: {app.reference}\n"
                f"Application Fee Paid: GHS {paid_ghs:.2f}\n\n"
                f"You can track your application status at:\n"
                f"{request.build_absolute_uri(reverse('recruitment:track_application'))}"
                f"?ref={app.reference}\n\n"
                f"We will notify you of any updates. Good luck!\n\n"
                f"Mastex Education Platform"
            ),
            recipients=[app.email],
        )
        _send_sms_notice(
            app.phone,
            f"Your application for {app.job.title} at {app.job.school.name} (Ref: {app.reference}) has been received. GHS {paid_ghs:.2f} paid.",
        )

        # Notify school admin
        try:
            from notifications.models import Notification
            admins = app.job.school.user_set.filter(role__in=["school_admin", "deputy_head"])
            for admin in admins:
                Notification.create_notification(
                    user=admin,
                    title=f"New Job Application — {app.job.title}",
                    message=f"{app.full_name} has applied for the {app.job.title} position (Ref: {app.reference}).",
                    notification_type="info",
                    link=reverse("recruitment:school_application_detail", kwargs={"pk": app.pk}),
                    school=app.job.school,
                )
        except Exception:
            logger.exception("Failed to notify school admin of new job application")

        return redirect("recruitment:application_submitted", ref=app.reference)

    messages.error(request, "Payment could not be verified. Please contact support if you were charged.")
    return redirect("recruitment:job_pay", ref=app.reference)


def application_submitted(request, ref):
    """Confirmation page after successful payment."""
    app = get_object_or_404(JobApplication, reference=ref, payment_status="paid")
    return render(request, "recruitment/application_submitted.html", {"app": app})


def track_application(request):
    """Public status tracker — applicant enters their reference."""
    app = None
    ref = request.GET.get("ref", "").strip().upper()
    if ref:
        app = JobApplication.objects.filter(reference=ref, payment_status="paid").select_related(
            "job", "job__school", "interview_schedule"
        ).first()
        if not app:
            messages.error(request, "No paid application found for that reference.")
    return render(request, "recruitment/track_application.html", {"app": app, "ref": ref})


# ---------------------------------------------------------------------------
# SCHOOL ADMIN VIEWS — login + school staff required
# ---------------------------------------------------------------------------

def _require_job_portal(request):
    """Return a redirect response if job_portal feature is not enabled, else None."""
    if not is_feature_enabled(request, "job_portal"):
        messages.error(request, "The Job Portal feature is not enabled for your school.")
        return redirect("accounts:school_dashboard")
    return None


@login_required
def school_job_list(request):
    """School admin: list own job postings."""
    school = _school_or_403(request)
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    if not is_feature_enabled(request, "job_portal"):
        messages.error(request, "The Job Portal feature is not enabled for your school.")
        return redirect("accounts:school_dashboard")
    jobs = (
        JobPosting.objects.filter(school=school)
        .annotate(
            paid_apps=Count("applications", filter=Q(applications__payment_status="paid")),
            shortlisted=Count("applications", filter=Q(applications__status="shortlisted")),
        )
        .order_by("-created_at")
    )
    return render(request, "recruitment/school_job_list.html", {"jobs": jobs})


@login_required
def school_job_create(request):
    """School admin: create a new job posting."""
    school = _school_or_403(request)
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    resp = _require_job_portal(request)
    if resp:
        return resp

    if request.method == "POST":
        import datetime
        deadline_raw = request.POST.get("deadline", "")
        try:
            deadline = datetime.date.fromisoformat(deadline_raw)
        except ValueError:
            messages.error(request, "Invalid deadline date.")
            return render(request, "recruitment/school_job_form.html", {
                "job_types": JobPosting.JOB_TYPES, "qual_choices": QUALIFICATION_CHOICES, "post": request.POST,
            })

        try:
            min_years = int(request.POST.get("min_years_experience", 0) or 0)
        except (ValueError, TypeError):
            min_years = 0
        job = JobPosting.objects.create(
            school=school,
            title=request.POST.get("title", "").strip(),
            job_type=request.POST.get("job_type", "teacher"),
            subjects=request.POST.get("subjects", "").strip(),
            description=request.POST.get("description", "").strip(),
            requirements=request.POST.get("requirements", "").strip(),
            salary_range=request.POST.get("salary_range", "").strip(),
            min_qualification=request.POST.get("min_qualification", "").strip(),
            min_years_experience=max(0, min_years),
            slots_available=int(request.POST.get("slots_available", 1) or 1),
            application_fee=Decimal(request.POST.get("application_fee", "50.00") or "50.00"),
            deadline=deadline,
            is_active=True,
            created_by=request.user,
        )
        messages.success(request, f"Job posting '{job.title}' created. Reference: {job.reference_code}")
        return redirect("recruitment:school_job_list")

    return render(request, "recruitment/school_job_form.html", {
        "job_types": JobPosting.JOB_TYPES,
        "qual_choices": QUALIFICATION_CHOICES,
        "action": "Create",
        "post": {},
    })


@login_required
def school_job_edit(request, pk):
    """School admin: edit existing job posting."""
    school = _school_or_403(request)
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    resp = _require_job_portal(request)
    if resp:
        return resp
    job = get_object_or_404(JobPosting, pk=pk, school=school)

    if request.method == "POST":
        import datetime
        deadline_raw = request.POST.get("deadline", "")
        try:
            deadline = datetime.date.fromisoformat(deadline_raw)
        except ValueError:
            messages.error(request, "Invalid deadline date.")
            return render(request, "recruitment/school_job_form.html", {
                "job": job, "job_types": JobPosting.JOB_TYPES, "qual_choices": QUALIFICATION_CHOICES, "post": request.POST,
            })
        try:
            min_years = int(request.POST.get("min_years_experience", 0) or 0)
        except (ValueError, TypeError):
            min_years = 0
        job.title = request.POST.get("title", job.title).strip()
        job.job_type = request.POST.get("job_type", job.job_type)
        job.subjects = request.POST.get("subjects", "").strip()
        job.description = request.POST.get("description", "").strip()
        job.requirements = request.POST.get("requirements", "").strip()
        job.salary_range = request.POST.get("salary_range", "").strip()
        job.min_qualification = request.POST.get("min_qualification", "").strip()
        job.min_years_experience = max(0, min_years)
        job.slots_available = int(request.POST.get("slots_available", 1) or 1)
        job.deadline = deadline
        job.save()
        messages.success(request, "Job posting updated.")
        return redirect("recruitment:school_job_list")

    return render(request, "recruitment/school_job_form.html", {
        "job": job, "job_types": JobPosting.JOB_TYPES,
        "qual_choices": QUALIFICATION_CHOICES, "action": "Edit",
    })


@login_required
@require_POST
def school_job_toggle(request, pk):
    """Activate / deactivate a job posting."""
    school = _school_or_403(request)
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    resp = _require_job_portal(request)
    if resp:
        return resp
    job = get_object_or_404(JobPosting, pk=pk, school=school)
    job.is_active = not job.is_active
    job.save(update_fields=["is_active"])
    state = "activated" if job.is_active else "deactivated"
    messages.success(request, f"Job posting '{job.title}' {state}.")
    return redirect("recruitment:school_job_list")


@login_required
def school_applicant_list(request, job_pk):
    """School admin: list all paid applicants for a job."""
    school = _school_or_403(request)
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    resp = _require_job_portal(request)
    if resp:
        return resp
    job = get_object_or_404(JobPosting, pk=job_pk, school=school)
    status_filter = request.GET.get("status", "")
    apps = job.applications.filter(payment_status="paid").select_related("interview_schedule").order_by("-submitted_at")
    if status_filter:
        apps = apps.filter(status=status_filter)
    return render(request, "recruitment/school_applicant_list.html", {
        "job": job,
        "apps": apps,
        "status_choices": JobApplication.STATUS_CHOICES,
        "status_filter": status_filter,
    })


@login_required
def school_application_detail(request, pk):
    """School admin: view application and take actions."""
    school = _school_or_403(request)
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    resp = _require_job_portal(request)
    if resp:
        return resp
    app = get_object_or_404(
        JobApplication.objects.select_related("job", "job__school", "interview_schedule"),
        pk=pk, job__school=school, payment_status="paid",
    )
    allowed_statuses = [(s, l) for s, l in JobApplication.STATUS_CHOICES if s != "pending_payment"]
    return render(request, "recruitment/school_application_detail.html", {
        "app": app,
        "statuses": allowed_statuses,
    })


@login_required
@require_POST
def school_application_shortlist(request, pk):
    school = _school_or_403(request)
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    resp = _require_job_portal(request)
    if resp:
        return resp
    app = get_object_or_404(JobApplication, pk=pk, job__school=school, payment_status="paid")
    app.status = "shortlisted"
    app.reviewed_by = request.user
    app.reviewed_at = timezone.now()
    app.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    _send_email(
        subject=f"Application Update — {app.job.title} at {app.job.school.name}",
        body=(
            f"Dear {app.full_name},\n\n"
            f"Congratulations! Your application for '{app.job.title}' at {app.job.school.name} "
            f"has been shortlisted.\n\nRef: {app.reference}\n\n"
            f"You will be contacted shortly with further details.\n\nMastex Education Platform"
        ),
        recipients=[app.email],
    )
    _send_sms_notice(app.phone, f"Good news! Your application {app.reference} for {app.job.title} has been shortlisted.")
    messages.success(request, f"{app.full_name} has been shortlisted.")
    return redirect("recruitment:school_application_detail", pk=pk)


@login_required
@require_POST
def school_application_reject(request, pk):
    school = _school_or_403(request)
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    resp = _require_job_portal(request)
    if resp:
        return resp
    app = get_object_or_404(JobApplication, pk=pk, job__school=school, payment_status="paid")
    reason = request.POST.get("rejection_reason", "").strip()
    app.status = "rejected"
    app.rejection_reason = reason
    app.reviewed_by = request.user
    app.reviewed_at = timezone.now()
    app.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at"])
    _send_email(
        subject=f"Application Outcome — {app.job.title} at {app.job.school.name}",
        body=(
            f"Dear {app.full_name},\n\n"
            f"Thank you for applying for '{app.job.title}' at {app.job.school.name}.\n"
            f"After careful consideration, we regret to inform you that your application has not been successful.\n"
            + (f"\nFeedback: {reason}\n" if reason else "") +
            f"\nWe wish you the best in your future endeavours.\n\nMastex Education Platform"
        ),
        recipients=[app.email],
    )
    _send_sms_notice(
        app.phone,
        f"Update on your application {app.reference} for {app.job.title} at {app.job.school.name}: your application was unsuccessful. Thank you for applying.",
    )
    messages.success(request, f"{app.full_name} has been rejected.")
    return redirect("recruitment:school_applicant_list", job_pk=app.job_id)


@login_required
@require_POST
def school_application_hire(request, pk):
    school = _school_or_403(request)
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    resp = _require_job_portal(request)
    if resp:
        return resp
    app = get_object_or_404(JobApplication, pk=pk, job__school=school, payment_status="paid")
    app.status = "hired"
    app.reviewed_by = request.user
    app.reviewed_at = timezone.now()
    app.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    _send_email(
        subject=f"Offer of Employment — {app.job.title} at {app.job.school.name}",
        body=(
            f"Dear {app.full_name},\n\n"
            f"We are delighted to inform you that you have been selected for the position of "
            f"'{app.job.title}' at {app.job.school.name}.\n\n"
            f"The school will contact you directly to finalise the terms of your engagement.\n\n"
            f"Ref: {app.reference}\n\nCongratulations!\n\nMastex Education Platform"
        ),
        recipients=[app.email],
    )
    _send_sms_notice(app.phone, f"Congratulations! You have been selected for {app.job.title} at {app.job.school.name}.")
    messages.success(request, f"{app.full_name} marked as hired.")
    return redirect("recruitment:school_application_detail", pk=pk)


@login_required
def school_schedule_interview(request, pk):
    """Schedule interview and send invite link + message to applicant."""
    school = _school_or_403(request)
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    resp = _require_job_portal(request)
    if resp:
        return resp
    app = get_object_or_404(JobApplication, pk=pk, job__school=school, payment_status="paid")

    if request.method == "POST":
        import datetime
        date_raw = request.POST.get("interview_date", "")
        time_raw = request.POST.get("interview_time", "")
        mode = request.POST.get("mode", "in_person")
        location = request.POST.get("location", "").strip()
        meeting_link = request.POST.get("meeting_link", "").strip()
        message_text = request.POST.get("message_to_applicant", "").strip()

        if mode == "video_call" and not meeting_link:
            import uuid as _uuid
            room_id = _uuid.uuid4().hex[:8].upper()
            meeting_link = f"https://meet.jit.si/mastex-{school.id}-interview-{app.reference}-{room_id}"

        try:
            interview_date = datetime.date.fromisoformat(date_raw)
            interview_time = datetime.time.fromisoformat(time_raw)
        except ValueError:
            messages.error(request, "Invalid date or time.")
            return render(request, "recruitment/schedule_interview.html", {"app": app, "post": request.POST})

        schedule, _ = InterviewSchedule.objects.update_or_create(
            application=app,
            defaults=dict(
                interview_date=interview_date,
                interview_time=interview_time,
                mode=mode,
                location=location,
                meeting_link=meeting_link,
                message_to_applicant=message_text,
                scheduled_by=request.user,
                notified_at=timezone.now(),
            ),
        )
        app.status = "interview_scheduled"
        app.save(update_fields=["status"])

        mode_label = dict(InterviewSchedule.MODE_CHOICES).get(mode, mode)
        link_line = f"Link: {meeting_link}\n" if meeting_link else ""
        location_line = f"Venue: {location}\n" if location else ""
        body = (
            f"Dear {app.full_name},\n\n"
            f"You have been invited for an interview for the position of '{app.job.title}' "
            f"at {app.job.school.name}.\n\n"
            f"Date: {interview_date.strftime('%A, %d %B %Y')}\n"
            f"Time: {interview_time.strftime('%I:%M %p')}\n"
            f"Format: {mode_label}\n"
            f"{location_line}{link_line}\n"
            f"Message from the school:\n{message_text}\n\n"
            f"Application Reference: {app.reference}\n\n"
            f"Track your application: "
            f"{request.build_absolute_uri(reverse('recruitment:track_application'))}?ref={app.reference}\n\n"
            f"Mastex Education Platform"
        )
        _send_email(
            subject=f"Interview Invitation — {app.job.title} at {app.job.school.name}",
            body=body,
            recipients=[app.email],
        )
        sms_msg = (
            f"Interview scheduled: {app.job.title} at {app.job.school.name} on "
            f"{interview_date.strftime('%d %b %Y')} {interview_time.strftime('%I:%M %p')}. "
            f"Ref: {app.reference}"
        )
        _send_sms_notice(app.phone, sms_msg)
        messages.success(request, f"Interview scheduled and invitation sent to {app.full_name}.")
        return redirect("recruitment:school_application_detail", pk=pk)

    schedule = getattr(app, "interview_schedule", None)
    return render(request, "recruitment/schedule_interview.html", {
        "app": app,
        "schedule": schedule,
        "modes": InterviewSchedule.MODE_CHOICES,
    })


@login_required
@require_POST
def school_application_action(request, pk):
    """Single-endpoint status update for school admin (shortlist / reject / hire)."""
    school = _school_or_403(request)
    if not user_can_manage_school(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")
    resp = _require_job_portal(request)
    if resp:
        return resp
    app = get_object_or_404(JobApplication, pk=pk, job__school=school, payment_status="paid")
    new_status = request.POST.get("status", "").strip()
    reason = request.POST.get("rejection_reason", "").strip()
    valid = [s for s, _ in JobApplication.STATUS_CHOICES]
    if new_status not in valid:
        messages.error(request, "Invalid status.")
        return redirect("recruitment:school_application_detail", pk=pk)
    app.status = new_status
    app.rejection_reason = reason if new_status == "rejected" else app.rejection_reason
    app.reviewed_by = request.user
    app.reviewed_at = timezone.now()
    app.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at"])

    if new_status == "shortlisted":
        _send_email(
            subject=f"Application Update — {app.job.title} at {app.job.school.name}",
            body=(
                f"Dear {app.full_name},\n\n"
                f"Congratulations! Your application for '{app.job.title}' at {app.job.school.name} "
                f"has been shortlisted.\n\nRef: {app.reference}\n\n"
                f"You will be contacted shortly with further details.\n\nMastex Education Platform"
            ),
            recipients=[app.email],
        )
        _send_sms_notice(app.phone, f"Good news! Your application {app.reference} for {app.job.title} has been shortlisted.")
    elif new_status == "rejected":
        _send_email(
            subject=f"Application Outcome — {app.job.title} at {app.job.school.name}",
            body=(
                f"Dear {app.full_name},\n\n"
                f"Thank you for applying for '{app.job.title}' at {app.job.school.name}.\n"
                f"After careful consideration, we regret to inform you that your application has not been successful.\n"
                + (f"\nFeedback: {reason}\n" if reason else "")
                + f"\nWe wish you the best in your future endeavours.\n\nMastex Education Platform"
            ),
            recipients=[app.email],
        )
        _send_sms_notice(
            app.phone,
            f"Update on your application {app.reference} for {app.job.title} at {app.job.school.name}: your application was unsuccessful. Thank you for applying.",
        )
    elif new_status == "hired":
        _send_email(
            subject=f"Offer of Employment — {app.job.title} at {app.job.school.name}",
            body=(
                f"Dear {app.full_name},\n\n"
                f"We are delighted to inform you that you have been selected for the position of "
                f"'{app.job.title}' at {app.job.school.name}.\n\n"
                f"The school will contact you directly to finalise the terms of your engagement.\n\n"
                f"Ref: {app.reference}\n\nCongratulations!\n\nMastex Education Platform"
            ),
            recipients=[app.email],
        )
        _send_sms_notice(app.phone, f"Congratulations! You have been selected for {app.job.title} at {app.job.school.name}.")

    messages.success(request, f"Application status updated to '{new_status}'.")
    return redirect("recruitment:school_application_detail", pk=pk)


# ---------------------------------------------------------------------------
# SUPER ADMIN DASHBOARD
# ---------------------------------------------------------------------------

@login_required
def platform_dashboard(request):
    """Super admin: overview of all job postings and application revenue."""
    if not is_super_admin(request.user):
        messages.error(request, "Access denied.")
        return redirect("home")

    stats = {
        "total_jobs": JobPosting.objects.count(),
        "open_jobs": JobPosting.objects.filter(is_active=True, deadline__gte=timezone.now().date()).count(),
        "total_applications": JobApplication.objects.filter(payment_status="paid").count(),
        "total_revenue": JobApplication.objects.filter(payment_status="paid").aggregate(
            total=Sum("amount_paid")
        )["total"] or Decimal("0"),
        "total_hired": JobApplication.objects.filter(payment_status="paid", status="hired").count(),
    }

    recent_jobs = (
        JobPosting.objects.select_related("school")
        .annotate(app_count=Count("applications", filter=Q(applications__payment_status="paid")))
        .order_by("-created_at")[:15]
    )

    school_revenue = list(
        School.objects.filter(job_postings__isnull=False)
        .distinct()
        .annotate(
            jobs=Count("job_postings", distinct=True),
            apps=Count(
                "job_postings__applications",
                filter=Q(job_postings__applications__payment_status="paid"),
                distinct=True,
            ),
            revenue=Sum(
                "job_postings__applications__amount_paid",
                filter=Q(job_postings__applications__payment_status="paid"),
            ),
        )
        .order_by("-apps")
        .values("name", "jobs", "apps", "revenue")[:10]
    )

    return render(request, "recruitment/platform_dashboard.html", {
        "stats": stats,
        "recent_jobs": recent_jobs,
        "school_revenue": school_revenue,
    })
