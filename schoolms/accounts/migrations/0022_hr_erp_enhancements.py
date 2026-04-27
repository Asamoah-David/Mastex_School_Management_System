"""
Fix #11: HR models adopt SchoolScopedModel (no DB change — schema unchanged).
Fix #24: LeavePolicy + LeaveBalance models.
Fix #25: PayrollRun model + payroll_run FK on StaffPayrollPayment.
"""

import decimal
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0021_staffpayroll_deductions_fields"),
        ("schools", "0016_school_ai_monthly_token_cap"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # --- PayrollRun --------------------------------------------------
        migrations.CreateModel(
            name="PayrollRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period_label", models.CharField(help_text="e.g. 'January 2026'", max_length=64)),
                ("pay_date", models.DateField()),
                ("status", models.CharField(
                    choices=[("draft","Draft"),("processing","Processing"),("completed","Completed"),("failed","Failed")],
                    db_index=True, default="draft", max_length=20,
                )),
                ("total_gross", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("total_net", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("total_paye", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("total_ssnit", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("staff_count", models.PositiveIntegerField(default=0)),
                ("notes", models.TextField(blank=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payroll_runs", to="schools.school")),
                ("created_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="payroll_runs_created", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"verbose_name": "Payroll Run", "verbose_name_plural": "Payroll Runs", "ordering": ["-pay_date", "-id"]},
        ),
        migrations.AddIndex(
            model_name="payrollrun",
            index=models.Index(fields=["school", "status"], name="idx_payrollrun_school_status"),
        ),

        # --- payroll_run FK on StaffPayrollPayment ----------------------
        migrations.AddField(
            model_name="staffpayrollpayment",
            name="payroll_run",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="payments", to="accounts.payrollrun",
                help_text="The payroll run batch this payment belongs to.",
            ),
        ),

        # --- LeavePolicy ------------------------------------------------
        migrations.CreateModel(
            name="LeavePolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("leave_type", models.CharField(
                    choices=[
                        ("annual","Annual / Vacation"),("sick","Sick Leave"),("maternity","Maternity Leave"),
                        ("paternity","Paternity Leave"),("compassionate","Compassionate Leave"),
                        ("study","Study / Exam Leave"),("unpaid","Unpaid Leave"),
                    ],
                    max_length=30,
                )),
                ("days_per_year", models.PositiveSmallIntegerField(default=21)),
                ("carry_over_max_days", models.PositiveSmallIntegerField(default=0, help_text="Max days that can roll to next year; 0 = no carry-over.")),
                ("is_active", models.BooleanField(default=True)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="leave_policies", to="schools.school")),
            ],
            options={"verbose_name": "Leave Policy", "verbose_name_plural": "Leave Policies"},
        ),
        migrations.AddConstraint(
            model_name="leavepolicy",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_active=True),
                fields=["school", "leave_type"],
                name="uniq_leavepolicy_school_type_active",
            ),
        ),

        # --- LeaveBalance -----------------------------------------------
        migrations.CreateModel(
            name="LeaveBalance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("leave_type", models.CharField(
                    choices=[
                        ("annual","Annual / Vacation"),("sick","Sick Leave"),("maternity","Maternity Leave"),
                        ("paternity","Paternity Leave"),("compassionate","Compassionate Leave"),
                        ("study","Study / Exam Leave"),("unpaid","Unpaid Leave"),
                    ],
                    max_length=30,
                )),
                ("academic_year", models.CharField(help_text="e.g. 2025/2026", max_length=9)),
                ("allocated_days", models.DecimalField(decimal_places=1, default=0, max_digits=5, help_text="Total days allocated for this year.")),
                ("used_days", models.DecimalField(decimal_places=1, default=0, max_digits=5, help_text="Days consumed by approved leave requests.")),
                ("carried_over", models.DecimalField(decimal_places=1, default=0, max_digits=5, help_text="Days carried over from previous year.")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="leave_balances", to="schools.school")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="leave_balances", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Leave Balance", "verbose_name_plural": "Leave Balances"},
        ),
        migrations.AddConstraint(
            model_name="leavebalance",
            constraint=models.UniqueConstraint(
                fields=["school", "user", "leave_type", "academic_year"],
                name="uniq_leavebalance_user_type_year",
            ),
        ),
        migrations.AddIndex(
            model_name="leavebalance",
            index=models.Index(fields=["school", "user"], name="idx_leavebal_school_user"),
        ),
    ]
