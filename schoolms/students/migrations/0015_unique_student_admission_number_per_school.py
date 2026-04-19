from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0014_studentclearance"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="student",
            constraint=models.UniqueConstraint(
                fields=["school", "admission_number"],
                name="uniq_student_admission_number_per_school",
            ),
        ),
    ]
