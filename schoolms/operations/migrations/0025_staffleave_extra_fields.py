# Generated manually — staff leave metadata and review notes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0024_admission_public_reference_uploads"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffleave",
            name="leave_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("sick", "Sick leave"),
                    ("annual", "Annual leave"),
                    ("personal", "Personal leave"),
                    ("emergency", "Emergency"),
                    ("maternity", "Maternity"),
                    ("paternity", "Paternity"),
                    ("study", "Study leave"),
                    ("other", "Other"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="staffleave",
            name="covering_teacher",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="staffleave",
            name="contact_during_leave",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="staffleave",
            name="review_notes",
            field=models.TextField(blank=True),
        ),
    ]
