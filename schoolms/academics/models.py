from django.db import models
from students.models import Student
from schools.models import School


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
    
    def __str__(self):
        return self.name


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
        school = self.student.school
        return get_grade_for_score(school, self.score)


class Homework(models.Model):
    """Homework assignments per class."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    class_name = models.CharField(max_length=100)  # e.g. "Form 1A"
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField()
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="homework_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-due_date"]

    def __str__(self):
        return f"{self.title} - {self.class_name}"


class ExamSchedule(models.Model):
    """Exam timetable per term."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    # Optional class or group this exam is scheduled for (e.g. "JHS 1", "SHS 2 Science").
    class_name = models.CharField(max_length=100, blank=True)
    exam_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    room = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["exam_date", "start_time"]

    def __str__(self):
        return f"{self.subject.name} - {self.exam_date}"


class Timetable(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    class_name = models.CharField(max_length=50)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    day = models.CharField(max_length=20)
    start_time = models.TimeField()
    end_time = models.TimeField()
