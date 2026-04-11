# Generated manually for absence date ranges

from django.db import migrations, models
from django.db.models import F


def backfill_end_date(apps, schema_editor):
    AbsenceRequest = apps.get_model("students", "AbsenceRequest")
    AbsenceRequest.objects.filter(end_date__isnull=True).update(end_date=F("date"))


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0011_backfill_school_class"),
    ]

    operations = [
        migrations.AddField(
            model_name="absencerequest",
            name="end_date",
            field=models.DateField(
                blank=True,
                help_text="Last day absent (inclusive). Leave blank for a single day.",
                null=True,
            ),
        ),
        migrations.RunPython(backfill_end_date, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="absencerequest",
            name="date",
            field=models.DateField(help_text="First day the student will be absent."),
        ),
    ]
