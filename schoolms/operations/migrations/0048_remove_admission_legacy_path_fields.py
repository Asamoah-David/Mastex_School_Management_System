from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0047_ptmeeting_meeting_link"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="admissionapplication",
            name="birth_certificate_path",
        ),
        migrations.RemoveField(
            model_name="admissionapplication",
            name="previous_report_path",
        ),
        migrations.RemoveField(
            model_name="admissionapplication",
            name="passport_photo_path",
        ),
    ]
