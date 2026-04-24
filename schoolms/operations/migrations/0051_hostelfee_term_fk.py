"""
Fix 11: Add term_fk FK to HostelFee alongside the legacy term CharField.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0050_expense_budget_fk_hostel_constraint_expensecategory_unique_remove_cert_pdffile"),
        ("academics", "0053_gradeboundary_term_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="hostelfee",
            name="term_fk",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="hostel_fees",
                to="academics.term",
                help_text="Structured term FK. Prefer this over the legacy term CharField.",
            ),
        ),
    ]
