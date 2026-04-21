"""
Phase 2: School funds ledger and balance models.

- SchoolFundsLedgerEntry: append-only financial ledger
- SchoolFundsBalance: denormalized running totals per school
"""
from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0012_school_payout_setup_fields"),
        ("finance", "0019_restore_default_objects_managers"),
    ]

    operations = [
        # --- SchoolFundsLedgerEntry ---
        migrations.CreateModel(
            name="SchoolFundsLedgerEntry",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Always positive.  Direction is set by the ``direction`` field.",
                        max_digits=14,
                    ),
                ),
                (
                    "direction",
                    models.CharField(
                        choices=[("credit", "Credit"), ("debit", "Debit")],
                        max_length=6,
                    ),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("collected", "Collected"),
                            ("cleared", "Cleared"),
                            ("available", "Available"),
                            ("reserved", "Reserved"),
                            ("paid_out", "Paid Out"),
                        ],
                        max_length=12,
                    ),
                ),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("fee_payment", "Fee Payment"),
                            ("settlement", "Settlement / Reconciliation"),
                            ("payout_reserve", "Payout Reserve"),
                            ("payout_execute", "Payout Execution"),
                            ("payout_release", "Payout Release (fail/cancel)"),
                            ("adjustment", "Manual Adjustment"),
                        ],
                        max_length=24,
                    ),
                ),
                (
                    "reference",
                    models.CharField(
                        db_index=True,
                        help_text="Paystack reference, payout-request id, or adjustment ticket.",
                        max_length=255,
                    ),
                ),
                (
                    "description",
                    models.CharField(blank=True, default="", max_length=500),
                ),
                (
                    "currency",
                    models.CharField(default="GHS", max_length=8),
                ),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="funds_ledger_entries",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "School Funds Ledger Entry",
                "verbose_name_plural": "School Funds Ledger Entries",
                "ordering": ["-created_at", "-pk"],
            },
        ),
        migrations.AddIndex(
            model_name="schoolfundsledgerentry",
            index=models.Index(
                fields=["school", "state", "created_at"],
                name="idx_fundsle_school_state_ts",
            ),
        ),
        migrations.AddIndex(
            model_name="schoolfundsledgerentry",
            index=models.Index(
                fields=["school", "source_type", "created_at"],
                name="idx_fundsle_school_src_ts",
            ),
        ),
        migrations.AddIndex(
            model_name="schoolfundsledgerentry",
            index=models.Index(
                fields=["reference"],
                name="idx_fundsle_reference",
            ),
        ),
        migrations.AddConstraint(
            model_name="schoolfundsledgerentry",
            constraint=models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="chk_fundsle_amount_positive",
            ),
        ),
        # --- SchoolFundsBalance ---
        migrations.CreateModel(
            name="SchoolFundsBalance",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "collected_total",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=14,
                    ),
                ),
                (
                    "cleared_total",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=14,
                    ),
                ),
                (
                    "available_total",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=14,
                    ),
                ),
                (
                    "reserved_total",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=14,
                    ),
                ),
                (
                    "paid_out_total",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=14,
                    ),
                ),
                (
                    "last_reconciled_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "school",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="funds_balance",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "School Funds Balance",
                "verbose_name_plural": "School Funds Balances",
            },
        ),
        migrations.AddConstraint(
            model_name="schoolfundsbalance",
            constraint=models.CheckConstraint(
                check=models.Q(collected_total__gte=0),
                name="chk_fundsbal_collected_gte0",
            ),
        ),
        migrations.AddConstraint(
            model_name="schoolfundsbalance",
            constraint=models.CheckConstraint(
                check=models.Q(cleared_total__gte=0),
                name="chk_fundsbal_cleared_gte0",
            ),
        ),
        migrations.AddConstraint(
            model_name="schoolfundsbalance",
            constraint=models.CheckConstraint(
                check=models.Q(available_total__gte=0),
                name="chk_fundsbal_available_gte0",
            ),
        ),
        migrations.AddConstraint(
            model_name="schoolfundsbalance",
            constraint=models.CheckConstraint(
                check=models.Q(reserved_total__gte=0),
                name="chk_fundsbal_reserved_gte0",
            ),
        ),
        migrations.AddConstraint(
            model_name="schoolfundsbalance",
            constraint=models.CheckConstraint(
                check=models.Q(paid_out_total__gte=0),
                name="chk_fundsbal_paidout_gte0",
            ),
        ),
    ]
