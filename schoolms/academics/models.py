from django.db import models
from students.models import Student
from schools.models import School
from accounts.models import User


class ExamType(models.Model):
    """Exam types like Class Test, Term Exam, Mid-Term, etc."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)  # e.g., "Class Test", "Term Exam"
    
    def __str__(self):
        return self.name


class Term(models.Model):
    """Academic terms like Term 1, Term 2, Term 3."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)  # e.g., "Term 1", "Term 2"
    is_current = models.BooleanField(default=False)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        # If this term is being set as current, uncheck all other terms for this school
        if self.is_current:
            Term.objects.filter(school=self.school, is_current=True).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)
    
    class Meta:
        ordering = ["-is_current", "-id"]


class Subject(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

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


def get_grade_for_score(school, score):
    """Return grade from school's boundaries, or default if none configured."""
    boundaries = GradeBoundary.objects.filter(school=school).order_by("-min_score")
    for gb in boundaries:
        if gb.min_score <= score <= gb.max_score:
            return gb.grade
    # Default fallback
    if score >= 80:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 60:
        return "C"
    elif score >= 50:
        return "D"
    return "F"


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


class GradingPolicy(models.Model):
    """
    School-specific grading policy that defines weights for CA and Exam.
    Default: 50% CA + 50% Exam, but can be configured.
    """
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, default="Default Policy")
    ca_weight = models.FloatField(default=50.0)  # Percentage for Continuous Assessment
    exam_weight = models.FloatField(default=50.0)  # Percentage for Exam
    is_default = models.BooleanField(default=False)  # Only one default per school
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ("school", "is_default")
    
    def __str__(self):
        return f"{self.name} ({self.ca_weight}% CA + {self.exam_weight}% Exam)"
    
    def save(self, *args, **kwargs):
        # Ensure only one default policy per school
        if self.is_default:
            GradingPolicy.objects.filter(school=self.school, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active_policy(cls, school):
        """Get the active grading policy for a school."""
        policy = cls.objects.filter(school=school, is_default=True).first()
        if not policy:
            # Create default policy if none exists
            policy = cls.objects.create(
                school=school,
                name="Default Policy",
                ca_weight=50.0,
                exam_weight=50.0,
                is_default=True
            )
        return policy


class GradePoint(models.Model):
    """
    Maps grades to point values for GPA calculation.
    Default 5.0 scale: A=5.0, B=4.0, C=3.0, D=2.0, F=0
    """
    GRADE_CHOICES = [
        ('A+', 'A+'),
        ('A', 'A'),
        ('A-', 'A-'),
        ('B+', 'B+'),
        ('B', 'B'),
        ('B-', 'B-'),
        ('C+', 'C+'),
        ('C', 'C'),
        ('C-', 'C-'),
        ('D+', 'D+'),
        ('D', 'D'),
        ('D-', 'D-'),
        ('F', 'F'),
    ]
    SCALE_CHOICES = [
        ('5.0', '5.0 Scale'),
        ('4.0', '4.0 Scale'),
    ]
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    grade = models.CharField(max_length=5, choices=GRADE_CHOICES)
    min_score = models.FloatField()  # Minimum score for this grade
    max_score = models.FloatField()  # Maximum score for this grade
    point_value = models.FloatField()  # GPA point value (e.g., 5.0 for A)
    scale = models.CharField(max_length=5, choices=SCALE_CHOICES, default='5.0')
    is_default = models.BooleanField(default=False)
    
    class Meta:
        ordering = ["-min_score"]
        unique_together = ("school", "grade", "scale")
    
    def __str__(self):
        return f"{self.grade} ({self.min_score}-{self.max_score}) = {self.point_value} pts"


def get_grade_point_value(school, score, scale='5.0'):
    """
    Return the grade point value for a given score.
    Falls back to default 5.0 scale if no custom configuration exists.
    """
    try:
        gp = GradePoint.objects.filter(
            school=school, 
            scale=scale,
            min_score__lte=score,
            max_score__gte=score
        ).first()
        if gp:
            return gp.point_value
    except Exception:
        pass
    
    # Default 5.0 scale fallback
    if score >= 90:
        return 5.0  # A+
    elif score >= 80:
        return 5.0  # A
    elif score >= 70:
        return 4.0  # B
    elif score >= 60:
        return 3.0  # C
    elif score >= 50:
        return 2.0  # D
    return 0.0  # F


class AssessmentScore(models.Model):
    """
    Individual Continuous Assessment (CA) scores.
    Examples: Class Exercise (85), Assignment (90), Project (88)
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    assessment_type = models.ForeignKey(AssessmentType, on_delete=models.CASCADE)
    score = models.FloatField()  # Score out of 100
    max_score = models.FloatField(default=100.0)  # Maximum possible score
    date = models.DateField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-date"]
        verbose_name = "Assessment Score"
        verbose_name_plural = "Assessment Scores"
    
    def __str__(self):
        return f"{self.student} - {self.subject} - {self.assessment_type}: {self.score}"
    
    @property
    def normalized_score(self):
        """Return score as percentage (0-100)"""
        if self.max_score > 0:
            return (self.score / self.max_score) * 100
        return 0


class ExamScore(models.Model):
    """
    Final exam scores for each subject/term.
    This is separate from AssessmentScore to allow clear distinction.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    score = models.FloatField()  # Score out of 100
    max_score = models.FloatField(default=100.0)
    exam_type = models.ForeignKey(ExamType, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ("student", "subject", "term")
        verbose_name = "Exam Score"
        verbose_name_plural = "Exam Scores"
    
    def __str__(self):
        return f"{self.student} - {self.subject} ({self.term}): {self.score}"
    
    @property
    def normalized_score(self):
        """Return score as percentage (0-100)"""
        if self.max_score > 0:
            return (self.score / self.max_score) * 100
        return 0


class StudentResultSummary(models.Model):
    """
    Cached summary of student results for a specific term.
    Contains calculated fields: CA score, Exam score, Final score, Grade, GPA, Position.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    
    # Raw scores
    ca_score = models.FloatField(default=0)  # Calculated from AssessmentScore
    exam_score = models.FloatField(default=0)  # From ExamScore
    final_score = models.FloatField(default=0)  # Weighted final score
    
    # Grade info
    grade = models.CharField(max_length=5, blank=True)
    grade_point = models.FloatField(default=0)  # For GPA calculation
    
    # Position tracking
    term_position = models.PositiveIntegerField(null=True, blank=True)  # Position in class for this term
    cumulative_position = models.PositiveIntegerField(null=True, blank=True)  # Position across all terms
    
    # Calculated fields
    gpa = models.FloatField(default=0)  # Grade Point Average for the term
    cumulative_gpa = models.FloatField(default=0)  # Cumulative GPA across all terms
    
    # Timestamps
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ("student", "subject", "term")
        ordering = ["term", "student"]
        verbose_name = "Student Result Summary"
        verbose_name_plural = "Student Result Summaries"
    
    def __str__(self):
        return f"{self.student} - {self.subject} ({self.term}): Final={self.final_score}, Grade={self.grade}"
    
    @classmethod
    def calculate_ca_score(cls, student, subject, term):
        """Calculate the average CA score from all assessments."""
        from django.db.models import Avg
        assessments = AssessmentScore.objects.filter(
            student=student,
            subject=subject,
            term=term
        )
        if assessments.exists():
            # Average of normalized scores
            total = sum(a.normalized_score for a in assessments)
            return total / assessments.count()
        return 0
    
    @classmethod
    def calculate_final_score(cls, student, subject, term, policy=None):
        """Calculate final score using grading policy weights."""
        school = student.school
        if policy is None:
            policy = GradingPolicy.get_active_policy(school)
        
        ca = cls.calculate_ca_score(student, subject, term)
        exam = 0
        
        # Get exam score
        exam_record = ExamScore.objects.filter(
            student=student,
            subject=subject,
            term=term
        ).first()
        if exam_record:
            exam = exam_record.normalized_score
        
        # Apply weights
        ca_weight = policy.ca_weight / 100
        exam_weight = policy.exam_weight / 100
        
        final = (ca * ca_weight) + (exam * exam_weight)
        return round(final, 2)


class Result(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    exam_type = models.ForeignKey(ExamType, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(Term, on_delete=models.SET_NULL, null=True, blank=True)
    score = models.FloatField()

    def grade(self):
        if self.score >= 80:
            return "A"
        elif self.score >= 70:
            return "B"
        elif self.score >= 60:
            return "C"
        elif self.score >= 50:
            return "D"
        return "F"


class Timetable(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    class_name = models.CharField(max_length=50)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    day = models.CharField(max_length=20)
    start_time = models.TimeField()
    end_time = models.TimeField()


class Homework(models.Model):
    """Homework assignments for students."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    class_name = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    attachment = models.FileField(upload_to='homework/attachments/', null=True, blank=True)
    due_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='homework_created')

    class Meta:
        ordering = ["-due_date"]

    def __str__(self):
        return self.title


class ExamSchedule(models.Model):
    """Exam schedule/timetable for exams."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    exam_date = models.DateField()
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    room = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    class_name = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        ordering = ["exam_date", "start_time"]

    def __str__(self):
        return f"{self.subject.name} - {self.exam_date}"


# Online Quiz/Exam System
class Quiz(models.Model):
    """Online quiz/exam that students can take"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.SET_NULL, null=True, blank=True)
    class_name = models.CharField(max_length=50)
    duration_minutes = models.PositiveIntegerField(default=30)  # Time limit in minutes
    passing_score = models.PositiveIntegerField(default=50)  # Minimum score to pass
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-created_at"]
    
    def __str__(self):
        return self.title


class QuizQuestion(models.Model):
    """Questions for a quiz"""
    QUESTION_TYPES = [
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('short_answer', 'Short Answer'),
    ]
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='multiple_choice')
    option_a = models.CharField(max_length=500, blank=True)
    option_b = models.CharField(max_length=500, blank=True)
    option_c = models.CharField(max_length=500, blank=True)
    option_d = models.CharField(max_length=500, blank=True)
    correct_answer = models.CharField(max_length=10)  # A, B, C, D, or True/False
    marks = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ["order"]
    
    def __str__(self):
        return self.question_text[:50]


class QuizAttempt(models.Model):
    """Track student quiz attempts"""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    is_passed = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    
    class Meta:
        ordering = ["-started_at"]
    
    def __str__(self):
        return f"{self.student.user.username} - {self.quiz.title}"


class QuizAnswer(models.Model):
    """Student's answer to a question"""
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE)
    answer = models.CharField(max_length=10)
    is_correct = models.BooleanField(default=False)
    marks_obtained = models.FloatField(default=0)
