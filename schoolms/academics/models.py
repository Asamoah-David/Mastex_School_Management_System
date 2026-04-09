from django.db import models
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
    grade = models.CharField(max_length=5)  # A, B, C, D, F
    min_score = models.FloatField()
    max_score = models.FloatField()
    order = models.PositiveIntegerField(default=0)  # for sorting best to worst

    class Meta:
        ordering = ["-min_score"]
        unique_together = ("school", "grade")

    def __str__(self):
        return f"{self.grade} ({self.min_score}-{self.max_score})"


def get_grade_for_score(school, score, _boundaries=None):
    """Return grade from school's boundaries, or default if none configured.

    Uses Django's cache framework so the lookup is safe across multiple
    Gunicorn/ASGI workers (unlike a module-level dict).
    Accepts an optional pre-fetched list of boundaries to avoid repeated
    queries when grading many students in a loop.
    """
    if _boundaries is None:
        from django.core.cache import cache as _cache
        cache_key = f"grade_boundaries_{getattr(school, 'pk', school)}"
        boundaries = _cache.get(cache_key)
        if boundaries is None:
            boundaries = list(
                GradeBoundary.objects.filter(school=school).order_by("-min_score")
            )
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
    """DEPRECATED: Use students.SchoolClass instead. Kept for migration compatibility."""
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
    """DEPRECATED: Use operations.AssignmentSubmission instead. Kept for migration compat."""
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

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Result"
        verbose_name_plural = "Results"
        indexes = [
            models.Index(fields=["student", "term"], name="idx_result_student_term"),
            models.Index(fields=["student", "subject", "term"], name="idx_result_stu_subj_term"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "subject", "exam_type", "term"],
                name="uniq_result_stu_sub_exam_term",
            ),
        ]
    
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


class Timetable(models.Model):
    """Weekly timetable."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    class_name = models.CharField(max_length=50)
    school_class = models.ForeignKey(
        "students.SchoolClass", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="timetable_entries",
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='timetable_subjects')
    day_of_week = models.CharField(max_length=10)  # Monday, Tuesday, etc.
    start_time = models.TimeField()
    end_time = models.TimeField()
    venue = models.CharField(max_length=100, blank=True)
    
    class Meta:
        ordering = ['day_of_week', 'start_time']
        unique_together = ("school", "class_name", "day_of_week", "start_time")

    def __str__(self):
        return f"{self.class_name} - {self.subject} - {self.day_of_week}"


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
    passing_score = models.PositiveIntegerField(default=50)
    is_active = models.BooleanField(default=True)
    due_date = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title


class QuizQuestion(models.Model):
    """Quiz questions."""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=[
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('short_answer', 'Short Answer')
    ], default='multiple_choice')
    option_a = models.CharField(max_length=500, blank=True)
    option_b = models.CharField(max_length=500, blank=True)
    option_c = models.CharField(max_length=500, blank=True)
    option_d = models.CharField(max_length=500, blank=True)
    correct_answer = models.CharField(max_length=10)
    marks = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return self.question_text[:50]


class QuizAnswer(models.Model):
    """Quiz answer model (from migration)."""
    attempt = models.ForeignKey('QuizAttempt', on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE)
    answer = models.CharField(max_length=10)
    is_correct = models.BooleanField(default=False)
    marks_obtained = models.FloatField(default=0)
    
    def __str__(self):
        return f"Answer for {self.question}"


class QuizAttempt(models.Model):
    """Student quiz attempts."""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='quiz_attempts')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    is_passed = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=["student", "is_completed"], name="idx_quizatt_stu_done"),
        ]
    
    def __str__(self):
        return f"{self.student} - {self.quiz.title}"


# ==========================================
# COMPREHENSIVE ASSESSMENT MODELS
# ==========================================

class GradingPolicy(models.Model):
    """School grading policy settings."""
    school = models.OneToOneField(School, on_delete=models.CASCADE)
    use_custom_grades = models.BooleanField(default=False)
    pass_mark = models.FloatField(default=50.0)
    allows_decimal = models.BooleanField(default=True)
    max_score = models.FloatField(default=100.0)
    use_weighted_averages = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Grading Policy - {self.school.name}"


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
    
    def __str__(self):
        return f"{self.student} - {self.subject}: {self.score}/{self.max_score}"


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
    
    def __str__(self):
        return f"{self.student} - {self.subject}: {self.score}/{self.max_score}"


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
