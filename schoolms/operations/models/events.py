from django.db import models
from django.utils import timezone

from accounts.models import User
from students.models import Student
from schools.models import School


class SchoolEvent(models.Model):
    """School events and activities"""

    EVENT_TYPE_CHOICES = (
        ("academic", "Academic"),
        ("sports", "Sports"),
        ("cultural", "Cultural"),
        ("meeting", "Meeting"),
        ("holiday", "Holiday"),
        ("other", "Other"),
    )
    TARGET_AUDIENCE_CHOICES = (
        ("all", "Everyone"),
        ("students", "Students only"),
        ("staff", "Staff only"),
        ("parents", "Parents only"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    event_type = models.CharField(max_length=50, choices=EVENT_TYPE_CHOICES, default="other")
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    target_audience = models.CharField(
        max_length=20, choices=TARGET_AUDIENCE_CHOICES, default="all"
    )
    is_mandatory = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.title

    def _window_end(self):
        return self.end_date if self.end_date else self.start_date

    @property
    def is_upcoming(self):
        return self.start_date > timezone.now()

    @property
    def is_ongoing(self):
        now = timezone.now()
        end = self._window_end()
        return self.start_date <= now <= end

    @property
    def is_past(self):
        return self._window_end() < timezone.now()


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
