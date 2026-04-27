"""
Fix #9: Add target_class_fk FK to BroadcastNotification alongside legacy CharField.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("messaging", "0002_outbound_comm_log"),
        ("students", "0016_studentguardian"),
    ]

    operations = [
        migrations.AddField(
            model_name="broadcastnotification",
            name="target_class_fk",
            field=models.ForeignKey(
                blank=True,
                help_text="Structured class target (takes precedence over target_class CharField).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="broadcast_notifications",
                to="students.schoolclass",
            ),
        ),
    ]
