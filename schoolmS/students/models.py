from django.db import models
from accounts.models import User
from schools.models import School

class Student(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    admission_number = models.CharField(max_length=50)
    parent = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="children")

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.admission_number})"