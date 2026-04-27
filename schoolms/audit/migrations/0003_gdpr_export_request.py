"""
Fix #34: GDPRExportRequest model for data portability / right-of-access requests.
Fix #3: IP extraction improvement (Python-only change to _get_client_ip).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0002_auditlog_request_id"),
        ("schools", "0017_schoolnetwork"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GDPRExportRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(
                    choices=[
                        ("pending", "Pending"),
                        ("processing", "Processing"),
                        ("ready", "Ready for download"),
                        ("downloaded", "Downloaded"),
                        ("expired", "Expired"),
                        ("failed", "Failed"),
                    ],
                    db_index=True, default="pending", max_length=20,
                )),
                ("export_url", models.URLField(blank=True, max_length=500, help_text="Signed URL to the exported JSON file.")),
                ("error_message", models.TextField(blank=True)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True, help_text="Download link expiry.")),
                ("school", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name="gdpr_export_requests", to="schools.school",
                )),
                ("requested_by", models.ForeignKey(
                    null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="gdpr_export_requests", to=settings.AUTH_USER_MODEL,
                )),
                ("subject_user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="gdpr_exports", to=settings.AUTH_USER_MODEL,
                    help_text="The user whose data is being exported.",
                )),
            ],
            options={
                "verbose_name": "GDPR Export Request",
                "verbose_name_plural": "GDPR Export Requests",
                "ordering": ["-requested_at"],
            },
        ),
        migrations.AddIndex(
            model_name="gdprexportrequest",
            index=models.Index(fields=["school", "status"], name="idx_gdpr_school_status"),
        ),
    ]
