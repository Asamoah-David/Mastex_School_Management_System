"""
Fix #5: StudentAttendance unique_together — add school to constraint.
Fix #13: TeacherAttendance — expand limit_choices_to (Python only, no DB change).
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0054_libraryfine"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="studentattendance",
            unique_together={("school", "student", "date")},
        ),
    ]
