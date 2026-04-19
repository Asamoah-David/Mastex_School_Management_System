from django.db import models
from accounts.models import User
from students.models import Student
from schools.models import School
from django.core.exceptions import ValidationError


class ExamHall(models.Model):
    """Examination halls"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    rows = models.PositiveIntegerField(default=10)
    seats_per_row = models.PositiveIntegerField(default=10)
    description = models.TextField(blank=True)
    
    @property
    def total_seats(self):
        return self.rows * self.seats_per_row
    
    def __str__(self):
        return f"{self.name} ({self.total_seats} seats)"


class SeatingPlan(models.Model):
    """Exam seating arrangements"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    exam_schedule = models.ForeignKey('academics.ExamSchedule', on_delete=models.CASCADE, related_name='seating_plans')
    hall = models.ForeignKey(ExamHall, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ("exam_schedule", "hall")
    
    def __str__(self):
        return f"{self.exam_schedule.subject.name} - {self.hall.name}"

    def clean(self):
        super().clean()
        if self.school_id and self.hall_id and getattr(self.hall, "school_id", None) != self.school_id:
            raise ValidationError({"hall": "Hall must belong to the same school as the seating plan."})
        if self.school_id and self.exam_schedule_id and getattr(self.exam_schedule, "school_id", None) != self.school_id:
            raise ValidationError({"exam_schedule": "Exam schedule must belong to the same school as the seating plan."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class SeatAssignment(models.Model):
    """Individual seat assignments"""
    seating_plan = models.ForeignKey(SeatingPlan, on_delete=models.CASCADE, related_name='seat_assignments')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='seat_assignments')
    row_number = models.PositiveIntegerField()
    seat_number = models.PositiveIntegerField()
    
    class Meta:
        unique_together = ("seating_plan", "row_number", "seat_number")
    
    def __str__(self):
        return f"{self.student} - Row {self.row_number}, Seat {self.seat_number}"

    def clean(self):
        super().clean()
        # Ensure student belongs to the same school as the seating plan.
        if self.seating_plan_id and self.student_id:
            sp_school_id = getattr(self.seating_plan, "school_id", None)
            st_school_id = getattr(self.student, "school_id", None)
            if sp_school_id and st_school_id and sp_school_id != st_school_id:
                raise ValidationError({"student": "Student must belong to the same school as the seating plan."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class OnlineExam(models.Model):
    """Online examination with auto-grading"""
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    subject = models.ForeignKey('academics.Subject', on_delete=models.CASCADE)
    class_level = models.CharField(max_length=50)  # Target class
    exam_type = models.CharField(max_length=50, default='quiz')  # quiz, test, exam
    duration_minutes = models.PositiveIntegerField(default=30)
    total_marks = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    passing_marks = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    max_attempts_per_student = models.PositiveSmallIntegerField(
        default=1,
        help_text="Maximum completed attempts per student (e.g. 3 for practice). Staff can still reset an attempt.",
    )
    instructions = models.TextField(blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_random_questions = models.BooleanField(default=False)
    show_results_immediately = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-start_time"]
    
    def __str__(self):
        return f"{self.title} - {self.subject.name}"

    def clean(self):
        super().clean()
        if self.school_id and self.subject_id and getattr(self.subject, "school_id", None) != self.school_id:
            raise ValidationError({"subject": "Subject must belong to the same school as the exam."})
        if self.school_id and self.created_by_id and getattr(self.created_by, "school_id", None) not in (None, self.school_id):
            raise ValidationError({"created_by": "Creator must belong to the same school as the exam."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ExamQuestion(models.Model):
    """Questions for online exams"""
    QUESTION_TYPES = (
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('short_answer', 'Short Answer'),
        ('essay', 'Essay'),
    )
    exam = models.ForeignKey(OnlineExam, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    marks = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    
    # For multiple choice
    option_a = models.CharField(max_length=500, blank=True)
    option_b = models.CharField(max_length=500, blank=True)
    option_c = models.CharField(max_length=500, blank=True)
    option_d = models.CharField(max_length=500, blank=True)
    correct_answer = models.CharField(max_length=200, blank=True)  # A–D / T&F / expected short text
    
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ["order"]
    
    def __str__(self):
        return f"Q{self.order}: {self.question_text[:50]}..."


class ExamAttempt(models.Model):
    """Track student exam attempts (multiple per exam when max_attempts_per_student > 1)."""
    exam = models.ForeignKey(OnlineExam, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_attempts')
    attempt_number = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    tab_blur_count = models.PositiveIntegerField(
        default=0,
        help_text="How often the exam tab lost visibility during this attempt (honesty signal).",
    )
    
    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "student", "attempt_number"],
                name="ops_exmatt_ex_stu_attn_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["exam", "student", "is_completed"], name="ops_exmatt_ex_st_done"),
        ]
    
    def __str__(self):
        return f"{self.student} - {self.exam.title} (#{self.attempt_number})"

    def clean(self):
        super().clean()
        if self.exam_id and self.student_id:
            ex_school_id = getattr(self.exam, "school_id", None)
            st_school_id = getattr(self.student, "school_id", None)
            if ex_school_id and st_school_id and ex_school_id != st_school_id:
                raise ValidationError({"student": "Student must belong to the same school as the exam."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ExamAnswer(models.Model):
    """Individual answers from exam attempts"""
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE)
    answer_given = models.CharField(max_length=500, blank=True)
    is_correct = models.BooleanField(default=False)
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    teacher_reviewed = models.BooleanField(
        default=True,
        help_text="False for essay answers until a teacher enters marks.",
    )
    
    class Meta:
        unique_together = ("attempt", "question")
