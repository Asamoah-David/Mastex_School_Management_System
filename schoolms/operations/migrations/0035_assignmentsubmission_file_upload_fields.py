from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0034_studentdocument_file_upload_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignmentsubmission",
            name="file",
            field=models.FileField(blank=True, null=True, upload_to="assignment_submissions/%Y/%m/%d/"),
        ),
        migrations.AddField(
            model_name="assignmentsubmission",
            name="notes",
            field=models.TextField(blank=True, default=""),
        ),
    ]
