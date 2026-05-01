"""
C1 — Copy legacy DisciplineIncident rows → students.StudentDiscipline.

DisciplineIncident is DEPRECATED; StudentDiscipline is the canonical model.
This migration is idempotent: it skips any row already copied
(matched on school + student + incident_date + title).

Field mapping:
  DisciplineIncident.incident_type  (free text)   → StudentDiscipline.title
  DisciplineIncident.severity       (choice)       → StudentDiscipline.incident_type
      minor / moderate  → 'minor'
      serious           → 'major'
      severe            → 'major'
  DisciplineIncident.description                  → StudentDiscipline.description
  DisciplineIncident.action_taken                 → StudentDiscipline.action_taken
  DisciplineIncident.incident_date  (DateTimeField)→ StudentDiscipline.incident_date (.date())
  DisciplineIncident.school                       → StudentDiscipline.school
  DisciplineIncident.student                      → StudentDiscipline.student
  DisciplineIncident.reported_by                  → StudentDiscipline.reported_by
"""
from django.db import migrations

_SEVERITY_MAP = {
    "minor": "minor",
    "moderate": "minor",
    "serious": "major",
    "severe": "major",
}


def copy_discipline_incidents(apps, schema_editor):
    DisciplineIncident = apps.get_model("operations", "DisciplineIncident")
    StudentDiscipline = apps.get_model("students", "StudentDiscipline")

    existing = set(
        StudentDiscipline.objects.values_list(
            "school_id", "student_id", "incident_date", "title"
        )
    )

    to_create = []
    for inc in DisciplineIncident.objects.select_related("school", "student", "reported_by").iterator(chunk_size=500):
        inc_date = inc.incident_date.date() if hasattr(inc.incident_date, "date") else inc.incident_date
        title = (inc.incident_type or "")[:200]
        key = (inc.school_id, inc.student_id, inc_date, title)
        if key in existing:
            continue
        to_create.append(
            StudentDiscipline(
                school_id=inc.school_id,
                student_id=inc.student_id,
                incident_type=_SEVERITY_MAP.get(inc.severity, "minor"),
                title=title,
                description=inc.description or "",
                incident_date=inc_date,
                action_taken=inc.action_taken or "",
                reported_by_id=inc.reported_by_id,
            )
        )

    if to_create:
        StudentDiscipline.objects.bulk_create(to_create, batch_size=500)


def reverse_copy(apps, schema_editor):
    pass  # Intentionally non-destructive — do not delete StudentDiscipline rows on rollback.


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0060_erp_new_models_batch"),
        ("students", "0020_erp_new_models_batch"),
    ]

    operations = [
        migrations.RunPython(copy_discipline_incidents, reverse_copy),
    ]
