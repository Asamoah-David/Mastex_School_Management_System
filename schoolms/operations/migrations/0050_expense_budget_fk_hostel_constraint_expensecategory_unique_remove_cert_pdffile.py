"""
Fix 12: Remove Certificate.pdf_file BinaryField.
Fix 15: Add Expense.budget FK to Budget.
Fix 21: Add UniqueConstraint (one active hostel assignment per student).
Fix 25: Add UniqueConstraint to ExpenseCategory (school + name).
Budget.Meta CheckConstraint for non-negative allocated_amount.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0049_busroute_weekly_frequency"),
    ]

    operations = [
        # Fix 12: remove Certificate.pdf_file (BinaryField)
        migrations.RemoveField(
            model_name="certificate",
            name="pdf_file",
        ),
        # Fix 15: Expense.budget FK
        migrations.AddField(
            model_name="expense",
            name="budget",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="expenses",
                to="operations.budget",
                help_text="Budget this expense is charged against. Budget.spent_amount auto-updates.",
            ),
        ),
        # Fix 21: unique active hostel assignment per student
        migrations.AddConstraint(
            model_name="hostelassignment",
            constraint=models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(is_active=True),
                name="uniq_hostelasn_one_active_per_student",
            ),
        ),
        # Fix 25: unique ExpenseCategory name per school
        migrations.AddConstraint(
            model_name="expensecategory",
            constraint=models.UniqueConstraint(
                fields=["school", "name"],
                name="uniq_expensecategory_school_name",
            ),
        ),
        # Budget: non-negative allocated_amount
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.CheckConstraint(
                check=models.Q(allocated_amount__gte=0),
                name="chk_budget_allocated_nonneg",
            ),
        ),
    ]
