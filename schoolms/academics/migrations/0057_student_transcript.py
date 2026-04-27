"""
Fix #26: StudentTranscript model — cumulative academic standing per student per year.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0056_alter_academicyear_is_current"),
        ("schools", "0017_schoolnetwork"),
        ("students", "0018_backfill_guardian_school"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudentTranscript",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("total_subjects", models.PositiveSmallIntegerField(default=0)),
                ("subjects_passed", models.PositiveSmallIntegerField(default=0)),
                ("average_score", models.DecimalField(decimal_places=2, default=0, max_digits=6)),
                ("gpa", models.DecimalField(
                    decimal_places=2, default=0, max_digits=4,
                    help_text="Weighted GPA using subject credit_weight.",
                )),
                ("class_rank", models.PositiveSmallIntegerField(
                    blank=True, null=True,
                    help_text="Rank within the student's class for this period.",
                )),
                ("year_rank", models.PositiveSmallIntegerField(
                    blank=True, null=True,
                    help_text="Rank within the school year cohort.",
                )),
                ("remarks", models.TextField(blank=True, help_text="Class/form teacher's overall remarks.")),
                ("is_published", models.BooleanField(default=False)),
                ("generated_at", models.DateTimeField(auto_now=True)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transcripts", to="schools.school")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transcripts", to="students.student")),
                ("academic_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transcripts", to="academics.academicyear")),
                ("term", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="transcripts", to="academics.term",
                    help_text="Null = full-year aggregate; set for per-term transcript.",
                )),
            ],
            options={"verbose_name": "Student Transcript", "verbose_name_plural": "Student Transcripts"},
        ),
        migrations.AddConstraint(
            model_name="studenttranscript",
            constraint=models.UniqueConstraint(
                fields=["student", "academic_year", "term"],
                name="uniq_transcript_student_year_term",
            ),
        ),
        migrations.AddIndex(
            model_name="studenttranscript",
            index=models.Index(fields=["school", "academic_year"], name="idx_transcript_school_year"),
        ),
        migrations.AddIndex(
            model_name="studenttranscript",
            index=models.Index(fields=["school", "is_published"], name="idx_transcript_school_pub"),
        ),
    ]
