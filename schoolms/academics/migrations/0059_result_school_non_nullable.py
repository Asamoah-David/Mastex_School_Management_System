"""
Fix #18: Result.school — backfill from student.school then make non-nullable.

Runs in two steps:
  1. Data migration: set school_id = student.school_id for all Result rows where school is NULL.
  2. Schema migration: AlterField to remove null=True, blank=True.

Rows without a student (orphaned) are deleted first to avoid constraint violations.
"""

import django.db.models.deletion
from django.db import migrations, models


def _backfill_result_school(apps, schema_editor):
    Result = apps.get_model("academics", "Result")
    # Remove orphaned results that have no student at all
    Result.objects.filter(student__isnull=True, school__isnull=True).delete()
    # Backfill from student.school
    to_update = []
    for r in Result.objects.filter(school__isnull=True).select_related("student"):
        if r.student_id and r.student.school_id:
            r.school_id = r.student.school_id
            to_update.append(r)
    if to_update:
        Result.objects.bulk_update(to_update, ["school_id"], batch_size=500)
    # Any remaining NULLs (no school on student either) — delete to allow NOT NULL constraint
    Result.objects.filter(school__isnull=True).delete()


def _reverse_nullable(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0058_alter_homeworksubmission_options_and_more"),
        ("schools", "0017_schoolnetwork"),
    ]

    operations = [
        migrations.RunPython(_backfill_result_school, _reverse_nullable),
        migrations.AlterField(
            model_name="result",
            name="school",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="results",
                to="schools.school",
                help_text="School this result belongs to.",
            ),
        ),
    ]
