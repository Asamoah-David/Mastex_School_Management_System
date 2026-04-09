from django.db import models
from accounts.models import User
from schools.models import School


class TimetableSlot(models.Model):
    """Timetable slots for classes"""
    DAYS = (
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    class_name = models.CharField(max_length=50)
    school_class = models.ForeignKey(
        "students.SchoolClass", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="timetable_slots",
    )
    day = models.CharField(max_length=20, choices=DAYS)
    period_number = models.PositiveIntegerField()  # 1, 2, 3, etc.
    subject = models.ForeignKey('academics.Subject', on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, limit_choices_to={'role': 'teacher'})
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ("school", "class_name", "day", "period_number")
        ordering = ["day", "period_number"]
    
    def __str__(self):
        return f"{self.class_name} - {self.day} P{self.period_number} - {self.subject.name}"


class TimetableConflict(models.Model):
    """Track timetable conflicts"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    conflict_type = models.CharField(max_length=50)  # teacher_room, room_time, etc.
    slot_1 = models.ForeignKey(TimetableSlot, on_delete=models.CASCADE, related_name='conflicts_1')
    slot_2 = models.ForeignKey(TimetableSlot, on_delete=models.CASCADE, related_name='conflicts_2')
    description = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-created_at"]
