"""
Fix 11: Add term_fk FK to FeeStructure alongside the legacy term CharField.
The CharField is kept for backward compatibility; new code should use term_fk.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0023_feepayment_school_paid_at"),
        ("academics", "0053_gradeboundary_term_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="feestructure",
            name="term_fk",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="fee_structures",
                to="academics.term",
                help_text="Structured term FK. Prefer this over the legacy term CharField.",
            ),
        ),
    ]
