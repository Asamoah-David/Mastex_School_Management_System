"""
Fix #8: Add academic_year_fk and term_fk ForeignKeys to Budget model.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0056_alter_academicyear_is_current"),
        ("operations", "0055_attendance_school_unique_together"),
    ]

    operations = [
        migrations.AddField(
            model_name="budget",
            name="academic_year_fk",
            field=models.ForeignKey(
                blank=True,
                help_text="Structured academic year (prefer over the legacy CharField).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="budgets",
                to="academics.academicyear",
            ),
        ),
        migrations.AddField(
            model_name="budget",
            name="term_fk",
            field=models.ForeignKey(
                blank=True,
                help_text="Structured term (prefer over the legacy CharField).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="budgets",
                to="academics.term",
            ),
        ),
    ]
