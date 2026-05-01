"""
Recruitment Portal Models
- JobPosting: school-scoped open position
- JobApplication: public applicant (no account), GHS 50 fee to platform
- InterviewSchedule: school-scheduled interview with notification
"""
from __future__ import annotations

import secrets
import uuid

from django.db import models
from django.utils import timezone

from schools.models import School
from core.tenancy import SchoolScopedModel


QUALIFICATION_CHOICES = (
    ("wassce", "WASSCE"),
    ("ssce", "SSCE"),
    ("diploma", "Diploma / HND"),
    ("degree", "Bachelor's Degree"),
    ("masters", "Master's Degree"),
    ("phd", "PhD / Doctorate"),
    ("professional", "Professional Certificate"),
    ("other", "Other"),
)

QUAL_RANK = {"wassce": 1, "ssce": 1, "diploma": 2, "degree": 3, "professional": 3, "masters": 4, "phd": 5, "other": 0}


def _gen_ref(prefix, cls):
    for _ in range(64):
        ref = f"{prefix}-{secrets.token_hex(4).upper()}"
        if not cls.objects.filter(reference_code=ref).exists():
            return ref
    raise RuntimeError(f"Unable to allocate unique reference for {prefix}")


def _gen_app_ref(cls):
    for _ in range(64):
        ref = f"APP-{secrets.token_hex(4).upper()}"
        if not cls.objects.filter(reference=ref).exists():
            return ref
    raise RuntimeError("Unable to allocate unique application reference")


class JobPosting(SchoolScopedModel):
    JOB_TYPES = (
        ("teacher", "Teacher"),
        ("hod", "Head of Department"),
        ("admin", "Administration Staff"),
        ("support", "Support Staff"),
        ("other", "Other"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="job_postings")
    reference_code = models.CharField(max_length=20, unique=True, editable=False)
    title = models.CharField(max_length=150, help_text="e.g. Mathematics Teacher, Deputy Head")
    job_type = models.CharField(max_length=20, choices=JOB_TYPES, default="teacher")
    subjects = models.CharField(max_length=255, blank=True, help_text="Relevant subjects, comma-separated")
    description = models.TextField(help_text="Full role description")
    requirements = models.TextField(help_text="Minimum qualifications and requirements")
    salary_range = models.CharField(max_length=100, blank=True, help_text="e.g. GHS 1,500 – 2,500 / month")
    min_qualification = models.CharField(
        max_length=20, choices=QUALIFICATION_CHOICES, blank=True,
        help_text="Minimum qualification required (leave blank for any)"
    )
    min_years_experience = models.PositiveSmallIntegerField(
        default=0, help_text="Minimum years of experience required (0 = any)"
    )
    slots_available = models.PositiveSmallIntegerField(default=1)
    application_fee = models.DecimalField(max_digits=10, decimal_places=2, default=50.00,
                                          help_text="Platform application fee in GHS (goes to Mastex platform)")
    deadline = models.DateField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_job_postings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "is_active", "deadline"], name="idx_jobposting_school_active"),
        ]

    def save(self, *args, **kwargs):
        if not self.reference_code:
            for _ in range(64):
                ref = f"JOB-{secrets.token_hex(4).upper()}"
                if not JobPosting.objects.filter(reference_code=ref).exists():
                    self.reference_code = ref
                    break
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.is_active and self.deadline >= timezone.now().date()

    @property
    def application_count(self):
        return self.applications.filter(payment_status="paid").count()

    def __str__(self):
        return f"{self.title} — {self.school.name}"


class JobApplication(models.Model):
    QUALIFICATION_CHOICES = QUALIFICATION_CHOICES
    PAYMENT_STATUS = (
        ("unpaid", "Unpaid"),
        ("paid", "Paid"),
    )
    STATUS_CHOICES = (
        ("pending_payment", "Pending Payment"),
        ("submitted", "Submitted"),
        ("shortlisted", "Shortlisted"),
        ("interview_scheduled", "Interview Scheduled"),
        ("rejected", "Rejected"),
        ("hired", "Hired"),
    )

    job = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name="applications")
    reference = models.CharField(max_length=20, unique=True, editable=False)

    # Applicant personal info
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    nationality = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=10, choices=[("male", "Male"), ("female", "Female"), ("other", "Other")], blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    # Professional info
    highest_qualification = models.CharField(max_length=20, choices=QUALIFICATION_CHOICES, default="degree")
    years_experience = models.PositiveSmallIntegerField(default=0)
    current_employer = models.CharField(max_length=200, blank=True)
    subjects_taught = models.CharField(max_length=255, blank=True, help_text="Subjects able to teach")
    cover_letter = models.TextField()
    cv_upload = models.FileField(
        upload_to="job_applications/cvs/", blank=True, null=True,
        help_text="CV/Resume (PDF, DOC, DOCX — max 5 MB)"
    )
    referees = models.TextField(
        blank=True,
        help_text="Names, positions and contact details of referees (2–3 recommended)"
    )

    # Payment (platform fee — no school subaccount)
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS, default="unpaid", db_index=True)
    paystack_reference = models.CharField(max_length=100, blank=True, db_index=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Workflow status
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="pending_payment", db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    # Review fields
    reviewed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_job_applications",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-applied_at"]
        indexes = [
            models.Index(fields=["job", "status"], name="idx_jobapp_job_status"),
            models.Index(fields=["job", "payment_status"], name="idx_jobapp_job_payment"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "email"],
                condition=models.Q(payment_status="paid"),
                name="uniq_paid_jobapp_job_email",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.reference:
            for _ in range(64):
                ref = f"APP-{secrets.token_hex(4).upper()}"
                if not JobApplication.objects.filter(reference=ref).exists():
                    self.reference = ref
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} → {self.job.title} ({self.reference})"


class InterviewSchedule(models.Model):
    MODE_CHOICES = (
        ("in_person", "In Person"),
        ("video_call", "Video Call"),
        ("phone", "Phone Interview"),
    )

    application = models.OneToOneField(
        JobApplication, on_delete=models.CASCADE, related_name="interview_schedule",
    )
    interview_date = models.DateField()
    interview_time = models.TimeField()
    mode = models.CharField(max_length=15, choices=MODE_CHOICES, default="in_person")
    location = models.CharField(max_length=300, blank=True, help_text="Physical address or 'Online'")
    meeting_link = models.URLField(blank=True, help_text="Zoom / Google Meet / Teams link")
    message_to_applicant = models.TextField(blank=True, help_text="Personal message included in the interview invitation")
    scheduled_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True,
        related_name="scheduled_interviews",
    )
    notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["interview_date", "interview_time"]

    def __str__(self):
        return f"Interview: {self.application.full_name} on {self.interview_date}"
