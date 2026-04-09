from django.db import models
from accounts.models import User
from students.models import Student
from schools.models import School


class SchoolEvent(models.Model):
    """School events and activities"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    event_type = models.CharField(max_length=50)  # assembly, sports, concert, trip, meeting, other
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    target_audience = models.CharField(max_length=20, default="all")  # all, students, staff, parents
    is_mandatory = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-start_date"]
    
    def __str__(self):
        return self.title


class EventRSVP(models.Model):
    """Track event attendance/confirmation"""
    event = models.ForeignKey(SchoolEvent, on_delete=models.CASCADE, related_name="rsvps")
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    is_attending = models.BooleanField(default=True)
    responded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = ("event", "student")
    
    def __str__(self):
        return f"{self.student} - {self.event.title}"


class PTMeeting(models.Model):
    """Parent-Teacher Meeting scheduling"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    meeting_date = models.DateTimeField()
    location = models.CharField(max_length=200)
    max_slots = models.PositiveIntegerField(default=20)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-meeting_date"]
    
    def __str__(self):
        return f"{self.title} - {self.meeting_date}"
    
    @property
    def booked_slots(self):
        return self.bookings.count()
    
    @property
    def available_slots(self):
        return max(0, self.max_slots - self.booked_slots)


class PTMeetingBooking(models.Model):
    """Individual meeting slot booking"""
    meeting = models.ForeignKey(PTMeeting, on_delete=models.CASCADE, related_name='bookings')
    parent = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'parent'})
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='pt_bookings')
    preferred_time = models.TimeField(null=True, blank=True)
    topics_to_discuss = models.TextField(blank=True)
    is_confirmed = models.BooleanField(default=False)
    booked_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ("meeting", "parent", "student")
        ordering = ["booked_at"]
    
    def __str__(self):
        return f"{self.parent.get_full_name()} - {self.student}"
