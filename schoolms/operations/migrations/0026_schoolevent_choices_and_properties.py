# Generated manually for SchoolEvent choices alignment

from django.db import migrations, models

VALID_TYPES = {"academic", "sports", "cultural", "meeting", "holiday", "other"}
VALID_AUDIENCE = {"all", "students", "staff", "parents"}


def forwards_normalize_school_events(apps, schema_editor):
    SchoolEvent = apps.get_model("operations", "SchoolEvent")
    for row in SchoolEvent.objects.all().only("id", "event_type", "target_audience"):
        changed = []
        if row.event_type not in VALID_TYPES:
            row.event_type = "other"
            changed.append("event_type")
        if row.target_audience not in VALID_AUDIENCE:
            row.target_audience = "all"
            changed.append("target_audience")
        if changed:
            row.save(update_fields=changed)


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0025_staffleave_extra_fields"),
    ]

    operations = [
        migrations.RunPython(forwards_normalize_school_events, backwards_noop),
        migrations.AlterField(
            model_name="schoolevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("academic", "Academic"),
                    ("sports", "Sports"),
                    ("cultural", "Cultural"),
                    ("meeting", "Meeting"),
                    ("holiday", "Holiday"),
                    ("other", "Other"),
                ],
                default="other",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="schoolevent",
            name="target_audience",
            field=models.CharField(
                choices=[
                    ("all", "Everyone"),
                    ("students", "Students only"),
                    ("staff", "Staff only"),
                    ("parents", "Parents only"),
                ],
                default="all",
                max_length=20,
            ),
        ),
    ]
