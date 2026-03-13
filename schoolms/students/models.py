from django.db import models
from accounts.models import User
from schools.models import School


class SchoolClass(models.Model):
    """Structured class/section with capacity and class teacher."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)  # e.g. "Form 1A", "Primary 3B"
    capacity = models.PositiveIntegerField(default=40, blank=True, null=True)
    class_teacher = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="classes_taught", limit_choices_to={"role__in": ["admin", "teacher"]}
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("school", "name")
        verbose_name = "Class"
        verbose_name_plural = "Classes"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.school.name})"

    def student_count(self):
        return Student.objects.filter(school=self.school, class_name=self.name).count()


class Student(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    admission_number = models.CharField(max_length=50)
    class_name = models.CharField(max_length=50, blank=True)  # e.g. "Primary 3A", "Form 2"
    parent = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="children")
    date_enrolled = models.DateField(null=True, blank=True)

    # Health Information
    blood_group = models.CharField(max_length=10, blank=True, null=True)  # e.g., "A+", "O-"
    allergies = models.TextField(blank=True, null=True)
    medical_conditions = models.TextField(blank=True, null=True)  # e.g., Asthma, Diabetes
    medications = models.TextField(blank=True, null=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True, null=True)
    doctor_phone = models.CharField(max_length=20, blank=True, null=True)
    last_medical_checkup = models.DateField(null=True, blank=True)
    medical_notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.admission_number})"


class StudentAchievement(models.Model):
    """Track student achievements, awards, and activities"""
    ACHIEVEMENT_TYPES = (
        ('academic', 'Academic'),
        ('sports', 'Sports'),
        ('arts', 'Arts & Culture'),
        ('leadership', 'Leadership'),
        ('community', 'Community Service'),
        ('behavior', 'Behavior/Discipline'),
        ('other', 'Other'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="achievements")
    achievement_type = models.CharField(max_length=20, choices=ACHIEVEMENT_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date_achieved = models.DateField()
    awarded_by = models.CharField(max_length=100, blank=True)
    certificate_number = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_achieved"]

    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.title}"


class StudentActivity(models.Model):
    """Track extracurricular activities"""
    ACTIVITY_TYPES = (
        ('sports', 'Sports'),
        ('clubs', 'Clubs'),
        ('music', 'Music & Dance'),
        ('art', 'Art & Craft'),
        ('science', 'Science Club'),
        ('reading', 'Reading Club'),
        ('debate', 'Debate Club'),
        ('scout', 'Scouting/Guidance'),
        ('other', 'Other'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="activities")
    activity_name = models.CharField(max_length=100)
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    position = models.CharField(max_length=50, blank=True)  # Captain, Member, etc.
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.activity_name}"


class StudentDiscipline(models.Model):
    """Track behavior and discipline records"""
    INCIDENT_TYPES = (
        ('positive', 'Positive Behavior'),
        ('minor', 'Minor Infraction'),
        ('major', 'Major Infraction'),
        ('suspension', 'Suspension'),
        ('expulsion', 'Expulsion'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="discipline_records")
    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    incident_date = models.DateField()
    action_taken = models.TextField(blank=True)
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="reported_discipline")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-incident_date"]

    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.title}"
