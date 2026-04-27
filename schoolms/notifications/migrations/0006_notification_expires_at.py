from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0005_notificationpreference_academic_event_alerts_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="expires_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                help_text="When set, the notification is eligible for auto-purge after this timestamp.",
            ),
        ),
    ]
