"""
Fix 19: Add fee_payment, admission_status, attendance, result_published event
flags to SchoolWebhookEndpoint.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0002_webhookdeliveryattempt"),
    ]

    operations = [
        migrations.AddField(
            model_name="schoolwebhookendpoint",
            name="notify_fee_payment",
            field=models.BooleanField(default=False, help_text="Fee payment completed"),
        ),
        migrations.AddField(
            model_name="schoolwebhookendpoint",
            name="notify_admission_status",
            field=models.BooleanField(
                default=False, help_text="Admission status changed (approved/rejected)"
            ),
        ),
        migrations.AddField(
            model_name="schoolwebhookendpoint",
            name="notify_attendance",
            field=models.BooleanField(
                default=False, help_text="Attendance marked for a class"
            ),
        ),
        migrations.AddField(
            model_name="schoolwebhookendpoint",
            name="notify_result_published",
            field=models.BooleanField(default=False, help_text="Exam result published"),
        ),
    ]
