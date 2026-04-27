from django.db import models
from accounts.models import User, STAFF_ROLES
from students.models import Student
from schools.models import School
from core.tenancy import SchoolScopedModel


class TeacherAttendance(SchoolScopedModel):
    STATUS_CHOICES = (("present", "Present"), ("absent", "Absent"), ("late", "Late"), ("excused", "Excused"))
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role__in': list(STAFF_ROLES)})
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="present")
    notes = models.CharField(max_length=255, blank=True)
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="marked_teacher_attendances")

    class Meta:
        unique_together = ("school", "teacher", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.teacher.get_full_name()} - {self.date} ({self.status})"


class StudentAttendance(SchoolScopedModel):
    STATUS_CHOICES = (("present", "Present"), ("absent", "Absent"), ("late", "Late"), ("excused", "Excused"))
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="present")
    notes = models.CharField(max_length=255, blank=True)
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="marked_attendances")

    class Meta:
        unique_together = ("school", "student", "date")
        ordering = ["-date"]
        verbose_name = "Student Attendance"
        verbose_name_plural = "Student Attendance Records"
        indexes = [
            models.Index(fields=["school", "date"], name="idx_att_school_date"),
            models.Index(fields=["school", "date", "status"], name="idx_att_school_date_status"),
        ]

    def __str__(self):
        return f"{self.student} - {self.date} ({self.status})"
