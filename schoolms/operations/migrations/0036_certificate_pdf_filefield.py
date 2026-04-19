from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0035_assignmentsubmission_file_upload_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="certificate",
            name="pdf",
            field=models.FileField(blank=True, null=True, upload_to="certificates/%Y/%m/%d/"),
        ),
    ]
