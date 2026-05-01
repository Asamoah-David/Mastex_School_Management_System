from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recruitment", "0001_auto_supply_recruitment"),
    ]

    operations = [
        # f7: prevent duplicate paid applications from the same email to the same job
        migrations.AddConstraint(
            model_name="jobapplication",
            constraint=models.UniqueConstraint(
                fields=["job", "email"],
                condition=models.Q(payment_status="paid"),
                name="uniq_paid_jobapp_job_email",
            ),
        ),
        # f11: allow blank message in InterviewSchedule
        migrations.AlterField(
            model_name="interviewschedule",
            name="message_to_applicant",
            field=models.TextField(
                blank=True,
                help_text="Personal message included in the interview invitation",
            ),
        ),
    ]
