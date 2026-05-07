from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.tenancy import SchoolScopedModel, SchoolScopedManager, SchoolScopedQuerySet
from schools.models import School


# ---------------------------------------------------------------------------
# Soft-delete aware manager for OmrExam
# ---------------------------------------------------------------------------

class OmrExamQuerySet(SchoolScopedQuerySet):
    def delete(self):
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super(SchoolScopedQuerySet, self).delete()

    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def deleted(self):
        return self.filter(deleted_at__isnull=False)


class OmrExamManager(SchoolScopedManager):
    def get_queryset(self):
        return OmrExamQuerySet(self.model, using=self._db).alive()

    def for_school(self, school):
        return self.get_queryset().for_school(school)

    def all_with_deleted(self):
        return OmrExamQuerySet(self.model, using=self._db)


TEMPLATE_CHOICES = [
    ("basic_30_ad", "30 Questions (A–D)"),
    ("bece_60_ae", "60 Questions (A–E)"),
]


class OmrTemplateCalibration(SchoolScopedModel):
    """Per-school calibrated geometry + optional blank sheet for template subtraction."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="omr_template_calibrations")
    template_id = models.CharField(max_length=64, db_index=True)
    template_name = models.CharField(max_length=200, blank=True)
    calibrated_config = models.JSONField(default=dict, blank=True)
    blank_sheet = models.ImageField(upload_to="omr/blanks/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "OMR template calibration"
        verbose_name_plural = "OMR template calibrations"
        constraints = [
            models.UniqueConstraint(fields=["school", "template_id"], name="uniq_omr_calibration_school_template"),
        ]

    def __str__(self):
        return f"{self.template_id} @ {self.school_id}"


class OmrExam(SchoolScopedModel):
    """An OMR-marked exam session for a class/subject.

    Supports soft deletion: calling .delete() sets deleted_at rather than
    removing the row, preserving historical result data.  Use .hard_delete()
    to permanently remove.
    """

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="omr_exams")
    title = models.CharField(max_length=200)
    subject = models.CharField(max_length=100)
    class_name = models.CharField(max_length=100)
    date = models.DateField()
    template_type = models.CharField(max_length=50, choices=TEMPLATE_CHOICES)
    total_questions = models.PositiveIntegerField()
    answer_key = models.JSONField(null=True, blank=True)
    answer_key_confirmed = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="omr_exams_created",
    )
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OmrExamManager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "OMR Exam"
        verbose_name_plural = "OMR Exams"

    def __str__(self):
        return f"{self.title} — {self.class_name}"

    @property
    def result_count(self):
        return self.results.count()

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def has_answer_key(self):
        return bool(self.answer_key and self.answer_key_confirmed)


class OmrResult(SchoolScopedModel):
    """Per-student OMR marking result."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="omr_results")
    exam = models.ForeignKey(OmrExam, on_delete=models.CASCADE, related_name="results")

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="omr_results",
    )
    student_name = models.CharField(max_length=200, blank=True)
    class_name = models.CharField(max_length=100, blank=True)
    subject = models.CharField(max_length=100, blank=True)
    template_type = models.CharField(max_length=50, blank=True)

    detected_answers = models.JSONField(default=dict)
    raw_cv_answers = models.JSONField(default=dict, blank=True)
    cv_per_question = models.JSONField(default=dict, blank=True)
    answer_key = models.JSONField(default=dict)
    per_question_result = models.JSONField(default=dict)

    score = models.FloatField(default=0)
    total_questions = models.PositiveIntegerField(default=0)
    percentage = models.FloatField(default=0)
    correct_count = models.IntegerField(default=0)
    wrong_count = models.IntegerField(default=0)
    blank_count = models.IntegerField(default=0)
    multiple_answer_count = models.IntegerField(default=0)
    uncertain_count = models.IntegerField(default=0)

    flagged_questions = models.JSONField(default=list)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="omr_results_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-percentage", "student_name"]
        verbose_name = "OMR Result"
        verbose_name_plural = "OMR Results"

    def __str__(self):
        name = self.student_name or (self.student.user.get_full_name() if self.student else "Unknown")
        return f"{name} — {self.exam.title} — {self.score}/{self.total_questions}"

    def get_student_display_name(self):
        if self.student_name:
            return self.student_name
        if self.student:
            return self.student.user.get_full_name()
        return "Unknown Student"


class OmrExamSectionB(SchoolScopedModel):
    """Manual Section B marks for an OMR exam.

    Section A (objective) is marked automatically by OMR; Section B
    (theory / practical) is entered here by the teacher.
    The combined total = section_a_effective + section_b_score.
    """

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="omr_section_b_scores")
    exam = models.ForeignKey(OmrExam, on_delete=models.CASCADE, related_name="section_b_scores")
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="omr_section_b_scores",
    )
    student_name = models.CharField(
        max_length=200, blank=True,
        help_text="Used when student FK is not set (name-based matching).",
    )
    section_b_max_score = models.FloatField(default=40.0, help_text="Maximum marks for Section B.")
    section_b_score = models.FloatField(default=0.0)
    section_a_omr_score = models.FloatField(
        null=True, blank=True,
        help_text="Cached Section A score from OmrResult (auto-filled, read-only).",
    )
    section_a_max_score = models.FloatField(
        null=True, blank=True,
        help_text="Cached Section A max from OmrExam total_questions.",
    )
    section_a_override = models.FloatField(
        null=True, blank=True,
        help_text="Teacher correction of the OMR-detected Section A score.",
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="omr_section_b_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("exam", "student")]
        ordering = ["student_name"]
        verbose_name = "OMR Section B Score"
        verbose_name_plural = "OMR Section B Scores"
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "student_name"],
                condition=models.Q(student__isnull=True),
                name="uniq_omrsectionb_exam_name_nostu",
            ),
        ]

    def clean(self):
        super().clean()
        if self.student_id is None and not self.student_name.strip():
            raise ValidationError(
                {"student_name": "A student name is required when no student record is linked."}
            )

    def __str__(self):
        name = self.get_student_display_name()
        return f"{name} — {self.exam.title} Section B: {self.section_b_score}/{self.section_b_max_score}"

    def get_student_display_name(self):
        if self.student_name:
            return self.student_name
        if self.student:
            return self.student.user.get_full_name()
        return "Unknown Student"

    @property
    def section_a_effective(self):
        """Return the effective Section A score (override if set, else OMR result)."""
        if self.section_a_override is not None:
            return self.section_a_override
        return self.section_a_omr_score or 0.0

    @property
    def total_raw_score(self):
        return round(self.section_a_effective + self.section_b_score, 2)

    @property
    def total_max_score(self):
        return round((self.section_a_max_score or 0.0) + self.section_b_max_score, 2)

    @property
    def total_percentage(self):
        if self.total_max_score > 0:
            return round((self.total_raw_score / self.total_max_score) * 100, 1)
        return 0.0
