# Generated manually — support short-answer keys on online exams

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0020_alter_staffidcard_photo_alter_studentidcard_photo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="examquestion",
            name="correct_answer",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
