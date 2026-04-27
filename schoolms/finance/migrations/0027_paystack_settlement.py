"""
Fix #35: PaystackSettlement model for bank/Paystack reconciliation.
Fix #14: FeeStructure and Fee adopt SchoolScopedModel (Python-only — schema unchanged).
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0026_alter_feepayment_school"),
        ("schools", "0017_schoolnetwork"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaystackSettlement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("settlement_id", models.CharField(max_length=100, unique=True, help_text="Paystack settlement ID.")),
                ("batch_reference", models.CharField(blank=True, max_length=100)),
                ("amount", models.DecimalField(
                    decimal_places=2, max_digits=14,
                    help_text="Gross settlement amount in subunit / 100.",
                )),
                ("effective_amount", models.DecimalField(
                    decimal_places=2, max_digits=14,
                    help_text="Net after Paystack deductions.",
                )),
                ("settlement_date", models.DateField()),
                ("status", models.CharField(
                    choices=[("pending","Pending"),("processing","Processing"),("settled","Settled"),("failed","Failed")],
                    db_index=True, default="pending", max_length=20,
                )),
                ("transactions_count", models.PositiveIntegerField(default=0)),
                ("raw_payload", models.JSONField(blank=True, default=dict, help_text="Raw Paystack settlement JSON for audit.")),
                ("reconciled", models.BooleanField(db_index=True, default=False)),
                ("reconciliation_notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("school", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="paystack_settlements", to="schools.school",
                )),
            ],
            options={
                "verbose_name": "Paystack Settlement",
                "verbose_name_plural": "Paystack Settlements",
                "ordering": ["-settlement_date", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="paystacksettlement",
            index=models.Index(fields=["school", "settlement_date"], name="idx_pssettl_school_date"),
        ),
        migrations.AddIndex(
            model_name="paystacksettlement",
            index=models.Index(fields=["school", "reconciled"], name="idx_pssettl_school_rec"),
        ),
    ]
