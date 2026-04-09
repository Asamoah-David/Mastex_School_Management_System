"""Sync Django migration state with actual database schema.

Migration 0010 added Result fields via raw SQL (RunSQL) which
bypassed Django's state tracking.  This migration declares those
fields in state only (no database changes) so subsequent migrations
can reference them correctly.
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0012_onlinemeeting_fields"),
        ("students", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="result",
                    name="created_by",
                    field=models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AddField(
                    model_name="result",
                    name="created_at",
                    field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
                    preserve_default=False,
                ),
                migrations.AddField(
                    model_name="result",
                    name="updated_at",
                    field=models.DateTimeField(auto_now=True),
                ),
                migrations.AddField(
                    model_name="result",
                    name="remarks",
                    field=models.TextField(blank=True, default=""),
                ),
                migrations.AddField(
                    model_name="result",
                    name="total_score",
                    field=models.FloatField(default=100),
                ),
            ],
            database_operations=[],
        ),
    ]
