# Generated manually — enterprise hardening

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def forwards_workflow(apps, schema_editor):
    Result = apps.get_model("academics", "Result")
    for row in Result.objects.all().only("pk", "is_published", "workflow_status").iterator(chunk_size=500):
        if row.is_published and row.workflow_status == "draft":
            Result.objects.filter(pk=row.pk).update(workflow_status="published")
        elif not row.is_published and row.workflow_status == "draft":
            pass


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0064_earlywarningflag_acknowledged_at_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ScoreChangeLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_model", models.CharField(db_index=True, max_length=120)),
                ("target_id", models.PositiveBigIntegerField(db_index=True)),
                ("field_name", models.CharField(max_length=64)),
                ("old_value", models.CharField(blank=True, max_length=500)),
                ("new_value", models.CharField(blank=True, max_length=500)),
                ("reason", models.TextField(blank=True)),
                ("source", models.CharField(blank=True, default="orm", help_text="orm, api, omr, import, admin, …", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="score_change_logs", to=settings.AUTH_USER_MODEL)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="score_change_logs", to="schools.school")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="result",
            name="workflow_status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("reviewed", "Reviewed"),
                    ("approved", "Approved"),
                    ("published", "Published"),
                    ("locked", "Locked"),
                ],
                db_index=True,
                default="draft",
                help_text="Draft → reviewed → approved → published → locked.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="result",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="result",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="result",
            name="locked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="result",
            name="approved_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="results_approved", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="result",
            name="locked_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="results_locked", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="result",
            name="reviewed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="results_reviewed", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="reportcard",
            name="calculation_snapshot",
            field=models.JSONField(blank=True, default=dict, help_text="Immutable scheme-based breakdown at generation/publish time (StudentReportCardScore rows)."),
        ),
        migrations.AddIndex(
            model_name="result",
            index=models.Index(fields=["school", "workflow_status"], name="idx_result_school_workflow"),
        ),
        migrations.AddIndex(
            model_name="scorechangelog",
            index=models.Index(fields=["school", "target_model", "target_id"], name="idx_scorelog_school_tgt"),
        ),
        migrations.RunPython(forwards_workflow, migrations.RunPython.noop),
    ]
