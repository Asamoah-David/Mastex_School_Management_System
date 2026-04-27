"""
Fix #12: Backfill StudentGuardian.school from student.school.

Runs as a data migration so all existing rows get populated before
we can make the field non-nullable in a future migration.
"""

from django.db import migrations


def _backfill_guardian_school(apps, schema_editor):
    StudentGuardian = apps.get_model("students", "StudentGuardian")
    updated = (
        StudentGuardian.objects.filter(school__isnull=True)
        .select_related("student__school")
    )
    to_update = []
    for sg in updated:
        if sg.student_id and sg.student.school_id:
            sg.school_id = sg.student.school_id
            to_update.append(sg)
    if to_update:
        StudentGuardian.objects.bulk_update(to_update, ["school_id"], batch_size=500)


def _reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0017_school_fk_on_studentguardian"),
    ]

    operations = [
        migrations.RunPython(_backfill_guardian_school, _reverse_noop),
    ]
