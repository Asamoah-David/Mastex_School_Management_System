"""
Fix 18: Add base_salary and salary_currency to StaffContract.
Fix 27: Add school_class FK to StaffTeachingAssignment.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0016_erp_enhancements_batch1"),
        ("students", "0015_unique_student_admission_number_per_school"),
    ]

    operations = [
        # Fix 18: salary fields on StaffContract
        migrations.AddField(
            model_name="staffcontract",
            name="base_salary",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Agreed gross salary per payment period (e.g. monthly).",
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="staffcontract",
            name="salary_currency",
            field=models.CharField(default="GHS", max_length=8),
        ),
        # Fix 27: school_class FK on StaffTeachingAssignment
        migrations.AddField(
            model_name="staffteachingassignment",
            name="school_class",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="staff_teaching_assignments",
                to="students.schoolclass",
                help_text="Structured class FK (takes precedence over class_name for filtering).",
            ),
        ),
    ]
