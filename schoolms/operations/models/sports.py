from django.db import models
from accounts.models import User
from students.models import Student
from schools.models import School


class Sport(models.Model):
    """Sports teams/activities"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    coach = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='coached_sports')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    max_members = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum approved roster size. Empty means no limit.",
    )
    join_requires_approval = models.BooleanField(
        default=False,
        help_text="Student self-joins require coach or leadership approval before they appear on the roster.",
    )

    def __str__(self):
        return f"{self.name} - {self.school.name}"

    def approved_member_count(self):
        return self.members.filter(is_active=True, pending_approval=False).count()

    def pending_request_count(self):
        return self.members.filter(is_active=True, pending_approval=True).count()

    def is_at_capacity(self):
        if not self.max_members:
            return False
        return self.approved_member_count() >= self.max_members


class Club(models.Model):
    """School clubs/organizations"""
    CATEGORY_CHOICES = (
        ('academic', 'Academic'),
        ('sports', 'Sports'),
        ('arts', 'Arts & Culture'),
        ('science', 'Science & Tech'),
        ('social', 'Social Service'),
        ('religious', 'Religious'),
        ('other', 'Other'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    sponsor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sponsored_clubs')
    description = models.TextField(blank=True)
    meeting_day = models.CharField(max_length=20, blank=True)  # e.g., "Monday"
    meeting_time = models.TimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    max_members = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum approved members. Empty means no limit.",
    )
    join_requires_approval = models.BooleanField(
        default=False,
        help_text="Student self-joins require sponsor or leadership approval before they appear on the roster.",
    )

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    def approved_member_count(self):
        return self.members.filter(is_active=True, pending_approval=False).count()

    def pending_request_count(self):
        return self.members.filter(is_active=True, pending_approval=True).count()

    def is_at_capacity(self):
        if not self.max_members:
            return False
        return self.approved_member_count() >= self.max_members


class StudentSport(models.Model):
    """Student participation in sports"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='sports')
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name='members')
    jersey_number = models.CharField(max_length=10, blank=True)
    position = models.CharField(max_length=50, blank=True)
    joined_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    pending_approval = models.BooleanField(
        default=False,
        help_text="Awaiting staff approval for student-initiated join.",
    )

    class Meta:
        unique_together = ("student", "sport")

    def __str__(self):
        return f"{self.student} - {self.sport.name}"


class StudentClub(models.Model):
    """Student membership in clubs"""
    ROLE_CHOICES = (
        ('member', 'Member'),
        ('secretary', 'Secretary'),
        ('vice_president', 'Vice President'),
        ('president', 'President'),
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='club_memberships')
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name='members')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    pending_approval = models.BooleanField(
        default=False,
        help_text="Awaiting staff approval for student-initiated join.",
    )

    class Meta:
        unique_together = ("student", "club")

    def __str__(self):
        return f"{self.student} - {self.club.name} ({self.role})"
