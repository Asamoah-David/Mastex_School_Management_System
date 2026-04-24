import secrets

from django.core.validators import FileExtensionValidator
from django.db import models

from accounts.models import User
from schools.models import School
from students.models import Student

_DOC_EXT = ["pdf", "jpg", "jpeg", "png", "webp"]
_IMG_EXT = ["jpg", "jpeg", "png", "gif", "webp"]
_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "gif", "webp"]


class AdmissionApplication(models.Model):
    """Online admission applications from prospective students"""
    STATUS_CHOICES = (
        ("pending", "Pending review"),
        ("under_review", "Under review"),
        ("interview", "Interview / assessment"),
        ("documents_pending", "Documents pending"),
        ("offered", "Offer / provisional acceptance"),
        ("waitlisted", "Waitlisted"),
        ("withdrawn", "Withdrawn by applicant"),
        ("approved", "Approved / enrolled"),
        ("rejected", "Rejected"),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)  # School can be set if public form has school selection

    public_reference = models.CharField(
        max_length=20,
        unique=True,
        help_text="Shown to applicant for status tracking (not secret; do not use as password).",
    )
    
    # Student Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=[('male', 'Male'), ('female', 'Female')])
    previous_school = models.CharField(max_length=200, blank=True)
    class_applied_for = models.CharField(max_length=50)
    
    # Parent/Guardian Information
    parent_first_name = models.CharField(max_length=100)
    parent_last_name = models.CharField(max_length=100)
    parent_phone = models.CharField(max_length=20)
    parent_email = models.EmailField(blank=True)
    parent_occupation = models.CharField(max_length=100, blank=True)
    address = models.TextField()
    
    # Additional Information
    reason_for_applying = models.TextField(blank=True)
    medical_conditions = models.TextField(blank=True)
    how_did_you_hear = models.CharField(max_length=200, blank=True)
    
    birth_certificate = models.FileField(
        upload_to="admission_docs/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=_DOC_EXT)],
    )
    previous_report = models.FileField(
        upload_to="admission_docs/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=_DOC_EXT)],
    )
    passport_photo = models.ImageField(
        upload_to="admission_photos/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=_IMG_EXT)],
    )
    
    # Status and Tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    applied_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_applications")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # If approved, link to created student
    created_student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="admission_application")
    
    class Meta:
        ordering = ["-applied_at"]
        indexes = [
            models.Index(fields=["school", "status"], name="idx_admission_school_st"),
        ]

    @classmethod
    def allocate_public_reference(cls):
        for _ in range(64):
            ref = "ADM-" + secrets.token_hex(4).upper()
            if not cls.objects.filter(public_reference=ref).exists():
                return ref
        raise RuntimeError("Unable to allocate a unique admission reference")

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.class_applied_for} ({self.status})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Certificate(models.Model):
    """Academic certificates (completion, graduation, merit)"""
    CERTIFICATE_TYPES = (
        ('completion', 'Certificate of Completion'),
        ('graduation', 'Graduation Certificate'),
        ('merit', 'Merit Certificate'),
        ('attendance', 'Certificate of Attendance'),
        ('character', 'Certificate of Good Character'),
    )
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='certificates')
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    certificate_type = models.CharField(max_length=20, choices=CERTIFICATE_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    issued_date = models.DateField()
    academic_year = models.CharField(max_length=20)  # e.g., "2024/2025"
    term = models.CharField(max_length=50, blank=True)  # e.g., "Term 1"
    
    pdf = models.FileField(upload_to="certificates/%Y/%m/%d/", null=True, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="issued_certificates")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-issued_date"]
    
    def __str__(self):
        return f"{self.student} - {self.title} ({self.issued_date})"


class StudentIDCard(models.Model):
    """Student ID Card management"""
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name='id_card')
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    # Card numbers are unique per school, not globally: two schools may
    # legitimately reuse the same human-facing card number series.
    card_number = models.CharField(max_length=50)
    photo = models.ImageField(
        upload_to='id_cards/', null=True, blank=True,
        validators=[FileExtensionValidator(allowed_extensions=_IMAGE_EXTENSIONS)],
    )
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "card_number"],
                name="uniq_studentidcard_school_card_number",
            ),
        ]

    def __str__(self):
        return f"{self.student} - {self.card_number}"


class StaffIDCard(models.Model):
    """Staff ID Card management"""
    staff = models.OneToOneField(User, on_delete=models.CASCADE, related_name='id_card')
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    # See StudentIDCard: per-school uniqueness, not global.
    card_number = models.CharField(max_length=50)
    position = models.CharField(max_length=100, blank=True)
    photo = models.ImageField(
        upload_to='staff_id_cards/', null=True, blank=True,
        validators=[FileExtensionValidator(allowed_extensions=_IMAGE_EXTENSIONS)],
    )
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "card_number"],
                name="uniq_staffidcard_school_card_number",
            ),
        ]
    
    def __str__(self):
        return f"{self.staff.get_full_name()} - {self.card_number}"
