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
