"""
Phase 2 (continued): StaffPayoutRequest model for maker-checker payout workflow.
"""
import uuid
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import finance.models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0012_school_payout_setup_fields"),
        ("finance", "0020_school_funds_ledger_and_balance"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffPayoutRequest",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID",
                    ),
                ),
                (
                    "reference",
                    models.CharField(
                        db_index=True, default=finance.models._generate_payout_ref,
                        max_length=64, unique=True,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="GHS", max_length=8)),
                (
                    "period_label",
                    models.CharField(help_text="e.g. January 2026, Week 3", max_length=64),
                ),
                (
                    "route",
                    models.CharField(
                        choices=[("momo", "Mobile Money"), ("bank", "Bank Transfer")],
                        max_length=8,
                    ),
                ),
                ("reason", models.CharField(blank=True, default="", max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending_approval", "Pending Approval"),
                            ("approved", "Approved"),
                            ("funds_reserved", "Funds Reserved"),
                            ("executing", "Executing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                            ("rejected", "Rejected"),
                        ],
                        db_index=True, default="pending_approval", max_length=20,
                    ),
                ),
                ("funds_reserved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "ledger_reference",
                    models.CharField(
                        blank=True, default="",
                        help_text="Reference used in SchoolFundsLedgerEntry for the reservation.",
                        max_length=255,
                    ),
                ),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("rejected_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("rejection_reason", models.CharField(blank=True, default="", max_length=500)),
                ("cancellation_reason", models.CharField(blank=True, default="", max_length=500)),
                ("failure_reason", models.TextField(blank=True, default="")),
                ("recipient_snapshot", models.CharField(blank=True, default="", max_length=200)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_payout_requests",
                        to="schools.school",
                    ),
                ),
                (
                    "staff_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payout_requests_received",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payout_requests_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payout_requests_approved",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "rejected_by",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payout_requests_rejected",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "cancelled_by",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payout_requests_cancelled",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Staff Payout Request",
                "verbose_name_plural": "Staff Payout Requests",
                "ordering": ["-requested_at"],
            },
        ),
        migrations.AddIndex(
            model_name="staffpayoutrequest",
            index=models.Index(
                fields=["school", "status", "requested_at"],
                name="idx_payoutreq_school_status_ts",
            ),
        ),
        migrations.AddIndex(
            model_name="staffpayoutrequest",
            index=models.Index(
                fields=["school", "staff_user", "period_label"],
                name="idx_payoutreq_school_staff_per",
            ),
        ),
        migrations.AddConstraint(
            model_name="staffpayoutrequest",
            constraint=models.CheckConstraint(
                check=~models.Q(approved_by=models.F("requested_by"))
                | models.Q(approved_by__isnull=True),
                name="chk_payoutreq_maker_checker",
            ),
        ),
        migrations.AddConstraint(
            model_name="staffpayoutrequest",
            constraint=models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="chk_payoutreq_amount_positive",
            ),
        ),
    ]
