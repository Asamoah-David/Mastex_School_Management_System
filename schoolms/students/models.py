from django.db import models
from accounts.models import ACADEMIC_ROLES, User
from schools.models import School
from core.tenancy import SchoolScopedModel, SoftDeleteManager, UnscopedManager


class SchoolClass(SchoolScopedModel):
    """Structured class/section with capacity and class teacher."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)  # e.g. "Form 1A", "Primary 3B"
    capacity = models.PositiveIntegerField(default=40, blank=True, null=True)
    class_teacher = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="classes_taught",
        limit_choices_to={"role__in": list(ACADEMIC_ROLES)},
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("school", "name")
        verbose_name = "Class"
        verbose_name_plural = "Classes"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.school.name})"

    def student_count(self):
        return self.students.filter(deleted_at__isnull=True, status="active").count()

    @property
    def is_at_capacity(self) -> bool:
        if not self.capacity:
            return False
        return self.student_count() >= self.capacity

    @property
    def remaining_seats(self) -> int | None:
        if not self.capacity:
            return None
        return max(0, self.capacity - self.student_count())


class Student(models.Model):
    objects = SoftDeleteManager()
    all_with_deleted = UnscopedManager()

    STATUS_CHOICES = (
        ("active", "Active"),
        ("graduated", "Graduated / Alumni"),
        ("withdrawn", "Withdrawn / Transferred"),
        ("dismissed", "Dismissed / Expelled"),
        ("suspended", "Suspended"),
        ("deceased", "Deceased"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    admission_number = models.CharField(max_length=50)
    class_name = models.CharField(max_length=50, blank=True)
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="students",
    )
    parent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        limit_choices_to={"role": "parent"},
    )
    date_enrolled = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
        help_text="Use this instead of deleting students so history is preserved.",
    )
    exit_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the student left, graduated, or was dismissed.",
    )
    exit_reason = models.CharField(
        max_length=50,
        blank=True,
        help_text="Reason for exit: graduated, left, transferred, suspended, expelled, deceased",
    )
    exit_notes = models.TextField(
        blank=True,
        help_text="Additional notes about the exit",
    )

    deleted_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="Set when soft-deleted. Use restore() to undo. Hard delete via hard_delete().",
    )

    # Health Information
    blood_group = models.CharField(max_length=10, blank=True, null=True)  # e.g., "A+", "O-"
    allergies = models.TextField(blank=True, null=True)
    medical_conditions = models.TextField(blank=True, null=True)  # e.g., Asthma, Diabetes
    medications = models.TextField(blank=True, null=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True, null=True)
    doctor_phone = models.CharField(max_length=20, blank=True, null=True)
    last_medical_checkup = models.DateField(null=True, blank=True)
    medical_notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Student"
        verbose_name_plural = "Students"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "admission_number"],
                name="uniq_student_admission_number_per_school",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "class_name"], name="idx_student_school_class"),
            models.Index(fields=["school", "status"], name="idx_student_school_status"),
            models.Index(fields=["parent"], name="idx_student_parent"),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.admission_number})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.school_class_id and self.status == "active":
            try:
                sc = SchoolClass.objects.get(pk=self.school_class_id)
                if sc.capacity:
                    active_qs = Student.objects.filter(
                        school_class_id=self.school_class_id,
                        status="active",
                        deleted_at__isnull=True,
                    )
                    if self.pk:
                        active_qs = active_qs.exclude(pk=self.pk)
                    if active_qs.count() >= sc.capacity:
                        raise ValidationError(
                            {"school_class": f"Class '{sc.name}' is at full capacity ({sc.capacity} students)."}
                        )
            except SchoolClass.DoesNotExist:
                pass

    def delete(self, using=None, keep_parents=False):
        """Soft-delete: set deleted_at instead of removing the DB row."""
        from django.utils import timezone
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def hard_delete(self):
        """Permanently remove the row. Use only after confirming no historical dependencies."""
        super().delete()

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_active_student(self) -> bool:
        """
        Convenience flag combining the student record and linked user.
        """
        return self.status == "active" and bool(getattr(self.user, "is_active", True))


class StudentGuardian(SchoolScopedModel):
    """Multiple guardians / parents per student.

    Replaces (and extends) the legacy single ``Student.parent`` FK.
    The legacy FK is kept for backward compatibility but new code should
    use this model for all parent-student relationships.
    """

    RELATIONSHIP_CHOICES = (
        ("father", "Father"),
        ("mother", "Mother"),
        ("guardian", "Guardian"),
        ("step_parent", "Step Parent"),
        ("grandparent", "Grandparent"),
        ("sibling", "Sibling"),
        ("other", "Other"),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="student_guardians",
        help_text="Denormalised from student.school for efficient tenant-scoped queries.",
        null=True,
        blank=True,
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="guardians")
    guardian = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ward_relationships",
        limit_choices_to={"role": "parent"},
    )
    relationship = models.CharField(max_length=20, choices=RELATIONSHIP_CHOICES, default="guardian")
    is_primary = models.BooleanField(
        default=False,
        help_text="Primary guardian receives all notifications and fee alerts.",
    )
    can_pickup = models.BooleanField(default=True, help_text="Authorised to collect student from school.")
    emergency_contact = models.BooleanField(default=False, help_text="Listed as emergency contact.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Student Guardian"
        verbose_name_plural = "Student Guardians"
        unique_together = ("student", "guardian")
        indexes = [
            models.Index(fields=["guardian"], name="idx_stuguardian_guardian"),
            models.Index(fields=["student", "is_primary"], name="idx_stuguardian_primary"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(is_primary=True),
                name="uniq_stuguardian_one_primary_per_student",
            ),
        ]

    def __str__(self):
        return f"{self.guardian.get_full_name()} → {self.student} ({self.get_relationship_display()})"


class StudentClearance(models.Model):
    """Leaver checklist (fees, library, ID, discipline) before exit processing."""

    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name="clearance_record",
    )
    fees_cleared = models.BooleanField(default=False)
    library_cleared = models.BooleanField(default=False)
    id_card_returned = models.BooleanField(default=False)
    discipline_cleared = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "Student clearance"
        verbose_name_plural = "Student clearances"

    @property
    def is_complete(self) -> bool:
        return all(
            (
                self.fees_cleared,
                self.library_cleared,
                self.discipline_cleared,
                self.id_card_returned,
            )
        )

    def __str__(self):
        return f"Clearance · {self.student_id}"


class StudentAchievement(models.Model):
    """Track student achievements, awards, and activities"""
    ACHIEVEMENT_TYPES = (
        ('academic', 'Academic'),
        ('sports', 'Sports'),
        ('arts', 'Arts & Culture'),
        ('leadership', 'Leadership'),
        ('community', 'Community Service'),
        ('behavior', 'Behavior/Discipline'),
        ('other', 'Other'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="achievements")
    achievement_type = models.CharField(max_length=20, choices=ACHIEVEMENT_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date_achieved = models.DateField()
    awarded_by = models.CharField(max_length=100, blank=True)
    certificate_number = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_achieved"]

    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.title}"


class StudentActivity(models.Model):
    """Track extracurricular activities"""
    ACTIVITY_TYPES = (
        ('sports', 'Sports'),
        ('clubs', 'Clubs'),
        ('music', 'Music & Dance'),
        ('art', 'Art & Craft'),
        ('science', 'Science Club'),
        ('reading', 'Reading Club'),
        ('debate', 'Debate Club'),
        ('scout', 'Scouting/Guidance'),
        ('other', 'Other'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="activities")
    activity_name = models.CharField(max_length=100)
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    position = models.CharField(max_length=50, blank=True)  # Captain, Member, etc.
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.activity_name}"


class StudentDiscipline(models.Model):
    """Track behavior and discipline records"""
    INCIDENT_TYPES = (
        ('positive', 'Positive Behavior'),
        ('minor', 'Minor Infraction'),
        ('major', 'Major Infraction'),
        ('suspension', 'Suspension'),
        ('expulsion', 'Expulsion'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="discipline_records")
    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    incident_date = models.DateField()
    action_taken = models.TextField(blank=True)
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="reported_discipline")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-incident_date"]

    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.title}"


class AbsenceRequest(models.Model):
    """Student-requested permission to be absent from school."""

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="absence_requests")
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="absence_requests_submitted",
        help_text="Who submitted this request (student or parent).",
    )
    date = models.DateField(help_text="First day the student will be absent.")
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Last day absent (inclusive). Leave blank for a single day.",
    )
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="absence_requests_reviewed",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        end = self.end_date or self.date
        span = f"{self.date}" if end == self.date else f"{self.date}–{end}"
        return f"{self.student.user.get_full_name()} - {span} ({self.status})"


# ---------------------------------------------------------------------------
# F7 — Individual Learning Plan (IEP / SEN support)
# ---------------------------------------------------------------------------

class LearningPlan(SchoolScopedModel):
    """Student Individual Learning Plan for SEN / gifted / remedial support.

    Records goals, accommodations, and review dates.  Linked to the student
    record so that subject teachers, the SENCO, and parents share the same
    documented plan.
    """

    PLAN_TYPES = (
        ("sen", "Special Educational Needs (SEN)"),
        ("gifted", "Gifted & Talented"),
        ("remedial", "Remedial Support"),
        ("behavioural", "Behavioural Support Plan"),
        ("other", "Other"),
    )
    STATUS_CHOICES = (
        ("draft", "Draft"),
        ("active", "Active"),
        ("under_review", "Under Review"),
        ("completed", "Completed"),
        ("discontinued", "Discontinued"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="learning_plans")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="learning_plans")
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPES, default="sen")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft", db_index=True)
    academic_year = models.CharField(max_length=20, help_text="e.g. 2025/2026")
    start_date = models.DateField()
    review_date = models.DateField(null=True, blank=True, help_text="Scheduled next review date.")
    end_date = models.DateField(null=True, blank=True)
    goals = models.TextField(help_text="Specific, measurable learning goals for this plan period.")
    accommodations = models.TextField(
        blank=True,
        help_text="Classroom accommodations: extra time, seating, reader, etc.",
    )
    support_resources = models.TextField(blank=True, help_text="External or internal support: speech therapy, tutoring, etc.")
    progress_notes = models.TextField(blank=True, help_text="Ongoing teacher/SENCO progress notes.")
    parent_acknowledged = models.BooleanField(
        default=False,
        help_text="Set when parent/guardian has been briefed and agrees to the plan.",
    )
    parent_acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="learning_plans_created",
    )
    last_updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="learning_plans_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Learning Plan"
        verbose_name_plural = "Learning Plans"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "status"], name="idx_lplan_school_status"),
            models.Index(fields=["school", "student"], name="idx_lplan_school_student"),
            models.Index(fields=["school", "review_date"], name="idx_lplan_school_review"),
        ]

    def __str__(self):
        return f"{self.student} — {self.get_plan_type_display()} ({self.academic_year})"
