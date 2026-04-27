"""
Production fixes batch:
 - Add AcademicYear model (replaces raw academic_year CharField everywhere)
 - Link Term to AcademicYear FK
 - Add Subject.is_core + credit_weight for GPA computation
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0054_result_school_fk_score_constraints"),
        ("schools", "0015_school_timezone_email_branding"),
    ]

    operations = [
        # 1. Create AcademicYear
        migrations.CreateModel(
            name="AcademicYear",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Human-readable label, e.g. '2025/2026'.", max_length=20)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("is_current", models.BooleanField(default=False, help_text="Only one year per school should be current.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="academic_years",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Academic Year",
                "verbose_name_plural": "Academic Years",
                "ordering": ["-start_date"],
            },
        ),
        migrations.AddConstraint(
            model_name="academicyear",
            constraint=models.UniqueConstraint(
                fields=["school", "name"],
                name="uniq_academicyear_school_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="academicyear",
            constraint=models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(is_current=True),
                name="uniq_academicyear_current_per_school",
            ),
        ),
        # 2. Add academic_year FK to Term (nullable so existing Terms keep working)
        migrations.AddField(
            model_name="term",
            name="academic_year",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="terms",
                to="academics.academicyear",
                help_text="Structured academic year this term belongs to.",
            ),
        ),
        # 3. Add is_core and credit_weight to Subject
        migrations.AddField(
            model_name="subject",
            name="is_core",
            field=models.BooleanField(
                default=True,
                help_text="Core subjects are compulsory. Electives are optional. Affects GPA computation.",
            ),
        ),
        migrations.AddField(
            model_name="subject",
            name="credit_weight",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="Credit unit weight for GPA calculation (e.g. 1=normal, 2=double-credit).",
            ),
        ),
    ]
