from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from students.models import Student
from schools.models import School
from accounts.models import User

_DOCUMENT_EXTENSIONS = ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "jpg", "jpeg", "png", "gif"]


class ExamType(models.Model):
    """Exam types like Class Test, Term Exam, Mid-Term, etc."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Exam Type"
        verbose_name_plural = "Exam Types"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Term(models.Model):
    """Academic terms like Term 1, Term 2, Term 3."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    is_current = models.BooleanField(default=False)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-is_current", "-id"]
        verbose_name = "Term"
        verbose_name_plural = "Terms"
        constraints = [
            models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(is_current=True),
                name="unique_current_term_per_school",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_current:
            Term.objects.filter(school=self.school, is_current=True).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)


class Subject(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"
        ordering = ["name"]

    def __str__(self):
        return self.name


class GradeBoundary(models.Model):
    """Configurable grade boundaries per school (e.g. A=80-100, B=70-79)."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    term = models.ForeignKey(
        "Term", on_delete=models.CASCADE, null=True, blank=True,
        help_text="Leave blank for the school-wide default scale; set to override for a specific term.",
    )
    grade = models.CharField(max_length=5)  # A, B, C, D, F
    min_score = models.FloatField()
    max_score = models.FloatField()
    order = models.PositiveIntegerField(default=0)  # for sorting best to worst

    class Meta:
        ordering = ["-min_score"]
        unique_together = ("school", "term", "grade")

    def clean(self):
        super().clean()
        if self.min_score < 0 or self.max_score < 0:
            raise ValidationError("Grade boundaries cannot be negative.")
        if self.min_score > self.max_score:
            raise ValidationError("Grade boundary min_score cannot exceed max_score.")
        if self.max_score > 100:
            raise ValidationError("Grade boundary max_score cannot exceed 100.")

    def save(self, *args, **kwargs):
        # Keep stable precision while retaining FloatField compatibility.
        self.min_score = round(float(self.min_score), 2)
        self.max_score = round(float(self.max_score), 2)
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.grade} ({self.min_score}-{self.max_score})"


def get_grade_for_score(school, score, _boundaries=None, term=None):
    """Return grade from school's boundaries, or default if none configured.

    Uses Django's cache framework so the lookup is safe across multiple
    Gunicorn/ASGI workers (unlike a module-level dict).
    Accepts an optional pre-fetched list of boundaries to avoid repeated
    queries when grading many students in a loop.
    When *term* is provided, term-specific boundaries take precedence over
    the school-wide default scale.
    """
    if _boundaries is None:
        from django.core.cache import cache as _cache
        term_pk = getattr(term, "pk", term) if term else None
        cache_key = f"grade_boundaries_{getattr(school, 'pk', school)}_{term_pk or 'default'}"
        boundaries = _cache.get(cache_key)
        if boundaries is None:
            qs = GradeBoundary.objects.filter(school=school)
            if term_pk:
                term_boundaries = list(qs.filter(term_id=term_pk).order_by("-min_score"))
                boundaries = term_boundaries if term_boundaries else list(qs.filter(term__isnull=True).order_by("-min_score"))
            else:
                boundaries = list(qs.filter(term__isnull=True).order_by("-min_score"))
                if not boundaries:
                    boundaries = list(qs.order_by("-min_score"))
            _cache.set(cache_key, boundaries, 300)
    else:
        boundaries = _boundaries

    for gb in boundaries:
        if gb.min_score <= score <= gb.max_score:
            return gb.grade
    if score >= 80:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 60:
        return "C"
    elif score >= 50:
        return "D"
    return "F"


def clear_grade_cache(school=None):
    """Clear the grade boundary cache (call after grade config changes)."""
    from django.core.cache import cache as _cache
    if school:
        _cache.delete(f"grade_boundaries_{getattr(school, 'pk', school)}")
    else:
        _cache.clear()


@receiver(post_save, sender=GradeBoundary)
@receiver(post_delete, sender=GradeBoundary)
def _grade_boundary_cache_invalidator(sender, instance, **kwargs):
    """Ensure cached grading scales refresh immediately after edits."""
    if instance and instance.school_id:
        clear_grade_cache(instance.school)


def bulk_annotate_grades(results, school):
    """Pre-compute ``.grade_cached`` on a list/queryset of Result objects.

    Uses a single boundary cache lookup for the school, then applies it to
    every result.  Templates can then use ``{{ r.grade_cached }}`` (or the
    existing ``{{ r.grade }}`` property still works as a fallback).
    """
    from django.core.cache import cache as _cache
    cache_key = f"grade_boundaries_{getattr(school, 'pk', school)}"
    boundaries = _cache.get(cache_key)
    if boundaries is None:
        boundaries = list(
            GradeBoundary.objects.filter(school=school).order_by("-min_score")
        )
        _cache.set(cache_key, boundaries, 300)
    for r in results:
        r.grade_cached = get_grade_for_score(school, r.percentage, _boundaries=boundaries)
    return results


# ==========================================
# NEW MODELS FOR COMPREHENSIVE GRADING SYSTEM
# ==========================================

class AssessmentType(models.Model):
    """
    Types of Continuous Assessment (CA) activities.
    Examples: Class Exercise, Assignment, Project, Quiz, Homework
    """
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)  # e.g., "Class Exercise", "Assignment", "Project", "Quiz", "Homework"
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = "Assessment Types"
        ordering = ["name"]
    
    def __str__(self):
        return self.name


class StudentClass(models.Model):
    """
    DEPRECATED — do not use in new code.
    Use students.SchoolClass instead. Retained only so existing migrations do not break.
    Will be removed in a future release once all references are purged.
    """
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    level = models.PositiveIntegerField()
    
    class Meta:
        ordering = ["level"]
        unique_together = ("school", "name")
        managed = True
    
    def __str__(self):
        return self.name


class Homework(models.Model):
    """Homework/Assignment model."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    class_name = models.CharField(max_length=50, blank=True)
    school_class = models.ForeignKey(
        "students.SchoolClass", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="homework_set",
    )
    due_date = models.DateTimeField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='homework_created')
    created_at = models.DateTimeField(auto_now_add=True)
    attachment = models.FileField(
        upload_to='homework/', null=True, blank=True,
        validators=[FileExtensionValidator(allowed_extensions=_DOCUMENT_EXTENSIONS)],
    )

    class Meta:
        ordering = ['-due_date']
        indexes = [
            models.Index(fields=["school", "class_name"], name="idx_hw_school_class"),
            models.Index(fields=["school", "due_date"], name="idx_hw_school_due"),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.subject.name}"


class HomeworkSubmission(models.Model):
    """
    DEPRECATED — do not use in new code.
    Use operations.AssignmentSubmission instead. Retained only for migration compat.
    Will be removed in a future release once all references are purged.
    """
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE, related_name='academic_submissions')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='homework_submissions')
    submission_text = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to='submissions/', null=True, blank=True,
        validators=[FileExtensionValidator(allowed_extensions=_DOCUMENT_EXTENSIONS)],
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    grade = models.CharField(max_length=10, blank=True)
    feedback = models.TextField(blank=True)
    
    class Meta:
        unique_together = ("homework", "student")
        ordering = ['-submitted_at']
    
    def __str__(self):
        return f"{self.student} - {self.homework.title}"


class Result(models.Model):
    """Student exam/test results."""
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True,
        help_text="Denormalised from student.school for efficient school-scoped queries.",
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='results')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    exam_type = models.ForeignKey(ExamType, on_delete=models.SET_NULL, null=True)
    term = models.ForeignKey(Term, on_delete=models.CASCADE, null=True, blank=True)
    score = models.FloatField()
    total_score = models.FloatField(default=100)
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Only published results are visible to students/parents.",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results_published",
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Result"
        verbose_name_plural = "Results"
        indexes = [
            models.Index(fields=["student", "term"], name="idx_result_student_term"),
            models.Index(fields=["student", "subject", "term"], name="idx_result_stu_subj_term"),
            models.Index(fields=["school", "term"], name="idx_result_school_term"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "subject", "exam_type", "term"],
                name="uniq_result_stu_sub_exam_term",
            ),
            models.CheckConstraint(
                check=models.Q(score__gte=0),
                name="chk_result_score_nonneg",
            ),
            models.CheckConstraint(
                check=models.Q(total_score__gt=0),
                name="chk_result_total_score_pos",
            ),
        ]

    def clean(self):
        super().clean()
        if self.total_score <= 0:
            raise ValidationError({"total_score": "Total score must be greater than 0."})
        if self.score < 0:
            raise ValidationError({"score": "Score cannot be negative."})
        if self.score > self.total_score:
            raise ValidationError({"score": "Score cannot exceed total_score."})

    def save(self, *args, **kwargs):
        if not self.school_id and self.student_id:
            try:
                self.school_id = self.student.school_id
            except Exception:
                pass
        self.score = round(float(self.score), 2)
        self.total_score = round(float(self.total_score), 2)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.student} - {self.subject}: {self.score}/{self.total_score}"
    
    @property
    def percentage(self):
        if self.total_score > 0:
            return round((self.score / self.total_score) * 100, 1)
        return 0
    
    @property
    def grade(self):
        if hasattr(self, "grade_cached"):
            return self.grade_cached
        return get_grade_for_score(self.student.school, self.percentage)


class ExamSchedule(models.Model):
    """Exam timetable."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE, null=True, blank=True)
    class_name = models.CharField(max_length=50, blank=True, default='')
    school_class = models.ForeignKey(
        "students.SchoolClass", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="exam_schedules",
    )
    exam_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    venue = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['exam_date', 'start_time']
    
    def __str__(self):
        return f"{self.subject} - {self.exam_date}"

    def clean(self):
        super().clean()
        if self.school_id and self.subject_id and getattr(self.subject, "school_id", None) != self.school_id:
            raise ValidationError({"subject": "Subject must belong to the same school as the exam schedule."})
        if self.school_id and self.term_id and getattr(self.term, "school_id", None) != self.school_id:
            raise ValidationError({"term": "Term must belong to the same school as the exam schedule."})
        if self.school_id and self.school_class_id and getattr(self.school_class, "school_id", None) != self.school_id:
            raise ValidationError({"school_class": "Class must belong to the same school as the exam schedule."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Timetable(models.Model):
    """Weekly timetable."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    class_name = models.CharField(max_length=50)
    school_class = models.ForeignKey(
        "students.SchoolClass", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="timetable_entries",
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="timetable_subjects",
    )
    day_of_week = models.CharField(max_length=10)  # Monday, Tuesday, etc.
    start_time = models.TimeField()
    end_time = models.TimeField()
    venue = models.CharField(max_length=100, blank=True)
    
    class Meta:
        ordering = ['day_of_week', 'start_time']
        unique_together = ("school", "class_name", "day_of_week", "start_time")

    def __str__(self):
        return f"{self.class_name} - {self.subject} - {self.day_of_week}"

    def clean(self):
        super().clean()
        if self.school_id and self.subject_id and getattr(self.subject, "school_id", None) != self.school_id:
            raise ValidationError({"subject": "Subject must belong to the same school as the timetable entry."})
        if self.school_id and self.teacher_id and getattr(self.teacher, "school_id", None) not in (None, self.school_id):
            raise ValidationError({"teacher": "Teacher must belong to the same school as the timetable entry."})
        if self.school_id and self.school_class_id and getattr(self.school_class, "school_id", None) != self.school_id:
            raise ValidationError({"school_class": "Class must belong to the same school as the timetable entry."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Quiz(models.Model):
    """Online quiz model."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    class_name = models.CharField(max_length=50)
    school_class = models.ForeignKey(
        "students.SchoolClass", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="quizzes",
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.SET_NULL, null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=30)
    passing_score = models.PositiveIntegerField(
        default=50,
        help_text="Minimum percentage (0–100) to pass.",
    )
    max_attempts_per_student = models.PositiveSmallIntegerField(
        default=1,
        help_text="How many times each student may complete this quiz.",
    )
    is_active = models.BooleanField(default=True)
    due_date = models.DateTimeField(null=True, blank=True)
    start_time = models.DateTimeField(
        null=True, blank=True,
        help_text="Optional open window start. If blank, quiz is open immediately when active.",
    )
    show_results_immediately = models.BooleanField(
        default=True,
        help_text="Show score and correct answers to students right after submission.",
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title


class QuizQuestion(models.Model):
    """Quiz questions."""
    QUESTION_TYPES = [
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('short_answer', 'Short Answer'),
        ('essay', 'Essay'),
        ('multi_select', 'Multi-Select (Checkboxes)'),
        ('dropdown', 'Dropdown'),
        ('matching', 'Matching'),
    ]
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='multiple_choice')
    option_a = models.CharField(max_length=500, blank=True)
    option_b = models.CharField(max_length=500, blank=True)
    option_c = models.CharField(max_length=500, blank=True)
    option_d = models.CharField(max_length=500, blank=True)
    option_e = models.CharField(max_length=500, blank=True)
    option_f = models.CharField(max_length=500, blank=True)
    correct_answer = models.CharField(
        max_length=500, blank=True,
        help_text="A–D for MCQ/T-F/dropdown; comma-separated for multi_select (e.g. A,C); JSON pairs for matching.",
    )
    match_left = models.TextField(
        blank=True,
        help_text="Pipe-separated left-side items for matching questions.",
    )
    match_right = models.TextField(
        blank=True,
        help_text="Pipe-separated right-side items for matching questions.",
    )
    penalty = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Marks deducted per wrong selected answer for multi_select (0 = no penalty).",
    )
    marks = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return self.question_text[:50]


class QuizAnswer(models.Model):
    """Quiz answer model."""
    attempt = models.ForeignKey('QuizAttempt', on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE)
    answer = models.TextField(blank=True)  # expanded for essays and matching JSON
    is_correct = models.BooleanField(default=False)
    marks_obtained = models.FloatField(default=0)
    teacher_reviewed = models.BooleanField(
        default=True,
        help_text="False for essay answers until a teacher enters marks.",
    )

    class Meta:
        unique_together = ("attempt", "question")

    def __str__(self):
        return f"Answer for {self.question}"


class QuizAttempt(models.Model):
    """Student quiz attempts."""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='quiz_attempts')
    attempt_number = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    is_passed = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    tab_blur_count = models.PositiveIntegerField(
        default=0,
        help_text="How often the quiz tab lost visibility during this attempt (honesty signal).",
    )

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=["student", "is_completed"], name="idx_quizatt_stu_done"),
        ]

    def clean(self):
        super().clean()
        if self.score is not None:
            if self.score < 0 or self.score > 100:
                raise ValidationError({"score": "Quiz score must be between 0 and 100."})

    def save(self, *args, **kwargs):
        if self.score is not None:
            self.score = round(float(self.score), 2)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.student} - {self.quiz.title}"


# ==========================================
# COMPREHENSIVE ASSESSMENT MODELS
# ==========================================

class GradingPolicy(models.Model):
    """School grading policy settings.
    Supports both the legacy OneToOne relationship and the newer per-school
    named policies with CA/Exam weight splitting.
    """
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='grading_policies')
    name = models.CharField(max_length=100, default='Default Policy')
    # CA vs Exam weighting (must sum to 100)
    ca_weight = models.FloatField(default=50.0, help_text="Continuous Assessment weight %")
    exam_weight = models.FloatField(default=50.0, help_text="End-of-term Exam weight %")
    is_default = models.BooleanField(default=False)
    # Legacy fields kept for backward compatibility
    use_custom_grades = models.BooleanField(default=False)
    pass_mark = models.FloatField(default=50.0)
    allows_decimal = models.BooleanField(default=True)
    max_score = models.FloatField(default=100.0)
    use_weighted_averages = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Grading Policy"
        verbose_name_plural = "Grading Policies"

    def clean(self):
        super().clean()
        if self.ca_weight < 0 or self.exam_weight < 0:
            raise ValidationError("CA and exam weights cannot be negative.")
        total = round(float(self.ca_weight) + float(self.exam_weight), 4)
        if total != 100.0:
            raise ValidationError(
                {"ca_weight": "CA and exam weights must sum to 100.", "exam_weight": "CA and exam weights must sum to 100."}
            )
        if self.max_score <= 0:
            raise ValidationError({"max_score": "Maximum score must be greater than 0."})
        if self.pass_mark < 0 or self.pass_mark > self.max_score:
            raise ValidationError({"pass_mark": "Pass mark must be between 0 and max_score."})

    def __str__(self):
        return f"{self.name} – {self.school.name}"

    @classmethod
    def get_active_policy(cls, school):
        """Return the default grading policy for a school, creating one if needed."""
        policy = cls.objects.filter(school=school, is_default=True).first()
        if not policy:
            policy = cls.objects.filter(school=school).first()
        if not policy:
            policy = cls.objects.create(
                school=school,
                name='Default Policy',
                ca_weight=50.0,
                exam_weight=50.0,
                is_default=True,
            )
        return policy


class GradePoint(models.Model):
    """Grade point values for GPA calculation."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    grade = models.CharField(max_length=5, choices=[
        ('A+', 'A+'), ('A', 'A'), ('A-', 'A-'),
        ('B+', 'B+'), ('B', 'B'), ('B-', 'B-'),
        ('C+', 'C+'), ('C', 'C'), ('C-', 'C-'),
        ('D+', 'D+'), ('D', 'D'), ('D-', 'D-'),
        ('F', 'F'),
    ])
    min_score = models.FloatField()
    max_score = models.FloatField()
    point_value = models.FloatField()
    scale = models.CharField(max_length=5, choices=[('5.0', '5.0 Scale'), ('4.0', '4.0 Scale')], default='5.0')
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ['-min_score']
        unique_together = [('school', 'grade', 'scale')]

    def __str__(self):
        return f"{self.grade} ({self.point_value}) – {self.school.name}"


def get_grade_point_value(school, score, scale='5.0'):
    """Return numeric grade point for a score on the given scale."""
    points = list(GradePoint.objects.filter(school=school, scale=scale).order_by('-min_score'))
    for gp in points:
        if gp.min_score <= score <= gp.max_score:
            return gp.point_value
    # Default 5.0-scale fallback
    if score >= 90: return 5.0
    if score >= 80: return 4.5
    if score >= 70: return 4.0
    if score >= 60: return 3.0
    if score >= 50: return 2.0
    return 0.0


class AssessmentScore(models.Model):
    """Individual assessment scores (CA components)."""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='assessment_scores')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    assessment_type = models.ForeignKey(AssessmentType, on_delete=models.CASCADE)
    score = models.FloatField()
    max_score = models.FloatField(default=100.0)
    date = models.DateField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)

    class Meta:
        ordering = ['-date']
        verbose_name = 'Assessment Score'
        verbose_name_plural = 'Assessment Scores'
        indexes = [
            models.Index(fields=["student", "subject", "term"], name="idx_ascore_stu_sub_term"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(score__gte=0), name="chk_ascore_score_nonneg"),
            models.CheckConstraint(check=models.Q(max_score__gt=0), name="chk_ascore_max_pos"),
        ]

    def __str__(self):
        return f"{self.student} - {self.subject}: {self.score}/{self.max_score}"

    @property
    def normalized_score(self):
        """Score normalised to 0-100 scale."""
        if self.max_score and self.max_score > 0:
            return round((self.score / self.max_score) * 100, 2)
        return 0.0


class ExamScore(models.Model):
    """End of term exam scores."""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_scores')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    score = models.FloatField()
    max_score = models.FloatField(default=100.0)
    date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    exam_type = models.ForeignKey(ExamType, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Exam Score'
        verbose_name_plural = 'Exam Scores'
        unique_together = [('student', 'subject', 'term')]
        constraints = [
            models.CheckConstraint(check=models.Q(score__gte=0), name="chk_exscore_score_nonneg"),
            models.CheckConstraint(check=models.Q(max_score__gt=0), name="chk_exscore_max_pos"),
        ]

    def __str__(self):
        return f"{self.student} - {self.subject}: {self.score}/{self.max_score}"

    @property
    def normalized_score(self):
        """Score normalised to 0-100 scale."""
        if self.max_score and self.max_score > 0:
            return round((self.score / self.max_score) * 100, 2)
        return 0.0


class StudentResultSummary(models.Model):
    """Computed result summary per student/subject/term."""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='result_summaries')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    ca_score = models.FloatField(default=0)
    exam_score = models.FloatField(default=0)
    final_score = models.FloatField(default=0)
    grade = models.CharField(max_length=5, blank=True)
    grade_point = models.FloatField(default=0)
    term_position = models.PositiveIntegerField(null=True, blank=True)
    cumulative_position = models.PositiveIntegerField(null=True, blank=True)
    gpa = models.FloatField(default=0)
    cumulative_gpa = models.FloatField(default=0)
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['term', 'student']
        verbose_name = 'Student Result Summary'
        verbose_name_plural = 'Student Result Summaries'
        unique_together = [('student', 'subject', 'term')]

    def __str__(self):
        return f"{self.student} – {self.subject} – {self.term}: {self.final_score}"


# ==========================================
# ONLINE MEETING MODELS
# ==========================================

class OnlineMeeting(models.Model):
    """Model for storing online class meeting information."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='online_meetings')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    subject = models.CharField(max_length=100, blank=True)
    class_name = models.CharField(max_length=50, blank=True)
    school_class = models.ForeignKey(
        "students.SchoolClass", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="online_meetings",
    )
    target_audience = models.CharField(max_length=20, choices=[
        ('students', 'Students Only'),
        ('staff', 'Staff Only'),
        ('all', 'All Users')
    ], default='all')
    scheduled_time = models.DateTimeField()
    duration = models.PositiveIntegerField(default=60)  # minutes
    meeting_link = models.URLField(blank=True)
    meeting_id = models.CharField(max_length=100, blank=True)
    host_url = models.URLField(blank=True)
    recording_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=[
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], default='scheduled')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_time']
        indexes = [
            models.Index(fields=["school", "scheduled_time"], name="idx_meeting_school_time"),
        ]

    def __str__(self):
        return f"{self.title} - {self.scheduled_time.strftime('%Y-%m-%d %H:%M')}"

    @property
    def get_time_until(self):
        """Return human-readable time until meeting."""
        from django.utils import timezone
        now = timezone.now()
        if self.scheduled_time > now:
            diff = self.scheduled_time - now
            days = diff.days
            hours = diff.seconds // 3600
            minutes = (diff.seconds % 3600) // 60
            if days > 0:
                return f"in {days}d {hours}h"
            elif hours > 0:
                return f"in {hours}h {minutes}m"
            else:
                return f"in {minutes}m"
        return "Started"


class AIStudentComment(models.Model):
    """Model for storing AI-generated student comments."""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='ai_comments')
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    term = models.CharField(max_length=50)
    academic_year = models.CharField(max_length=20)
    comment_type = models.CharField(max_length=20, choices=[
        ('academic', 'Academic Performance'),
        ('behavioral', 'Behavioral'),
        ('overall', 'Overall Summary')
    ])
    tone = models.CharField(max_length=20, choices=[
        ('encouraging', 'Encouraging'),
        ('professional', 'Professional'),
        ('detailed', 'Detailed'),
        ('concise', 'Concise')
    ], default='professional')
    content = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='generated_comments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'AI Student Comment'
        verbose_name_plural = 'AI Student Comments'

    def __str__(self):
        return f"Comment for {self.student} - {self.term}"
